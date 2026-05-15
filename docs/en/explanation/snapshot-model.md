# Snapshot model

agentcloak represents web pages as accessibility trees where each interactive element gets a `[N]` reference number. This model lets agents interact with pages through stable indices rather than fragile CSS selectors.

This page will explain the snapshot architecture in depth: how the accessibility tree is built from Chrome's AX tree, the compact mode pruning algorithm, ARIA state extraction, progressive loading with focus/offset/max-nodes, multi-frame tree merging, snapshot diffing, and the relationship between `[N]` references and the underlying DOM elements.

Detailed content will be added in a future update. For practical usage, see the [quick start tutorial](../getting-started/quickstart.md).
