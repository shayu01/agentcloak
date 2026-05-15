# Spells

Spells wrap common site operations as one-liner commands. They can be written as declarative pipeline DSL or async Python functions, and support five strategy levels: PUBLIC, COOKIE, HEADER, INTERCEPT, and UI.

This guide will cover the spell system architecture, writing custom spells with the `@spell` decorator, pipeline DSL syntax, auto-discovery from built-in and user directories, and the scaffold command for generating spell templates.

Detailed content will be added in a future update. See the [CLI reference](../reference/cli.md#capture-and-spells) for `spell list`, `spell run`, `spell info`, and `spell scaffold` commands.
