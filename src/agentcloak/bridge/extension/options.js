// agentcloak Bridge — Options page logic

const STORAGE_KEYS = [
  "bridge_host",
  "bridge_port",
  "bridge_token",
  "last_connected_host",
  "last_connected_port",
];

const hostInput = document.getElementById("host");
const portInput = document.getElementById("port");
const tokenInput = document.getElementById("token");
const saveBtn = document.getElementById("save-btn");
const resetBtn = document.getElementById("reset-btn");
const savedMsg = document.getElementById("saved-msg");
const statusEl = document.getElementById("status");

// Load saved settings
chrome.storage.local.get(STORAGE_KEYS, (data) => {
  hostInput.value = data.bridge_host || "";
  portInput.value = data.bridge_port || "";
  tokenInput.value = data.bridge_token || "";
});

// Save settings
saveBtn.addEventListener("click", () => {
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
    savedMsg.classList.add("show");
    setTimeout(() => savedMsg.classList.remove("show"), 2500);
  });
});

// Reset to defaults
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

// Poll connection status from background
function updateStatus() {
  chrome.runtime.sendMessage({ type: "get_status" }, (response) => {
    if (chrome.runtime.lastError || !response) {
      statusEl.textContent = "Cannot reach background service worker.";
      statusEl.className = "status status-disconnected";
      return;
    }
    if (response.connected) {
      statusEl.textContent = `Connected to ${response.host}:${response.port}`;
      statusEl.className = "status status-connected";
    } else if (response.reconnecting) {
      statusEl.textContent = "Reconnecting...";
      statusEl.className = "status status-reconnecting";
    } else {
      statusEl.textContent = "Disconnected";
      statusEl.className = "status status-disconnected";
    }
  });
}

updateStatus();
setInterval(updateStatus, 3000);
