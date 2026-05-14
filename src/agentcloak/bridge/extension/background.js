// agentcloak Bridge — Chrome MV3 service worker
// Connects to bridge/daemon via WebSocket with auto-discovery.

const DEFAULT_HOST = "127.0.0.1";
const DEFAULT_PORT = 18765;
const PORT_RANGE_START = 18765;
const PORT_RANGE_END = 18774;
const PROBE_TIMEOUT = 2000;
const RECONNECT_BASE = 1000;
const RECONNECT_MAX = 30000;

let ws = null;
let reconnectDelay = RECONNECT_BASE;
let attachedTabs = new Map();
let currentHost = null;
let currentPort = null;
let currentService = null; // "agentcloak-daemon" or "agentcloak-bridge"
let isReconnecting = false;

// --- Badge ---

function setBadge(state) {
  const badges = {
    on: { text: "ON", color: "#4caf50" },
    off: { text: "OFF", color: "#f44336" },
    wait: { text: "...", color: "#ff9800" },
  };
  const b = badges[state] || badges.off;
  chrome.action.setBadgeText({ text: b.text });
  chrome.action.setBadgeBackgroundColor({ color: b.color });
}

setBadge("off");

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
  const data = await chrome.storage.local.get(["_attached_tabs"]);
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

  // Prefer daemon direct connection over bridge
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
    currentHost = null;
    currentPort = null;
    currentService = null;
    setBadge("off");
    scheduleReconnect();
  };

  ws.onerror = () => {
    ws.close();
  };
}

function scheduleReconnect() {
  isReconnecting = true;
  setBadge("wait");
  setTimeout(() => {
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
      case "cdp":
        return await cmdCDP(msg);
      case "batch":
        return await cmdBatch(msg);
      case "ping":
        return { ok: true, data: { pong: true } };
      default:
        return { ok: false, error: `unknown command: ${msg.cmd}` };
    }
  } catch (e) {
    return { ok: false, error: e.message };
  }
}

async function ensureAttached(tabId) {
  if (attachedTabs.has(tabId)) return;
  await chrome.debugger.attach({ tabId }, "1.3");
  attachedTabs.set(tabId, true);
  await saveAttachedTabs();
}

async function detachTab(tabId) {
  if (!attachedTabs.has(tabId)) return;
  try {
    await chrome.debugger.detach({ tabId });
  } catch {}
  attachedTabs.delete(tabId);
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
  await chrome.debugger.sendCommand({ tabId }, "Page.enable", {});

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

async function cmdEvaluate(msg) {
  const tabId = resolveTabId(msg) || (await getActiveTabId());
  if (!tabId) return { ok: false, error: "no active tab" };

  const js = msg.params?.js || msg.params?.expression;
  if (!js) return { ok: false, error: "js expression required" };

  // Path A: chrome.scripting.executeScript (fast, no debugger bar)
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
  } catch {
    // Path B: CDP fallback (CSP-restricted pages)
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

// Clean up debugger attachments when tabs close
chrome.tabs.onRemoved.addListener((tabId) => {
  attachedTabs.delete(tabId);
  saveAttachedTabs();
});

// Strip CSP headers for CDP JS injection
chrome.runtime.onInstalled.addListener(() => {
  chrome.declarativeNetRequest.updateDynamicRules({
    removeRuleIds: [9999],
    addRules: [
      {
        id: 9999,
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
          urlFilter: "*",
          resourceTypes: ["main_frame", "sub_frame"],
        },
      },
    ],
  });
});

// Restore state and start connection
restoreAttachedTabs().then(() => connect());
