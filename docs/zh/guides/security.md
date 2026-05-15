# 安全模型（IDPI）

agentcloak 内置了可选的 IDPI（间接提示注入）安全层，保护 agent 免受恶意网页内容的攻击。三层模型涵盖域名访问控制、内容扫描和不可信内容包裹。

本指南将涵盖域名白名单和黑名单配置（glob 模式）、内容扫描正则模式、非白名单域名的 `<untrusted_web_content>` 包裹机制，以及 SecureBrowserContext 包装器如何在所有后端上透明地应用这些保护。

详细内容将在后续更新中补充。安全相关设置参见[配置参考](../reference/config.md)。
