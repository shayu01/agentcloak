# Project Roadmap & Architecture Decisions

> browserctl 项目级路线图和关键架构决策。提取自初始研究 PRD (D1-D20)。
> 原始研究完整记录：`.trellis/tasks/archive/2026-05/05-06-reference-projects-research/prd.md`

---

## Core Positioning (D1)

- **Primary**: 通用 agent 浏览器能力层——稳定的"眼睛和手"
- **Secondary**: 日常网站自动化——登录态复用的常见任务
- **Long-term**: 网站能力资产平台——站点操作沉淀为可复用 CLI 命令
- **Complementary**: jshookmcp 作为 MCP 覆盖 JS Hook/CDP/逆向（不重复实现）

## Tech Stack (D4)

- **Python**：CloakBrowser/Scrapling/patchright 生态、Playwright-Python、typer CLI、orjson JSON 输出
- **CLI primary, MCP optional** (D2)：CLI 稳定可调试，MCP 作为可选增强层共享同一 daemon 引擎

## Three-Tier Stealth (D5)

```
Local browser:
  ├─ Default: patchright (mid-stealth, Playwright API)
  ├─ Stealth: CloakBrowser (high-stealth, same API, patched binary + humanize)
  └─ Future: Camoufox (Firefox stealth, different API)

Remote browser:
  └─ RemoteBridge (real Chrome, inherently real fingerprint)
```

## Core Abstraction — BrowserContext Protocol (D6)

六方法 + 两属性的统一协议，所有后端（Patchright/Cloak/RemoteBridge）实现此接口。CLI 和 daemon 只与 Protocol 交互，后端选择在 launch 时透明决定。详见 `spec/browser/browser-backend-contract.md`。

## Reuse Strategy (D7)

| Project | Reuse Mode | What |
|---|---|---|
| bb-browser | Port to Python | seq+since model, three-field error envelope |
| OpenCLI | Port to Python | Strategy enum, pipeline DSL |
| CloakBrowser | pip dependency | Stealth backend, humanize layer |
| Scrapling | pip dependency + extract | StealthyFetcher, Cloudflare solver |
| GenericAgent | Extract + rewrite | TMWebDriver connection model |
| pinchtab | Port to Python | Endpoint catalog, IDPI security |

---

## Phase Roadmap (D8)

### Phase 0: Skeleton runs (done)

daemon + CLI + local browser basics

- PatchrightContext as default backend
- daemon (aiohttp), seq counter, tab manager, ring buffer
- CLI (typer), JSON output, three-field error envelope
- Commands: open, screenshot, execute-js, snapshot, network, console, tab, doctor
- Deliverable: **agent can open pages, screenshot, execute JS, see network requests**
- Ref: `research/ai-browser-agents.md`（selector_map、seq 模型）, `research/browser-cli-platforms.md`（bb-browser seq+since、三字段 envelope）

### Phase 1: Full interaction (done)

- click/fill/type/scroll/hover/select/press (accessibility-tree `[N]` ref driven)
- `network requests --since last_action` filtering
- `fetch` with cookie (Strategy: COOKIE)
- `profile create/list/launch/delete`
- Deliverable: **agent can interact with pages, reuse login states**
- Ref: `research/ai-browser-agents.md`（browser-use multi_act + terminates_sequence、open-codex --calls-file batch）, `research/browser-cli-platforms.md`（bb-browser/OpenCLI action 集合）, `research/neo-analyzer-wireshark.md`（neo v2 a11y interaction）

### Phase 2: Stealth layer (done)

- [x] CloakBrowser integration (`--stealth`) — pip optional dep, CloakContext subclass
- [x] Xvfb + humanize behavioral layer — XvfbManager auto-spawn/cleanup
- [x] Cloudflare Turnstile bypass — screenX patch extension (Manifest V3, MAIN world)
- [x] httpcloak LocalProxy — tls_only transparent proxy for fetch, graceful degradation
- Deliverable: **agent can bypass most anti-bot detection**
- Ref: `research/browser-stealth.md`（CloakBrowser/httpcloak/Scrapling/Camoufox）, `reference/doc/sop/Cloudflare Turnstile*`、`reference/doc/sop/hCaptcha*`、`reference/doc/sop/滑块拼图*`

### Phase 3: Remote bridge (done)

- [x] Chrome MV3 extension (debugger/cookies/tabs, WS to bridge, CDP command routing)
- [x] Python bridge process (WS hub, extension ↔ daemon routing, auto-reconnect)
- [x] RemoteBridgeContext (BrowserContext Protocol over WS)
- [x] Daemon `/bridge/ws` endpoint + bridge CLI commands
- [x] Bridge config with daemon candidate list auto-probe
- [x] WS token auth (localhost bypass, Bearer token for remote)
- [x] Cookie/session export (`browserctl cookies export`)
- [x] Extension install guidance (first-run auto-open chrome://extensions)
- [x] PyInstaller build spec (`scripts/build_bridge.py`)
- [x] mDNS auto-discovery (optional zeroconf, daemon register + bridge discover)
- Deliverable: **agent operates shayu's real browser remotely**
- Ref: `research/browser-cli-platforms.md`（GenericAgent TMWebDriver WS+HTTP 双传输）, `reference/doc/sop/TMWebdriver*`、`reference/doc/sop/TMWebDriver CDP*`

### Phase 4: Adapter platform (done)

- [x] Strategy enum (PUBLIC/COOKIE/HEADER/INTERCEPT/UI) + `@adapter` decorator + AdapterRegistry
- [x] Pipeline DSL (declarative) + Function (async def) dual mode
- [x] Template engine with `{path}` syntax, 7 built-in pipeline steps
- [x] CaptureStore — full request/response recording with auto-filtering
- [x] HAR 1.2 import/export (to_har/from_har)
- [x] PatternAnalyzer — path parameterization, endpoint clustering, auth detection, schema inference
- [x] AdapterGenerator — API pattern → pipeline adapter Python code
- [x] `site list/info/run/scaffold` CLI commands
- [x] `capture start/stop/status/export/analyze/clear` CLI commands
- [x] Daemon `/capture/*` endpoints
- [x] Adapter auto-discovery (built-in + user directory)
- Deliverable: **common site operations as one-liner commands**
- Ref: `research/browser-cli-platforms.md`（OpenCLI Strategy enum + pipeline DSL、bb-browser @meta adapter）, `research/neo-analyzer-wireshark.md`（neo schema synthesis + workflow discover）

### Phase 5: Skill + integration (in progress)

- [x] MCP server (10 tools, FastMCP + stdio bridge to daemon)
- [x] jshookmcp CDP coordination (browserctl_cdp_endpoint + /cdp/endpoint)
- [x] Response body capture fix (async handler + 100KB truncation)
- [x] Enhanced /health (stealth_tier, current URL, capture state)

#### Phase 5c: UX + daemon auto-start (done)

- [x] daemon auto-start from MCP (DaemonBridge auto-start on first request)
- [x] MCP site run tool (browserctl_adapter_run + browserctl_adapter_list)
- [x] CLI cdp endpoint 命令 (`browserctl cdp endpoint`)
- [x] 多 tab 管理 (tab list/new/close/switch — browser + daemon + CLI + MCP)
- Deliverable: **frictionless daemon startup, multi-tab agent workflows**

#### Phase 5d: IDPI 安全层 (done)

- [x] Domain whitelist + blacklist (glob matching, `file://`/`data:`/`javascript:` always blocked)
- [x] Content scan framework (off by default, user-configured regex patterns)
- [x] `<untrusted_web_content>` wrapping for non-whitelisted domains
- [x] SecureBrowserContext wrapper — all backends protected transparently
- Deliverable: **opt-in IDPI three-layer security model**

### Phase 5 施工准则

> **CLI / MCP 能力同步**：每个新增或修改的能力，必须同时暴露到 CLI 命令和 MCP tool。不允许出现"CLI 有但 MCP 没有"或反过来的情况。两者共享 daemon route，保持接口一致。
>
> **Skill 文件跟进**：每个 Phase 完成后，更新 Skill 文件（`skills/agentcloak/SKILL.md` + `.claude/skills/agentcloak/SKILL.md`）反映新能力、变更的参数、废弃的 flag。Skill 是 agent 的主要使用指南，必须和实际能力同步。

#### Phase 5e: 后端重构（隐身层简化）(done)

基于竞品分析（`spec/guides/competitive-analysis.md`）确认的架构变更。

- [x] 移除 Patchright 依赖，CloakBrowser 提升为必装依赖
- [x] `cloak_ctx.py`: `backend="patchright"` 移除（CloakBrowser 默认 playwright）
- [x] `browser/__init__.py`: 默认 tier 改为 CLOAK，humanize=False
- [x] `PatchrightContext` 重命名为 `PlaywrightContext`，import 改为 `playwright.async_api`
- [x] `--stealth` flag 废弃（发 deprecation warning，隐藏 flag）
- [x] 配置文件支持 `humanize = true/false`（config.toml + env var）
- [x] BrowserContext Protocol 增加 `raw_cdp()` 透传方法
- [x] Skill 文件、spec、doctor 命令同步更新
- Deliverable: **CloakBrowser 默认，依赖链简化，Playwright CDP 天花板打开**
- 依据: CloakBrowser 包体积更小（15MB vs 137MB），57 C++ patch 已覆盖 Patchright 驱动层修复，Patchright 反而破坏 proxy auth
- Ref: `reference/CloakBrowser/README.md`（CloakBrowser API + backend 选项 + humanize 配置）, `spec/guides/competitive-analysis.md`（第二层对比 + Patchright 移除决策依据）

#### Phase 5f: Snapshot 增强 + 渐进加载 (done)

snapshot 从扁平列表重写为树形结构，完整提取 ARIA 属性，渐进加载支持大页面。

- [x] Shadow DOM 穿透（`pierce: True`）
- [x] 添加 ARIA 状态输出（expanded、checked、selected、disabled、pressed、invalid、required、focused、hidden）
- [x] 添加输入框当前值（value/valuetext/valuemin/valuemax/valuenow）
- [x] 密码字段脱敏（`value="••••"`）
- [x] 零宽字符清理（BOM、ZWS、ZWNJ、ZWJ、word joiner）
- [x] StaticText 聚合去重
- [x] 扩充 INTERACTIVE_ROLES（+6: dialog、alertdialog、grid、listbox、tree、menu）
- [x] 新增 CONTEXT_ROLES（toolbar、tabpanel、figure、table、form、status、alert 等 14 个）
- [x] 缩进树形输出（2 空格，childIds 重建父子关系）
- [x] generic 节点折叠（无名 + 单子节点 → 提升）
- [x] compact 模式压缩树形（自底向上祖先保留算法）
- [x] 渐进加载：daemon 缓存完整 snapshot + 节点级截断 + 摘要目录
- [x] `--focus=N` 子树展开（含祖先面包屑）
- [x] `--offset=N` 分页
- [x] `--max-nodes=N` 统一截断控制（节点级，默认 150/80）
- [x] DRY 重构：accessible/compact 合并为统一 `_build_snapshot()`
- [x] Skill 文件更新
- [x] CLI / MCP / daemon 新参数同步
- Deliverable: **agent 页面感知能力对齐竞品水平，大页面可渐进探索**
- 推后项: ref 版本号机制、`*[N]` diff 标记、iframe 嵌套、cursor:pointer 发现、link URL 提取
- Ref: `reference/agent-browser`（@eN ref + 缩进树形 + 200-400 token）, `reference/pinchtab`（eN + diff + token 预算）, `spec/guides/competitive-analysis.md`（第三层对比 + 渐进加载设计）

#### Phase 5g: 交互补齐 + Proactive State Feedback (done)

Playwright API 已支持，暴露到 BrowserContext Protocol → daemon → CLI/MCP 链路。

- [x] Proactive State Feedback 机制（action 返回值主动包含 pending_requests/dialog/navigation/download/current_value）
- [x] 对话框处理（`page.on("dialog")` — alert/beforeunload 自动 accept，confirm/prompt 暂存等 agent 处理）
- [x] 条件等待（`wait --selector/--url/--load/--js/--ms`，直接映射 Playwright API）
- [x] keyboard 组合键（`press --key "Control+a"` Playwright 原生 `+` 语法 + `keydown`/`keyup` 独立命令）
- [x] 文件上传（`upload --index N --file path`，Playwright `set_input_files()`）
- [x] frame 切换（`frame list` / `frame focus --name/--url/--main`，Playwright Frame API）
- [x] 高危操作日志（evaluate/upload 审计日志，structlog）
- [x] 批量模式增强（dialog 中断 + read-after-write settle + wait 作为 batch step）
- [x] Config 扩展（action_timeout/batch_settle_timeout，env var 覆盖）
- [x] Skill 文件更新：新增交互命令用法、feedback 机制、dialog/wait/upload/frame
- [x] CLI / MCP / daemon 同步：14 个新 MCP tool，4 个新 CLI command group，6 个新 daemon route
- Deliverable: **交互覆盖补齐，proactive state feedback，agent 操作流畅性大幅提升**
- 推后项: network route 拦截（`page.route()`）、drag & drop、剪贴板
- Ref: `reference/agent-browser`（54+ commands, wait/dialog/frame/keyboard）, `reference/GenericAgent`（对话框抑制 + CSP 剥离实现参考）, `spec/guides/competitive-analysis.md`（第四/五/六层对比）, `spec/guides/proactive-state-feedback.md`（设计原则）

#### Phase 5h: RemoteBridge 能力对齐 + 共享层重构 (done)

- [x] 共享 Snapshot Builder：`_snapshot_builder.py` 抽取，两端复用同一套树构建/compact/ARIA/渐进加载逻辑
- [x] RemoteBridge snapshot 对齐：compact 模式、ARIA 状态、渐进加载、backendDOMNodeId 精确元素定位
- [x] Extension 可靠性：chrome.alarms keepalive、双执行路径（scripting + CDP fallback）、CDP navigate 等待、状态持久化
- [x] RemoteBridge action 补齐：scroll/hover/select/dialog/wait/upload/frame 全部 CDP 实现
- [x] 多 Frame AX Tree 合并：`--frames` 参数，iframe 内容自动嵌入 snapshot 树（两端）
- [x] Snapshot Diff：`--diff` 参数，标记 `[+]` 新增 / `[~]` 变更 / removed 摘要（两端）
- [x] includeSnapshot：action 返回可选附带 compact snapshot（daemon 层，两端）
- [x] $N Batch 引用：batch 命令支持 `$N.path` 结果引用（daemon 层，两端）
- [x] Stale Ref 自动重试：element_not_found 自动 re-snapshot + 重试一次（daemon 层，两端）
- [x] 统一端口范围：daemon 默认端口 9222→18765，与 bridge 共享 18765-18774
- [x] 模式自适应连接：Extension 同时发现 daemon/bridge，优先 daemon 直连；daemon 新增 `/ext` endpoint
- [x] Tab Claiming：`bridge claim` 接管用户已打开的标签页
- [x] Tab Group：agent 操作的 tab 自动归入蓝色 "agentcloak" Chrome tab group
- [x] Session Finalize：`bridge finalize` 三种模式（close/handoff/deliverable）
- [x] Skill 文件更新
- Deliverable: **RemoteBridge 生产可用，共享层消除重复，通用增强两端受益**
- 推后项: jshook 松耦合（另开 Skill），Camoufox 后端，network route 拦截，drag & drop，剪贴板
- Ref: `reference/chrome-devtools-mcp`（CLI 自动生成、Skill 拆分、includeSnapshot）, `reference/open-codex-browser-use`（tab group、session lifecycle）, `reference/pinchtab`（eN ref、snapshot diff、multi-frame）, `reference/GenericAgent`（alarms keepalive、双执行路径、$N batch）

#### Phase 5i: 端到端测试 + 发布

测试与稳定性：
- [ ] daemon + 真实浏览器集成测试
- [ ] 错误恢复（daemon 崩溃重连、浏览器意外关闭）
- [ ] CLI / MCP 能力一致性检查（自动化验证两侧参数和输出格式对齐）

CI / 工程基础：
- [ ] GitHub Actions CI（ruff + pyright + pytest unit + build check）
- [ ] 独立 LICENSE 文件（MIT）
- [ ] SECURITY.md（威胁模型、漏洞报告方式、cookie/profile/bridge 安全边界）

CLI / MCP 接口审查：
- [ ] CLI 命令名和参数一致性审查（`open` 加 `navigate` 别名，高频参数统一为选项风格）
- [ ] MCP 工具名和参数一致性审查（与 CLI 对齐，参数命名统一）
- [ ] agent 易用性测试（不加载 Skill 的情况下，agent 能否凭直觉正确使用命令）

文档与发布：
- [ ] README 拆分（README 保持轻量 quickstart，长内容迁到 `docs/`）
- [ ] Skill 文件 final packaging（反映 Phase 5e-5h 全部新能力）
- [ ] Demo 素材（GIF / asciinema：CLI 完整案例 + MCP 集成案例）
- [ ] 稳定性矩阵（各后端 × 各平台的支持状态表）
- [ ] PyPI 发布 + GitHub Releases
- [ ] Docker 分发（基于 CloakBrowser 官方 image `cloakhq/cloakbrowser`）
- Deliverable: **production-ready release with CI, docs, and ecosystem readiness**
- Ref: `research/neo-analyzer-wireshark.md`（Wireshark-MCP installer 模式）

---

## Key Design Decisions

### Page Addressing (D9)

`selector_map` + dual mode: numeric index `[N]` primary, coordinate `(x, y)` fallback.
> Note: `*[N]` 新元素标记尚未实现（参考 OpenCLI，列入 Phase 5f 待评估）。

### Batch Invocation (D10)

`--calls-file batch.json --sleep 0.15`。每个 action 前后检测 URL/focus 变化，变化则中止剩余 action 返回 partial results。

### Triple-Surface Architecture (D11, D17, D21)

Skill + CLI（主推，~300 tokens）> MCP（兼容选项，~6000 tokens）> jshook 松耦合（逆向场景）。
MCP token 开销是 CLI 的 20 倍（参考 mariozechner.at 分析），Bash-capable agent 推荐 CLI 模式。

### HybridSession (D12)

Browser ↔ httpx mode switching with automatic cookie + UA + header sync.

### Remote Bridge via Chrome Extension (D14)

Zero-setup Chrome extension on Windows, auto-connect back to Linux daemon via WebSocket.

### Captcha Solver Strategy (D19)

Three-tier: Cloudflare Turnstile (screenX patch) → Slider (CV + trajectory) → hCaptcha (physical mouse only).

---

## Research References

- SOP documents: `reference/doc/sop/` (11 files, CDP/Captcha/Vision/jshookmcp patterns)
- Full research notes: `.trellis/tasks/archive/2026-05/05-06-reference-projects-research/research/`
