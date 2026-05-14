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

Config file: `~/.config/agentcloak/config.toml` (auto-created on first run).

Key settings:
- `humanize = true` — enable human-like mouse/keyboard timing
- `action_timeout = 30000` — default action timeout (ms)
- `batch_settle_timeout = 500` — settle time between batch actions (ms)

Environment variable overrides: `AGENTCLOAK_HUMANIZE=1`, `AGENTCLOAK_ACTION_TIMEOUT=60000`.

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
