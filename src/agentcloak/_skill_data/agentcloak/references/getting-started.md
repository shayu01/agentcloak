# Getting Started

## Installation

```bash
pip install agentcloak
agentcloak doctor --fix    # verify and fix the environment in one step
```

One install gets you: CLI (`agentcloak` and `cloak`), MCP server (`agentcloak-mcp`), CloakBrowser stealth backend, httpcloak TLS fingerprint proxy.

`doctor --fix` runs the in-process repairs it can (downloads the ~200 MB CloakBrowser binary, creates the data dir) and prints a one-liner shell command for anything that needs system-level intervention. Adding `--sudo` runs that command for you when sudo / root is available.

### Detect the host OS before suggesting commands

When an agent needs to give the user a platform-specific instruction:

```bash
python -c "import platform; print(platform.system())"   # Linux | Darwin | Windows
```

Or just run the doctor — it already produces tailored hints:

```bash
agentcloak doctor          # read-only — emits per-distro Xvfb suggestion, etc.
```

### Run without installing — uv / uvx

```bash
uvx agentcloak doctor --fix             # one-shot env check
uvx agentcloak browser navigate https://example.com   # one-shot navigate
```

For MCP, point your client config at `uvx`:

```json
{ "command": "uvx", "args": ["agentcloak-mcp"] }
```

### System Dependencies (headless Linux only)

CloakBrowser runs in headless mode by default in v0.2.0 — no system dependencies needed. If you switch to headed mode on a server without a display (`headless=false`), Xvfb is auto-started. The doctor prints the right install command per distro:

| Distro | Install |
|--------|---------|
| Debian / Ubuntu | `sudo apt-get install -y xvfb` |
| Fedora / RHEL | `sudo dnf install -y xorg-x11-server-Xvfb` |
| Arch | `sudo pacman -S xorg-server-xvfb` |
| Alpine | `sudo apk add xvfb` |

Desktop Linux, macOS, and Windows need no extra dependencies.

### Verify Setup

```bash
cloak doctor             # read-only diagnosis
cloak doctor --fix       # diagnose + auto-fix (prints sudo command)
cloak doctor --fix --sudo  # diagnose + auto-fix + execute system command
```

Checks: Python version, PATH, required packages, CloakBrowser binary, Playwright system libs (Linux), Xvfb (when relevant), data directory, daemon connectivity.

## How It Works

```
You (CLI) ──HTTP──> Daemon (auto-starts) ──Playwright──> Browser
```

The daemon starts automatically on your first command. It manages browser instances, tracks state, and exposes all operations via HTTP API.

If the daemon fails to start, the agent doesn't get a useful error directly — run `agentcloak doctor --fix` to find out *why*. The doctor works even when the daemon is down (it runs the checks in-process), so it's the right first step for any "daemon_unreachable" / "daemon_auto_start_failed" error.

## Configuration

Config file: `~/.agentcloak/config.toml`. Precedence: env vars > config.toml > defaults.

```toml
[daemon]
host = "127.0.0.1"        # daemon bind address
port = 18765               # daemon port (auto-increments if busy)
http_client_timeout = 120  # CLI/MCP → daemon request timeout (seconds)
auto_start_timeout = 15.0  # how long auto-start waits for /health
auto_start_poll_interval = 0.5

[browser]
default_tier = "auto"      # "auto" (CloakBrowser) | "cloak" | "playwright"
default_profile = ""       # auto-launch this profile
viewport_width = 1280
viewport_height = 720
navigation_timeout = 30    # seconds
action_timeout = 30000     # ms, per-action timeout
batch_settle_timeout = 5000 # ms, settle between batch actions
humanize = false           # human-like mouse/keyboard timing
headless = true            # headless mode (v0.2.0 default); set false for max stealth
idle_timeout_min = 0       # auto-shutdown after idle (0 = disabled)
stop_on_exit = false       # stop daemon when CLI exits
log_level = "warning"      # debug | info | warning | error
log_to_file = false        # write daemon log to ~/.agentcloak/logs/daemon.log
log_max_bytes = 10000000   # rotate when log exceeds this size (10 MB)
log_backup_count = 3       # keep N rotated logs
max_return_size = 50000    # /evaluate response cap (bytes)
screenshot_quality = 80    # CLI JPEG quality
mcp_screenshot_quality = 50 # MCP JPEG quality (smaller base64)

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
| `AGENTCLOAK_HEADLESS` | `false` |
| `AGENTCLOAK_IDLE_TIMEOUT_MIN` | `30` |
| `AGENTCLOAK_STOP_ON_EXIT` | `true` |
| `AGENTCLOAK_LOG_LEVEL` | `debug` |
| `AGENTCLOAK_LOG_TO_FILE` | `true` |
| `AGENTCLOAK_HTTP_CLIENT_TIMEOUT` | `180` |
| `AGENTCLOAK_AUTO_START_TIMEOUT` | `30` |
| `AGENTCLOAK_MAX_RETURN_SIZE` | `100000` |
| `AGENTCLOAK_SCREENSHOT_QUALITY` | `90` |
| `AGENTCLOAK_MCP_SCREENSHOT_QUALITY` | `40` |
| `AGENTCLOAK_DOMAIN_WHITELIST` | `*.github.com,example.com` |
| `AGENTCLOAK_DOMAIN_BLACKLIST` | `evil.com` |
| `AGENTCLOAK_CONTENT_SCAN` | `true` |
| `AGENTCLOAK_CONTENT_SCAN_PATTERNS` | `password=.*,ssn:\d+` |
| `AGENTCLOAK_SKIP_FIRST_RUN_BANNER` | `1` (silence the first-run nudge) |

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

For Claude Code, add it with:

```bash
claude mcp add agentcloak -- agentcloak-mcp
```

The CLI + Skill mode is recommended for Claude Code (~300 tokens context vs ~6,000 for MCP).

## Troubleshooting

If something doesn't work, your first move is almost always:

```bash
agentcloak doctor --fix
```

The doctor knows about per-distro Xvfb packages, Playwright system libs, the CloakBrowser binary, PATH issues, and the daemon's liveness. It works in-process so it doesn't need the daemon to be running.

Common error → action map:

| Error from a tool/CLI | First step |
|----------------------|-----------|
| `daemon_unreachable` | `agentcloak doctor --fix` to find out why the daemon won't come up |
| `daemon_auto_start_failed` | Same — doctor in-process diagnosis tells you what's missing |
| `stealth_not_installed` | The cloakbrowser pip dep didn't install correctly — `pip install agentcloak --upgrade` |
| `xvfb_not_found` | Either install Xvfb (doctor prints the per-distro command) or set `headless = true` |
| `daemon_timeout` | The daemon is up but slow — increase `AGENTCLOAK_HTTP_CLIENT_TIMEOUT` |
