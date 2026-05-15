# Security model (IDPI)

agentcloak includes an opt-in IDPI (Indirect Prompt Injection) security layer that protects agents from malicious web content. The three-layer model covers domain access control, content scanning, and untrusted content wrapping.

This guide will cover domain whitelist and blacklist configuration (glob patterns), content scan regex patterns, the `<untrusted_web_content>` wrapping mechanism for non-whitelisted domains, and how the SecureBrowserContext wrapper applies these protections transparently across all backends.

Detailed content will be added in a future update. See the [configuration reference](../reference/config.md) for security settings.
