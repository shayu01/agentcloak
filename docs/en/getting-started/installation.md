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

Then verify and fix the environment in one step:

```bash
agentcloak doctor --fix
```

`doctor --fix` does the in-process work itself (downloads the CloakBrowser binary, creates the data dir) and prints a single shell command for anything that needs system-level intervention (Xvfb on Linux servers, Playwright libs). Pass `--sudo` if you want it to run that command for you.

Everything is included in the one `pip install`:

- `agentcloak` and `cloak` CLI commands
- `agentcloak-mcp` MCP server (23 tools)
- CloakBrowser stealth browser backend (default)
- httpcloak TLS fingerprint proxy for `cloak fetch`
- The background daemon (FastAPI + uvicorn, OpenAPI at `http://127.0.0.1:18765/openapi.json`)

CloakBrowser downloads its patched Chromium binary automatically on first use (~200 MB, cached at `~/.cloakbrowser/`). Running `doctor --fix` upfront avoids that wait happening during your first navigate.

## Install the Skill bundle

`pip install agentcloak` gives you the CLI and the MCP server. If your AI agent supports **Skills**, install the Skill bundle (`SKILL.md` + the `references/` directory) so the agent can lazy-load `cloak` knowledge on demand (~300 tokens, vs ~6,000 for MCP tool definitions).

> **Recommended: install Skill + CLI only.** The MCP server is an optional alternative for agents that don't have bash access. If you install both, the MCP tool definitions consume ~6,000 tokens in every conversation even when unused. Pick one:
> - **Skill + CLI** (recommended): agent loads skill on demand, calls `cloak` via bash
> - **MCP only**: for agents without bash capability (e.g., some chat-only interfaces)

### Where to put it

Each agent platform reads skills from its own directory:

| Agent platform | Project-scoped | User-global |
|---|---|---|
| Claude Code | `.claude/skills/agentcloak/` | `~/.claude/skills/agentcloak/` |
| Codex | `.codex/skills/agentcloak/` | `~/.codex/skills/agentcloak/` |
| Cursor | `.cursor/skills/agentcloak/` | (n/a — project-scoped) |
| OpenCode | `.opencode/skills/agentcloak/` | (n/a — project-scoped) |
| Other | Consult your agent's docs | Consult your agent's docs |

Project-scoped installs only apply to that repo; user-global installs apply everywhere. Pick whichever fits your workflow.

### Install with curl + tar (Linux / macOS / WSL)

The Skill bundle lives at [`skills/agentcloak/`](https://github.com/shayuc137/agentcloak/tree/main/skills/agentcloak) in the repo. The snippet below pulls just that directory out of the GitHub tarball:

```bash
# Pick your destination from the table above. Example: project-scoped Claude Code.
DEST=".claude/skills"

mkdir -p "$DEST"
curl -L https://github.com/shayuc137/agentcloak/archive/refs/heads/main.tar.gz \
  | tar -xz --strip-components=2 -C "$DEST" \
    agentcloak-main/skills/agentcloak
```

After the command, `$DEST/agentcloak/SKILL.md` and `$DEST/agentcloak/references/` should exist.

### Install with PowerShell (Windows)

```powershell
# Project-scoped Claude Code example. Adjust $Dest per the table above.
$Dest = ".claude\skills"
New-Item -ItemType Directory -Force -Path $Dest | Out-Null

$tmp = New-TemporaryFile
Invoke-WebRequest "https://github.com/shayuc137/agentcloak/archive/refs/heads/main.tar.gz" -OutFile "$tmp.tgz"
tar -xz -C $Dest --strip-components=2 -f "$tmp.tgz" agentcloak-main/skills/agentcloak
Remove-Item "$tmp.tgz"
```

(Windows 10 1803+ ships `tar`/`curl.exe` out of the box.)

### Install from a git clone (developers)

If you already cloned the repo, just copy or symlink the directory:

```bash
# From the repo root
cp -r skills/agentcloak ~/.claude/skills/         # global install
# or
ln -s "$PWD/skills/agentcloak" ~/.claude/skills/  # live-edit symlink
```

### Updating the Skill

Re-run the same `curl | tar` (or `cp -r`) command. The Skill is plain markdown; there's no migration step.

## Optional extras

| Extra | What it adds | When you need it |
|-------|-------------|-----------------|
| `discovery` | [zeroconf](https://github.com/python-zeroconf/python-zeroconf) mDNS | Auto-discovering daemon from remote bridge |

```bash
pip install agentcloak[discovery]
```

## Run without installing — uv / uvx

[uv](https://github.com/astral-sh/uv) is an ultra-fast package manager that can run agentcloak in a one-shot virtual environment:

```bash
# One-time environment check (no install)
uvx agentcloak doctor --fix

# Same for the MCP server — add this to your MCP client config:
{
  "command": "uvx",
  "args": ["agentcloak-mcp"]
}
```

Or install permanently via uv:

```bash
uv pip install agentcloak
```

## Verify the installation

```bash
agentcloak doctor
```

This checks:

- Python version (3.12+)
- PATH (so the `agentcloak` / `cloak` commands are reachable)
- Required packages (typer, fastapi, cloakbrowser, playwright, httpcloak, mcp, ...)
- CloakBrowser binary status
- Playwright system libraries (Linux only)
- Data directory
- Xvfb (only when needed — Linux without a display and `headless=false`)
- Daemon liveness

A healthy install prints `"healthy": true`. If something's missing, `agentcloak doctor --fix` is the next step.

## Platform-specific notes

### Linux server (no display)

The default headless flag in v0.2.0 is `true`, so headless mode "just works" with no system dependencies. If you opt into headed mode (better stealth on some sites) on a server without a display, agentcloak auto-starts Xvfb and the doctor will tell you to install it:

| Distro | Install |
|--------|---------|
| Debian / Ubuntu / Mint | `sudo apt-get install -y xvfb` |
| Fedora / RHEL / CentOS / Rocky / AlmaLinux | `sudo dnf install -y xorg-x11-server-Xvfb` |
| Arch / Manjaro | `sudo pacman -S xorg-server-xvfb` |
| Alpine | `sudo apk add xvfb` |
| openSUSE | `sudo zypper install -y xorg-x11-server` |

If you don't want Xvfb at all, keep `headless = true` in `~/.agentcloak/config.toml` (or set `AGENTCLOAK_HEADLESS=true`). The doctor only nags about Xvfb when headed mode is configured.

Playwright/Chromium runtime libs (`libnss3`, `libgbm`, `libasound`, ...) are usually already present on a desktop install. On minimal server images you may need:

```bash
sudo playwright install-deps chromium
```

`agentcloak doctor --fix --sudo` handles both Xvfb and Playwright libs in a single command tailored to your distro.

### macOS

- **No Xvfb needed** — macOS always has a display.
- **Gatekeeper warning on first run** — macOS may quarantine the downloaded Chromium binary the first time you launch it. If you see "cannot be opened because the developer cannot be verified", clear the attribute:

  ```bash
  xattr -d com.apple.quarantine ~/.cloakbrowser/chromium-*/chrome
  ```

- **Use Homebrew Python** for the smoothest experience (`brew install python@3.12`). The bundled `/usr/bin/python3` works too but the Homebrew version has a friendlier pip story.

### Windows

- **No Xvfb needed** — Windows always has a display.
- **PATH after `pip install --user`** — when you install with `pip install --user agentcloak`, the entry-point scripts land in `%APPDATA%\Python\Python312\Scripts` (adjust for your Python version). Add that directory to `PATH` if running `agentcloak` complains it's not found:
  1. Open *System Properties → Environment Variables*
  2. Edit `Path` for your user
  3. Add `%APPDATA%\Python\Python312\Scripts`
  4. Restart your shell so the change takes effect

  Or run the doctor through Python to confirm it's installed even if PATH is broken:

  ```cmd
  py -m agentcloak.cli.app doctor
  ```

- **WSL2** users get the Linux experience — install Xvfb in the WSL distro if you want headed mode.

## System dependencies (Linux only)

### Playwright system libraries

CloakBrowser uses Playwright under the hood. If you see errors about missing shared libraries (`libnss3.so`, `libgbm.so`, ...), let Playwright install them:

```bash
sudo playwright install-deps chromium
```

`agentcloak doctor` probes for the four most common libs and tells you exactly which command to run.

### Xvfb (headed mode on a server)

Only relevant when:

1. You're on Linux without `$DISPLAY` or `$WAYLAND_DISPLAY`, **and**
2. You've set `headless = false` (or `AGENTCLOAK_HEADLESS=false`)

In that combo agentcloak auto-starts Xvfb. The doctor and the install table above cover the per-distro install commands.

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

## Troubleshooting first-run issues

| Symptom | Fix |
|---------|-----|
| `command not found: agentcloak` | PATH not configured (Windows: add `%APPDATA%\Python\Python3X\Scripts`; *nix: `pip install` puts it in `~/.local/bin`). Or run `py -m agentcloak.cli.app doctor` / `python -m agentcloak.cli.app doctor`. |
| `cloakbrowser_binary: not downloaded` | `agentcloak doctor --fix` |
| `xvfb: not found` on a Linux server | Either set `headless = true` in `~/.agentcloak/config.toml`, or `agentcloak doctor --fix --sudo` |
| `playwright_libs: missing: ...` | `sudo playwright install-deps chromium` (or `agentcloak doctor --fix --sudo`) |
| `daemon_unreachable` after install | `agentcloak doctor --fix` will tell you what broke; if nothing, `agentcloak daemon start -b` to launch manually and watch the logs at `~/.agentcloak/logs/daemon.log` |
| Gatekeeper blocks Chromium (macOS) | `xattr -d com.apple.quarantine ~/.cloakbrowser/chromium-*/chrome` |

## Next steps

- [Quick start tutorial](./quickstart.md) -- learn the observe-act loop
- [Browser backends](../guides/backends.md) -- choose the right backend for your use case
- [MCP setup](../guides/mcp-setup.md) -- connect from MCP-native clients
