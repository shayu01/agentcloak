# Changelog

## 0.1.0 (2026-05-12)

Initial release.

### CLI

- 45 commands across navigation, interaction, content, capture, profile, tab, adapter, and daemon management
- JSON output envelope with `ok`/`seq`/`data` on success, `error`/`hint`/`action` on failure
- Batch action execution via `--calls-file` with auto-abort on navigation
- Top-level shortcuts: `bctl open`, `bctl snapshot`, `bctl click`, etc.
- `bctl doctor` diagnostics self-check

### MCP Server

- 18 tools covering navigation, interaction, content, network, capture, and management
- Auto-start daemon on first MCP request
- `pip install browserctl[mcp]` optional dependency

### Browser Backends

- **PatchrightContext** — default backend, Playwright API, mid-stealth
- **CloakContext** — CloakBrowser high-stealth with Xvfb + humanize behavioral layer
- **RemoteBridgeContext** — Chrome extension + WebSocket bridge for remote browser control

### Core Features

- Daemon architecture with auto-start, PID management, health checks
- Accessibility-tree snapshots with `[N]` element refs (accessible/compact/content/dom modes)
- Monotonic seq counter for state tracking
- Profile persistence (create/list/launch/delete)
- Multi-tab management (list/new/close/switch)
- Network capture with HAR 1.2 export, pattern analysis, adapter generation
- Site adapter framework (Strategy enum, pipeline DSL, function mode)
- HTTP fetch with browser cookie forwarding
- Cloudflare Turnstile bypass (screenX patch extension)
- IDPI security model (domain whitelist/blacklist, content scanning)
- mDNS auto-discovery (optional zeroconf)
- Resume snapshot for session recovery
