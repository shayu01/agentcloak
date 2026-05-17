# RemoteBridge (Real Browser)

Operate your real Chrome browser on another machine via a Chrome extension + WebSocket connection.

## Setup

### 1. Install the Extension

```bash
cloak bridge extension-path
# outputs: /path/to/src/agentcloak/bridge/agentcloak-chrome-extension/
```

Copy that directory to your Chrome machine, then:
- Chrome → `chrome://extensions` → Enable Developer mode
- Click "Load unpacked" → select the extension directory
- The extension badge shows connection status (green = connected)

### 2. Start the Connection

**Direct mode** (extension connects to daemon directly):
```bash
cloak daemon start -b   # daemon on port 18765
# Extension auto-discovers daemon via port probing (18765-18774)
```

**Bridge mode** (for NAT/firewall traversal):
```bash
cloak bridge start -b   # bridge process relays between extension and daemon
```

## Usage

Once connected, all regular commands work on the real browser:

```bash
cloak snapshot           # sees the real page content
cloak click --target 5   # clicks in the real browser
cloak navigate "https://example.com"
```

### Tab Claiming

Take over a tab the user already has open:

```bash
cloak bridge claim --url "github.com"            # claim tab matching URL
cloak snapshot                                   # now sees that tab
```

### Tab Group

Agent-managed tabs are automatically grouped under a blue "agentcloak" Chrome tab group, keeping them visually separate from user tabs.

### Session Finalize

When done, clean up with one of three modes:

```bash
cloak bridge finalize --mode close       # close all agent tabs
cloak bridge finalize --mode handoff     # keep tabs open for user to continue
cloak bridge finalize --mode deliverable # mark tabs as results for user to review
```

## CDP Coordination with jshookmcp

agentcloak and jshookmcp can share the same browser via CDP:

```bash
# 1. Start browser with agentcloak
cloak navigate "https://target-site.com"

# 2. Get CDP endpoint
cloak cdp endpoint
# returns: {"ws_endpoint": "ws://127.0.0.1:18765/devtools/browser/..."}

# 3. In jshookmcp: browser_attach(wsEndpoint)
# Now: navigation/interaction via agentcloak, JS analysis via jshookmcp
```

## Cookie Export

Export cookies from the real browser for use in scripts:

```bash
cloak cookies export                    # export all cookies as JSON
cloak cookies export --url "github.com" # export for specific domain

# Import currently has no CLI wrapper — use the MCP tool agentcloak_cookies
# with action=import, or POST to daemon /cookies/import directly.
```
