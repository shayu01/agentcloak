# CLI 参考

agentcloak 提供两个等效的 CLI 入口：`agentcloak` 和 `cloak`（简写）。以下示例统一使用 `cloak`。

每个命令在 stdout 输出一个 JSON 对象：

```json
{"ok": true, "seq": 3, "data": {...}}
```

错误包含恢复建议：

```json
{"ok": false, "error": "error_code", "hint": "description", "action": "suggested next step"}
```

## 导航与观察

### navigate

导航浏览器到指定 URL。

```bash
cloak navigate URL [--timeout SECONDS] [--snapshot] [--snapshot-mode MODE]
```

| 参数 | 默认值 | 说明 |
|------|-------|------|
| `--timeout` | `30` | 等待页面加载的最大秒数 |
| `--snapshot` | 关闭 | 在响应中包含无障碍树 snapshot |
| `--snapshot-mode` | `compact` | 使用 `--snapshot` 时的 snapshot 模式 |

### snapshot

获取带有 `[N]` 元素引用的无障碍树。

```bash
cloak snapshot [--mode MODE] [--max-nodes N] [--focus N] [--offset N] [--frames] [--diff]
```

| 参数 | 默认值 | 说明 |
|------|-------|------|
| `--mode` | `accessible` | `accessible`、`compact`、`content` 或 `dom` |
| `--max-nodes` | `0` | 在 N 个节点后截断（0 = 不限制） |
| `--focus` | `0` | 展开元素 `[N]` 周围的子树 |
| `--offset` | `0` | 从第 N 个元素开始输出（分页） |
| `--frames` | 关闭 | 包含 iframe 内容 |
| `--diff` | 关闭 | 标记与上一次 snapshot 相比的变更 |

### screenshot

截取当前页面的屏幕截图。

```bash
cloak screenshot [--output FILE] [--full-page] [--format FORMAT] [--quality N]
```

| 参数 | 默认值 | 说明 |
|------|-------|------|
| `--output` | stdout | 保存到文件而非在 JSON 中返回 base64 |
| `--full-page` | 关闭 | 捕获完整可滚动页面 |
| `--format` | `jpeg` | `jpeg` 或 `png` |
| `--quality` | `80` | JPEG 质量 0-100（PNG 时忽略） |

### resume

获取会话状态用于上下文恢复。

```bash
cloak resume
```

返回当前 URL、打开的标签页、最近 5 次操作、捕获状态和隐身等级。

## 交互

### click

通过 `[N]` 引用点击元素。

```bash
cloak click --target N [--snapshot]
```

### fill

清空输入框并设置值。

```bash
cloak fill --target N --text "value" [--snapshot]
```

### type

逐字符输入文本（触发按键事件）。

```bash
cloak type --target N --text "value" [--snapshot]
```

### press

按下键盘按键或组合键。

```bash
cloak press --key KEY [--target N] [--snapshot]
```

按键名称使用 Playwright 语法：`Enter`、`Tab`、`Escape`、`Control+a`、`Shift+ArrowDown`。

### scroll

滚动页面。

```bash
cloak scroll --direction DIRECTION [--snapshot]
```

方向：`up` 或 `down`。

### hover

悬停在元素上。

```bash
cloak hover --target N [--snapshot]
```

### select

选择下拉选项。

```bash
cloak select --target N --value "option" [--snapshot]
```

> [!NOTE]
> 所有交互命令支持 `--snapshot` 在响应中附带 compact snapshot，省去一次往返请求。

## 内容与网络

### js evaluate

在页面上下文中执行 JavaScript。

```bash
cloak js evaluate "expression"
```

默认在页面主世界运行。页面全局对象（jQuery、Vue、React 等）均可访问。

### fetch

使用浏览器的 cookie 和 user agent 发起 HTTP 请求。

```bash
cloak fetch URL [--method METHOD] [--body BODY] [--headers-json JSON]
```

### network requests

列出最近的网络请求。

```bash
cloak network requests [--since SEQ]
```

使用 `--since last_action` 查看最近一次操作触发的请求。

### network console

列出控制台消息。

```bash
cloak network console [--since SEQ]
```

## 对话框处理

### dialog status

检查是否有待处理的浏览器对话框。

```bash
cloak dialog status
```

### dialog accept / dismiss

处理待处理的对话框。

```bash
cloak dialog accept [--text "reply"]
cloak dialog dismiss
```

## 等待

### wait

等待满足指定条件后继续。

```bash
cloak wait --selector "CSS_SELECTOR"
cloak wait --url "**/dashboard"
cloak wait --load networkidle
cloak wait --js "document.readyState === 'complete'"
cloak wait --ms 2000
```

| 参数 | 说明 |
|------|------|
| `--selector` | 等待 CSS 选择器出现 |
| `--url` | 等待 URL 匹配（glob 模式） |
| `--load` | 等待加载状态（`load`、`domcontentloaded`、`networkidle`） |
| `--js` | 等待 JS 表达式返回真值 |
| `--ms` | 休眠 N 毫秒 |
| `--timeout` | 最大等待时间（毫秒，默认 30000） |

## 文件上传

### upload

向文件输入元素上传文件。

```bash
cloak upload --index N --file /path/to/file [--file /path/to/another]
```

## Frame 管理

### frame list

列出页面中的所有 frame。

```bash
cloak frame list
```

### frame focus

切换到指定 frame。

```bash
cloak frame focus --name "frame-name"
cloak frame focus --url "partial-url"
cloak frame focus --main
```

## 捕获与 spell

### capture start / stop

控制网络流量录制。

```bash
cloak capture start
cloak capture stop
```

### capture status

检查录制状态。

```bash
cloak capture status
```

### capture export

导出捕获的流量。

```bash
cloak capture export --format har [-o output.har]
cloak capture export --format json
```

### capture analyze

从捕获的流量中自动检测 API 模式。

```bash
cloak capture analyze [--domain example.com]
```

### capture clear

删除所有捕获数据。

```bash
cloak capture clear
```

### spell list

列出所有已注册的 spell。

```bash
cloak spell list
```

### spell run

运行命名 spell。

```bash
cloak spell run NAME [--args-json '{"key": "value"}']
```

### spell info

获取 spell 详情。

```bash
cloak spell info NAME
```

### spell scaffold

生成 spell 模板。

```bash
cloak spell scaffold SITE COMMAND
```

## Profile 管理

### profile create

创建命名的浏览器 profile。

```bash
cloak profile create NAME [--from-current]
```

`--from-current` 从当前活跃浏览器会话复制 cookie。

### profile list

列出所有已保存的 profile。

```bash
cloak profile list
```

### profile launch

使用已保存的 profile 启动浏览器。

```bash
cloak profile launch NAME
```

### profile delete

删除已保存的 profile。

```bash
cloak profile delete NAME
```

## 标签页管理

### tab list

列出已打开的浏览器标签页。

```bash
cloak tab list
```

### tab new

打开新标签页。

```bash
cloak tab new [--url URL]
```

### tab close

按 ID 关闭标签页。

```bash
cloak tab close --tab-id N
```

### tab switch

按 ID 切换标签页。

```bash
cloak tab switch --tab-id N
```

## Bridge 命令

### bridge claim

接管用户已打开的标签页（仅 RemoteBridge）。

```bash
cloak bridge claim --tab-id N
cloak bridge claim --url-pattern "dashboard"
```

### bridge finalize

结束 agent 会话（仅 RemoteBridge）。

```bash
cloak bridge finalize --mode close        # 关闭 agent 标签页
cloak bridge finalize --mode handoff      # 保留标签页给用户
cloak bridge finalize --mode deliverable  # 将 group 重命名为 "results"
```

## Cookie 管理

### cookies export

从浏览器导出 cookie（本地或 RemoteBridge）。

```bash
cloak cookies export
```

### cookies import

向浏览器注入 cookie，支持 httpOnly。

```bash
cloak cookies import -c '[{"name":"token","value":"abc","domain":".example.com","path":"/"}]'
```

## 配置

### config

显示合并后的配置及每个值的来源（default / config.toml / 环境变量）。

```bash
cloak config
```

## Daemon 管理

### daemon start

启动后台 daemon。

```bash
cloak daemon start [--host HOST] [--port PORT] [--headed] [--profile NAME]
```

### daemon stop

停止运行中的 daemon。

```bash
cloak daemon stop
```

### daemon health

检查 daemon 状态。

```bash
cloak daemon health
```

## 诊断

### doctor

运行诊断检查。

```bash
cloak doctor
```

检查 Python 版本、CloakBrowser 状态、daemon 连通性和配置。

### cdp endpoint

获取 CDP WebSocket URL（供 jshookmcp 或其他 CDP 工具使用）。

```bash
cloak cdp endpoint
```
