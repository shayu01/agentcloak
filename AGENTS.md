<!-- TRELLIS:START -->
# Trellis Instructions

These instructions are for AI assistants working in this project.

This project is managed by Trellis. The working knowledge you need lives under `.trellis/`:

- `.trellis/workflow.md` — development phases, when to create tasks, skill routing
- `.trellis/spec/` — package- and layer-scoped coding guidelines (read before writing code in a given layer)
- `.trellis/workspace/` — per-developer journals and session traces
- `.trellis/tasks/` — active and archived tasks (PRDs, research, jsonl context)

If a Trellis command is available on your platform (e.g. `/trellis:finish-work`, `/trellis:continue`), prefer it over manual steps. Not every platform exposes every command.

If you're using Codex or another agent-capable tool, additional project-scoped helpers may live in:
- `.agents/skills/` — reusable Trellis skills
- `.codex/agents/` — optional custom subagents

Managed by Trellis. Edits outside this block are preserved; edits inside may be overwritten by a future `trellis update`.

<!-- TRELLIS:END -->

## Project Overview

agentcloak — 通用 agent 浏览器能力层，为 Claude Code 等 AI 编程工具提供稳定的"眼睛和手"。
Skill + CLI（主推）/ MCP（兼容）双表面，通过 daemon 管理浏览器实例。
默认后端 CloakBrowser（57 C++ patch 隐身），可选 RemoteBridge（attach 用户真实浏览器）。

## Roadmap

@.trellis/spec/guides/project-roadmap.md

完成 phase 相关任务时，同步更新 roadmap 中对应 phase 的进度状态。

## Triple-Surface Architecture

agentcloak 提供三种运行模式，按场景选择：

### Skill + CLI 模式（推荐默认）

Claude Code Skill（`skills/agentcloak/SKILL.md`）按需加载，agent 通过 Bash 调用 `agentcloak` CLI。
零常驻 MCP 开销，Skill 仅在 agent 需要浏览器能力时加载到 context。CLI 直接输出 JSON，daemon 首次命令时自动启动。
适用于大多数场景：导航、交互、截图、数据提取、表单填写。

### 独立 MCP 模式

`agentcloak-mcp` 作为独立 MCP server 运行，覆盖 90% 的 web 自动化场景：navigate、snapshot、action、screenshot、evaluate、fetch、capture、adapter、profile、tab。
适用于不支持 Bash 的纯 MCP 客户端。注意：MCP 工具定义常驻 context 约 ~6000 tokens，是 Skill+CLI 模式（~300 tokens）的 20 倍。Bash-capable agent 推荐使用 Skill+CLI 模式。

### jshookmcp 松耦合模式（逆向/hook 场景）

agentcloak 和 jshookmcp 作为两个独立 MCP server 并行运行，通过 CDP endpoint 共享浏览器。
适用于需要 jshookmcp 独特能力（JS hook、instrument、protocol analysis、进程内存扫描）的场景。

**协调方式**：
1. agent 通过 Bash 调 agentcloak CLI 启动隐身浏览器并交互
2. agent 调 `agentcloak cdp endpoint` 获取 CDP WebSocket URL
3. agent 调 jshookmcp 的 `browser_attach(wsEndpoint)` 连上同一浏览器
4. 后续：浏览器操作走 agentcloak CLI，JS 分析走 jshookmcp MCP

**决策记录（2026-05-13 竞品分析确认）**：
- 原 6 patch plugin 注入模式维护成本高（jshookmcp 更新后 patch 失效）、patch 5 有已知 bypass、SDK 架构缺陷导致迁移走不通。
- 松耦合方式零维护成本，两边独立升级，故障隔离。agent 做一步 CDP 传递的协调成本极低。
- 详见 `spec/guides/competitive-analysis.md` 第七层分析。

### 三种模式的能力对比

| 能力 | Skill + CLI（主推） | 独立 MCP（兼容） | jshookmcp 松耦合 |
|------|------------|---------|------------|
| navigate/snapshot/action | agentcloak CLI | agentcloak daemon | agentcloak CLI |
| screenshot/evaluate | agentcloak CLI | agentcloak daemon | agentcloak CLI |
| JS hook/instrument | 无 | 无 | jshookmcp MCP tools |
| stealth (CloakBrowser) | 内置 | 内置 | 内置（agentcloak 启动） |
| context 开销 | ~300 tokens | ~6000 tokens | ~300 + jshookmcp 工具定义 |
| 工具发现性 | Skill 自动匹配 | 完整（MCP 标准） | 分别发现 |
| 维护成本 | 零 | 零 | 零（独立运行） |

## Layer Isolation (Hard Constraint)

| Layer | Allowed dependencies | Forbidden |
|-------|---------------------|-----------|
| `cli/` | daemon HTTP API | `browser/`, `daemon/` internals |
| `daemon/` | `browser/`, `core/` | `cli/` |
| `browser/` | `core/` | `cli/`, `daemon/` |
| `core/` | stdlib + third-party | any sibling layer |
| `adapters/` | `core/`, `browser/protocol` | `daemon/`, `cli/` |
| `mcp/` | `core/`, `adapters/`, daemon HTTP API | `browser/`, `daemon/` internals |
