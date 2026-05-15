# 快速开始

本教程介绍 agentcloak 的核心工作流：导航到页面、通过无障碍树 snapshot 读取页面、与元素交互、验证结果。

## 观察-操作循环

agentcloak 基于一个简单的循环：

1. **导航**到页面
2. **Snapshot** 查看带有 `[N]` 元素引用的无障碍树
3. **操作**元素，使用其 `[N]` 引用编号
4. **重新 snapshot**（页面更新后引用编号会变化）

## 首次运行

daemon 在首次命令时自动启动，无需手动设置。

```bash
# 导航并一步获取 snapshot
cloak navigate "https://example.com" --snapshot
```

输出同时包含导航结果和页面 snapshot：

```json
{
  "ok": true,
  "seq": 1,
  "data": {
    "url": "https://example.com/",
    "title": "Example Domain",
    "snapshot": {
      "tree_text": "[1] <heading level=1> Example Domain\n  More information...\n[2] <link> More information...",
      "mode": "compact",
      "total_nodes": 5,
      "total_interactive": 2
    }
  }
}
```

## 阅读 snapshot

snapshot 是一棵无障碍树，每个可交互元素分配一个 `[N]` 引用：

```
[1] <heading level=1> Example Domain
  More information...
[2] <link> More information...
```

- `[1]` 是标题 -- 不可交互，但有索引方便引用
- `[2]` 是可点击链接

元素展示其 ARIA 角色、名称和状态。输入字段包含当前值。缩进表示页面层级结构。

### Snapshot 模式

| 模式 | 显示内容 | 使用场景 |
|------|---------|---------|
| `accessible` | 完整无障碍树，带 `[N]` 引用和 ARIA 状态、值 | 默认 -- 完整页面视图 |
| `compact` | 仅可交互元素和命名容器 | action 之后 -- 输出更小 |
| `content` | 文本提取 | 阅读文章或文本密集页面 |
| `dom` | 原始 HTML | 调试或 CSS 选择器相关工作 |

```bash
cloak snapshot --mode compact    # 仅可交互元素
cloak snapshot --mode content    # 文本提取
```

## 与元素交互

使用 snapshot 中的 `[N]` 引用作为操作目标：

```bash
# 点击链接
cloak click --target 2

# 填充文本字段
cloak fill --target 5 --text "search query"

# 按键
cloak press --key Enter --target 5

# 选择下拉选项
cloak select --target 8 --value "option-2"
```

### 获取操作后状态

给任何 action 命令添加 `--snapshot` 可在同一响应中获取 snapshot：

```bash
cloak click --target 2 --snapshot
```

相比操作后单独运行 `cloak snapshot`，这省去了一次往返请求。响应中在 action 结果旁包含一个 `snapshot` 对象。

## 完整登录示例

```bash
# 导航到登录页并获取 snapshot
cloak navigate "https://example.com/login" --snapshot

# Snapshot 输出：
# [1] <heading level=1> Sign In
# [2] <textbox> Email
# [3] <textbox type=password> Password
# [4] <button> Sign In

# 填写凭据
cloak fill --target 2 --text "user@example.com"
cloak fill --target 3 --text "my-password"

# 提交并获取新 snapshot
cloak click --target 4 --snapshot

# 保存登录状态以便复用
cloak profile create my-session
```

下次使用保存的 profile 启动：

```bash
cloak daemon start --profile my-session
cloak navigate "https://example.com/dashboard" --snapshot
```

## 网络监控

查看页面发出的网络请求：

```bash
# 查看最近的请求
cloak network requests

# 仅查看上一次操作以来的请求
cloak network requests --since last_action
```

## 截图

```bash
# 视口截图（JPEG，比 PNG 小约 75-85%）
cloak screenshot

# 完整可滚动页面
cloak screenshot --full-page

# PNG 格式获取像素级精确度
cloak screenshot --format png

# 保存到文件
cloak screenshot --output page.png
```

## 处理大页面

对于元素众多的页面，使用渐进加载：

```bash
# 限制输出为 80 个节点
cloak snapshot --max-nodes 80

# 分页浏览结果
cloak snapshot --offset 80 --max-nodes 80

# 聚焦特定元素的子树
cloak snapshot --focus 15

# 查看操作后的变更
cloak snapshot --diff
```

## 捕获 API 流量

录制和分析网络流量以发现 API 模式：

```bash
cloak capture start
cloak navigate "https://api-heavy-site.com"
# 与页面交互...
cloak capture stop

# 导出为 HAR
cloak capture export --format har -o traffic.har

# 自动检测 API 模式
cloak capture analyze
```

详情参见[流量捕获指南](../guides/capture.md)。

## 输出格式

每个命令在 stdout 输出一个 JSON 对象：

```json
{"ok": true, "seq": 3, "data": {"url": "https://example.com", "title": "Example"}}
```

错误包含恢复建议：

```json
{"ok": false, "error": "element_not_found", "hint": "No element at index 99", "action": "re-snapshot to get fresh [N] refs"}
```

`seq` 是单调递增计数器，每次浏览器状态变化时递增。使用 `jq` 解析：

```bash
cloak snapshot | jq -r '.data.tree_text'
```

## 后续步骤

- [CLI 参考](../reference/cli.md) -- 所有命令和参数
- [浏览器后端](../guides/backends.md) -- CloakBrowser 与 Playwright 与 RemoteBridge 对比
- [MCP 配置](../guides/mcp-setup.md) -- 通过 MCP 从 AI 客户端连接
- [配置参考](../reference/config.md) -- 自定义 daemon 行为
