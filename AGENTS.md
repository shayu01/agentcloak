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

agentcloak — agent 浏览器能力层，为 AI 编程工具提供稳定的"眼睛和手"。
Skill + CLI（主推）/ MCP（兼容）双表面，daemon 管理浏览器实例。
默认后端 CloakBrowser（57 C++ patch 隐身），可选 Playwright（无隐身）和 RemoteBridge（用户真实浏览器）。

## Roadmap

@.trellis/spec/guides/project-roadmap.md

完成 phase 相关任务时，同步更新 roadmap 中对应 phase 的进度状态。

## Architecture

三种运行模式：Skill + CLI（~300 tokens 按需加载）、MCP server（23 tools, ~6000 tokens 常驻）、jshookmcp 松耦合（CDP 共享）。详见 `spec/guides/project-roadmap.md` Triple-Surface Architecture 段。

所有后端继承 `BrowserContextBase` ABC（~900 行共享行为，29 个原子 `_xxx_impl`）。daemon 用 FastAPI + uvicorn，CLI/MCP 通过 `DaemonClient`（httpx sync+async）调用。

## Layer Isolation (Hard Constraint)

| Layer | Allowed dependencies | Forbidden |
|-------|---------------------|-----------|
| `cli/` | daemon HTTP API | `browser/`, `daemon/` internals |
| `daemon/` | `browser/`, `core/` | `cli/` |
| `browser/` | `core/` | `cli/`, `daemon/` |
| `core/` | stdlib + third-party | any sibling layer |
| `spells/` | `core/`, `browser/base` | `daemon/`, `cli/` |
| `mcp/` | `core/`, `spells/`, daemon HTTP API | `browser/`, `daemon/` internals |

## Quality Baseline

Commit 前跑 preflight（10 项自动检查，~6s）：

```bash
uv run python scripts/preflight.py
```

覆盖：unit tests、lint、typecheck、daemon/CLI/MCP 三方对齐、DaemonClient 方法对齐、Skill 参考同步、Skill 命令覆盖、config 文档同步、版本一致、CLI smoke。任何一项不过都不应该 commit。

## Code Generation Pipeline

daemon 的 OpenAPI spec 是唯一事实来源。新增 daemon route 时需要同步：

1. **映射表**：`scripts/generate_skill.py` 中的 `ROUTE_TO_CLI` + `ROUTE_TO_MCP` 各加一行
2. **DaemonClient**：`src/agentcloak/client.py` 加 async + sync 方法对
3. **CLI 命令**：`src/agentcloak/cli/commands/` 下对应文件
4. **MCP 工具**：`src/agentcloak/mcp/tools/` 下对应文件

preflight 的 surface/client/skill checks 会自动报出遗漏。`commands-reference.md` 由 `generate_skill.py --write` 从 OpenAPI 自动生成，不手动编辑。

## Doc Sync

改完代码后检查文档是否需要更新。规则和映射表在 `spec/guides/documentation-workflow.md` Phase 7。

核心原则：
- 改 config 默认值 → 同步 `docs/*/reference/config.md`（en+zh）
- 改 CLI 参数/命令 → 同步 `skills/agentcloak/SKILL.md` + `docs/*/reference/cli.md`
- 改 snapshot 输出格式 → 同步 `docs/*/explanation/snapshot-model.md` + SKILL.md
- 改安全层行为 → 同步 `docs/*/guides/security.md`
- 所有 `docs/en/` 的变更必须同步到 `docs/zh/`
