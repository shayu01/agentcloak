// agentcloak Bridge — Options page logic
//
// Auto-saves on input change so the "Save" button is mostly there for
// the satisfying toast — the service worker has already reconnected by
// the time the user reads it. Connection status and the most recent
// error are polled from the background worker so the hint stays fresh
// even if Chrome put the worker to sleep between visits.

const STORAGE_KEYS = [
  "bridge_host",
  "bridge_port",
  "bridge_token",
  "last_connected_host",
  "last_connected_port",
  "_last_error",
];

const hostInput = document.getElementById("host");
const portInput = document.getElementById("port");
const tokenInput = document.getElementById("token");
const saveBtn = document.getElementById("save-btn");
const resetBtn = document.getElementById("reset-btn");
const testBtn = document.getElementById("test-btn");
const savedMsg = document.getElementById("saved-msg");
const statusEl = document.getElementById("status");
const statusTextEl = document.getElementById("status-text");
const errorHintEl = document.getElementById("error-hint");

// --- Settings persistence ---

chrome.storage.local.get(STORAGE_KEYS, (data) => {
  hostInput.value = data.bridge_host || "";
  portInput.value = data.bridge_port || "";
  tokenInput.value = data.bridge_token || "";
});

function persistSettings(showToast) {
  const settings = {};
  const host = hostInput.value.trim();
  const port = portInput.value.trim();
  const token = tokenInput.value.trim();

  if (host) settings.bridge_host = host;
  else chrome.storage.local.remove("bridge_host");

  if (port) settings.bridge_port = parseInt(port, 10);
  else chrome.storage.local.remove("bridge_port");

  if (token) settings.bridge_token = token;
  else chrome.storage.local.remove("bridge_token");

  chrome.storage.local.set(settings, () => {
    if (showToast) {
      savedMsg.classList.add("show");
      setTimeout(() => savedMsg.classList.remove("show"), 2500);
    }
  });
}

// Auto-save on input — matches the chrome-extension-ui
// "options-auto-save" guideline so the user never has a surprise
// "unsaved changes" state. Small debounce so we don't write on every
// keystroke when the user is mid-typing a token.
let saveTimer = null;
function scheduleAutoSave() {
  if (saveTimer != null) clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    saveTimer = null;
    persistSettings(false);
  }, 600);
}

hostInput.addEventListener("input", scheduleAutoSave);
portInput.addEventListener("input", scheduleAutoSave);
tokenInput.addEventListener("input", scheduleAutoSave);

saveBtn.addEventListener("click", () => persistSettings(true));

resetBtn.addEventListener("click", () => {
  chrome.storage.local.remove(STORAGE_KEYS, () => {
    hostInput.value = "";
    portInput.value = "";
    tokenInput.value = "";
    savedMsg.textContent = "Settings reset to defaults.";
    savedMsg.classList.add("show");
    setTimeout(() => {
      savedMsg.textContent = "Settings saved. Reconnecting...";
      savedMsg.classList.remove("show");
    }, 2500);
  });
});

testBtn.addEventListener("click", () => {
  // Drop any stored failure now — the worker will record a new one if
  // the test actually fails, but we don't want stale text mid-test.
  chrome.storage.local.remove("_last_error");
  statusTextEl.textContent = "Testing...";
  statusEl.className = "status status-reconnecting";
  errorHintEl.style.display = "none";
  chrome.runtime.sendMessage({ type: "force_reconnect" }, () => {
    // Status polling will surface success/failure in the next tick;
    // no need to wait synchronously here.
  });
});

// --- Error hint mapping ---
// Maps the WebSocket close code (or "1006 + never opened") to a short,
// actionable explanation. The agent runs in someone else's browser so
// we can't link to a fix dialog — text plus the exact CLI command they
// should run is the most useful thing we can put on screen.

function describeError(err) {
  if (!err || err.code == null) return null;
  const code = err.code;
  const reason = err.reason || "";
  if (code === 4001) {
    return {
      title: "Token mismatch",
      body: (
        "The daemon rejected this extension's token. Get the current " +
        "token by running this command on the daemon host, then paste " +
        "it into the Token field above:"
      ),
      command: "agentcloak bridge token",
    };
  }
  if (code === 4002) {
    return {
      title: "Another client is already connected",
      body: (
        "Only one extension can hold the remote bridge at a time. " +
        "Close the other Chrome window using agentcloak, or restart " +
        "the daemon to drop the stale connection."
      ),
      command: null,
    };
  }
  if (code === 4003) {
    return {
      title: "Bridge denied the connection",
      body: reason || "The daemon refused the WebSocket handshake.",
      command: null,
    };
  }
  if (code === 1006) {
    return {
      title: "Cannot reach the daemon",
      body: (
        "The browser couldn't open a TCP connection to the configured " +
        "host/port. Make sure the daemon is running and reachable:"
      ),
      command: "agentcloak daemon health",
    };
  }
  return {
    title: `Disconnected (code ${code})`,
    body: reason || "WebSocket closed unexpectedly.",
    command: null,
  };
}

function renderErrorHint(err) {
  const info = describeError(err);
  if (!info) {
    errorHintEl.style.display = "none";
    return;
  }
  // Build the DOM manually — never trust `reason` to be HTML-safe even
  // if today it always is. textContent + appendChild keeps us out of
  // the XSS minefield.
  errorHintEl.textContent = "";
  const title = document.createElement("strong");
  title.textContent = info.title;
  errorHintEl.appendChild(title);
  errorHintEl.appendChild(document.createElement("br"));
  errorHintEl.appendChild(document.createTextNode(info.body));
  if (info.command) {
    errorHintEl.appendChild(document.createElement("br"));
    const code = document.createElement("code");
    code.textContent = info.command;
    errorHintEl.appendChild(code);
  }
  errorHintEl.style.display = "block";
}

// --- Status polling ---

function updateStatus() {
  chrome.runtime.sendMessage({ type: "get_status" }, (response) => {
    chrome.storage.local.get(["_last_error"], (data) => {
      const err = data._last_error;
      if (chrome.runtime.lastError || !response) {
        statusTextEl.textContent = "Background worker unreachable";
        statusEl.className = "status status-error";
        renderErrorHint(err);
        return;
      }
      if (response.connected) {
        statusTextEl.textContent = `Connected to ${response.host}:${response.port}`;
        statusEl.className = "status status-connected";
        // Hide stale hints when we're actually online — the worker
        // also clears _last_error on a clean open; this is a safety
        // net for the moment between events.
        errorHintEl.style.display = "none";
        return;
      }
      // Disconnected. Pick the flavour based on whether there's a
      // user-actionable error waiting.
      if (err && (err.code === 4001 || err.code === 4002 || err.code === 4003)) {
        statusTextEl.textContent = "Error — see hint below";
        statusEl.className = "status status-error";
      } else if (response.reconnecting) {
        statusTextEl.textContent = "Reconnecting...";
        statusEl.className = "status status-reconnecting";
      } else {
        statusTextEl.textContent = "Disconnected";
        statusEl.className = "status status-disconnected";
      }
      renderErrorHint(err);
    });
  });
}

updateStatus();
setInterval(updateStatus, 2000);
