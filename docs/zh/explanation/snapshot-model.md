# Snapshot 模型

agentcloak 将网页表示为无障碍树，每个可交互元素分配一个 `[N]` 引用编号。这个模型让 agent 通过稳定的索引与页面交互，而非脆弱的 CSS 选择器。

本页面将深入解释 snapshot 架构：如何从 Chrome 的 AX tree 构建无障碍树、compact 模式的剪枝算法、ARIA 状态提取、通过 focus/offset/max-nodes 实现的渐进加载、多 frame 树合并、snapshot diff，以及 `[N]` 引用与底层 DOM 元素之间的关系。

详细内容将在后续更新中补充。实际用法参见[快速开始教程](../getting-started/quickstart.md)。
