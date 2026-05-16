# 网络流量捕获与 API 分析

capture 系统会记录浏览器发出的每一个有意义的 HTTP 请求，导出为 HAR 1.2 格式，并能分析流量以发现可以做成 spell 的 API 模式。在准备脚本化一个站点之前，用它来摸清楚站点是怎么和后端通信的。

## 快速开始

```bash
cloak capture start                  # 启动录制
cloak navigate "https://example.com" # 浏览、点击、滚动——任意操作
cloak capture stop                   # 停止录制
cloak capture export -o traffic.har  # 导出可被 DevTools 打开的 HAR 1.2 文件
```

只要录制处于启动状态，后续的每次 navigation 和 `do` action 都会收集请求，直到你停止。

## 录制

| 命令 | 用途 |
|------|------|
| `cloak capture start` | 开始录制；不会清空已有数据（上次会话的条目保留） |
| `cloak capture stop` | 停止录制；缓冲区保留所有内容直到你 `clear` |
| `cloak capture status` | 查看录制是否激活、已存多少条目 |
| `cloak capture clear` | 清空缓冲区 |

存储有 5000 条目的滚动容量上限。超过后最老的条目会被淘汰——长时间会话建议定期导出。

### 默认录制什么

自动录制：
- HTML、JSON、纯文本、XML、form-urlencoded 的请求和响应体
- 全部请求和响应 header
- method、URL、status、时间、resource type

默认过滤掉：
- 静态资源：`.js`、`.css`、图片、字体、媒体、ico
- manifest、`other` 类型
- 响应体超过 100 KB 的部分被截断

这套过滤器正是让 5000 条目容量足够用的关键——纯 API 流量被保留，页面"装修件"被排除。

## 导出

```bash
cloak capture export                       # HAR 1.2 输出到 stdout
cloak capture export --format json         # 原始 JSON（请求/响应对）
cloak capture export --format har -o out.har
```

HAR 导出可以直接被 Chrome DevTools（Network 面板 → 右键 → Import HAR）和任何兼容 HAR 的工具（Charles、Fiddler、Postman）打开。JSON 导出是 analyzer 消费的格式。

## 分析

```bash
cloak capture analyze              # 全部 domain
cloak capture analyze --domain api.example.com
```

analyzer 检查捕获到的流量，报告：

- **端点聚类**——共享同一路径模板的 URL（`/api/users/123`、`/api/users/456` → `/api/users/{id}`）
- **路径参数**——不同调用之间变化的段 vs 固定段
- **认证检测**——Bearer token、session cookie、自定义 header
- **请求 schema**——从样本推断的 JSON 请求体结构
- **响应 schema**——JSON 响应结构

输出是结构化 JSON，可直接驱动代码生成。

## Replay

```bash
cloak capture replay "https://api.example.com/data"
cloak capture replay "https://api.example.com/submit" --method POST
```

重新发出与 URL + method 匹配的最近一次捕获请求。使用 agent 当前的 cookie 和 header，所以会话刷新后也能 replay。

## 从 capture 到 spell

capture 喂入 spell 生成。完整流程：

```bash
# 1. 录制真实操作
cloak capture start
cloak navigate "https://target-site.com"
# 登录、点击、走一遍想自动化的流程
cloak capture stop

# 2. 看看发现了什么
cloak capture analyze --domain target-site.com

# 3. 从模式生成 spell 模板
cloak spell scaffold target-site --domain target-site.com
```

`spell scaffold` 会在 `~/.config/agentcloak/spells/` 下写出 Python 文件，`@spell(...)` 装饰器已根据 analyzer 的发现预填——端点 URL、method、检测到的认证策略、推断出的请求/响应 schema。你再润色生成代码、写单测、然后 `cloak spell run`。

spell 这一侧详见 [spells 指南](./spells.md)。

## 故障排查

**"我的请求没出现"**——检查 resource type。静态资源（`.js`、`.css`、图片）被过滤。用 `cloak capture status` 确认触发请求时录制是开着的。

**"响应体为空或截断"**——超过 100 KB 的响应体被截断。二进制 content type（图片、视频）只录 header。需要完整 body 时用 `cloak fetch URL` 重新拉。

**"daemon 重启后 capture 还在"**——不应该。capture store 只在内存。如果 `status` 在重启后还显示有条目，说明 daemon 其实没真的重启过——用 `cloak daemon health` 查 PID。
