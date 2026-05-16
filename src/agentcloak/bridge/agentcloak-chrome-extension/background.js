// agentcloak Bridge — Chrome MV3 service worker
// Connects to bridge/daemon via WebSocket with auto-discovery.

const DEFAULT_HOST = "127.0.0.1";
const DEFAULT_PORT = 18765;
const PORT_RANGE_START = 18765;
const PORT_RANGE_END = 18774;
const PROBE_TIMEOUT = 2000;
const RECONNECT_BASE = 1000;
const RECONNECT_MAX = 30000;

// declarativeNetRequest rule ids
// Range 10000..14999 is reserved for per-tab CSP strip rules.
const CSP_RULE_BASE_ID = 10000;
const CSP_RULE_RANGE = 5000;

let ws = null;
let reconnectDelay = RECONNECT_BASE;
let reconnectTimer = null;
let attachedTabs = new Map();
let currentHost = null;
let currentPort = null;
let currentService = null; // "agentcloak-daemon" or "agentcloak-bridge"
let isReconnecting = false;
let agentTabGroupId = null; // Chrome tab group for agent-managed tabs
let managedTabIds = new Set(); // tabs created or claimed by agent

// --- Badge ---
// Four states map onto traffic-light semantics that match the badge skill:
//   on   — green, connected and healthy
//   wait — yellow, attempting / reconnecting
//   err  — red, last attempt failed (token wrong, port busy, etc.)
//   off  — grey/empty, not configured or manually stopped
// The grey "off" state intentionally clears the badge text so a dormant
// extension doesn't scream at the user — only failures earn a red label.

function setBadge(state) {
  const badges = {
    on: { text: "ON", color: "#4caf50" },
    wait: { text: "...", color: "#ff9800" },
    err: { text: "ERR", color: "#f44336" },
    off: { text: "", color: "#9e9e9e" },
  };
  const b = badges[state] || badges.off;
  chrome.action.setBadgeText({ text: b.text });
  chrome.action.setBadgeBackgroundColor({ color: b.color });
}

setBadge("off");

// --- Error feedback ---
// Persist the most recent failure so the options page can show a hint
// instead of just "disconnected". Cleared whenever a fresh connection
// succeeds so stale info doesn't outlive a working connection.

async function recordLastError(code, reason) {
  try {
    await chrome.storage.local.set({
      _last_error: {
        code,
        reason: reason || "",
        timestamp: Date.now(),
      },
    });
  } catch {
    // Storage failures shouldn't crash the worker.
  }
}

async function clearLastError() {
  try {
    await chrome.storage.local.remove("_last_error");
  } catch {
    // ignore
  }
}

// --- MV3 Service Worker Keepalive (chrome.alarms) ---

chrome.alarms.create("agentcloak-probe", { periodInMinutes: 0.1 });
chrome.alarms.create("agentcloak-keepalive", { periodInMinutes: 0.4 });

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "agentcloak-probe") {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      connect();
    }
  }
  if (alarm.name === "agentcloak-keepalive") {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "ping" }));
    }
  }
});

// --- State Persistence ---

async function saveAttachedTabs() {
  const entries = Array.from(attachedTabs.entries());
  await chrome.storage.local.set({ _attached_tabs: entries });
}

async function restoreAttachedTabs() {
  const data = await chrome.storage.local.get([
    "_attached_tabs",
    "_agent_tab_group_id",
    "_managed_tab_ids",
  ]);
  if (data._attached_tabs) {
    for (const [tabId, val] of data._attached_tabs) {
      try {
        await chrome.tabs.get(tabId);
        attachedTabs.set(tabId, val);
      } catch {
        // tab no longer exists
      }
    }
  }
  // Restore tab group — verify it still exists
  if (data._agent_tab_group_id != null) {
    try {
      const groups = await chrome.tabGroups.query({});
      if (groups.some((g) => g.id === data._agent_tab_group_id)) {
        agentTabGroupId = data._agent_tab_group_id;
      }
    } catch {
      // tabGroups API unavailable or group gone
    }
  }
  // Restore managed tab set — prune closed tabs
  if (data._managed_tab_ids) {
    for (const tabId of data._managed_tab_ids) {
      try {
        await chrome.tabs.get(tabId);
        managedTabIds.add(tabId);
      } catch {
        // tab no longer exists
      }
    }
  }
}

// --- Tab Group Management ---

async function saveTabGroupState() {
  await chrome.storage.local.set({
    _agent_tab_group_id: agentTabGroupId,
    _managed_tab_ids: Array.from(managedTabIds),
  });
}

async function ensureTabGroup(tabId) {
  /**
   * Add a tab to the "agentcloak" tab group, creating the group on first use.
   */
  try {
    // Verify existing group still exists
    if (agentTabGroupId != null) {
      try {
        const groups = await chrome.tabGroups.query({});
        if (!groups.some((g) => g.id === agentTabGroupId)) {
          agentTabGroupId = null;
        }
      } catch {
        agentTabGroupId = null;
      }
    }

    if (agentTabGroupId == null) {
      // Create new tab group
      const groupId = await chrome.tabs.group({ tabIds: [tabId] });
      await chrome.tabGroups.update(groupId, {
        title: "agentcloak",
        color: "blue",
        collapsed: false,
      });
      agentTabGroupId = groupId;
    } else {
      // Add tab to existing group
      await chrome.tabs.group({ tabIds: [tabId], groupId: agentTabGroupId });
    }

    managedTabIds.add(tabId);
    await saveTabGroupState();
  } catch (e) {
    // Tab grouping is non-fatal — log and continue
    console.log(`[agentcloak] tab group error: ${e.message}`);
  }
}

// --- Config ---

async function loadConfig() {
  return new Promise((resolve) => {
    chrome.storage.local.get(
      [
        "bridge_host",
        "bridge_port",
        "bridge_token",
        "last_connected_host",
        "last_connected_port",
        "last_connected_service",
      ],
      (data) => resolve(data || {})
    );
  });
}

async function saveLastConnected(host, port, service) {
  return new Promise((resolve) => {
    chrome.storage.local.set(
      {
        last_connected_host: host,
        last_connected_port: port,
        last_connected_service: service,
      },
      resolve
    );
  });
}

// --- Auto-Discovery (daemon preferred over bridge) ---

async function probeHealth(host, port) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), PROBE_TIMEOUT);
  try {
    const resp = await fetch(`http://${host}:${port}/health`, {
      signal: controller.signal,
    });
    const data = await resp.json();
    clearTimeout(timer);
    if (
      data.ok &&
      (data.service === "agentcloak-daemon" ||
        data.service === "agentcloak-bridge")
    ) {
      return { host, port, service: data.service };
    }
    return null;
  } catch {
    clearTimeout(timer);
    return null;
  }
}

async function discoverTarget(config) {
  const hosts = [];
  if (config.last_connected_host) hosts.push(config.last_connected_host);
  if (config.bridge_host && !hosts.includes(config.bridge_host)) {
    hosts.push(config.bridge_host);
  }
  if (!hosts.includes(DEFAULT_HOST)) hosts.push(DEFAULT_HOST);

  const userPort = config.bridge_port || null;
  let allResults = [];

  for (const host of hosts) {
    if (userPort) {
      const result = await probeHealth(host, userPort);
      if (result) allResults.push(result);
    }

    if (
      config.last_connected_port &&
      config.last_connected_port !== userPort &&
      host === config.last_connected_host
    ) {
      const result = await probeHealth(host, config.last_connected_port);
      if (result) allResults.push(result);
    }

    const probes = [];
    for (let p = PORT_RANGE_START; p <= PORT_RANGE_END; p++) {
      if (p === userPort || p === config.last_connected_port) continue;
      probes.push(probeHealth(host, p));
    }
    const results = await Promise.allSettled(probes);
    for (const r of results) {
      if (r.status === "fulfilled" && r.value) allResults.push(r.value);
    }
  }

  // Prefer the service we successfully connected to last time, then daemon, then bridge.
  if (config.last_connected_service) {
    const preferred = allResults.find(
      (r) => r.service === config.last_connected_service
    );
    if (preferred) return preferred;
  }
  const daemon = allResults.find((r) => r.service === "agentcloak-daemon");
  if (daemon) return daemon;
  const bridge = allResults.find((r) => r.service === "agentcloak-bridge");
  if (bridge) return bridge;

  return {
    host: config.bridge_host || DEFAULT_HOST,
    port: config.bridge_port || DEFAULT_PORT,
    service: null,
  };
}

// --- WebSocket Connection ---

async function connect() {
  if (ws && ws.readyState <= 1) return;

  isReconnecting = true;
  setBadge("wait");

  const config = await loadConfig();
  const target = await discoverTarget(config);
  const wsUrl = `ws://${target.host}:${target.port}/ext`;

  console.log(
    `[agentcloak] connecting to ${wsUrl} (${target.service || "unknown"})`
  );

  try {
    ws = new WebSocket(wsUrl);
  } catch (e) {
    console.log(`[agentcloak] WebSocket creation failed: ${e.message}`);
    scheduleReconnect();
    return;
  }

  ws.onopen = () => {
    console.log(
      `[agentcloak] connected to ${target.service} at ${target.host}:${target.port}`
    );
    reconnectDelay = RECONNECT_BASE;
    isReconnecting = false;
    currentHost = target.host;
    currentPort = target.port;
    currentService = target.service;
    setBadge("on");
    // A clean connect means whatever previously failed is fixed — drop
    // the stored error so the options page stops showing the old hint.
    clearLastError();

    saveLastConnected(target.host, target.port, target.service);

    const hello = { type: "hello", agent: "agentcloak-extension" };
    if (config.bridge_token) {
      hello.token = config.bridge_token;
    }
    ws.send(JSON.stringify(hello));
  };

  ws.onmessage = async (event) => {
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch {
      return;
    }
    if (!msg.id || !msg.cmd) return;
    const result = await handleCommand(msg);
    ws.send(JSON.stringify({ id: msg.id, ...result }));
  };

  ws.onclose = (event) => {
    console.log(
      `[agentcloak] disconnected (code=${event.code}, reason=${event.reason})`
    );
    // Snapshot the previous "we were connected" state *before* we tear
    // it down — we need it to tell "connection refused" (never opened)
    // apart from "server cut us off" (was healthy, now isn't).
    const wasConnected = currentHost !== null;
    currentHost = null;
    currentPort = null;
    currentService = null;

    // Auth / mutual-exclusion failures are user-actionable, so we flag
    // them as "err" (red badge) and persist the close code+reason for
    // the options page. Plain 1000/1001 disconnects just look like
    // network blips — fall through to the wait state and let the
    // reconnect timer retry quietly.
    const closeCode = event.code;
    const closeReason = event.reason || "";
    if (closeCode === 4001 || closeCode === 4002 || closeCode === 4003) {
      setBadge("err");
      recordLastError(closeCode, closeReason);
    } else if (closeCode === 1006 && !wasConnected) {
      // 1006 without a successful prior handshake means the TCP layer
      // failed — almost always "connection refused" or wrong host/port.
      // Don't flip to red on this (the reconnect timer might cure it
      // when the daemon comes up), but do persist the hint so the
      // options page can explain *why* we're stuck in "..."
      recordLastError(closeCode, closeReason || "connection refused");
    }
    scheduleReconnect();
  };

  ws.onerror = () => {
    ws.close();
  };
}

function scheduleReconnect() {
  isReconnecting = true;
  setBadge("wait");
  // Clear any prior pending reconnect; multiple stacked timers cause
  // overlapping connect() calls when storage changes also trigger a reconnect.
  if (reconnectTimer != null) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    reconnectDelay = Math.min(reconnectDelay * 1.5, RECONNECT_MAX);
    connect();
  }, reconnectDelay);
}

// Reconnect when config changes in options page
chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "local") return;
  const relevant = ["bridge_host", "bridge_port", "bridge_token"];
  if (relevant.some((k) => k in changes)) {
    console.log("[agentcloak] config changed, reconnecting...");
    reconnectDelay = RECONNECT_BASE;
    if (reconnectTimer != null) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (ws && ws.readyState <= 1) {
      ws.close();
    } else {
      connect();
    }
  }
});

// Respond to status queries from options page
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "get_status") {
    sendResponse({
      connected: ws !== null && ws.readyState === WebSocket.OPEN,
      reconnecting: isReconnecting,
      host: currentHost,
      port: currentPort,
      service: currentService,
    });
    return true;
  }
  if (msg.type === "force_reconnect") {
    // The options page "Test Connection" button drops here. We want
    // the reconnect to happen immediately (reset backoff) so the user
    // gets feedback in seconds rather than waiting out the current
    // back-off window.
    console.log("[agentcloak] force_reconnect requested");
    reconnectDelay = RECONNECT_BASE;
    if (reconnectTimer != null) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (ws && ws.readyState <= 1) {
      ws.close();
    } else {
      connect();
    }
    sendResponse({ ok: true });
    return true;
  }
});

// --- Global CDP event forwarding ---
// Every attached tab streams events back through the WebSocket so the daemon
// can spot dialogs, navigations, console errors etc. without polling. This
// is the channel that makes Proactive State Feedback work for RemoteBridge.

chrome.debugger.onEvent.addListener((source, method, params) => {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  try {
    ws.send(
      JSON.stringify({
        type: "cdp_event",
        method,
        params,
        tabId: source.tabId,
      })
    );
  } catch (e) {
    console.log(`[agentcloak] cdp_event forward failed: ${e.message}`);
  }
});

// --- Command Handlers ---

async function handleCommand(msg) {
  try {
    switch (msg.cmd) {
      case "navigate":
        return await cmdNavigate(msg);
      case "screenshot":
        return await cmdScreenshot(msg);
      case "evaluate":
        return await cmdEvaluate(msg);
      case "cookies":
        return await cmdCookies(msg);
      case "tabs":
        return await cmdTabs(msg);
      case "tab_new":
        return await cmdTabNew(msg);
      case "tab_close":
        return await cmdTabClose(msg);
      case "tab_switch":
        return await cmdTabSwitch(msg);
      case "fetch":
        return await cmdFetch(msg);
      case "cdp":
        return await cmdCDP(msg);
      case "batch":
        return await cmdBatch(msg);
      case "claim":
        return await cmdClaim(msg);
      case "finalize":
        return await cmdFinalize(msg);
      case "ping":
        return { ok: true, data: { pong: true } };
      default:
        return { ok: false, error: `unknown command: ${msg.cmd}` };
    }
  } catch (e) {
    return { ok: false, error: e.message };
  }
}

// --- Per-tab CSP strip rules (declarativeNetRequest) ---

function cspRuleIdForTab(tabId) {
  // Map tabId into reserved range so we never collide with other rules.
  // Modulo keeps the id stable per session even with large tabIds.
  return CSP_RULE_BASE_ID + (tabId % CSP_RULE_RANGE);
}

async function addCspRuleForTab(tabId) {
  const id = cspRuleIdForTab(tabId);
  try {
    await chrome.declarativeNetRequest.updateDynamicRules({
      removeRuleIds: [id],
      addRules: [
        {
          id,
          priority: 1,
          action: {
            type: "modifyHeaders",
            responseHeaders: [
              { header: "content-security-policy", operation: "remove" },
              {
                header: "content-security-policy-report-only",
                operation: "remove",
              },
            ],
          },
          condition: {
            tabIds: [tabId],
            resourceTypes: ["main_frame", "sub_frame"],
          },
        },
      ],
    });
  } catch (e) {
    console.log(
      `[agentcloak] CSP rule add failed for tab ${tabId}: ${e.message}`
    );
  }
}

async function removeCspRuleForTab(tabId) {
  const id = cspRuleIdForTab(tabId);
  try {
    await chrome.declarativeNetRequest.updateDynamicRules({
      removeRuleIds: [id],
    });
  } catch (e) {
    console.log(
      `[agentcloak] CSP rule remove failed for tab ${tabId}: ${e.message}`
    );
  }
}

async function removeAllCspRules() {
  try {
    const existing = await chrome.declarativeNetRequest.getDynamicRules();
    const ids = existing
      .filter((r) => r.id >= CSP_RULE_BASE_ID && r.id < CSP_RULE_BASE_ID + CSP_RULE_RANGE)
      .map((r) => r.id);
    if (ids.length) {
      await chrome.declarativeNetRequest.updateDynamicRules({
        removeRuleIds: ids,
      });
    }
  } catch (e) {
    console.log(`[agentcloak] CSP rule clear failed: ${e.message}`);
  }
}

async function reapplyCspRulesFromAttachedTabs() {
  // Called on browser restart — re-add per-tab CSP rules for any tabs the
  // service worker still considers attached (state restored from storage).
  for (const tabId of attachedTabs.keys()) {
    try {
      await chrome.tabs.get(tabId);
      await addCspRuleForTab(tabId);
    } catch {
      // tab gone; will be cleaned up by onRemoved
    }
  }
}

async function ensureAttached(tabId) {
  if (attachedTabs.has(tabId)) return;
  await chrome.debugger.attach({ tabId }, "1.3");
  attachedTabs.set(tabId, true);
  await saveAttachedTabs();
  await addCspRuleForTab(tabId);
  // Enable the CDP domains we want events from. These are best-effort —
  // a failure here shouldn't block the attach (e.g. devtools already open).
  try {
    await chrome.debugger.sendCommand({ tabId }, "Page.enable", {});
  } catch (e) {
    console.log(`[agentcloak] Page.enable failed: ${e.message}`);
  }
  try {
    await chrome.debugger.sendCommand({ tabId }, "Runtime.enable", {});
  } catch (e) {
    console.log(`[agentcloak] Runtime.enable failed: ${e.message}`);
  }
  // Add to agent tab group for visual isolation
  await ensureTabGroup(tabId);
}

async function detachTab(tabId) {
  if (!attachedTabs.has(tabId)) return;
  try {
    await chrome.debugger.detach({ tabId });
  } catch {}
  attachedTabs.delete(tabId);
  await removeCspRuleForTab(tabId);
  await saveAttachedTabs();
}

function resolveTabId(msg) {
  return msg.tabId || msg.params?.tabId;
}

async function getActiveTabId() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab?.id;
}

// --- Navigate with CDP event wait (replaces setTimeout) ---

function waitForDebuggerEvent(tabId, eventName, timeoutMs) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      chrome.debugger.onEvent.removeListener(listener);
      resolve(); // timeout is not fatal, page may still be usable
    }, timeoutMs);

    function listener(source, method) {
      if (source.tabId === tabId && method === eventName) {
        clearTimeout(timer);
        chrome.debugger.onEvent.removeListener(listener);
        resolve();
      }
    }
    chrome.debugger.onEvent.addListener(listener);
  });
}

async function cmdNavigate(msg) {
  const tabId = resolveTabId(msg) || (await getActiveTabId());
  if (!tabId) return { ok: false, error: "no active tab" };

  const url = msg.params?.url;
  if (!url) return { ok: false, error: "url required" };

  const waitUntil = msg.params?.waitUntil || "load";

  await ensureAttached(tabId);

  const eventName =
    waitUntil === "domcontentloaded"
      ? "Page.domContentEventFired"
      : "Page.loadEventFired";

  const loadPromise = waitForDebuggerEvent(tabId, eventName, 30000);
  const navResult = await chrome.debugger.sendCommand(
    { tabId },
    "Page.navigate",
    { url }
  );
  await loadPromise;

  const tab = await chrome.tabs.get(tabId);

  return {
    ok: true,
    data: {
      url: tab.url,
      title: tab.title,
      frameId: navResult.frameId,
    },
  };
}

async function cmdScreenshot(msg) {
  const tabId = resolveTabId(msg) || (await getActiveTabId());
  if (!tabId) return { ok: false, error: "no active tab" };

  await ensureAttached(tabId);
  const result = await chrome.debugger.sendCommand(
    { tabId },
    "Page.captureScreenshot",
    { format: "png" }
  );

  return { ok: true, data: { base64: result.data } };
}

// --- Dual execution path: scripting API first, CDP fallback ---

// Hints that mark Path A failure as CSP-related, where falling back to CDP
// (which can bypass CSP because we strip the headers for attached tabs) is
// the right call. For other errors (SyntaxError, ReferenceError, code bugs)
// we just surface them so the caller sees the real problem.
const CSP_ERROR_HINTS = [
  "content security policy",
  "violates the following content security policy",
  "refused to execute inline script",
  "refused to evaluate",
  "blocked by csp",
  "csp directive",
  "unsafe-eval",
  "unsafe-inline",
  "executescript",
];

function isCspError(err) {
  const msg = (err && (err.message || String(err))) || "";
  const lower = msg.toLowerCase();
  return CSP_ERROR_HINTS.some((hint) => lower.includes(hint));
}

async function cmdEvaluate(msg) {
  const tabId = resolveTabId(msg) || (await getActiveTabId());
  if (!tabId) return { ok: false, error: "no active tab" };

  const js = msg.params?.js || msg.params?.expression;
  if (!js) return { ok: false, error: "js expression required" };

  // Path A: chrome.scripting.executeScript (fast, no debugger bar)
  let pathAError = null;
  try {
    const wrapped = `(async () => { ${js} })()`;
    const [frame] = await chrome.scripting.executeScript({
      target: { tabId },
      world: "MAIN",
      func: (code) => {
        return new Function("return " + code)();
      },
      args: [wrapped],
    });
    return { ok: true, data: { result: frame.result } };
  } catch (e) {
    pathAError = e;
    // Only fall through to Path B for CSP-related failures. For real script
    // errors (syntax, reference, runtime exceptions) we want the caller to
    // see them — double-executing via CDP would either re-throw or mask them.
    if (!isCspError(e)) {
      return {
        ok: false,
        error: (e && e.message) || "evaluation error",
      };
    }
  }

  // Path B: CDP fallback (only reached when Path A hit CSP)
  await ensureAttached(tabId);
  const result = await chrome.debugger.sendCommand(
    { tabId },
    "Runtime.evaluate",
    {
      expression: js,
      returnByValue: true,
      awaitPromise: true,
    }
  );

  if (result.exceptionDetails) {
    return {
      ok: false,
      error: result.exceptionDetails.text || "evaluation error",
    };
  }

  return { ok: true, data: { result: result.result?.value } };
}

async function cmdCookies(msg) {
  const url = msg.params?.url;
  let cookies;
  if (url) {
    cookies = await chrome.cookies.getAll({ url });
  } else {
    const tabId = resolveTabId(msg) || (await getActiveTabId());
    if (tabId) {
      const tab = await chrome.tabs.get(tabId);
      cookies = await chrome.cookies.getAll({ url: tab.url });
    } else {
      cookies = await chrome.cookies.getAll({});
    }
  }
  return { ok: true, data: cookies };
}

async function cmdTabs(_msg) {
  const tabs = await chrome.tabs.query({});
  const data = tabs
    .filter((t) => t.url && !t.url.startsWith("chrome://"))
    .map((t) => ({
      id: t.id,
      url: t.url,
      title: t.title,
      active: t.active,
      windowId: t.windowId,
    }));
  return { ok: true, data };
}

async function cmdTabNew(msg) {
  const url = msg.params?.url || msg.url;
  const createOpts = {};
  if (url) createOpts.url = url;
  const tab = await chrome.tabs.create(createOpts);
  // Wait briefly for the new tab to be eligible for debugger attach.
  // chrome.tabs.create resolves before the tab finishes loading, but the
  // tab id is valid immediately so the attach call works.
  try {
    await ensureAttached(tab.id);
  } catch (e) {
    console.log(
      `[agentcloak] tab_new attach failed for tab ${tab.id}: ${e.message}`
    );
  }
  return {
    ok: true,
    data: {
      tab_id: tab.id,
      url: tab.url || url || "",
      title: tab.title || "",
      active: tab.active,
    },
  };
}

async function cmdTabClose(msg) {
  const tabId = msg.params?.tab_id ?? msg.params?.tabId ?? msg.tabId;
  if (tabId == null) {
    return { ok: false, error: "tab_id required" };
  }
  try {
    await detachTab(tabId);
  } catch {}
  try {
    await chrome.tabs.remove(tabId);
  } catch (e) {
    return { ok: false, error: e.message };
  }
  managedTabIds.delete(tabId);
  await saveTabGroupState();
  return { ok: true, data: { closed: true, tab_id: tabId } };
}

async function cmdTabSwitch(msg) {
  const tabId = msg.params?.tab_id ?? msg.params?.tabId ?? msg.tabId;
  if (tabId == null) {
    return { ok: false, error: "tab_id required" };
  }
  try {
    const tab = await chrome.tabs.update(tabId, { active: true });
    return {
      ok: true,
      data: {
        switched: true,
        tab_id: tab.id,
        url: tab.url || "",
        title: tab.title || "",
      },
    };
  } catch (e) {
    return { ok: false, error: e.message };
  }
}

async function cmdFetch(msg) {
  // Run fetch inside the active tab's page context so we inherit its
  // cookies + origin headers — this is what callers expect when they fetch
  // via a logged-in remote browser.
  const tabId = resolveTabId(msg) || (await getActiveTabId());
  if (!tabId) return { ok: false, error: "no active tab" };

  const url = msg.params?.url;
  if (!url) return { ok: false, error: "url required" };

  const method = (msg.params?.method || "GET").toUpperCase();
  const headers = msg.params?.headers || {};
  const body = msg.params?.body;
  const timeoutMs = (msg.params?.timeout || 30) * 1000;

  try {
    const [frame] = await chrome.scripting.executeScript({
      target: { tabId },
      world: "MAIN",
      func: async (fetchUrl, fetchMethod, fetchHeaders, fetchBody, timeout) => {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), timeout);
        try {
          const init = {
            method: fetchMethod,
            headers: fetchHeaders,
            signal: controller.signal,
          };
          if (fetchBody != null && fetchMethod !== "GET" && fetchMethod !== "HEAD") {
            init.body = fetchBody;
          }
          const resp = await fetch(fetchUrl, init);
          const respHeaders = {};
          resp.headers.forEach((v, k) => {
            respHeaders[k] = v;
          });
          const text = await resp.text();
          return {
            status: resp.status,
            url: resp.url,
            headers: respHeaders,
            body: text,
          };
        } catch (e) {
          return { error: e.message || String(e) };
        } finally {
          clearTimeout(timer);
        }
      },
      args: [url, method, headers, body ?? null, timeoutMs],
    });
    const result = frame?.result;
    if (!result) {
      return { ok: false, error: "fetch returned no result" };
    }
    if (result.error) {
      return { ok: false, error: result.error };
    }
    return { ok: true, data: result };
  } catch (e) {
    return { ok: false, error: e.message };
  }
}

async function cmdCDP(msg) {
  const tabId = resolveTabId(msg) || (await getActiveTabId());
  if (!tabId) return { ok: false, error: "no active tab" };

  const method = msg.params?.method || msg.method;
  const params = msg.params?.params || {};

  if (!method) return { ok: false, error: "CDP method required" };

  await ensureAttached(tabId);
  const result = await chrome.debugger.sendCommand({ tabId }, method, params);
  return { ok: true, data: result };
}

async function cmdBatch(msg) {
  const commands = msg.params?.commands || msg.commands || [];
  const results = [];

  for (const cmd of commands) {
    if (!cmd.tabId && msg.tabId) cmd.tabId = msg.tabId;
    const result = await handleCommand({ ...cmd, id: msg.id });
    results.push(result);
  }

  return { ok: true, data: { results, completed: results.length } };
}

// --- Tab Claiming (R6.1) ---

async function cmdClaim(msg) {
  const tabId = msg.params?.tabId;
  const urlPattern = msg.params?.urlPattern;

  if (!tabId && !urlPattern) {
    return { ok: false, error: "tabId or urlPattern required" };
  }

  let targetTab = null;

  if (tabId) {
    try {
      targetTab = await chrome.tabs.get(tabId);
    } catch {
      return { ok: false, error: `tab ${tabId} not found` };
    }
  } else {
    // Find first tab matching URL substring
    const allTabs = await chrome.tabs.query({});
    targetTab = allTabs.find(
      (t) => t.url && t.url.includes(urlPattern)
    );
    if (!targetTab) {
      return {
        ok: false,
        error: `no tab matching URL pattern: ${urlPattern}`,
      };
    }
  }

  // Attach debugger to the claimed tab
  await ensureAttached(targetTab.id);

  return {
    ok: true,
    data: {
      tabId: targetTab.id,
      url: targetTab.url,
      title: targetTab.title,
      claimed: true,
    },
  };
}

// --- Session Finalize (R6.3) ---

async function cmdFinalize(msg) {
  const mode = msg.params?.mode || "close";
  const validModes = ["close", "handoff", "deliverable"];

  if (!validModes.includes(mode)) {
    return {
      ok: false,
      error: `invalid mode: ${mode}. Use: ${validModes.join(", ")}`,
    };
  }

  const tabIds = Array.from(managedTabIds);
  let result = { mode, tabsAffected: 0 };

  if (mode === "close") {
    // Close all tabs in the agent group, reset group tracking
    let closed = 0;
    for (const tid of tabIds) {
      try {
        await detachTab(tid);
        await chrome.tabs.remove(tid);
        closed++;
      } catch {
        // tab may already be closed
      }
    }
    managedTabIds.clear();
    agentTabGroupId = null;
    result.tabsAffected = closed;
  } else if (mode === "handoff") {
    // Ungroup tabs (remove from group but keep open for user)
    for (const tid of tabIds) {
      try {
        await detachTab(tid);
        await chrome.tabs.ungroup(tid);
      } catch {
        // ignore errors for already-ungrouped tabs
      }
    }
    result.tabsAffected = tabIds.length;
    managedTabIds.clear();
    agentTabGroupId = null;
  } else if (mode === "deliverable") {
    // Rename group to "agentcloak results", change color to green
    if (agentTabGroupId != null) {
      try {
        await chrome.tabGroups.update(agentTabGroupId, {
          title: "agentcloak results",
          color: "green",
          collapsed: false,
        });
      } catch {
        // group may have been removed
      }
    }
    // Detach debugger but keep tabs in group
    for (const tid of tabIds) {
      try {
        await detachTab(tid);
      } catch {
        // ignore
      }
    }
    result.tabsAffected = tabIds.length;
    managedTabIds.clear();
    agentTabGroupId = null;
  }

  // After finalize there should be no per-tab CSP rules left.
  await removeAllCspRules();
  await saveTabGroupState();
  await saveAttachedTabs();
  return { ok: true, data: result };
}

// Clean up debugger attachments and managed tabs when tabs close
chrome.tabs.onRemoved.addListener((tabId) => {
  attachedTabs.delete(tabId);
  managedTabIds.delete(tabId);
  removeCspRuleForTab(tabId);
  saveAttachedTabs();
  saveTabGroupState();
});

// On install, ensure any leftover global CSP rule (from older extension
// versions) is dropped. Per-tab rules are added by ensureAttached().
chrome.runtime.onInstalled.addListener(async () => {
  try {
    // Old extension versions used rule id 9999 globally — clear it if present.
    await chrome.declarativeNetRequest.updateDynamicRules({
      removeRuleIds: [9999],
    });
  } catch {}
});

// On browser restart, re-apply per-tab CSP rules for tabs we still consider
// attached (state restored from chrome.storage.local).
chrome.runtime.onStartup.addListener(async () => {
  await restoreAttachedTabs();
  await reapplyCspRulesFromAttachedTabs();
  connect();
});

// Restore state and start connection
restoreAttachedTabs().then(() => connect());
