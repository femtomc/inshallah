/**
 * loopfarm web - SSE, keyboard navigation, and API interactions.
 */

(function () {
  'use strict';

  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------

  let focusedId = null;
  let allNodeIds = [];
  let focusIndex = -1;
  let cmdPaletteOpen = false;
  let initialBreadcrumbTrail = '';

  const SAVE_STATE_CLASSES = ['is-saving', 'is-saved', 'is-error'];

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  function api(method, path, body) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);

    return fetch(path, opts)
      .then(function (r) {
        return r.text().then(function (raw) {
          let data = {};
          if (raw) {
            try {
              data = JSON.parse(raw);
            } catch (err) {
              data = { error: raw };
            }
          }
          if (!r.ok) {
            return { error: data.error || r.statusText || 'request failed', status: r.status };
          }
          return data;
        });
      })
      .catch(function (err) {
        return { error: String(err) };
      });
  }

  function $(sel) { return document.querySelector(sel); }
  function $$(sel) { return Array.from(document.querySelectorAll(sel)); }

  function collectNodeIds() {
    allNodeIds = $$('.tree-node').map(function (el) { return el.dataset.id; });
  }

  function ago(ts) {
    if (!ts) return '';
    var d = Math.floor(Date.now() / 1000) - ts;
    if (d < 60) return 'just now';
    if (d < 3600) return Math.floor(d / 60) + 'm ago';
    if (d < 86400) return Math.floor(d / 3600) + 'h ago';
    return Math.floor(d / 86400) + 'd ago';
  }

  function escapeHtml(s) {
    var div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
  }

  function toast(message, type) {
    var stack = $('#lf-toast-stack');
    if (!stack) {
      stack = document.createElement('div');
      stack.id = 'lf-toast-stack';
      stack.className = 'lf-toast-stack';
      document.body.appendChild(stack);
    }

    var el = document.createElement('div');
    el.className = 'lf-toast is-' + (type || 'info');
    el.textContent = message;
    stack.appendChild(el);

    setTimeout(function () {
      if (el && el.parentElement) el.parentElement.removeChild(el);
    }, 2800);
  }

  function setSaveState(mode, text) {
    var el = $('#detail-save-state');
    if (!el) return;

    SAVE_STATE_CLASSES.forEach(function (cls) { el.classList.remove(cls); });

    if (mode === 'saving') {
      el.classList.add('is-saving');
      el.textContent = text || 'saving';
    } else if (mode === 'error') {
      el.classList.add('is-error');
      el.textContent = text || 'save failed';
    } else {
      el.classList.add('is-saved');
      el.textContent = text || 'saved';
    }
  }

  function setButtonPending(btn, pending, pendingLabel) {
    if (!btn) return;
    if (pending) {
      if (!btn.dataset.labelOriginal) btn.dataset.labelOriginal = btn.textContent;
      btn.disabled = true;
      btn.textContent = pendingLabel || 'working...';
      return;
    }
    btn.disabled = false;
    if (btn.dataset.labelOriginal) {
      btn.textContent = btn.dataset.labelOriginal;
      delete btn.dataset.labelOriginal;
    }
  }

  function findParentDep(deps) {
    var arr = Array.isArray(deps) ? deps : [];
    var dep = arr.find(function (d) { return d.type === 'parent'; });
    return dep ? dep.target : null;
  }

  function updateBreadcrumbTrail(id) {
    var trailEl = $('#breadcrumb-trail');
    if (!trailEl) return;

    if (!id) {
      trailEl.textContent = initialBreadcrumbTrail;
      return;
    }

    var currentId = id;
    var labels = [];
    var guard = 0;
    while (currentId && guard < 100) {
      guard += 1;
      var node = document.querySelector('.tree-node[data-id="' + currentId + '"]');
      if (!node) break;
      var titleEl = node.querySelector('.tree-title');
      labels.unshift(titleEl ? titleEl.textContent : currentId.slice(0, 8));
      currentId = node.dataset.parent || '';
    }

    trailEl.textContent = labels.length ? labels.join(' / ') : initialBreadcrumbTrail;
  }

  // ---------------------------------------------------------------------------
  // SSE
  // ---------------------------------------------------------------------------

  function initSSE() {
    var indicator = $('#sse-indicator');
    var statusEl = $('#sse-status');

    var syncStatusStats = function () {
      api('GET', '/api/status').then(function (data) {
        if (!data || data.error) return;
        var s = function (id, v) {
          var el = document.getElementById(id);
          if (el) el.textContent = v;
        };
        s('stat-roots', data.roots);
        s('stat-open', data.open);
        s('stat-ready', data.ready);
        s('stat-failed', data.failed);
      });
    };

    syncStatusStats();
    if (!indicator || !statusEl) return;

    var rootFilter = window.__rootId ? '?root=' + window.__rootId : '';
    var es = new EventSource('/api/events' + rootFilter);

    es.onopen = function () {
      indicator.className = 'status-indicator';
      statusEl.textContent = 'connected';
    };

    es.onerror = function () {
      indicator.className = 'status-indicator disconnected';
      statusEl.textContent = 'disconnected';
    };

    es.addEventListener('heartbeat', syncStatusStats);

    es.addEventListener('issue_created', function () {
      collectNodeIds();
      syncStatusStats();
    });

    es.addEventListener('issue_updated', function (e) {
      var data = JSON.parse(e.data || '{}');
      updateTreeNode(data);
      syncStatusStats();
      if (focusedId === data.id) loadDetail(data.id);
    });

    es.addEventListener('runner_step', function (e) {
      var data = JSON.parse(e.data || '{}');
      var el = $('#runner-status');
      if (el) el.textContent = data.status + ' step ' + data.step;
    });

    es.addEventListener('runner_done', function (e) {
      var data = JSON.parse(e.data || '{}');
      var el = $('#runner-status');
      if (el) el.textContent = 'done: ' + data.status;
      syncStatusStats();
    });
  }

  function updateTreeNode(data) {
    if (!data || !data.id) return;
    var node = document.querySelector('.tree-node[data-id="' + data.id + '"]');
    if (!node) return;

    node.dataset.status = data.status;
    node.dataset.outcome = data.outcome || '';

    var statusEl = node.querySelector('.tree-status');
    if (!statusEl) return;

    if (data.status === 'closed') {
      if (data.outcome === 'failure') {
        statusEl.className = 'tree-status tree-status-failure';
        statusEl.innerHTML = '&#x2715;';
      } else if (data.outcome === 'expanded') {
        statusEl.className = 'tree-status tree-status-expanded';
        statusEl.innerHTML = '&#x25CB;';
      } else if (data.outcome === 'skipped') {
        statusEl.className = 'tree-status tree-status-skipped';
        statusEl.innerHTML = '&#x2013;';
      } else {
        statusEl.className = 'tree-status tree-status-success';
        statusEl.innerHTML = '&#x2713;';
      }
      return;
    }

    if (data.status === 'in_progress') {
      statusEl.className = 'tree-status tree-status-active';
      statusEl.innerHTML = '&#x25CF;';
      return;
    }

    statusEl.className = 'tree-status tree-status-open';
    statusEl.innerHTML = '&#x25CB;';
  }

  // ---------------------------------------------------------------------------
  // Tree Navigation & Focus
  // ---------------------------------------------------------------------------

  function clearFocusStyling() {
    $$('.tree-node.focused').forEach(function (el) { el.classList.remove('focused'); });
    $$('.tree-node.focus-ancestor').forEach(function (el) { el.classList.remove('focus-ancestor'); });
    var container = $('#tree-container');
    if (container) container.classList.remove('has-focus');
  }

  function markAncestorChain(node) {
    if (!node) return;
    var parentId = node.dataset.parent || '';
    var guard = 0;
    while (parentId && guard < 100) {
      guard += 1;
      var parentNode = document.querySelector('.tree-node[data-id="' + parentId + '"]');
      if (!parentNode) break;
      parentNode.classList.add('focus-ancestor');
      parentId = parentNode.dataset.parent || '';
    }
  }

  function focusNode(id) {
    clearFocusStyling();

    if (!id) {
      focusedId = null;
      focusIndex = -1;
      closePanel();
      updateBreadcrumbTrail(null);
      return;
    }

    var node = document.querySelector('.tree-node[data-id="' + id + '"]');
    if (!node) return;

    node.classList.add('focused');
    markAncestorChain(node);

    var container = $('#tree-container');
    if (container) container.classList.add('has-focus');

    focusedId = id;
    focusIndex = allNodeIds.indexOf(id);
    updateBreadcrumbTrail(id);

    node.scrollIntoView({ block: 'nearest' });
  }

  function moveFocus(delta) {
    collectNodeIds();
    var visible = allNodeIds.filter(function (id) {
      var el = document.querySelector('.tree-node[data-id="' + id + '"]');
      return el && el.offsetParent !== null;
    });
    if (!visible.length) return;

    var currentIdx = visible.indexOf(focusedId);
    var next = currentIdx + delta;
    if (next < 0) next = 0;
    if (next >= visible.length) next = visible.length - 1;

    focusNode(visible[next]);
  }

  // ---------------------------------------------------------------------------
  // Detail Panel
  // ---------------------------------------------------------------------------

  function openPanel() {
    var pane = $('#detail-pane');
    if (pane) pane.classList.add('open');
  }

  function closePanel() {
    var pane = $('#detail-pane');
    if (pane) pane.classList.remove('open');
  }

  window.closePanel = closePanel;

  function fillDetailMeta(issue) {
    var meta = $('#detail-meta');
    if (!meta) return;

    meta.innerHTML = '';
    var fields = [
      ['status', issue.status],
      ['outcome', issue.outcome || '-'],
      ['priority', 'P' + issue.priority],
      ['id', issue.id],
      ['created', ago(issue.created_at)],
      ['updated', ago(issue.updated_at)]
    ];

    if (issue.execution_spec) {
      if (issue.execution_spec.role) fields.push(['role', issue.execution_spec.role]);
      if (issue.execution_spec.cli) fields.push(['cli', issue.execution_spec.cli]);
      if (issue.execution_spec.model) fields.push(['model', issue.execution_spec.model]);
    }

    fields.forEach(function (field) {
      var row = document.createElement('div');
      row.className = 'detail-meta-row';
      row.innerHTML = '<span class="detail-meta-label">' + escapeHtml(field[0]) + '</span>'
        + '<span class="detail-meta-value">' + escapeHtml(String(field[1])) + '</span>';
      meta.appendChild(row);
    });
  }

  function fillDetailTags(issue) {
    var tagsEl = $('#detail-tags');
    if (!tagsEl) return;

    tagsEl.innerHTML = '';
    var tags = Array.isArray(issue.tags) ? issue.tags : [];

    if (!tags.length) {
      var empty = document.createElement('span');
      empty.className = 'emes-text-xs emes-mono';
      empty.style.color = 'var(--lf-ink-muted)';
      empty.textContent = 'no tags';
      tagsEl.appendChild(empty);
      return;
    }

    tags.forEach(function (tag) {
      var chip = document.createElement('span');
      chip.className = 'emes-tag emes-tag-sm';
      chip.textContent = tag;
      tagsEl.appendChild(chip);
    });
  }

  function fillDetailDeps(issue) {
    var depsEl = $('#detail-deps');
    if (!depsEl) return;

    depsEl.innerHTML = '';
    var deps = Array.isArray(issue.deps) ? issue.deps : [];
    if (!deps.length) {
      var empty = document.createElement('span');
      empty.className = 'emes-text-xs emes-mono';
      empty.style.color = 'var(--lf-ink-muted)';
      empty.textContent = 'no dependencies';
      depsEl.appendChild(empty);
      return;
    }

    deps.forEach(function (dep) {
      var div = document.createElement('div');
      div.className = 'emes-text-xs emes-mono';
      div.textContent = dep.type + ' -> ' + dep.target;
      depsEl.appendChild(div);
    });
  }

  function makeActionButton(label, handler) {
    var btn = document.createElement('button');
    btn.className = 'emes-btn-sm';
    btn.textContent = label;
    btn.onclick = function () { handler(btn); };
    return btn;
  }

  function fillDetailActions(issue) {
    var actionsEl = $('#detail-actions');
    if (!actionsEl) return;

    actionsEl.innerHTML = '';

    if (issue.status !== 'closed') {
      actionsEl.appendChild(makeActionButton('close success', function (btn) {
        closeIssue(issue.id, 'success', btn);
      }));
      actionsEl.appendChild(makeActionButton('close failure', function (btn) {
        closeIssue(issue.id, 'failure', btn);
      }));
      actionsEl.appendChild(makeActionButton('close skipped', function (btn) {
        closeIssue(issue.id, 'skipped', btn);
      }));
      return;
    }

    actionsEl.appendChild(makeActionButton('reopen', function (btn) {
      reopenIssue(issue.id, btn);
    }));
  }

  function loadDetail(id) {
    return api('GET', '/api/issues/' + id).then(function (issue) {
      if (!issue || issue.error) {
        toast('Could not load issue detail.', 'error');
        return;
      }

      var titleEl = $('#detail-title');
      var bodyEl = $('#detail-body');
      var idBadge = $('#detail-issue-id');
      if (titleEl) titleEl.value = issue.title || '';
      if (bodyEl) bodyEl.value = issue.body || '';
      if (idBadge) idBadge.textContent = issue.id;
      setSaveState('saved', 'saved');

      fillDetailMeta(issue);
      fillDetailTags(issue);
      fillDetailDeps(issue);
      fillDetailActions(issue);
      loadLog(id);
      loadForum(id);
      openPanel();
    });
  }

  function loadLog(id) {
    var logEl = $('#detail-log');
    if (!logEl) return;

    logEl.innerHTML = '<span class="emes-text-xs" style="color:var(--lf-ink-muted)">loading...</span>';

    api('GET', '/api/logs/' + id).then(function (lines) {
      if (!Array.isArray(lines) || !lines.length) {
        logEl.innerHTML = '<span class="emes-text-xs" style="color:var(--lf-ink-muted)">no log</span>';
        return;
      }

      logEl.innerHTML = '';
      lines.forEach(function (line) {
        var div = document.createElement('div');
        div.className = 'detail-log-line';
        div.textContent = typeof line === 'object'
          ? JSON.stringify(line).substring(0, 260)
          : String(line).substring(0, 260);
        logEl.appendChild(div);
      });
      logEl.scrollTop = logEl.scrollHeight;
    });
  }

  function loadForum(id) {
    var el = $('#detail-forum');
    if (!el) return;

    el.innerHTML = '';

    api('GET', '/api/forum/issue:' + id).then(function (msgs) {
      if (!Array.isArray(msgs) || !msgs.length) {
        el.innerHTML = '<span class="emes-text-xs" style="color:var(--lf-ink-muted)">no messages</span>';
        return;
      }

      msgs.forEach(function (msg) {
        var div = document.createElement('div');
        div.className = 'forum-msg';
        div.innerHTML = '<div class="forum-msg-author">'
          + escapeHtml(msg.author || 'system') + ' - ' + ago(msg.created_at)
          + '</div><div class="forum-msg-body">'
          + escapeHtml(msg.body || '').substring(0, 900)
          + '</div>';
        el.appendChild(div);
      });
    });
  }

  function patchFocusedIssue(payload, onSuccess) {
    if (!focusedId) return Promise.resolve();

    setSaveState('saving', 'saving');
    return api('PATCH', '/api/issues/' + focusedId, payload).then(function (res) {
      if (res && res.error) {
        setSaveState('error', 'save failed');
        toast(res.error, 'error');
        return;
      }
      if (typeof onSuccess === 'function') onSuccess();
      setSaveState('saved', 'saved');
    });
  }

  window.saveTitle = function () {
    if (!focusedId) return Promise.resolve();

    var titleEl = $('#detail-title');
    if (!titleEl) return Promise.resolve();

    var val = titleEl.value.trim();
    if (!val) {
      setSaveState('error', 'title required');
      toast('Title cannot be empty.', 'error');
      return Promise.resolve();
    }

    return patchFocusedIssue({ title: val }, function () {
      var nodeTitle = document.querySelector('.tree-node[data-id="' + focusedId + '"] .tree-title');
      if (nodeTitle) nodeTitle.textContent = val;
      updateBreadcrumbTrail(focusedId);
    });
  };

  window.saveBody = function () {
    if (!focusedId) return Promise.resolve();

    var bodyEl = $('#detail-body');
    if (!bodyEl) return Promise.resolve();

    return patchFocusedIssue({ body: bodyEl.value });
  };

  function closeIssue(id, outcome, buttonEl) {
    setButtonPending(buttonEl, true, 'closing...');
    return api('POST', '/api/issues/' + id + '/close', { outcome: outcome }).then(function (res) {
      setButtonPending(buttonEl, false);
      if (res && res.error) {
        toast(res.error, 'error');
        return;
      }
      toast('Issue closed as ' + outcome + '.', 'success');
      loadDetail(id);
    });
  }

  function reopenIssue(id, buttonEl) {
    setButtonPending(buttonEl, true, 'reopening...');
    return api('POST', '/api/issues/' + id + '/reopen').then(function (res) {
      setButtonPending(buttonEl, false);
      if (res && res.error) {
        toast(res.error, 'error');
        return;
      }
      toast('Issue reopened.', 'success');
      loadDetail(id);
    });
  }

  window.postForumMessage = function (event) {
    if (event) event.preventDefault();
    if (!focusedId) return;

    var input = $('#forum-input');
    if (!input) return;

    var msg = input.value.trim();
    if (!msg) return;

    api('POST', '/api/forum/issue:' + focusedId, { body: msg, author: 'web' }).then(function (res) {
      if (res && res.error) {
        toast(res.error, 'error');
        return;
      }
      input.value = '';
      loadForum(focusedId);
      toast('Message posted.', 'success');
    });
  };

  function focusedParentId() {
    if (!focusedId) return null;
    var node = document.querySelector('.tree-node[data-id="' + focusedId + '"]');
    if (!node) return null;
    return node.dataset.parent || null;
  }

  function setInlineFormVisibility(formId, visible, inputId) {
    var form = $('#' + formId);
    if (!form) return;
    if (visible) {
      form.classList.add('open');
      var input = $('#' + inputId);
      if (input) input.focus();
      return;
    }
    form.classList.remove('open');
    var inputEl = $('#' + inputId);
    if (inputEl) inputEl.value = '';
  }

  window.beginCreateChild = function () {
    if (!focusedId) {
      toast('Select an issue before creating a child.', 'info');
      return;
    }
    setInlineFormVisibility('create-child-inline', true, 'create-child-title');
  };

  window.cancelCreateChild = function () {
    setInlineFormVisibility('create-child-inline', false, 'create-child-title');
  };

  window.beginCreateSibling = function () {
    if (!focusedId) {
      toast('Select an issue before creating a sibling.', 'info');
      return;
    }
    setInlineFormVisibility('create-sibling-inline', true, 'create-sibling-title');
  };

  window.cancelCreateSibling = function () {
    setInlineFormVisibility('create-sibling-inline', false, 'create-sibling-title');
  };

  function createIssueAndRefresh(payload) {
    return api('POST', '/api/issues', payload).then(function (res) {
      if (res && res.error) {
        toast(res.error, 'error');
        return;
      }
      toast('Issue created. Refreshing tree...', 'success');
      setTimeout(function () { window.location.reload(); }, 250);
    });
  }

  window.submitCreateChild = function (event) {
    if (event) event.preventDefault();
    if (!focusedId) return;

    var input = $('#create-child-title');
    if (!input) return;

    var title = input.value.trim();
    if (!title) {
      toast('Provide a child title.', 'error');
      return;
    }

    createIssueAndRefresh({ title: title, parent: focusedId });
  };

  window.submitCreateSibling = function (event) {
    if (event) event.preventDefault();
    if (!focusedId) return;

    var input = $('#create-sibling-title');
    if (!input) return;

    var title = input.value.trim();
    if (!title) {
      toast('Provide a sibling title.', 'error');
      return;
    }

    var payload = { title: title };
    var parentId = focusedParentId();
    if (parentId) payload.parent = parentId;
    createIssueAndRefresh(payload);
  };

  window.toggleNode = function (id) {
    var children = document.getElementById('children-' + id);
    if (!children) return;
    children.classList.toggle('collapsed');

    var node = document.querySelector('.tree-node[data-id="' + id + '"]');
    var toggle = node && node.querySelector('.tree-toggle');
    if (toggle) toggle.classList.toggle('expanded');

    collectNodeIds();
  };

  window.startRunner = function () {
    if (!window.__rootId) return;

    var runBtn = $('#btn-run');
    setButtonPending(runBtn, true, 'running...');
    api('POST', '/api/runner/start', { root_id: window.__rootId }).then(function (data) {
      setButtonPending(runBtn, false);
      var el = $('#runner-status');
      if (data && data.error) {
        if (el) el.textContent = data.error;
        toast(data.error, 'error');
        return;
      }
      if (el) el.textContent = 'running';
      toast('Runner started.', 'success');
    });
  };

  window.pauseRunner = function () {
    var pauseBtn = $('#btn-pause');
    setButtonPending(pauseBtn, true, 'pausing...');
    api('POST', '/api/runner/pause').then(function (data) {
      setButtonPending(pauseBtn, false);
      if (data && data.error) {
        toast(data.error, 'error');
        return;
      }
      var el = $('#runner-status');
      if (el) el.textContent = 'paused';
      toast('Runner paused.', 'info');
    });
  };

  // ---------------------------------------------------------------------------
  // Command Palette
  // ---------------------------------------------------------------------------

  function closeCmdPalette() {
    var el = $('#cmd-palette-backdrop');
    if (el) el.remove();
    cmdPaletteOpen = false;
  }

  function resolveRootIssueId(issue) {
    if (!issue || !issue.id) return Promise.resolve(null);
    if (Array.isArray(issue.tags) && issue.tags.indexOf('node:root') >= 0) {
      return Promise.resolve(issue.id);
    }

    var parentId = findParentDep(issue.deps);
    if (!parentId) return Promise.resolve(issue.id);

    var guard = 0;
    function step(id) {
      if (!id || guard > 60) return Promise.resolve(id);
      guard += 1;
      return api('GET', '/api/issues/' + id).then(function (parentIssue) {
        if (!parentIssue || parentIssue.error) return id;
        var nextParent = findParentDep(parentIssue.deps);
        if (!nextParent) return parentIssue.id;
        return step(nextParent);
      });
    }

    return step(parentId);
  }

  function navigateFromPalette(issue) {
    var treeNode = document.querySelector('.tree-node[data-id="' + issue.id + '"]');
    if (treeNode) {
      focusNode(issue.id);
      loadDetail(issue.id);
      return;
    }

    resolveRootIssueId(issue).then(function (rootId) {
      if (!rootId) {
        toast('Could not resolve root issue for selection.', 'error');
        return;
      }
      window.location.href = '/dag/' + rootId + '?focus=' + encodeURIComponent(issue.id);
    });
  }

  function renderPaletteResults(container, issues) {
    container.innerHTML = '';

    issues.slice(0, 40).forEach(function (issue, i) {
      var item = document.createElement('div');
      item.className = 'cmd-palette-item' + (i === 0 ? ' selected' : '');
      item.innerHTML = '<span>' + escapeHtml(issue.title) + '</span><span class="emes-mono">' + issue.id.substring(0, 16) + '</span>';
      item.onclick = function () {
        closeCmdPalette();
        navigateFromPalette(issue);
      };
      container.appendChild(item);
    });

    if (!issues.length) {
      container.innerHTML = '<div style="padding:1rem;color:var(--lf-ink-muted);text-align:center">No matches</div>';
    }
  }

  function openCmdPalette() {
    if (cmdPaletteOpen) return;
    cmdPaletteOpen = true;

    var backdrop = document.createElement('div');
    backdrop.className = 'cmd-palette-backdrop';
    backdrop.id = 'cmd-palette-backdrop';
    backdrop.onclick = function (e) {
      if (e.target === backdrop) closeCmdPalette();
    };

    var palette = document.createElement('div');
    palette.className = 'cmd-palette';

    var input = document.createElement('input');
    input.className = 'cmd-palette-input';
    input.placeholder = 'Search by issue title or id...';
    input.type = 'text';

    var results = document.createElement('div');
    results.className = 'cmd-palette-results';

    palette.appendChild(input);
    palette.appendChild(results);
    backdrop.appendChild(palette);
    document.body.appendChild(backdrop);

    input.focus();

    var allIssues = [];
    api('GET', '/api/issues').then(function (issues) {
      if (!Array.isArray(issues)) {
        toast('Could not load issues for search.', 'error');
        return;
      }
      allIssues = issues;
      renderPaletteResults(results, issues);
    });

    input.oninput = function () {
      var q = input.value.toLowerCase();
      var filtered = allIssues.filter(function (issue) {
        return issue.title.toLowerCase().includes(q) || issue.id.includes(q);
      });
      renderPaletteResults(results, filtered);
    };

    input.onkeydown = function (e) {
      if (e.key === 'Escape') {
        closeCmdPalette();
        e.preventDefault();
        return;
      }

      if (e.key === 'Enter') {
        var sel = results.querySelector('.cmd-palette-item.selected') || results.querySelector('.cmd-palette-item');
        if (sel) {
          sel.click();
          e.preventDefault();
        }
        return;
      }

      if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;

      var items = Array.from(results.querySelectorAll('.cmd-palette-item'));
      if (!items.length) return;

      var idx = items.findIndex(function (el) { return el.classList.contains('selected'); });
      items.forEach(function (el) { el.classList.remove('selected'); });

      if (idx < 0) idx = 0;
      if (e.key === 'ArrowDown') idx = Math.min(idx + 1, items.length - 1);
      else idx = Math.max(idx - 1, 0);

      items[idx].classList.add('selected');
      items[idx].scrollIntoView({ block: 'nearest' });
      e.preventDefault();
    };
  }

  // ---------------------------------------------------------------------------
  // Keyboard Handler
  // ---------------------------------------------------------------------------

  function initKeyboard() {
    collectNodeIds();

    $$('.tree-toggle').forEach(function (el) { el.classList.add('expanded'); });

    document.addEventListener('keydown', function (e) {
      var tag = e.target.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      if (cmdPaletteOpen) return;

      switch (e.key) {
        case 'j':
          moveFocus(1);
          e.preventDefault();
          break;
        case 'k':
          moveFocus(-1);
          e.preventDefault();
          break;
        case 'Enter':
          if (focusedId) loadDetail(focusedId);
          e.preventDefault();
          break;
        case 'Escape':
          closePanel();
          focusNode(null);
          e.preventDefault();
          break;
        case ' ':
          if (focusedId) window.toggleNode(focusedId);
          e.preventDefault();
          break;
        case 'Tab':
          if (!e.shiftKey) {
            window.beginCreateChild();
          }
          e.preventDefault();
          break;
        case 'n':
          window.beginCreateSibling();
          e.preventDefault();
          break;
        case 'e':
          if (focusedId) {
            openPanel();
            loadDetail(focusedId);
            setTimeout(function () {
              var title = $('#detail-title');
              if (title) title.focus();
            }, 100);
          }
          e.preventDefault();
          break;
        case 'x':
          if (focusedId) {
            var outcome = prompt('Outcome (success/failure/skipped):', 'success');
            if (outcome) closeIssue(focusedId, outcome, null);
          }
          e.preventDefault();
          break;
        case 'r':
          if (focusedId) reopenIssue(focusedId, null);
          e.preventDefault();
          break;
        case '1':
        case '2':
        case '3':
        case '4':
        case '5':
          if (focusedId) {
            setSaveState('saving', 'saving');
            api('PATCH', '/api/issues/' + focusedId, { priority: parseInt(e.key, 10) }).then(function (res) {
              if (res && res.error) {
                setSaveState('error', 'save failed');
                toast(res.error, 'error');
                return;
              }
              setSaveState('saved', 'saved');
            });
          }
          e.preventDefault();
          break;
        case '/':
          openCmdPalette();
          e.preventDefault();
          break;
      }
    });

    $$('.tree-row').forEach(function (row) {
      row.addEventListener('click', function () {
        var node = row.closest('.tree-node');
        if (!node) return;
        var id = node.dataset.id;
        focusNode(id);
        loadDetail(id);
      });
    });
  }

  function initDirtyStateHints() {
    var title = $('#detail-title');
    var body = $('#detail-body');

    if (title) {
      title.addEventListener('input', function () {
        setSaveState('saving', 'unsaved');
      });
    }

    if (body) {
      body.addEventListener('input', function () {
        setSaveState('saving', 'unsaved');
      });
    }
  }

  function initFocusFromUrl() {
    var params = new URLSearchParams(window.location.search || '');
    var focus = params.get('focus');
    if (!focus) return;

    var node = document.querySelector('.tree-node[data-id="' + focus + '"]');
    if (!node) return;

    focusNode(focus);
    loadDetail(focus);
  }

  // ---------------------------------------------------------------------------
  // Init
  // ---------------------------------------------------------------------------

  function init() {
    var trailEl = $('#breadcrumb-trail');
    if (trailEl) initialBreadcrumbTrail = trailEl.textContent;

    initSSE();
    initKeyboard();
    initDirtyStateHints();
    initFocusFromUrl();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
