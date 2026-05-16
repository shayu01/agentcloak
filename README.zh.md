<div align="center">

# agentcloak

Agent 原生隐身浏览器 -- 看见、交互、自动化。

你需要浏览器，你的 agent 也一样。

[![PyPI](https://img.shields.io/pypi/v/agentcloak?style=flat)](https://pypi.org/project/agentcloak/)
[![Python](https://img.shields.io/pypi/pyversions/agentcloak?style=flat)](https://pypi.org/project/agentcloak/)
[![License](https://img.shields.io/github/license/shayuc137/agentcloak?style=flat)](https://github.com/shayuc137/agentcloak/blob/main/LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/shayuc137/agentcloak/ci.yml?style=flat&label=CI)](https://github.com/shayuc137/agentcloak/actions)

<!-- README-I18N:START -->
[English](./README.md) | **中文**
<!-- README-I18N:END -->

</div>

## 亮点

- **页面即结构化文本** -- 页面转化为无障碍树，每个可交互元素带有 `[N]` 索引，agent 通过索引操作而非脆弱的 CSS 选择器
- **CLI + Skill 按需加载** -- agent 通过 Bash 调用 `cloak` 命令，Skill 按需加载仅占 ~300 tokens（MCP 工具定义常驻 ~6,000 tokens）
- **CloakBrowser 内置隐身** -- 基于 57 个 C++ 补丁的 Chromium，开箱即用绕过 Cloudflare
- **登录态复用** -- 保存/恢复登录 profile，通过 RemoteBridge 操控真实 Chrome 浏览器
- **Daemon 架构** -- 首次命令自动启动，管理浏览器生命周期，单调递增的 seq 计数器追踪状态
- **Spell + API 流量捕获** -- 常见站点操作封装为一行命令；捕获流量，分析模式，自动生成 spell
- **MCP server 23 个工具** -- 完整兼容 MCP 原生客户端（Claude Code、Codex、Cursor 等）

## 安装

**需要 Python 3.12+**

> [!TIP]
> **Agent 辅助安装** -- 将下面的文本复制给你的 AI agent：
>
> ```text
> 按照此文档安装和配置 agentcloak：
> https://github.com/shayuc137/agentcloak/blob/main/docs/zh/getting-started/installation.md
> ```

<details>
<summary>手动安装</summary>

```bash
pip install agentcloak
```

一条命令安装全部组件：CLI（`agentcloak` 和简写 `cloak`）、MCP server（`agentcloak-mcp`）、CloakBrowser 隐身后端、httpcloak TLS 指纹代理。补丁版 Chromium 二进制文件（约 200 MB）在首次使用时自动下载到 `~/.cloakbrowser/`。

**系统依赖（仅限无显示器的 Linux 服务器）：**

CloakBrowser 以有头模式运行以对抗反检测。在没有显示器的服务器上，agentcloak 会自动启动 Xvfb：

```bash
sudo apt-get install -y xvfb
```

桌面 Linux、macOS 和 Windows 无需额外依赖。

</details>

## 快速开始

daemon 在首次命令时自动启动。

```bash
# 导航并一次性获取页面 snapshot
cloak navigate "https://example.com" --snapshot

# 输出包含带 [N] 元素引用的无障碍树：
#   [1] link "About" href="https://example.com/about"
#   [2] button "Settings"
#   [3] combobox "Search" value="" focused

# 通过 [N] 引用进行交互 -- 加 --include-snapshot 可附带返回新 snapshot
cloak fill --target 3 --text "search query" --include-snapshot
cloak press --key Enter --target 3

# 截图
cloak screenshot --output page.png
```

每个命令在 stdout 输出一个 JSON 对象。错误包含恢复建议：

```json
{"ok": true, "seq": 3, "data": {"url": "https://example.com", "title": "Example"}}
{"ok": false, "error": "element_not_found", "hint": "No element at index 99", "action": "re-snapshot to get fresh [N] refs"}
```

`navigate` 和 action 命令的 `--snapshot` 参数让观察-操作循环更紧凑 -- 无需在每步之间单独调用 snapshot。

完整教程参见[快速开始指南](docs/zh/getting-started/quickstart.md)，涵盖登录持久化、profile 管理和 API 捕获。

## 使用模式

| | Skill + CLI（推荐） | MCP Server |
|---|---|---|
| **工作方式** | Skill 在需要浏览器时自动加载，agent 通过 Bash 调用 `cloak` | `agentcloak-mcp` 通过 stdio 暴露 23 个工具 |
| **上下文开销** | ~300 tokens（按需加载） | ~6,000 tokens（常驻） |
| **适用场景** | Claude Code 及任何支持 Bash 的 agent | 没有 Bash 能力的纯 MCP 客户端 |

**Skill + CLI** -- 将 Skill 安装到你的项目：

```bash
mkdir -p .claude/skills/agentcloak
curl -o .claude/skills/agentcloak/SKILL.md \
  https://raw.githubusercontent.com/shayuc137/agentcloak/main/.claude/skills/agentcloak/SKILL.md
```

**MCP Server** -- Claude Code 一行配置：

```bash
claude mcp add agentcloak -- agentcloak-mcp
```

<details>
<summary>其他 MCP 客户端（Codex、Cursor、uvx）</summary>

添加到 `.codex/mcp.json` 或 `.cursor/mcp.json`：

```json
{
  "mcpServers": {
    "agentcloak": {
      "command": "agentcloak-mcp"
    }
  }
}
```

通过 `uvx` 免安装运行：

```json
{
  "mcpServers": {
    "agentcloak": {
      "command": "uvx",
      "args": ["agentcloak[mcp]"]
    }
  }
}
```

</details>

完整配置指南参见 [MCP 配置](docs/zh/guides/mcp-setup.md)。

## 浏览器后端

| 后端 | 隐身能力 | 适用场景 |
|------|---------|---------|
| **CloakBrowser**（默认） | 57 个 C++ 补丁 + Cloudflare 绕过 | 大多数网站，反爬保护页面 |
| **Playwright** | 标准 Chromium | 开发调试，无需隐身的场景 |
| **RemoteBridge** | 真实浏览器指纹 | 操控另一台机器上的 Chrome |

详情参见[后端指南](docs/zh/guides/backends.md)。

## 架构

```mermaid
graph TD
    subgraph Surface["Surface Layer"]
        Skill["Skill + CLI<br/>~300 tokens"]
        MCP["MCP Server<br/>23 tools"]
    end

    subgraph Engine["Engine"]
        Daemon["Daemon<br/>FastAPI + uvicorn + seq counter"]
    end

    subgraph Backends["Browser Backends"]
        Cloak["CloakBrowser<br/>stealth default"]
        PW["Playwright<br/>fallback"]
        Bridge["RemoteBridge<br/>real Chrome"]
    end

    Skill --> Daemon
    MCP --> Daemon
    Daemon --> Cloak
    Daemon --> PW
    Daemon --> Bridge
```

所有后端继承统一的 `BrowserContextBase` ABC。基类包含约 900 行共享行为（action dispatch、batch、dialog、自恢复）；子类只实现 29 个原子 `_xxx_impl` 操作。层级隔离严格执行：CLI 不能导入 browser 内部模块，daemon 不能导入 CLI，后端两者都不导入。

详情参见[架构文档](docs/zh/explanation/architecture.md)。

## 文档

| 主题 | 链接 |
|------|------|
| 安装指南 | [docs/zh/getting-started/installation.md](docs/zh/getting-started/installation.md) |
| 快速开始教程 | [docs/zh/getting-started/quickstart.md](docs/zh/getting-started/quickstart.md) |
| CLI 参考 | [docs/zh/reference/cli.md](docs/zh/reference/cli.md) |
| MCP 工具参考 | [docs/zh/reference/mcp.md](docs/zh/reference/mcp.md) |
| 配置参考 | [docs/zh/reference/config.md](docs/zh/reference/config.md) |
| 浏览器后端 | [docs/zh/guides/backends.md](docs/zh/guides/backends.md) |
| MCP 配置 | [docs/zh/guides/mcp-setup.md](docs/zh/guides/mcp-setup.md) |
| 架构 | [docs/zh/explanation/architecture.md](docs/zh/explanation/architecture.md) |

## 安全

漏洞报告方式参见 [SECURITY.md](SECURITY.md)。

## 贡献

欢迎贡献。开发环境配置、代码风格和 PR 规范参见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 致谢

基于 [CloakBrowser](https://github.com/CloakHQ/CloakBrowser)（隐身 Chromium）和 [httpcloak](https://github.com/sardanioss/httpcloak)（TLS 指纹代理）构建。设计参考了 [bb-browser](https://github.com/epiral/bb-browser)、[browser-use](https://github.com/browser-use/browser-use)、[OpenCLI](https://github.com/jackwener/OpenCLI)、[GenericAgent](https://github.com/lsdefine/GenericAgent)、[pinchtab](https://github.com/pinchtab/pinchtab)、[open-codex-computer-use](https://github.com/iFurySt/open-codex-computer-use) 和 [Scrapling](https://github.com/D4Vinci/Scrapling)。

## 许可证

[MIT](LICENSE)
