# 网络流量捕获与 API 分析

agentcloak 可以录制网络流量、导出为 HAR 1.2 格式，并自动检测 API 模式。捕获到的模式可以用于生成 spell -- 直接调用 API 的可复用自动化命令。

本指南将涵盖捕获工作流（start/stop/export/analyze）、HAR 导入/导出、模式分析（端点聚类、认证检测、schema 推断），以及 spell 生成管道。

详细内容将在后续更新中补充。可用的捕获命令参见 [CLI 参考](../reference/cli.md#捕获与-spell)。
