# browserctl

Browser automation toolkit for AI agents. CLI + MCP dual interface, multi-backend stealth, remote browser bridge.

[English](#features) | [中文](#功能特性)

---

## Features

- **CLI-first design** — JSON output on stdout, structured errors with recovery hints, pipeable with `jq`
- **MCP server** — 18 tools for AI clients with native tool discovery (Claude, Cursor, etc.)
- **Accessibility-tree snapshots** — `[N]` indexed elements for precise interaction without CSS selectors
- **Multi-backend stealth** — Patchright (default), CloakBrowser (high-stealth), RemoteBridge (real Chrome)
- **Daemon architecture** — auto-starts on first command, manages browser lifecycle, seq-based state tracking
- **Profile persistence** — save and restore login sessions across runs
- **Network capture** — record traffic, export HAR, analyze API patterns, generate adapters
- **Site adapters** — wrap common site operations as one-liner commands
- **IDPI security** — domain whitelist/blacklist, content scanning, untrusted content wrapping

## Installation

```bash
pip install browserctl
```

With optional extras:

```bash
pip install browserctl[mcp]       # MCP server support
pip install browserctl[stealth]   # CloakBrowser high-stealth backend
pip install browserctl[mcp,stealth]  # both
```

After installation, install the browser binary:

```bash
python -m patchright install chromium
```

## Quick Start

The daemon starts automatically on first command.

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

The core workflow: **snapshot first, then act**. Element refs `[N]` are only valid for the current page state.

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

Errors include a recovery hint:

```json
{"ok": false, "error": "element_not_found", "hint": "No element at index 99", "action": "re-snapshot to get fresh [N] refs"}
```

`seq` is a monotonic counter tracking browser state changes. Parse with `jq`:

```bash
bctl snapshot | jq -r '.data.tree_text'
```

## Three Modes

browserctl provides three usage modes. Choose based on your integration:

| | Skill + CLI | Standalone MCP | jshook Plugin |
|---|---|---|---|
| **How** | Claude Code Skill loads on demand, agent calls `bctl` via Bash | `browserctl-mcp` as MCP server, 18 tools | browserctl as jshook plugin, sed patches |
| **Best for** | Claude Code, Bash-capable agents | MCP-native AI clients | JS hook / CDP / reverse engineering |
| **Context cost** | On-demand (Skill loads when needed) | Persistent (MCP tool definitions) | Persistent + patches |
| **Maintenance** | Zero | Zero | 6 sed patches |

### Skill + CLI (recommended default)

The Claude Code Skill at `.claude/skills/browserctl/SKILL.md` auto-loads when the agent needs browser capabilities. The agent calls `bctl` commands via Bash.

### Standalone MCP

Run `browserctl-mcp` as an MCP server:

```json
{
  "mcpServers": {
    "browserctl": {
      "command": "browserctl-mcp",
      "args": []
    }
  }
}
```

Or with `uvx` (no install needed):

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

### MCP Client Configuration

**Claude Code** — add to `.mcp.json` in project root or `~/.claude.json` globally.

**Cursor** — add to Cursor Settings > MCP Servers.

**Other MCP clients** — use the same `command` / `args` pattern above.

## Stealth Backends

```
Local browser:
  ├─ Default: Patchright (mid-stealth, Playwright API)
  ├─ Stealth: CloakBrowser (high-stealth, patched binary + humanize)
  └─ Future: Camoufox (Firefox stealth)

Remote browser:
  └─ RemoteBridge (real Chrome on another machine via WebSocket)
```

Enable stealth mode:

```bash
bctl open "https://protected-site.com" --stealth
```

Use remote bridge (requires Chrome extension on target machine):

```bash
bctl open "https://example.com" --backend bridge
```

## Command Reference

### Navigation & Observation

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

### Content & Network

| Command | Purpose |
|---------|---------|
| `bctl js eval "expression"` | Execute JavaScript |
| `bctl fetch URL` | HTTP GET with browser cookies |
| `bctl network requests` | Recent network requests |
| `bctl network console` | Console messages |

### Capture & Adapters

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
┌──────────────┐     ┌──────────────┐     ┌──────────────────────┐
│  CLI (typer)  │────▶│ Daemon (HTTP) │────▶│ Browser Backend      │
│  bctl / MCP   │     │  aiohttp      │     │  ├─ PatchrightContext │
└──────────────┘     │  seq counter  │     │  ├─ CloakContext      │
                      │  ring buffer  │     │  └─ RemoteBridgeCtx   │
                      └──────────────┘     └──────────────────────┘
```

- **CLI** talks to daemon over HTTP, outputs JSON
- **Daemon** manages browser lifecycle, tracks state with monotonic seq counter
- **Browser backends** implement a unified `BrowserContext` protocol (6 methods + 2 properties)

Layer isolation is enforced: CLI cannot import browser internals, daemon cannot import CLI.

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

## License

MIT

---

# 中文文档

## 功能特性

- **CLI 优先设计** — stdout 输出 JSON，结构化错误带恢复提示，可用 `jq` 管道处理
- **MCP 服务器** — 18 个工具，支持 AI 客户端原生工具发现（Claude、Cursor 等）
- **无障碍树快照** — `[N]` 索引元素，精确交互无需 CSS 选择器
- **多后端反检测** — Patchright（默认）、CloakBrowser（高隐蔽）、RemoteBridge（真实 Chrome）
- **守护进程架构** — 首次命令自动启动，管理浏览器生命周期，基于 seq 的状态追踪
- **会话持久化** — 跨运行保存和恢复登录状态
- **流量捕获** — 录制流量、导出 HAR、分析 API 模式、生成适配器
- **站点适配器** — 常见站点操作封装为一行命令
- **IDPI 安全模型** — 域名白名单/黑名单、内容扫描、不可信内容包装

## 安装

```bash
pip install browserctl
```

可选扩展：

```bash
pip install browserctl[mcp]       # MCP 服务器支持
pip install browserctl[stealth]   # CloakBrowser 高隐蔽后端
pip install browserctl[mcp,stealth]  # 全部安装
```

安装后，下载浏览器二进制文件：

```bash
python -m patchright install chromium
```

## 快速上手

守护进程在首次命令时自动启动。

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

核心工作流：**先快照，再操作**。元素索引 `[N]` 仅对当前页面状态有效。

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

错误包含恢复提示：

```json
{"ok": false, "error": "element_not_found", "hint": "No element at index 99", "action": "re-snapshot to get fresh [N] refs"}
```

`seq` 是追踪浏览器状态变化的单调递增计数器。用 `jq` 解析：

```bash
bctl snapshot | jq -r '.data.tree_text'
```

## 三种使用模式

browserctl 提供三种使用模式，按集成方式选择：

| | Skill + CLI | 独立 MCP | jshook 插件 |
|---|---|---|---|
| **方式** | Claude Code Skill 按需加载，agent 通过 Bash 调用 `bctl` | `browserctl-mcp` 作为 MCP 服务器，18 个工具 | browserctl 作为 jshook 插件，sed patch 注入 |
| **适用于** | Claude Code，支持 Bash 的 agent | MCP 原生 AI 客户端 | JS hook / CDP / 逆向工程 |
| **上下文开销** | 按需（Skill 需要时加载） | 持续（MCP 工具定义常驻） | 持续 + patch |
| **维护成本** | 零 | 零 | 6 个 sed patch |

### Skill + CLI（推荐默认）

Claude Code Skill 位于 `.claude/skills/browserctl/SKILL.md`，agent 需要浏览器能力时自动加载，通过 Bash 调用 `bctl` 命令。

### 独立 MCP

运行 `browserctl-mcp` 作为 MCP 服务器：

```json
{
  "mcpServers": {
    "browserctl": {
      "command": "browserctl-mcp",
      "args": []
    }
  }
}
```

或用 `uvx`（无需安装）：

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

### MCP 客户端配置

**Claude Code** — 添加到项目根目录 `.mcp.json` 或全局 `~/.claude.json`。

**Cursor** — 在 Cursor Settings > MCP Servers 中添加。

**其他 MCP 客户端** — 使用上述相同的 `command` / `args` 格式。

## 反检测后端

```
本地浏览器:
  ├─ 默认: Patchright（中等隐蔽，Playwright API）
  ├─ 隐蔽: CloakBrowser（高隐蔽，修补二进制 + 行为模拟）
  └─ 计划: Camoufox（Firefox 隐蔽）

远程浏览器:
  └─ RemoteBridge（通过 WebSocket 控制另一台机器上的真实 Chrome）
```

启用隐蔽模式：

```bash
bctl open "https://protected-site.com" --stealth
```

使用远程桥接（需要在目标机器的 Chrome 上安装扩展）：

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
┌──────────────┐     ┌──────────────┐     ┌──────────────────────┐
│  CLI (typer)  │────▶│ Daemon (HTTP) │────▶│ Browser Backend      │
│  bctl / MCP   │     │  aiohttp      │     │  ├─ PatchrightContext │
└──────────────┘     │  seq counter  │     │  ├─ CloakContext      │
                      │  ring buffer  │     │  └─ RemoteBridgeCtx   │
                      └──────────────┘     └──────────────────────┘
```

- **CLI** 通过 HTTP 与守护进程通信，输出 JSON
- **守护进程** 管理浏览器生命周期，用单调递增 seq 计数器追踪状态
- **浏览器后端** 实现统一的 `BrowserContext` 协议（6 个方法 + 2 个属性）

层级隔离严格执行：CLI 不能导入浏览器内部模块，守护进程不能导入 CLI。

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

## 许可证

MIT
