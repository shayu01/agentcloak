# browserctl

Browser automation toolkit for AI agents. Provides a CLI and MCP server that let AI agents see and interact with web pages -- navigate, read content via accessibility tree snapshots, click buttons, fill forms, take screenshots, and more. Supports anti-bot stealth and remote browser control.

[English](#features) | [中文](#功能特性)

---

## Features

- **CLI-first design** -- every command outputs one JSON object on stdout, with structured errors that include recovery hints, pipeable with `jq`
- **MCP server** -- 18 tools for AI clients with native tool discovery (Claude Code, Codex, Cursor, etc.)
- **Accessibility-tree snapshots** -- pages are represented as `[N]` indexed elements, so agents interact by index instead of fragile CSS selectors
- **Multi-backend stealth** -- Patchright (default Chromium), CloakBrowser (high-stealth patched binary), RemoteBridge (your real Chrome)
- **Daemon architecture** -- a background daemon auto-starts on first command, manages browser lifecycle, and tracks state with a monotonic seq counter
- **Profile persistence** -- save and restore login sessions across runs
- **Network capture** -- record traffic, export to HAR format, analyze API patterns, generate site adapters
- **Site adapters** -- wrap common site operations as one-liner commands
- **IDPI security** -- opt-in domain whitelist/blacklist, content scanning, untrusted content wrapping

## Installation

### Basic install

```bash
pip install browserctl
```

This installs the CLI tools (`browserctl` and `bctl` shorthand) plus the background daemon. The default browser backend is Patchright (a Chromium-based automation library). The Python package is included, but you need to download the Chromium browser binary separately:

```bash
python -m patchright install chromium
```

This downloads ~120MB to a local cache. You only need to run it once.

### Optional extras

```bash
pip install browserctl[stealth]       # adds CloakBrowser high-stealth backend
pip install browserctl[mcp]           # adds MCP server support (browserctl-mcp command)
pip install browserctl[mcp,stealth]   # everything
```

**What each extra adds:**

| Extra | What it installs | Browser binary |
|-------|-----------------|----------------|
| *(base)* | CLI + daemon + Patchright backend | Run `python -m patchright install chromium` (~120MB) |
| `stealth` | CloakBrowser patched Chromium + httpcloak proxy | Auto-downloads on first `--stealth` use (~200MB to `~/.cloakbrowser/`). No manual step. |
| `mcp` | MCP server (`browserctl-mcp` command) | No additional binary needed |

**Note on Patchright vs CloakBrowser:** The `patchright` Python package is always installed because CloakBrowser's code depends on it. However, if you only plan to use CloakBrowser (`--stealth` flag), you do NOT need to run `python -m patchright install chromium` -- CloakBrowser ships its own browser binary.

## Quick Start

The daemon starts automatically on first command. No setup step needed.

```bash
# Navigate to a page
bctl open "https://example.com"

# Get accessibility tree with [N] element refs
bctl snapshot

# Output:
# [1] <link> About
# [2] <button> Settings
# [3] <combobox> Search

# Interact using [N] refs from snapshot
bctl fill --target 3 --text "search query"
bctl press --key Enter --target 3

# Re-snapshot after navigation (refs change on page update)
bctl snapshot

# Take a screenshot
bctl screenshot --output page.png
```

### Observe-Act Loop

The core workflow: **snapshot first, then act**. Element refs `[N]` are only valid for the current page state -- they change whenever the page navigates or the DOM updates.

```bash
bctl open "https://example.com/login"
bctl snapshot --mode compact          # interactive elements only
bctl fill --target 3 --text "user"    # fill username
bctl fill --target 4 --text "pass"    # fill password
bctl click --target 5                 # submit
bctl snapshot                         # re-snapshot after navigation
bctl profile create my-session        # save login state
```

### Capture API Traffic

```bash
bctl capture start
bctl open "https://api-heavy-site.com"
# interact with the page...
bctl capture stop
bctl capture export --format har -o traffic.har
bctl capture analyze                  # detect API patterns
```

## Output Format

Every command returns one JSON object on stdout:

```json
{"ok": true, "seq": 3, "data": {"url": "https://example.com", "title": "Example"}}
```

Errors include a recovery hint that tells the agent (or you) what to try next:

```json
{"ok": false, "error": "element_not_found", "hint": "No element at index 99", "action": "re-snapshot to get fresh [N] refs"}
```

`seq` is a monotonic counter that increments on every browser state change. Parse with `jq`:

```bash
bctl snapshot | jq -r '.data.tree_text'
```

## Usage Modes

browserctl provides two usage modes. Choose based on your AI client:

| | Skill + CLI | MCP Server |
|---|---|---|
| **How it works** | Claude Code Skill auto-loads when browser is needed; agent calls `bctl` via Bash | `browserctl-mcp` runs as an MCP server exposing 18 tools |
| **Best for** | Claude Code, any Bash-capable agent | MCP-native AI clients (Claude Code, Codex, Cursor, etc.) |
| **Context cost** | On-demand -- Skill file loads only when needed | Persistent -- MCP tool definitions stay in context |
| **Setup** | Copy one Skill file | One config line |

### Skill + CLI (recommended for Claude Code)

The Skill file teaches Claude Code how to use `bctl` commands. It auto-loads when the agent needs browser capabilities.

**Install the Skill into your project:**

```bash
mkdir -p .claude/skills/browserctl
curl -o .claude/skills/browserctl/SKILL.md \
  https://raw.githubusercontent.com/shayu01/browserctl/main/.claude/skills/browserctl/SKILL.md
```

After this, Claude Code will automatically pick up the Skill when a task involves web pages. No further configuration needed.

### MCP Server

Run `browserctl-mcp` as an MCP server. The daemon auto-starts when the MCP server receives its first request.

#### Claude Code

One command, no file editing needed:

```bash
claude mcp add browserctl -- browserctl-mcp
```

#### Codex

Add to `.codex/mcp.json` in your project root:

```json
{
  "mcpServers": {
    "browserctl": {
      "command": "browserctl-mcp"
    }
  }
}
```

#### Cursor

Add to Cursor Settings > MCP Servers, or create `.cursor/mcp.json` in your project root:

```json
{
  "mcpServers": {
    "browserctl": {
      "command": "browserctl-mcp"
    }
  }
}
```

#### Other MCP clients

Use the same pattern. The MCP server command is `browserctl-mcp` (stdio transport, no additional args needed).

#### With uvx (no install needed)

If you do not want to install browserctl globally, use `uvx` to run it on-the-fly:

```json
{
  "mcpServers": {
    "browserctl": {
      "command": "uvx",
      "args": ["browserctl[mcp]"]
    }
  }
}
```

## Browser Backends

### Agent-dedicated browsers

These are Chromium instances managed by browserctl. They run headless by default, and no user interaction is needed.

**Patchright (default)** -- standard Chromium with mid-level stealth patches. Headless by default. Good for most sites.

```bash
bctl open "https://example.com"
```

**CloakBrowser (`--stealth`)** -- patched Chromium binary with behavioral humanization (realistic mouse movement, typing cadence). Runs in headed mode for anti-detection. On servers without a display, browserctl auto-starts Xvfb (a virtual framebuffer).

```bash
bctl open "https://protected-site.com" --stealth
```

### User browser bridging

**RemoteBridge (`--backend bridge`)** -- connects to a real Chrome browser on another machine (e.g., your Windows desktop) via a Chrome extension and WebSocket. The browser keeps its real fingerprint and login sessions.

```bash
bctl open "https://example.com" --backend bridge
```

See the [Remote Bridge](#remote-bridge) section below for setup instructions.

### Headed/headless modes and system dependencies

| Mode | Command | Display needed? | System dependencies |
|------|---------|----------------|-------------------|
| Headless (default) | `bctl open URL` | No | None |
| Headed | `bctl daemon start --headed` | Yes (desktop or VNC) | None |
| Stealth (CloakBrowser) | `bctl open URL --stealth` | Auto (uses Xvfb) | `xvfb` on headless Linux |

CloakBrowser runs in headed mode because anti-bot systems detect headless browsers. On a Linux server without a display, browserctl automatically starts Xvfb (a virtual framebuffer that simulates a screen). Install it with:

```bash
sudo apt-get install -y xvfb
```

On desktop Linux, macOS, or Windows, no extra dependencies are needed.

## Remote Bridge

Remote Bridge lets you control a real Chrome browser on another machine -- for example, operating your Windows desktop Chrome from a Linux server. This is useful when you need real login sessions, extensions, or a genuine browser fingerprint.

### How it works

1. A Chrome extension runs on the user's machine and connects to the browserctl daemon via WebSocket
2. The daemon routes commands to the extension, which executes them in the real browser
3. Results flow back through the same WebSocket connection

### Setup

1. **Get the extension files.** They are bundled in the source at `src/browserctl/bridge/extension/`.

2. **Install in Chrome:**
   - Open `chrome://extensions` in Chrome
   - Enable "Developer mode" (toggle in top-right)
   - Click "Load unpacked" and select the extension directory

3. **Configure the daemon address.** Click the extension icon and set the daemon host/port in the options page. The extension auto-connects once configured.

4. **Use it:**
   ```bash
   bctl open "https://example.com" --backend bridge
   ```

## Command Reference

### Navigation and Observation

| Command | Purpose |
|---------|---------|
| `bctl open URL` | Navigate to URL |
| `bctl snapshot` | Accessibility tree with `[N]` refs |
| `bctl snapshot --mode compact` | Interactive elements only |
| `bctl snapshot --mode content` | Text extraction |
| `bctl screenshot` | Take screenshot |
| `bctl resume` | Current state: URL, tabs, last actions |

### Interaction

| Command | Purpose |
|---------|---------|
| `bctl click --target N` | Click element |
| `bctl fill --target N --text "value"` | Clear + set input value |
| `bctl type --target N --text "value"` | Type character by character |
| `bctl press --key Enter` | Press keyboard key |
| `bctl scroll --direction down` | Scroll page |
| `bctl hover --target N` | Hover over element |
| `bctl select --target N --value "opt"` | Select dropdown option |

### Content and Network

| Command | Purpose |
|---------|---------|
| `bctl js eval "expression"` | Execute JavaScript |
| `bctl fetch URL` | HTTP GET with browser cookies |
| `bctl network requests` | Recent network requests |
| `bctl network console` | Console messages |

### Capture and Adapters

| Command | Purpose |
|---------|---------|
| `bctl capture start/stop` | Record network traffic |
| `bctl capture export --format har` | Export as HAR |
| `bctl capture analyze` | Detect API patterns |
| `bctl adapter list` | List site adapters |
| `bctl adapter run NAME` | Run named adapter |

### Management

| Command | Purpose |
|---------|---------|
| `bctl profile create/list/launch/delete` | Browser profile management |
| `bctl tab list/new/close/switch` | Tab management |
| `bctl doctor` | Diagnostics self-check |
| `bctl daemon start/stop/health` | Daemon lifecycle |

## Architecture

```
+--------------+     +--------------+     +----------------------+
|  CLI (typer) |---->| Daemon (HTTP)|---->| Browser Backend      |
|  bctl / MCP  |     |  aiohttp     |     |  +- PatchrightContext |
+--------------+     |  seq counter |     |  +- CloakContext      |
                     |  ring buffer |     |  +- RemoteBridgeCtx   |
                     +--------------+     +----------------------+
```

- **CLI** talks to the daemon over HTTP and outputs JSON to stdout
- **Daemon** manages browser lifecycle, tracks state with a monotonic seq counter, stores recent events in a ring buffer
- **Browser backends** all implement a unified `BrowserContext` protocol (6 methods + 2 properties), so the CLI and daemon never deal with backend-specific code

Layer isolation is strictly enforced: CLI cannot import browser internals, daemon cannot import CLI, browser backends cannot import either.

## Development

```bash
git clone https://github.com/shayu01/browserctl.git
cd browserctl
pip install -e ".[dev,mcp,stealth]"
python -m patchright install chromium
```

Run tests:

```bash
pytest                    # all tests
pytest tests/unit/        # fast unit tests only
pytest tests/integration/ # needs daemon + browser
```

Lint and type-check:

```bash
ruff check src/
pyright src/
```

## Acknowledgments

**Dependencies:**

- [patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright-python) -- Chromium automation library, core browser backend
- [CloakBrowser](https://github.com/CloakHQ/CloakBrowser) -- stealth browser with patched Chromium binary and behavioral humanization
- [httpcloak](https://github.com/sardanioss/httpcloak) -- TLS fingerprint protection proxy

**Design references:**

- [bb-browser](https://github.com/epiral/bb-browser) -- seq+since state tracking model, three-field error envelope
- [OpenCLI](https://github.com/jackwener/OpenCLI) -- Strategy enum and pipeline DSL for site adapters
- [GenericAgent](https://github.com/lsdefine/GenericAgent) -- WebSocket+HTTP dual-transport connection model for remote bridge
- [pinchtab](https://github.com/pinchtab/pinchtab) -- IDPI security model (domain whitelist/blacklist, content scanning)
- [browser-use](https://github.com/browser-use/browser-use) -- multi-action patterns for agent interaction
- [open-codex-computer-use](https://github.com/iFurySt/open-codex-computer-use) -- batch invocation via calls-file
- [Scrapling](https://github.com/D4Vinci/Scrapling) -- anti-bot bypass strategies

## License

MIT

---

# 中文文档

## 功能特性

- **CLI 优先设计** -- 每个命令在 stdout 输出一个 JSON 对象，结构化错误包含恢复提示，可用 `jq` 管道处理
- **MCP 服务器** -- 18 个工具，支持 AI 客户端原生工具发现（Claude Code、Codex、Cursor 等）
- **无障碍树快照** -- 页面元素以 `[N]` 索引表示，agent 通过索引交互，无需脆弱的 CSS 选择器
- **多后端反检测** -- Patchright（默认 Chromium）、CloakBrowser（高隐蔽修补二进制）、RemoteBridge（你的真实 Chrome）
- **守护进程架构** -- 后台守护进程在首次命令时自动启动，管理浏览器生命周期，用单调递增 seq 计数器追踪状态
- **会话持久化** -- 跨运行保存和恢复登录状态
- **流量捕获** -- 录制流量、导出 HAR 格式、分析 API 模式、生成站点适配器
- **站点适配器** -- 常见站点操作封装为一行命令
- **IDPI 安全模型** -- 可选的域名白名单/黑名单、内容扫描、不可信内容包装

## 安装

### 基本安装

```bash
pip install browserctl
```

安装 CLI 工具（`browserctl` 及其简写 `bctl`）和后台守护进程。默认浏览器后端是 Patchright（基于 Chromium 的自动化库）。Python 包会自动安装，但需要单独下载 Chromium 浏览器二进制文件：

```bash
python -m patchright install chromium
```

下载约 120MB 到本地缓存，只需运行一次。

### 可选扩展

```bash
pip install browserctl[stealth]       # 添加 CloakBrowser 高隐蔽后端
pip install browserctl[mcp]           # 添加 MCP 服务器支持（browserctl-mcp 命令）
pip install browserctl[mcp,stealth]   # 全部安装
```

**各扩展安装内容：**

| 扩展 | 安装内容 | 浏览器二进制 |
|------|---------|------------|
| *（基础）* | CLI + 守护进程 + Patchright 后端 | 运行 `python -m patchright install chromium`（约 120MB） |
| `stealth` | CloakBrowser 修补版 Chromium + httpcloak 代理 | 首次使用 `--stealth` 时自动下载（约 200MB 到 `~/.cloakbrowser/`），无需手动操作 |
| `mcp` | MCP 服务器（`browserctl-mcp` 命令） | 无需额外二进制 |

**关于 Patchright 与 CloakBrowser：** `patchright` Python 包始终会安装，因为 CloakBrowser 的代码依赖它。但如果你只使用 CloakBrowser（`--stealth` 标志），不需要运行 `python -m patchright install chromium` -- CloakBrowser 自带浏览器二进制文件。

## 快速上手

守护进程在首次命令时自动启动，无需额外设置。

```bash
# 导航到页面
bctl open "https://example.com"

# 获取无障碍树，带 [N] 元素索引
bctl snapshot

# 输出示例:
# [1] <link> About
# [2] <button> Settings
# [3] <combobox> Search

# 用快照中的 [N] 索引进行交互
bctl fill --target 3 --text "搜索内容"
bctl press --key Enter --target 3

# 页面变化后重新获取快照（索引会变）
bctl snapshot

# 截图
bctl screenshot --output page.png
```

### 观察-行动循环

核心工作流：**先快照，再操作**。元素索引 `[N]` 仅对当前页面状态有效，页面导航或 DOM 更新后索引会改变。

```bash
bctl open "https://example.com/login"
bctl snapshot --mode compact          # 仅交互元素
bctl fill --target 3 --text "用户名"   # 填写用户名
bctl fill --target 4 --text "密码"     # 填写密码
bctl click --target 5                 # 提交
bctl snapshot                         # 导航后重新快照
bctl profile create my-session        # 保存登录状态
```

### 捕获 API 流量

```bash
bctl capture start
bctl open "https://api-heavy-site.com"
# 与页面交互...
bctl capture stop
bctl capture export --format har -o traffic.har
bctl capture analyze                  # 检测 API 模式
```

## 输出格式

每个命令在 stdout 输出一个 JSON 对象：

```json
{"ok": true, "seq": 3, "data": {"url": "https://example.com", "title": "Example"}}
```

错误包含恢复提示，告诉 agent（或你）下一步该尝试什么：

```json
{"ok": false, "error": "element_not_found", "hint": "No element at index 99", "action": "re-snapshot to get fresh [N] refs"}
```

`seq` 是单调递增计数器，每次浏览器状态变化都会递增。用 `jq` 解析：

```bash
bctl snapshot | jq -r '.data.tree_text'
```

## 使用模式

browserctl 提供两种使用模式，按你的 AI 客户端选择：

| | Skill + CLI | MCP 服务器 |
|---|---|---|
| **工作方式** | Claude Code Skill 在需要浏览器时自动加载，agent 通过 Bash 调用 `bctl` | `browserctl-mcp` 作为 MCP 服务器运行，暴露 18 个工具 |
| **适用于** | Claude Code，任何支持 Bash 的 agent | MCP 原生 AI 客户端（Claude Code、Codex、Cursor 等） |
| **上下文开销** | 按需加载 -- Skill 文件仅在需要时加载 | 持续 -- MCP 工具定义常驻上下文 |
| **配置方式** | 复制一个 Skill 文件 | 一行配置 |

### Skill + CLI（推荐用于 Claude Code）

Skill 文件教会 Claude Code 如何使用 `bctl` 命令。当 agent 需要浏览器能力时，Skill 自动加载。

**将 Skill 安装到你的项目：**

```bash
mkdir -p .claude/skills/browserctl
curl -o .claude/skills/browserctl/SKILL.md \
  https://raw.githubusercontent.com/shayu01/browserctl/main/.claude/skills/browserctl/SKILL.md
```

安装后，Claude Code 在遇到涉及网页的任务时会自动识别并加载 Skill，无需其他配置。

### MCP 服务器

运行 `browserctl-mcp` 作为 MCP 服务器。守护进程在 MCP 服务器收到第一个请求时自动启动。

#### Claude Code

一条命令，无需编辑文件：

```bash
claude mcp add browserctl -- browserctl-mcp
```

#### Codex

添加到项目根目录的 `.codex/mcp.json`：

```json
{
  "mcpServers": {
    "browserctl": {
      "command": "browserctl-mcp"
    }
  }
}
```

#### Cursor

在 Cursor Settings > MCP Servers 中添加，或在项目根目录创建 `.cursor/mcp.json`：

```json
{
  "mcpServers": {
    "browserctl": {
      "command": "browserctl-mcp"
    }
  }
}
```

#### 其他 MCP 客户端

使用相同格式。MCP 服务器命令是 `browserctl-mcp`（stdio 传输，无需额外参数）。

#### 使用 uvx（无需安装）

如果不想全局安装 browserctl，可以用 `uvx` 直接运行：

```json
{
  "mcpServers": {
    "browserctl": {
      "command": "uvx",
      "args": ["browserctl[mcp]"]
    }
  }
}
```

## 浏览器后端

### Agent 专用浏览器

由 browserctl 管理的 Chromium 实例，默认无头运行，无需用户交互。

**Patchright（默认）** -- 标准 Chromium，中等反检测补丁，默认无头运行。适用于大多数网站。

```bash
bctl open "https://example.com"
```

**CloakBrowser（`--stealth`）** -- 修补版 Chromium 二进制文件，带行为模拟（真实鼠标移动、打字节奏）。以有头模式运行以对抗检测。在没有显示器的服务器上，browserctl 自动启动 Xvfb（虚拟帧缓冲）。

```bash
bctl open "https://protected-site.com" --stealth
```

### 用户浏览器桥接

**RemoteBridge（`--backend bridge`）** -- 通过 Chrome 扩展和 WebSocket 连接到另一台机器上的真实 Chrome 浏览器（例如从 Linux 服务器操作你的 Windows 桌面 Chrome）。浏览器保持真实指纹和登录状态。

```bash
bctl open "https://example.com" --backend bridge
```

设置方法请参见下方[远程桥接](#远程桥接)章节。

### 有头/无头模式与系统依赖

| 模式 | 命令 | 需要显示器？ | 系统依赖 |
|------|------|------------|---------|
| 无头（默认） | `bctl open URL` | 否 | 无 |
| 有头 | `bctl daemon start --headed` | 是（桌面或 VNC） | 无 |
| 隐蔽（CloakBrowser） | `bctl open URL --stealth` | 自动（使用 Xvfb） | Linux 无头服务器需要 `xvfb` |

CloakBrowser 以有头模式运行，因为反爬虫系统能检测无头浏览器。在没有显示器的 Linux 服务器上，browserctl 自动启动 Xvfb（模拟屏幕的虚拟帧缓冲）。安装方法：

```bash
sudo apt-get install -y xvfb
```

在桌面 Linux、macOS 或 Windows 上无需额外依赖。

## 远程桥接

远程桥接让你从一台机器控制另一台机器上的真实 Chrome 浏览器，例如从 Linux 服务器操作 Windows 桌面的 Chrome。适用于需要真实登录状态、浏览器扩展或真实浏览器指纹的场景。

### 工作原理

1. Chrome 扩展运行在用户的机器上，通过 WebSocket 连接到 browserctl 守护进程
2. 守护进程将命令路由到扩展，扩展在真实浏览器中执行
3. 结果通过同一 WebSocket 连接返回

### 设置步骤

1. **获取扩展文件。** 源码中包含在 `src/browserctl/bridge/extension/` 目录。

2. **在 Chrome 中安装：**
   - 打开 Chrome，访问 `chrome://extensions`
   - 开启"开发者模式"（右上角开关）
   - 点击"加载已解压的扩展程序"，选择扩展目录

3. **配置守护进程地址。** 点击扩展图标，在选项页中设置守护进程的主机和端口。配置完成后扩展自动连接。

4. **使用：**
   ```bash
   bctl open "https://example.com" --backend bridge
   ```

## 命令参考

### 导航与观察

| 命令 | 用途 |
|------|------|
| `bctl open URL` | 导航到 URL |
| `bctl snapshot` | 获取无障碍树，带 `[N]` 索引 |
| `bctl snapshot --mode compact` | 仅交互元素 |
| `bctl snapshot --mode content` | 文本提取 |
| `bctl screenshot` | 截图 |
| `bctl resume` | 当前状态：URL、标签页、最近操作 |

### 交互

| 命令 | 用途 |
|------|------|
| `bctl click --target N` | 点击元素 |
| `bctl fill --target N --text "值"` | 清空并设置输入值 |
| `bctl type --target N --text "值"` | 逐字符输入 |
| `bctl press --key Enter` | 按键 |
| `bctl scroll --direction down` | 滚动页面 |
| `bctl hover --target N` | 悬停 |
| `bctl select --target N --value "选项"` | 选择下拉选项 |

### 内容与网络

| 命令 | 用途 |
|------|------|
| `bctl js eval "expression"` | 执行 JavaScript |
| `bctl fetch URL` | 使用浏览器 cookie 发起 HTTP 请求 |
| `bctl network requests` | 最近的网络请求 |
| `bctl network console` | 控制台消息 |

### 捕获与适配器

| 命令 | 用途 |
|------|------|
| `bctl capture start/stop` | 录制网络流量 |
| `bctl capture export --format har` | 导出为 HAR |
| `bctl capture analyze` | 检测 API 模式 |
| `bctl adapter list` | 列出站点适配器 |
| `bctl adapter run NAME` | 运行指定适配器 |

### 管理

| 命令 | 用途 |
|------|------|
| `bctl profile create/list/launch/delete` | 浏览器配置管理 |
| `bctl tab list/new/close/switch` | 标签页管理 |
| `bctl doctor` | 诊断自检 |
| `bctl daemon start/stop/health` | 守护进程生命周期 |

## 架构

```
+--------------+     +--------------+     +----------------------+
|  CLI (typer) |---->| Daemon (HTTP)|---->| Browser Backend      |
|  bctl / MCP  |     |  aiohttp     |     |  +- PatchrightContext |
+--------------+     |  seq counter |     |  +- CloakContext      |
                     |  ring buffer |     |  +- RemoteBridgeCtx   |
                     +--------------+     +----------------------+
```

- **CLI** 通过 HTTP 与守护进程通信，输出 JSON 到 stdout
- **守护进程** 管理浏览器生命周期，用单调递增 seq 计数器追踪状态，用环形缓冲区存储最近事件
- **浏览器后端** 均实现统一的 `BrowserContext` 协议（6 个方法 + 2 个属性），CLI 和守护进程不直接接触后端代码

层级隔离严格执行：CLI 不能导入浏览器内部模块，守护进程不能导入 CLI，浏览器后端不能导入两者。

## 开发

```bash
git clone https://github.com/shayu01/browserctl.git
cd browserctl
pip install -e ".[dev,mcp,stealth]"
python -m patchright install chromium
```

运行测试：

```bash
pytest                    # 全部测试
pytest tests/unit/        # 仅快速单元测试
pytest tests/integration/ # 需要守护进程 + 浏览器
```

代码检查：

```bash
ruff check src/
pyright src/
```

## 致谢

**直接依赖：**

- [patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright-python) -- Chromium 自动化库，核心浏览器后端
- [CloakBrowser](https://github.com/CloakHQ/CloakBrowser) -- 反检测浏览器，修补 Chromium 二进制 + 行为模拟
- [httpcloak](https://github.com/sardanioss/httpcloak) -- TLS 指纹保护代理

**设计参考：**

- [bb-browser](https://github.com/epiral/bb-browser) -- seq+since 状态追踪模型、三字段错误信封
- [OpenCLI](https://github.com/jackwener/OpenCLI) -- Strategy 枚举和 pipeline DSL 适配器设计
- [GenericAgent](https://github.com/lsdefine/GenericAgent) -- WebSocket+HTTP 双传输连接模型，用于远程桥接
- [pinchtab](https://github.com/pinchtab/pinchtab) -- IDPI 安全模型（域名白名单/黑名单、内容扫描）
- [browser-use](https://github.com/browser-use/browser-use) -- agent 交互的多动作模式
- [open-codex-computer-use](https://github.com/iFurySt/open-codex-computer-use) -- 通过 calls-file 批量调用
- [Scrapling](https://github.com/D4Vinci/Scrapling) -- 反检测绕过策略

## 许可证

MIT
