# 安装指南

本指南涵盖在所有支持平台上安装 agentcloak 及其依赖。

## 系统要求

- **Python 3.12+**（同时支持 3.13）
- **pip** 或 **uv** 包管理器
- Linux（x64/arm64）、macOS（x64/arm64）或 Windows（x64）

## 基础安装

```bash
pip install agentcloak
```

接着一步验证并修复环境：

```bash
agentcloak doctor --fix
```

`doctor --fix` 会在进程内完成它自己能做的事（下载 CloakBrowser 二进制文件、创建数据目录），并为需要系统级权限的操作（Linux 服务器的 Xvfb、Playwright 系统库）输出一条整合好的 shell 命令。加上 `--sudo` 则会直接执行那条命令。

一条 `pip install` 包含所有组件：

- `agentcloak` 和 `cloak` CLI 命令
- `agentcloak-mcp` MCP server（23 个工具）
- CloakBrowser 隐身浏览器后端（默认）
- httpcloak TLS 指纹代理（用于 `cloak fetch`）
- 后台 daemon（FastAPI + uvicorn，OpenAPI 规范在 `http://127.0.0.1:18765/openapi.json`）

CloakBrowser 在首次使用时自动下载补丁版 Chromium 二进制文件（约 200 MB，缓存在 `~/.cloakbrowser/`）。提前运行 `doctor --fix` 可以避免下载发生在你第一次 navigate 时。

## 安装 Skill 安装包

`pip install agentcloak` 装好的是 CLI 和 MCP server。如果你的 AI agent 支持 **Skills**，还需要额外安装 Skill 安装包（`SKILL.md` + `references/` 目录），这样 agent 在需要时才按需加载 `cloak` 知识（约 300 tokens，比 MCP 工具定义的 6,000 tokens 节省 20 倍）。

> **推荐：只装 Skill + CLI。** MCP server 是给没有 bash 能力的 agent 准备的可选方案。如果两个都装，MCP 工具定义会在每次对话中消耗约 6,000 tokens（即使没用到）。二选一即可：
> - **Skill + CLI**（推荐）：agent 按需加载 skill，通过 bash 调用 `cloak` 命令
> - **仅 MCP**：适用于没有 bash 能力的 agent（如纯聊天界面）

### 各平台 Skill 目录

每个 agent 平台从各自的目录读取 Skill：

| Agent 平台 | 项目级 | 用户全局 |
|---|---|---|
| Claude Code | `.claude/skills/agentcloak/` | `~/.claude/skills/agentcloak/` |
| Codex | `.codex/skills/agentcloak/` | `~/.codex/skills/agentcloak/` |
| Cursor | `.cursor/skills/agentcloak/` | （无 — 仅项目级） |
| OpenCode | `.opencode/skills/agentcloak/` | （无 — 仅项目级） |
| 其他 | 查阅对应 agent 文档 | 查阅对应 agent 文档 |

项目级只在该仓库内生效；用户全局对所有项目生效。按需选择。

### 使用 curl + tar 安装（Linux / macOS / WSL）

Skill 安装包位于仓库的 [`skills/agentcloak/`](https://github.com/shayuc137/agentcloak/tree/main/skills/agentcloak)。下面的命令从 GitHub tarball 中只抽取该目录：

```bash
# 从上表中选择目标目录。示例：项目级 Claude Code。
DEST=".claude/skills"

mkdir -p "$DEST"
curl -L https://github.com/shayuc137/agentcloak/archive/refs/heads/main.tar.gz \
  | tar -xz --strip-components=2 -C "$DEST" \
    agentcloak-main/skills/agentcloak
```

执行后 `$DEST/agentcloak/SKILL.md` 和 `$DEST/agentcloak/references/` 都应该存在。

### 使用 PowerShell 安装（Windows）

```powershell
# 项目级 Claude Code 示例。请按上表调整 $Dest。
$Dest = ".claude\skills"
New-Item -ItemType Directory -Force -Path $Dest | Out-Null

$tmp = New-TemporaryFile
Invoke-WebRequest "https://github.com/shayuc137/agentcloak/archive/refs/heads/main.tar.gz" -OutFile "$tmp.tgz"
tar -xz -C $Dest --strip-components=2 -f "$tmp.tgz" agentcloak-main/skills/agentcloak
Remove-Item "$tmp.tgz"
```

（Windows 10 1803+ 自带 `tar` 和 `curl.exe`。）

### 从 git clone 安装（开发者）

如果你已经 clone 了仓库，直接复制或软链接即可：

```bash
# 从仓库根目录
cp -r skills/agentcloak ~/.claude/skills/         # 全局安装
# 或
ln -s "$PWD/skills/agentcloak" ~/.claude/skills/  # 可实时编辑的软链接
```

### 更新 Skill

重新执行相同的 `curl | tar`（或 `cp -r`）命令。Skill 都是纯 markdown，没有迁移步骤。

## 可选扩展

| 扩展 | 功能 | 使用场景 |
|------|------|---------|
| `discovery` | [zeroconf](https://github.com/python-zeroconf/python-zeroconf) mDNS | 远程 bridge 自动发现 daemon |

```bash
pip install agentcloak[discovery]
```

## 免安装运行 — uv / uvx

[uv](https://github.com/astral-sh/uv) 是一个极速包管理器，可以在临时虚拟环境中运行 agentcloak：

```bash
# 一次性环境检查（不安装）
uvx agentcloak doctor --fix

# MCP server 同样适用 — 加到你的 MCP 客户端配置：
{
  "command": "uvx",
  "args": ["agentcloak-mcp"]
}
```

或永久通过 uv 安装：

```bash
uv pip install agentcloak
```

## 验证安装

```bash
agentcloak doctor
```

检查内容：

- Python 版本（3.12+）
- PATH（确认 `agentcloak` / `cloak` 命令可调用）
- 必需依赖包（typer、fastapi、cloakbrowser、playwright、httpcloak、mcp 等）
- CloakBrowser 二进制文件状态
- Playwright 系统库（仅 Linux）
- 数据目录
- Xvfb（仅在需要时检查 —— 无显示器的 Linux 且 `headless=false`）
- Daemon 连通性

健康安装会输出 `"healthy": true`。如果有缺失，下一步运行 `agentcloak doctor --fix`。

## 平台专属说明

### Linux 服务器（无显示器）

v0.2.0 默认 `headless = true`，所以无头模式开箱即用，不需要系统依赖。如果你切换到有头模式（部分网站的反爬效果更好），且机器没有显示器，agentcloak 会自动启动 Xvfb，doctor 会提示你安装它：

| 发行版 | 安装命令 |
|--------|---------|
| Debian / Ubuntu / Mint | `sudo apt-get install -y xvfb` |
| Fedora / RHEL / CentOS / Rocky / AlmaLinux | `sudo dnf install -y xorg-x11-server-Xvfb` |
| Arch / Manjaro | `sudo pacman -S xorg-server-xvfb` |
| Alpine | `sudo apk add xvfb` |
| openSUSE | `sudo zypper install -y xorg-x11-server` |

如果你完全不想用 Xvfb，把 `~/.agentcloak/config.toml` 里的 `headless = true` 保持不动（或设置 `AGENTCLOAK_HEADLESS=true`）。doctor 只在有头模式配置下才会提示 Xvfb。

Playwright/Chromium 运行时库（`libnss3`、`libgbm`、`libasound` 等）在桌面 Linux 通常已经存在。最小化的服务器镜像可能需要：

```bash
sudo playwright install-deps chromium
```

`agentcloak doctor --fix --sudo` 会用一条针对你发行版的命令一次性搞定 Xvfb 和 Playwright 系统库。

### macOS

- **无需 Xvfb** —— macOS 始终有显示器。
- **Gatekeeper 首次启动可能拦截** —— macOS 可能给下载的 Chromium 加上隔离属性。如果看到 "cannot be opened because the developer cannot be verified"，清除属性：

  ```bash
  xattr -d com.apple.quarantine ~/.cloakbrowser/chromium-*/chrome
  ```

- **推荐使用 Homebrew Python**（`brew install python@3.12`）。系统自带的 `/usr/bin/python3` 也能用，但 Homebrew 版的 pip 体验更好。

### Windows

- **无需 Xvfb** —— Windows 始终有显示器。
- **`pip install --user` 后的 PATH 问题** —— 用 `pip install --user agentcloak` 安装时，入口脚本会放在 `%APPDATA%\Python\Python312\Scripts`（根据你的 Python 版本调整）。如果运行 `agentcloak` 提示找不到命令，将该目录加到 `PATH`：
  1. 打开 *系统属性 → 环境变量*
  2. 编辑用户的 `Path`
  3. 添加 `%APPDATA%\Python\Python312\Scripts`
  4. 重新启动终端使配置生效

  或者即使 PATH 没配好，也可以通过 Python 模块方式确认安装：

  ```cmd
  py -m agentcloak.cli.app doctor
  ```

- **WSL2** 用户获得的是 Linux 体验 —— 如果想用有头模式，在 WSL 发行版里安装 Xvfb。

## 系统依赖（仅 Linux）

### Playwright 系统库

CloakBrowser 底层使用 Playwright。如果看到关于缺失共享库（`libnss3.so`、`libgbm.so` 等）的错误，让 Playwright 安装它们：

```bash
sudo playwright install-deps chromium
```

`agentcloak doctor` 会探测四个最常见的库，并告诉你应该运行哪条命令。

### Xvfb（服务器上的有头模式）

仅在以下情况相关：

1. 你在 Linux 上，没有 `$DISPLAY` 或 `$WAYLAND_DISPLAY`，**且**
2. 你设置了 `headless = false`（或 `AGENTCLOAK_HEADLESS=false`）

这种组合下 agentcloak 会自动启动 Xvfb。doctor 和上面的安装表覆盖了每个发行版的安装命令。

## 开发环境安装

完整的开发环境配置参见 [CONTRIBUTING.md](../../../CONTRIBUTING.md)。

```bash
git clone https://github.com/shayuc137/agentcloak.git
cd agentcloak
pip install -e ".[dev,mcp,stealth]"
```

## 配置

安装后 agentcloak 无需任何配置即可使用。daemon 在首次命令时自动启动。

如需自定义行为，参见[配置参考](../reference/config.md)。

## 首次运行问题排查

| 现象 | 修复方式 |
|------|---------|
| `command not found: agentcloak` | PATH 未配置（Windows：添加 `%APPDATA%\Python\Python3X\Scripts`；*nix：`pip install` 把它放到 `~/.local/bin`）。或者运行 `py -m agentcloak.cli.app doctor` / `python -m agentcloak.cli.app doctor`。 |
| `cloakbrowser_binary: not downloaded` | `agentcloak doctor --fix` |
| Linux 服务器上 `xvfb: not found` | 要么在 `~/.agentcloak/config.toml` 设置 `headless = true`，要么运行 `agentcloak doctor --fix --sudo` |
| `playwright_libs: missing: ...` | `sudo playwright install-deps chromium`（或 `agentcloak doctor --fix --sudo`） |
| 安装后 `daemon_unreachable` | `agentcloak doctor --fix` 会告诉你哪里坏了；如果没问题，运行 `agentcloak daemon start -b` 手动启动并查看 `~/.agentcloak/logs/daemon.log` 日志 |
| macOS Gatekeeper 拦截 Chromium | `xattr -d com.apple.quarantine ~/.cloakbrowser/chromium-*/chrome` |

## 后续步骤

- [快速开始教程](./quickstart.md) -- 学习观察-操作循环
- [浏览器后端](../guides/backends.md) -- 根据场景选择合适的后端
- [MCP 配置](../guides/mcp-setup.md) -- 从 MCP 原生客户端连接
