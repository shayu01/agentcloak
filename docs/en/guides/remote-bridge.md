# Remote Bridge

Remote Bridge lets an agentcloak daemon drive a real Chrome browser running on another machine — for example, a Linux server's agent operating your Windows desktop's Chrome with all its logins, extensions, and the genuine fingerprint built up over months of normal use. No headless detection, no cookie shuttling.

## Architecture

```
┌──────────────────┐   HTTP    ┌──────────────────┐    WS     ┌─────────────────────┐
│  cloak CLI / MCP │ ────────► │  daemon (Linux)  │ ◄──────►  │  Chrome extension   │
│                  │           │  18765 + /ext WS │           │  (Windows / macOS)  │
└──────────────────┘           └──────────────────┘           └─────────────────────┘
```

The Chrome extension speaks CDP (via `chrome.debugger`) and tunnels every command from the daemon over WebSocket. The daemon's `RemoteBridgeAdapter` translates Playwright-style requests into raw CDP and ships them through the tunnel.

For network setups where the extension can't reach the daemon directly (NAT, firewall, different subnet), an intermediate `bridge` process can be run as a relay.

## Setup

### 1. Install the extension

On the daemon machine:

```bash
cloak bridge extension-path
# /home/you/.local/lib/python3.13/site-packages/agentcloak/bridge/extension
```

Copy that directory to the machine where Chrome lives, then in Chrome:

1. Open `chrome://extensions`
2. Enable **Developer mode** (top-right toggle)
3. Click **Load unpacked** and pick the extension directory
4. The extension icon should appear in the toolbar with a red badge ("disconnected")

### 2. Connect the extension

Click the extension icon and fill in the daemon address. The extension probes ports `18765-18774` on the configured host and auto-connects to the first daemon that answers `/ext`. The badge turns green when connected.

For most home networks the simplest setup is:

- Linux daemon: `cloak daemon start -b --host 0.0.0.0` (bind on all interfaces so the LAN can reach it)
- Extension options: host = the Linux server IP, port = 18765

### 3. Use the bridge

Once the extension is green, all regular commands work — they just drive the real browser:

```bash
cloak navigate "https://example.com" --backend bridge
cloak snapshot                                   # sees the real page
cloak click --target 5                           # clicks in real Chrome
```

Make the bridge the default for the daemon:

```bash
export AGENTCLOAK_DEFAULT_TIER=remote_bridge
```

## Tab claiming

The bridge starts out with no managed tabs. Two ways to put a tab under agent control:

```bash
# new tab opened by the agent
cloak tab new --url "https://github.com"

# or hijack a tab the user already opened
cloak bridge claim --url-pattern "github.com"     # first tab whose URL contains "github.com"
cloak bridge claim --tab-id 1234                  # specific Chrome tab id
```

Claimed tabs are added to a blue Chrome tab group named **agentcloak** so the user can visually tell agent-controlled tabs apart from their own.

## Session finalize

When the agent is done, clean up with one of three modes:

```bash
cloak bridge finalize --mode close         # close every agent-managed tab
cloak bridge finalize --mode handoff       # ungroup tabs, leave them open
cloak bridge finalize --mode deliverable   # rename group to "agentcloak results" (green)
```

Pick the mode that matches your hand-off intent: `close` for fully autonomous runs, `handoff` for "continue manually here", `deliverable` to flag results the user should review.

## Bridge relay mode

For NAT or firewall scenarios where the extension can't reach the daemon, run a relay:

```bash
cloak bridge start -b --port 18770
```

Configure the extension to point at the relay address instead of the daemon. The relay forwards extension WebSocket traffic to the daemon's `/ext` endpoint.

## WebSocket authentication

The `/ext` and `/bridge/ws` endpoints accept a Bearer token (auto-generated per daemon, printed at startup, stored in the session file). The extension picks it up via the options UI.

- **Localhost connections** bypass auth (you already have local access)
- **Remote connections** must present `Authorization: Bearer <token>`

Rotate by restarting the daemon — a new token is generated each launch.

## mDNS auto-discovery (optional)

If you install the optional `zeroconf` extra (`pip install agentcloak[mdns]`), the daemon advertises itself on the local network as `_agentcloak._tcp.local`. The extension can list available daemons and pick one without manual IP entry.

The auth token is **never** broadcast over mDNS — clients still need to obtain it from the session file.

## Cookie export

Pull cookies from the real browser for use in scripts or to seed a profile:

```bash
cloak cookies export                   # all domains, JSON to stdout
cloak cookies export --url github.com  # just one domain
cloak cookies import < cookies.json    # load into the active context
```

This is the easiest way to graduate a manual login into a reusable profile — log in via your real Chrome, export, then import into a new agentcloak profile.

## Troubleshooting

```bash
cloak bridge doctor
```

This checks: extension reachable, WebSocket connected, daemon `/ext` endpoint live, last extension heartbeat timestamp.

| Symptom | First step |
|---------|-----------|
| Extension badge stays red | Confirm daemon `--host 0.0.0.0` and firewall allows the port |
| `bridge_disconnected` errors | Check `cloak bridge doctor`; reload the extension from `chrome://extensions` |
| Commands hang on `navigate` | Chrome may have a permission popup blocking — focus the Chrome window and dismiss it |
| Token mismatch on remote LAN | Re-read the token from `~/.agentcloak/session.json` and paste into extension options |
| Extension drops after Chrome restart | The extension uses `chrome.alarms` keepalive but Chrome sometimes suspends MV3 service workers — click the icon once to wake it |
