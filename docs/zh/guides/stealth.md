# 隐身与反检测

agentcloak 的隐身能力基于 CloakBrowser，一个搭载了 57 个 C++ 修改的补丁版 Chromium 二进制文件，针对指纹识别和机器人检测系统。

本指南将涵盖三层隐身架构、Cloudflare Turnstile 绕过、拟人行为模拟、通过 httpcloak 的 TLS 指纹保护，以及如何使用常见检测测试验证隐身配置。

详细内容将在后续更新中补充。目前请参见[后端指南](./backends.md)了解 CloakBrowser 配置。
