import path from "node:path";
import fs from "node:fs/promises";
import type { EventRecord, ForumMessage, Issue, JsonRecord } from "./types";
import { parseJsonl } from "./jsonl";

const STORE_DIRNAME = ".inshallah";
const EVENTS_FILENAME = "events.jsonl";
const ENV_STORE_ROOT = "INSHALLAH_STORE_ROOT";

async function existsDir(p: string): Promise<boolean> {
  try {
    const st = await fs.stat(p);
    return st.isDirectory();
  } catch {
    return false;
  }
}

async function findAncestorWithStoreDir(startDir: string): Promise<string | null> {
  let dir = path.resolve(startDir);
  // Avoid infinite loops at filesystem root.
  for (;;) {
    if (await existsDir(path.join(dir, STORE_DIRNAME))) return dir;
    const parent = path.dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
}

export async function discoverStoreRoot(opts?: {
  cwd?: string;
  env?: Record<string, string | undefined>;
}): Promise<string> {
  const cwd = opts?.cwd ?? process.cwd();
  const env = opts?.env ?? (process.env as Record<string, string | undefined>);

  const override = env[ENV_STORE_ROOT]?.trim();
  if (override) {
    const root = path.resolve(override);
    const storeDir = path.join(root, STORE_DIRNAME);
    if (!(await existsDir(storeDir))) {
      throw new Error(`${ENV_STORE_ROOT}=${root} but ${storeDir} does not exist`);
    }
    return root;
  }

  const found = await findAncestorWithStoreDir(cwd);
  if (!found) {
    throw new Error(`could not discover store root from cwd=${cwd} (no ancestor contains ${STORE_DIRNAME}/)`);
  }
  return found;
}

function expectRecord(value: unknown, ctx: string): JsonRecord {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`expected object for ${ctx}`);
  }
  return value as JsonRecord;
}

function expectString(value: unknown, ctx: string): string {
  if (typeof value !== "string") throw new Error(`expected string for ${ctx}`);
  return value;
}

function asIssue(value: unknown): Issue {
  const obj = expectRecord(value, "issue");
  const id = expectString(obj.id, "issue.id");
  const title = typeof obj.title === "string" ? obj.title : "";
  return { ...obj, id, title } as Issue;
}

function asForumMessage(value: unknown): ForumMessage {
  const obj = expectRecord(value, "forum message");
  const topic = expectString(obj.topic, "forum.topic");
  const body = typeof obj.body === "string" ? obj.body : "";
  return { ...obj, topic, body } as ForumMessage;
}

function epochMsFromMessage(m: ForumMessage): number {
  if (typeof m.created_at_ms === "number" && Number.isFinite(m.created_at_ms)) return m.created_at_ms;
  if (typeof m.created_at === "number" && Number.isFinite(m.created_at)) return m.created_at * 1000;
  return 0;
}

class JsonlCache<T> {
  private cached: T[] | null = null;
  private mtimeMs: number | null = null;
  private size: number | null = null;

  constructor(
    private readonly filePath: string,
    private readonly coerce: (value: unknown) => T,
  ) {}

  async load(): Promise<T[]> {
    const st = await fs.stat(this.filePath);
    if (this.cached && this.mtimeMs === st.mtimeMs && this.size === st.size) return this.cached;

    const text = await Bun.file(this.filePath).text();
    const raw = parseJsonl(text, this.filePath);
    const out = raw.map(this.coerce);

    this.cached = out;
    this.mtimeMs = st.mtimeMs;
    this.size = st.size;
    return out;
  }
}

function asEventRecord(
  value: unknown,
  meta: { sourceFile: string; line: number; rawLine?: string; parse_error?: string },
): EventRecord {
  const errors: string[] = [];

  // Defaults for invalid/partial entries.
  let v = 0;
  let ts_ms = 0;
  let type = "parse_error";
  let source = meta.sourceFile;
  let payload: unknown = meta.rawLine ?? value;
  let issue_id: string | undefined;
  let run_id: string | undefined;

  if (value && typeof value === "object" && !Array.isArray(value)) {
    const obj = value as JsonRecord;

    if (typeof obj.v === "number" && Number.isFinite(obj.v)) v = obj.v;
    else errors.push("v");

    if (typeof obj.ts_ms === "number" && Number.isFinite(obj.ts_ms)) ts_ms = obj.ts_ms;
    else errors.push("ts_ms");

    if (typeof obj.type === "string") type = obj.type;
    else errors.push("type");

    if (typeof obj.source === "string") source = obj.source;
    else errors.push("source");

    if ("payload" in obj) payload = obj.payload;
    else errors.push("payload");

    if (typeof obj.issue_id === "string") issue_id = obj.issue_id;
    if (typeof obj.run_id === "string") run_id = obj.run_id;
  } else {
    errors.push("object");
  }

  const parse_error =
    meta.parse_error ?? (errors.length ? `invalid event envelope (missing/invalid: ${errors.join(",")})` : undefined);

  const ev: EventRecord = {
    v,
    ts_ms,
    type,
    source,
    payload,
    line: meta.line,
  };
  if (issue_id !== undefined) ev.issue_id = issue_id;
  if (run_id !== undefined) ev.run_id = run_id;
  if (parse_error) ev.parse_error = parse_error;
  return ev;
}

function parseEventLog(text: string, meta: { sourceFile: string }): EventRecord[] {
  const out: EventRecord[] = [];
  const lines = text.split(/\r?\n/);

  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    const line = raw.trim();
    if (!line) continue;

    const lineNo = i + 1;

    try {
      const parsed = JSON.parse(line) as unknown;
      out.push(
        asEventRecord(parsed, {
          ...meta,
          line: lineNo,
        }),
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      out.push(
        asEventRecord(line, {
          ...meta,
          line: lineNo,
          rawLine: line,
          parse_error: msg,
        }),
      );
    }
  }

  return out;
}

class EventLogCache {
  private cached: EventRecord[] | null = null;
  private mtimeMs: number | null = null;
  private size: number | null = null;

  constructor(private readonly filePath: string) {}

  async load(): Promise<EventRecord[]> {
    try {
      const st = await fs.stat(this.filePath);
      if (this.cached && this.mtimeMs === st.mtimeMs && this.size === st.size) return this.cached;

      const text = await Bun.file(this.filePath).text();
      const out = parseEventLog(text, { sourceFile: path.basename(this.filePath) });

      this.cached = out;
      this.mtimeMs = st.mtimeMs;
      this.size = st.size;
      return out;
    } catch (err) {
      // Missing events log is a valid state for a freshly initialized store.
      if (err && typeof err === "object" && "code" in err && (err as { code?: unknown }).code === "ENOENT") return [];
      throw err;
    }
  }
}

export class Store {
  readonly issuesPath: string;
  readonly forumPath: string;
  readonly eventsPath: string;

  private readonly issuesCache: JsonlCache<Issue>;
  private readonly forumCache: JsonlCache<ForumMessage>;
  private readonly eventsCache: EventLogCache;

  constructor(readonly root: string) {
    this.issuesPath = path.join(root, STORE_DIRNAME, "issues.jsonl");
    this.forumPath = path.join(root, STORE_DIRNAME, "forum.jsonl");
    this.eventsPath = path.join(root, STORE_DIRNAME, EVENTS_FILENAME);
    this.issuesCache = new JsonlCache(this.issuesPath, asIssue);
    this.forumCache = new JsonlCache(this.forumPath, asForumMessage);
    this.eventsCache = new EventLogCache(this.eventsPath);
  }

  async listIssues(): Promise<Issue[]> {
    const issues = await this.issuesCache.load();
    // Sort newest-first for a stable "monitor" feel.
    return [...issues].sort((a, b) => (b.updated_at ?? b.created_at ?? 0) - (a.updated_at ?? a.created_at ?? 0));
  }

  async getIssue(id: string): Promise<Issue | null> {
    const issues = await this.issuesCache.load();
    return issues.find((i) => i.id === id) ?? null;
  }

  async getIssueChildren(parentId: string): Promise<Issue[]> {
    const issues = await this.issuesCache.load();
    const children = issues.filter((i) => {
      const deps = i.deps;
      if (!Array.isArray(deps)) return false;
      return deps.some((d) => {
        if (!d || typeof d !== "object") return false;
        const dep = d as { type?: unknown; target?: unknown };
        return dep.type === "parent" && dep.target === parentId;
      });
    });
    return children.sort((a, b) => (b.updated_at ?? b.created_at ?? 0) - (a.updated_at ?? a.created_at ?? 0));
  }

  async listForumTopics(params?: { prefix?: string; limit?: number }): Promise<string[]> {
    const prefix = params?.prefix;
    const limit = params?.limit ?? 500;
    const messages = await this.forumCache.load();

    const newestByTopic = new Map<string, number>();
    for (const m of messages) {
      const topic = m.topic;
      if (prefix && !topic.startsWith(prefix)) continue;
      const ts = epochMsFromMessage(m);
      const prev = newestByTopic.get(topic);
      if (prev === undefined || ts > prev) newestByTopic.set(topic, ts);
    }

    const topics = [...newestByTopic.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([topic]) => topic);

    return topics.slice(0, limit);
  }

  async listForumMessages(params: { topic: string; limit?: number }): Promise<ForumMessage[]> {
    const limit = params.limit ?? 200;
    const messages = await this.forumCache.load();
    const topicMsgs = messages.filter((m) => m.topic === params.topic);
    topicMsgs.sort((a, b) => epochMsFromMessage(b) - epochMsFromMessage(a));
    return topicMsgs.slice(0, limit);
  }

  async queryEvents(params?: {
    issue_id?: string;
    run_id?: string;
    type?: string;
    limit?: number;
  }): Promise<EventRecord[]> {
    const issue_id = params?.issue_id;
    const run_id = params?.run_id;
    const type = params?.type;
    const limit = params?.limit ?? 200;

    let events = await this.eventsCache.load();
    if (issue_id) events = events.filter((e) => e.issue_id === issue_id);
    if (run_id) events = events.filter((e) => e.run_id === run_id);
    if (type) events = events.filter((e) => e.type === type);

    // Default to a "tail" view while keeping chronological ordering.
    if (events.length > limit) events = events.slice(events.length - limit);
    return events;
  }
}
