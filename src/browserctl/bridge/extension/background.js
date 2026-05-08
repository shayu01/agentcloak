// browserctl Bridge — Chrome MV3 service worker
// Connects to local bridge process via WebSocket, executes commands.

const BRIDGE_PORT = 18765;
const RECONNECT_BASE = 1000;
const RECONNECT_MAX = 30000;

let ws = null;
let reconnectDelay = RECONNECT_BASE;
let attachedTabs = new Map();

function connect() {
  if (ws && ws.readyState <= 1) return;

  ws = new WebSocket(`ws://127.0.0.1:${BRIDGE_PORT}/ext`);

  ws.onopen = () => {
    console.log("[browserctl] connected to bridge");
    reconnectDelay = RECONNECT_BASE;
    ws.send(JSON.stringify({ type: "hello", agent: "browserctl-extension" }));
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

  ws.onclose = () => {
    console.log("[browserctl] bridge disconnected, reconnecting...");
    scheduleReconnect();
  };

  ws.onerror = () => {
    ws.close();
  };
}

function scheduleReconnect() {
  setTimeout(() => {
    reconnectDelay = Math.min(reconnectDelay * 1.5, RECONNECT_MAX);
    connect();
  }, reconnectDelay);
}

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
}

async function detachTab(tabId) {
  if (!attachedTabs.has(tabId)) return;
  try {
    await chrome.debugger.detach({ tabId });
  } catch {}
  attachedTabs.delete(tabId);
}

function resolveTabId(msg) {
  return msg.tabId || msg.params?.tabId;
}

async function getActiveTabId() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab?.id;
}

async function cmdNavigate(msg) {
  const tabId = resolveTabId(msg) || (await getActiveTabId());
  if (!tabId) return { ok: false, error: "no active tab" };

  const url = msg.params?.url;
  if (!url) return { ok: false, error: "url required" };

  await ensureAttached(tabId);
  const result = await chrome.debugger.sendCommand(
    { tabId },
    "Page.navigate",
    { url }
  );

  // Wait for load
  await new Promise((resolve) => setTimeout(resolve, 500));
  const tab = await chrome.tabs.get(tabId);

  return {
    ok: true,
    data: {
      url: tab.url,
      title: tab.title,
      frameId: result.frameId,
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

async function cmdEvaluate(msg) {
  const tabId = resolveTabId(msg) || (await getActiveTabId());
  if (!tabId) return { ok: false, error: "no active tab" };

  const js = msg.params?.js || msg.params?.expression;
  if (!js) return { ok: false, error: "js expression required" };

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

// Start connection
connect();
