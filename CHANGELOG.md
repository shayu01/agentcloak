# Changelog

## 0.2.0 (2026-05-16)

Major architecture upgrade: RemoteBridge production-ready, CLI output redesign, dynamic tier switching.

### Highlights

- **Text-first CLI output** — stdout is the answer itself, no `jq` needed. `--json` flag for backward compat.
- **Dynamic tier switching** — `cloak launch --tier remote_bridge` hot-switches to user's Chrome without restarting daemon.
- **RemoteBridge fully functional** — evaluate, snapshot, tabs, capture all work through Chrome Extension.
- **`cloak skill install`** — one-command skill installation with platform auto-detection.
- **Bridge token persistence** — configure once, reconnects across daemon restarts.

### CLI

- Text-first output: 5 output primitives (success/value/info/error/json_out), errors to stderr
- `--snap` combo flag on all actions (action + observe in one step)
- `--limit` replaces `--max-nodes`, default snapshot mode is `compact`
- `cloak skill install/update/uninstall` — manage skill files across agent platforms
- `cloak launch --tier X` — hot-switch browser context (cloak/playwright/remote_bridge)
- `cloak bridge token [--reset]` — view or rotate persistent bridge auth token
- 20 CLI command groups, 41 daemon routes

### RemoteBridge (Chrome Extension) — experimental

> Remote Bridge is experimental. Core functionality works but has limited real-world testing. Report issues on GitHub.

- evaluate rewritten with CDP `Runtime.evaluate` (async support, no CSP issues)
- `activeTabId` state — navigate creates new tab instead of hijacking user's active tab
- Tab group lifecycle: blue "agentcloak" (active), green "handing off..." (handoff), auto-ungroup on disconnect
- CDP Network capture (capture start/stop/export works in RemoteBridge mode)
- CDP event forwarding (dialog detection, navigation feedback)
- Extension renamed to `agentcloak-chrome-extension/` for clarity
- Badge states: green ON / yellow wait / red ERR / grey OFF
- Options page: actionable error hints + Test Connection button

### Daemon

- FastAPI Accept negotiation: `text/plain` (CLI) vs `application/json` (MCP)
- `POST /launch` endpoint for context hot-switch
- `POST /bridge/token/reset` for hot token rotation
- ContextManager handles browser lifecycle + idle timer
- `config.example.toml` auto-generated on startup
- MCP responses: `exclude_none` for token savings

### Security

- CSP strip rules now per-tab only (was global)
- Token comparison via `secrets.compare_digest` (constant-time)
- `/ext` mutual exclusion (replace-on-reconnect for MV3 service worker restarts)

### Breaking Changes

- CLI default output is now **plain text** (was JSON). Use `--json` or `AGENTCLOAK_OUTPUT=json` for old behavior.
- Snapshot default mode is now `compact` (was `accessible`).
- `--include-snapshot` renamed to `--snap`.
- `--max-nodes` renamed to `--limit` (old name still accepted as alias).
- Extension directory renamed from `extension/` to `agentcloak-chrome-extension/`.

---

## 0.1.0 (2026-05-12)

Initial release.

### CLI

- 45 commands across navigation, interaction, content, capture, profile, tab, adapter, and daemon management
- JSON output envelope with `ok`/`seq`/`data` on success, `error`/`hint`/`action` on failure
- Batch action execution via `--calls-file` with auto-abort on navigation
- Top-level shortcuts: `cloak open`, `cloak snapshot`, `cloak click`, etc.
- `cloak doctor` diagnostics self-check

### MCP Server

- 18 tools covering navigation, interaction, content, network, capture, and management
- Auto-start daemon on first MCP request
- `pip install agentcloak[mcp]` optional dependency

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
