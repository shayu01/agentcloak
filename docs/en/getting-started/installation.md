# Installation

This guide covers installing agentcloak and its dependencies on all supported platforms.

## Requirements

- **Python 3.12+** (3.13 also supported)
- **pip** or **uv** package manager
- Linux (x64/arm64), macOS (x64/arm64), or Windows (x64)

## Base install

```bash
pip install agentcloak
```

Everything is included in one install:

- `agentcloak` and `cloak` CLI commands
- `agentcloak-mcp` MCP server (23 tools)
- CloakBrowser stealth browser backend (default)
- httpcloak TLS fingerprint proxy for `cloak fetch`
- The background daemon (FastAPI + uvicorn, OpenAPI at `http://127.0.0.1:18765/openapi.json`)

CloakBrowser downloads its patched Chromium binary automatically on first use (~200 MB, cached at `~/.cloakbrowser/`). No manual browser install step is needed.

## Optional extras

| Extra | What it adds | When you need it |
|-------|-------------|-----------------|
| `discovery` | [zeroconf](https://github.com/python-zeroconf/python-zeroconf) mDNS | Auto-discovering daemon from remote bridge |

```bash
pip install agentcloak[discovery]
```

## Verify the installation

Run the built-in diagnostics:

```bash
cloak doctor
```

This checks:

- Python version
- CloakBrowser availability and binary status
- Daemon connectivity
- Configuration

Expected output for a fresh install:

```json
{"ok": true, "data": {"checks": [
  {"name": "python_version", "ok": true, "value": "3.12.x"},
  {"name": "cloakbrowser", "ok": true, "hint": "CloakBrowser available -- default backend"},
  {"name": "default_tier", "value": "auto -> cloak"}
]}}
```

## System dependencies

### Xvfb (Linux servers only)

CloakBrowser runs in headed mode because anti-bot systems detect headless browsers. On Linux servers without a display, agentcloak automatically starts Xvfb (a virtual framebuffer). Install it with:

```bash
# Debian / Ubuntu
sudo apt-get install -y xvfb

# RHEL / Fedora
sudo dnf install -y xorg-x11-server-Xvfb
```

On desktop Linux, macOS, and Windows, no extra system dependencies are needed.

### Playwright system libraries

CloakBrowser uses Playwright under the hood. If you see missing shared library errors, install Playwright's system dependencies:

```bash
python -m playwright install-deps chromium
```

## Installing with uv

If you prefer [uv](https://github.com/astral-sh/uv):

```bash
uv pip install agentcloak
```

Or run without installing:

```bash
uvx agentcloak doctor
```

## Installing for development

See [CONTRIBUTING.md](../../../CONTRIBUTING.md) for the full development setup.

```bash
git clone https://github.com/shayuc137/agentcloak.git
cd agentcloak
pip install -e ".[dev,mcp,stealth]"
```

## Configuration

After installing, agentcloak works with zero configuration. The daemon starts automatically on the first command.

To customize behavior, see the [configuration reference](../reference/config.md).

## Next steps

- [Quick start tutorial](./quickstart.md) -- learn the observe-act loop
- [Browser backends](../guides/backends.md) -- choose the right backend for your use case
- [MCP setup](../guides/mcp-setup.md) -- connect from MCP-native clients
