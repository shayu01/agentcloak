# Quick start

This tutorial walks through the core agentcloak workflow: navigate to a page, read it through an accessibility tree snapshot, interact with elements, and verify results.

## The observe-act loop

agentcloak works on a simple cycle:

1. **Navigate** to a page
2. **Snapshot** to see the accessibility tree with `[N]` element references
3. **Act** on elements using their `[N]` reference numbers
4. **Re-snapshot** after actions (references change when the page updates)

## First run

The daemon starts automatically on the first command. No setup step needed.

```bash
# Navigate and get a snapshot in one step
cloak navigate "https://example.com" --snapshot
```

Output includes both the navigation result and the page snapshot:

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

## Reading the snapshot

The snapshot is an accessibility tree where each interactive element gets a `[N]` reference:

```
[1] <heading level=1> Example Domain
  More information...
[2] <link> More information...
```

- `[1]` is a heading -- not interactive, but indexed for reference
- `[2]` is a clickable link

Elements show their ARIA role, name, and state. Input fields include their current value. Indentation shows the page hierarchy.

### Snapshot modes

| Mode | What it shows | When to use |
|------|--------------|-------------|
| `accessible` | Full a11y tree with `[N]` refs, ARIA states, values | Default -- complete page view |
| `compact` | Interactive elements + named containers only | After actions -- smaller output |
| `content` | Text extraction | Reading articles or text-heavy pages |
| `dom` | Raw HTML | Debugging or CSS selector work |

```bash
cloak snapshot --mode compact    # interactive elements only
cloak snapshot --mode content    # text extraction
```

## Interacting with elements

Use `[N]` references from the snapshot as action targets:

```bash
# Click a link
cloak click --target 2

# Fill a text field
cloak fill --target 5 --text "search query"

# Press a key
cloak press --key Enter --target 5

# Select a dropdown option
cloak select --target 8 --value "option-2"
```

### Getting post-action state

Add `--snapshot` to any action to get a snapshot in the same response:

```bash
cloak click --target 2 --snapshot
```

This saves a round-trip compared to running a separate `cloak snapshot` after the action. The response includes a `snapshot` object alongside the action result.

## Complete login example

```bash
# Navigate to login page and get snapshot
cloak navigate "https://example.com/login" --snapshot

# Snapshot output:
# [1] <heading level=1> Sign In
# [2] <textbox> Email
# [3] <textbox type=password> Password
# [4] <button> Sign In

# Fill credentials
cloak fill --target 2 --text "user@example.com"
cloak fill --target 3 --text "my-password"

# Submit and get new snapshot
cloak click --target 4 --snapshot

# Save login state for reuse
cloak profile create my-session
```

Next time, launch with the saved profile:

```bash
cloak daemon start --profile my-session
cloak navigate "https://example.com/dashboard" --snapshot
```

## Network monitoring

Check what network requests a page makes:

```bash
# See recent requests
cloak network requests

# See only requests since the last action
cloak network requests --since last_action
```

## Taking screenshots

```bash
# Viewport screenshot (JPEG, ~75-85% smaller than PNG)
cloak screenshot

# Full scrollable page
cloak screenshot --full-page

# PNG for pixel-perfect fidelity
cloak screenshot --format png

# Save to file
cloak screenshot --output page.png
```

## Working with large pages

For pages with many elements, use progressive loading:

```bash
# Limit output to 80 nodes
cloak snapshot --max-nodes 80

# Paginate through results
cloak snapshot --offset 80 --max-nodes 80

# Focus on a specific element's subtree
cloak snapshot --focus 15

# See what changed after an action
cloak snapshot --diff
```

## Capturing API traffic

Record and analyze network traffic to discover API patterns:

```bash
cloak capture start
cloak navigate "https://api-heavy-site.com"
# interact with the page...
cloak capture stop

# Export as HAR
cloak capture export --format har -o traffic.har

# Auto-detect API patterns
cloak capture analyze
```

See the [capture guide](../guides/capture.md) for more on API analysis and spell generation.

## Output format

Every command returns one JSON object on stdout:

```json
{"ok": true, "seq": 3, "data": {"url": "https://example.com", "title": "Example"}}
```

Errors include a recovery hint:

```json
{"ok": false, "error": "element_not_found", "hint": "No element at index 99", "action": "re-snapshot to get fresh [N] refs"}
```

`seq` is a monotonic counter that increments on every browser state change. Parse with `jq`:

```bash
cloak snapshot | jq -r '.data.tree_text'
```

## Next steps

- [CLI reference](../reference/cli.md) -- all commands and flags
- [Browser backends](../guides/backends.md) -- CloakBrowser vs Playwright vs RemoteBridge
- [MCP setup](../guides/mcp-setup.md) -- connect from AI clients via MCP
- [Configuration](../reference/config.md) -- customize daemon behavior
