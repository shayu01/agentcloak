# Getting Started

## Installation

```bash
pip install agentcloak
```

This installs the `agentcloak` and `cloak` CLI commands plus the daemon.

### Browser Backend

agentcloak uses CloakBrowser (57 C++ patches for stealth) by default. The browser binary downloads on first run.

For humanize (realistic mouse/keyboard timing):
```bash
pip install agentcloak[stealth]
```

### Verify Setup

```bash
cloak doctor
```

Checks: Python version, dependencies, browser binary, Xvfb (Linux headed mode).

## How It Works

```
You (CLI) ──HTTP──> Daemon (auto-starts) ──Playwright──> Browser
```

The daemon starts automatically on your first command. It manages browser instances, tracks state, and exposes all operations via HTTP API.

## Configuration

Config file: `~/.agentcloak/config.toml`. Precedence: env vars > config.toml > defaults.

```toml
[daemon]
host = "127.0.0.1"        # daemon bind address
port = 18765               # daemon port (auto-increments if busy)

[browser]
default_tier = "auto"      # "auto" (CloakBrowser) | "cloak" | "playwright"
default_profile = ""       # auto-launch this profile
viewport_width = 1280
viewport_height = 720
navigation_timeout = 30    # seconds
action_timeout = 30000     # ms, per-action timeout
batch_settle_timeout = 5000 # ms, settle between batch actions
humanize = false           # human-like mouse/keyboard timing
idle_timeout_min = 0       # auto-shutdown after idle (0 = disabled)
stop_on_exit = false       # stop daemon when CLI exits
log_level = "warning"      # debug | info | warning | error

[security]
domain_whitelist = []       # glob patterns, e.g. ["*.github.com", "example.com"]
domain_blacklist = []       # blocked domains
content_scan = false        # scan page content against patterns
content_scan_patterns = []  # regex patterns for content scanning
```

### Environment Variables

All settings can be overridden with `AGENTCLOAK_` prefix:

| Variable | Example |
|----------|---------|
| `AGENTCLOAK_HOST` | `0.0.0.0` |
| `AGENTCLOAK_PORT` | `9000` |
| `AGENTCLOAK_DEFAULT_TIER` | `playwright` |
| `AGENTCLOAK_DEFAULT_PROFILE` | `my-session` |
| `AGENTCLOAK_VIEWPORT_WIDTH` | `1920` |
| `AGENTCLOAK_VIEWPORT_HEIGHT` | `1080` |
| `AGENTCLOAK_NAVIGATION_TIMEOUT` | `60` |
| `AGENTCLOAK_ACTION_TIMEOUT` | `60000` |
| `AGENTCLOAK_BATCH_SETTLE_TIMEOUT` | `1000` |
| `AGENTCLOAK_HUMANIZE` | `true` |
| `AGENTCLOAK_IDLE_TIMEOUT_MIN` | `30` |
| `AGENTCLOAK_STOP_ON_EXIT` | `true` |
| `AGENTCLOAK_LOG_LEVEL` | `debug` |
| `AGENTCLOAK_DOMAIN_WHITELIST` | `*.github.com,example.com` |
| `AGENTCLOAK_DOMAIN_BLACKLIST` | `evil.com` |
| `AGENTCLOAK_CONTENT_SCAN` | `true` |
| `AGENTCLOAK_CONTENT_SCAN_PATTERNS` | `password=.*,ssn:\d+` |

## Daemon Management

The daemon auto-starts and auto-stops. Manual control:

| Command | Purpose |
|---------|---------|
| `cloak daemon start -b` | Start daemon in background |
| `cloak daemon stop` | Stop daemon |
| `cloak daemon health` | Check daemon status |

Default port: 18765. The daemon auto-increments if the port is busy (18765 → 18766 → ...).

## Chrome Extension (RemoteBridge)

To operate your real Chrome browser on another machine, install the extension:

```bash
cloak bridge extension-path
# Copy the output directory to your Chrome machine
# Chrome → chrome://extensions → Developer mode → Load unpacked
```

See `references/remote-bridge.md` for the full RemoteBridge guide.

## MCP Mode

agentcloak also works as an MCP server for non-CLI clients:

```bash
agentcloak-mcp
```

The CLI + Skill mode is recommended for Claude Code (300 tokens context vs 6000 for MCP).
