import { describe, expect, test } from "bun:test";
import path from "node:path";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { handleRequest } from "../src/router";
import { Store } from "../src/store";

async function makeStoreRootWithEvents(): Promise<string> {
  const root = await mkdtemp(path.join(tmpdir(), "inshallah-monitor-events-"));
  await mkdir(path.join(root, ".inshallah"), { recursive: true });
  await writeFile(path.join(root, ".inshallah/issues.jsonl"), "");
  await writeFile(path.join(root, ".inshallah/forum.jsonl"), "");
  await writeFile(path.join(root, ".inshallah/events.jsonl"), "");
  return root;
}

async function writeEvents(root: string, events: Array<Record<string, unknown>>): Promise<void> {
  await writeFile(path.join(root, ".inshallah", "events.jsonl"), events.map((e) => JSON.stringify(e)).join("\n") + "\n");
}

describe("event logs", () => {
  test("parses .inshallah/events.jsonl and handles optional issue_id/run_id", async () => {
    const root = await makeStoreRootWithEvents();

    await writeEvents(root, [
      { v: 1, ts_ms: 1, type: "issue.create", source: "issue_store", issue_id: "inshallah-aaa11111", payload: { ok: true } },
      { v: 1, ts_ms: 2, type: "dag.run.start", source: "dag", run_id: "run-a-1", payload: {} },
      {
        v: 1,
        ts_ms: 3,
        type: "backend.run.start",
        source: "dag",
        run_id: "run-a-1",
        issue_id: "inshallah-aaa11111",
        payload: { cmd: "echo hi" },
      },
      { v: 1, ts_ms: 4, type: "forum.post", source: "forum_store", issue_id: "inshallah-aaa11111", payload: { body: "hello" } },
      { v: 1, ts_ms: 5, type: "system.tick", source: "timer", payload: { n: 1 } },
    ]);

    const store = new Store(root);
    const events = await store.queryEvents({ limit: 1000 });
    expect(events.map((e) => e.type)).toEqual([
      "issue.create",
      "dag.run.start",
      "backend.run.start",
      "forum.post",
      "system.tick",
    ]);

    const issueCreate = events.find((e) => e.type === "issue.create");
    expect(issueCreate).toBeTruthy();
    expect(issueCreate!.issue_id).toBe("inshallah-aaa11111");
    expect(issueCreate!.run_id).toBeUndefined();

    const dagStart = events.find((e) => e.type === "dag.run.start");
    expect(dagStart).toBeTruthy();
    expect(dagStart!.run_id).toBe("run-a-1");
    expect(dagStart!.issue_id).toBeUndefined();
  });

  test("supports filtering by issue_id, run_id, type, and limit (tail)", async () => {
    const root = await makeStoreRootWithEvents();

    await writeEvents(root, [
      { v: 1, ts_ms: 1, type: "issue.create", source: "issue_store", issue_id: "inshallah-aaa11111", payload: {} },
      { v: 1, ts_ms: 2, type: "dag.run.start", source: "dag", run_id: "run-a-1", payload: {} },
      { v: 1, ts_ms: 3, type: "forum.post", source: "forum_store", issue_id: "inshallah-aaa11111", payload: { body: "a" } },
      { v: 1, ts_ms: 4, type: "forum.post", source: "forum_store", issue_id: "inshallah-aaa11111", run_id: "run-a-1", payload: { body: "b" } },
      { v: 1, ts_ms: 5, type: "forum.post", source: "forum_store", issue_id: "inshallah-bbb22222", payload: { body: "c" } },
    ]);

    const store = new Store(root);

    const byIssue = await store.queryEvents({ issue_id: "inshallah-aaa11111", limit: 1000 });
    expect(byIssue.map((e) => e.type)).toEqual(["issue.create", "forum.post", "forum.post"]);

    const byRun = await store.queryEvents({ run_id: "run-a-1", limit: 1000 });
    expect(byRun.map((e) => e.type)).toEqual(["dag.run.start", "forum.post"]);

    const byType = await store.queryEvents({ type: "forum.post", limit: 1000 });
    expect(byType.map((e) => e.issue_id ?? "")).toEqual(["inshallah-aaa11111", "inshallah-aaa11111", "inshallah-bbb22222"]);

    const tail = await store.queryEvents({ issue_id: "inshallah-aaa11111", limit: 2 });
    expect(tail.map((e) => e.payload)).toEqual([{ body: "a" }, { body: "b" }]);
  });

  test("exposes /api/events with filters", async () => {
    const root = await makeStoreRootWithEvents();

    await writeEvents(root, [
      { v: 1, ts_ms: 1, type: "issue.create", source: "issue_store", issue_id: "inshallah-aaa11111", payload: {} },
      { v: 1, ts_ms: 2, type: "forum.post", source: "forum_store", issue_id: "inshallah-aaa11111", payload: { body: "hello" } },
      { v: 1, ts_ms: 3, type: "forum.post", source: "forum_store", issue_id: "inshallah-bbb22222", payload: { body: "bye" } },
    ]);

    const store = new Store(root);
    const res = await handleRequest(new Request("http://example.test/api/events?issue_id=inshallah-aaa11111&type=forum.post&limit=10"), {
      storeRoot: root,
      store,
    });
    expect(res.status).toBe(200);
    const body = (await res.json()) as Array<{ type: string; issue_id?: string; payload: unknown }>;
    expect(body.map((e) => e.type)).toEqual(["forum.post"]);
    expect(body.map((e) => e.issue_id ?? "")).toEqual(["inshallah-aaa11111"]);
    expect(body[0]!.payload).toEqual({ body: "hello" });
  });

  test("exposes /api/events with run_id filtering", async () => {
    const root = await makeStoreRootWithEvents();

    await writeEvents(root, [
      { v: 1, ts_ms: 1, type: "dag.run.start", source: "dag", run_id: "run-a-1", payload: {} },
      { v: 1, ts_ms: 2, type: "forum.post", source: "forum_store", issue_id: "inshallah-aaa11111", run_id: "run-a-1", payload: { body: "hello" } },
      { v: 1, ts_ms: 3, type: "dag.run.start", source: "dag", run_id: "run-b-1", payload: {} },
    ]);

    const store = new Store(root);
    const res = await handleRequest(new Request("http://example.test/api/events?run_id=run-a-1&limit=10"), {
      storeRoot: root,
      store,
    });
    expect(res.status).toBe(200);
    const body = (await res.json()) as Array<{ type: string; run_id?: string }>;
    expect(body.map((e) => e.type)).toEqual(["dag.run.start", "forum.post"]);
    expect(body.map((e) => e.run_id ?? "")).toEqual(["run-a-1", "run-a-1"]);
  });

  test("renders /events HTML with structured fields", async () => {
    const root = await makeStoreRootWithEvents();

    await writeEvents(root, [
      { v: 1, ts_ms: 1, type: "issue.create", source: "issue_store", issue_id: "inshallah-aaa11111", payload: {} },
      { v: 1, ts_ms: 4, type: "forum.post", source: "forum_store", issue_id: "inshallah-aaa11111", payload: { body: "hello" } },
      { v: 1, ts_ms: 5, type: "forum.post", source: "forum_store", issue_id: "inshallah-bbb22222", payload: { body: "bye" } },
    ]);

    const store = new Store(root);
    const res = await handleRequest(new Request("http://example.test/events?issue_id=inshallah-aaa11111&type=forum.post&limit=10"), {
      storeRoot: root,
      store,
    });
    expect(res.status).toBe(200);
    const html = await res.text();

    // Filtered to a single matching event.
    expect(html).toContain("| events=1 |");
    expect(html).toContain('name="issue_id" value="inshallah-aaa11111"');
    expect(html).toContain('name="type" value="forum.post"');

    // Structured columns.
    expect(html).toContain("<th>ts</th>");
    expect(html).toContain("<th>type</th>");
    expect(html).toContain("<th>source</th>");
    expect(html).toContain("<th>payload</th>");

    // Human-readable timestamp from ts_ms.
    expect(html).toContain("1970-01-01 00:00:00.004Z");

    // Pretty JSON payload (indented).
    expect(html).toContain("forum_store");
    expect(html).toContain("forum.post");
    expect(html).toContain('\n  &quot;body&quot;: &quot;hello&quot;\n');
  });
});
