---
name: agentcloak
description: "Browser automation via cloak CLI. Navigates pages with anti-bot stealth, snapshots accessibility tree with [N] element refs for interaction, takes screenshots, evaluates JS, fetches HTTP with cookies, captures network traffic, manages profiles/tabs. Use this skill whenever the task involves ANY web page interaction: opening URLs, reading page content, filling forms, clicking buttons, taking screenshots, extracting data from websites, logging into sites, checking what a page shows, scraping, or automating browser workflows. Also use when the user mentions a URL and wants to see or interact with its content, even if they don't say 'browser'. This skill provides stealth bypass for anti-bot protections."
---

# agentcloak

Stealth browser automation for AI agents. Daemon auto-starts on first command.

Use `cloak` (short for `agentcloak`). High-frequency commands have top-level shortcuts -- `cloak open`, `cloak snapshot`, `cloak click` etc.

## Core Workflow

Observe-then-act. Snapshot first because `[N]` refs are only valid for the current page state.

1. **Navigate**: `cloak open "https://example.com"`
2. **Observe**: `cloak snapshot` -- get a11y tree with `[N]` element refs
3. **Act**: `cloak click --target 5` or `cloak fill --target 3 --text "query"`
4. **Handle feedback**: check action return for `pending_requests`, `dialog`, `navigation`
5. **Re-observe if needed**: when `caused_navigation: true` or `dom_changed: true`, snapshot again
6. **Repeat** steps 2-5

## Proactive State Feedback

Every action returns state changes triggered by the operation -- you do not need to poll. Fields appear only when relevant (null/empty omitted, 0 values kept):

| Field | Type | Meaning |
|-------|------|---------|
| `pending_requests` | int | In-flight network requests after this action |
| `dialog` | object | A dialog appeared: `{type, message}` |
| `navigation` | object | Page navigated: `{url}` |
| `download` | object | Download triggered: `{filename}` |
| `current_value` | string | Value after fill/select |

When a dialog blocks operations, you get `error: "blocked_by_dialog"` with dialog info. Handle it with `cloak dialog accept` or `cloak dialog dismiss` before retrying.

`seq` is always included -- a global monotonic counter tracking every state change. Use it as a time anchor for `--since` filtering.

## Element Addressing

`cloak snapshot` returns an indented accessibility tree with `[N]` indexed elements:

```
navigation "Main Nav"
  [1] link "Home"
  [2] link "Shop"
  [3] textbox "Search" value="shoes" focused
main "Content"
  heading "Products" level=2
    [4] link "Item 1 - $29.99"
    [5] button "Add to cart"
    [6] link "Item 2 - $49.99"
    [7] button "Add to cart" disabled
form "Login"
  [8] textbox "Email" value="user@example.com" required
  [9] textbox "Password" value="~~~~" required
  [10] checkbox "Remember me" checked
  [11] button "Submit"
```

Use the number as `--target` in action commands. Numbers are **page-specific and change on navigation/DOM update** -- always re-snapshot for fresh refs.

### Snapshot output includes

- **ARIA states**: `checked`, `disabled`, `expanded`, `selected`, `pressed`, `invalid`, `required`, `focused`, `hidden`
- **Current values**: `value="..."` for inputs, `value=75 min=0 max=100` for sliders
- **Heading levels**: `level=2` for h2, etc.
- **Password redaction**: password fields show `value="~~~~"` (real value hidden)
- **Indentation**: 2-space indent shows parent-child relationships
- **Dialog/menu/grid**: interactive overlays get `[N]` refs too

### Snapshot modes

- `accessible` (default) -- full a11y tree with `[N]`, ARIA states, values, indentation
- `compact` -- interactive elements + named containers only, much smaller output
- `content` -- text extraction, no `[N]` refs
- `dom` -- raw HTML, very large, rarely needed

## Command Reference

### Navigation & Observation

| Command | Purpose |
|---------|---------|
| `cloak open URL` | Navigate to URL |
| `cloak snapshot` | Get a11y tree with `[N]` refs |
| `cloak snapshot --mode compact` | Interactive elements + containers only |
| `cloak snapshot --mode content` | Text extraction |
| `cloak snapshot --max-nodes 50` | Limit to 50 nodes (shows summary of hidden elements) |
| `cloak snapshot --focus N` | Expand subtree around element [N] |
| `cloak snapshot --offset 50` | Start from 50th element (pagination) |
| `cloak snapshot --max-chars 5000` | Limit by character count |
| `cloak screenshot` | Take page screenshot |
| `cloak resume` | Current state: URL, tabs, last 5 actions |

### Progressive Loading (large pages)

When a page has many elements, use progressive loading:

1. Start with compact mode: `cloak snapshot --mode compact`
2. If truncated, use `--focus=N` to zoom into an area: `cloak snapshot --focus 15`
3. Or paginate with `--offset`: `cloak snapshot --offset 80`
4. You can **always action on any [N] ref**, even if not visible in truncated output -- the daemon keeps the full ref mapping

Truncated output shows a summary like:
```
--- not shown: [13]-[24] 12 elements (--focus=N to expand subtree, --offset=12 to page) ---
```

### Interaction

All actions use `--target N` where N comes from the most recent snapshot.

| Command | Purpose |
|---------|---------|
| `cloak click --target N` | Click element |
| `cloak fill --target N --text "value"` | Clear input, set value |
| `cloak type --target N --text "value"` | Type character by character |
| `cloak press --key Enter` | Press keyboard key |
| `cloak press --key "Control+a"` | Combo key (Playwright syntax) |
| `cloak press --key Tab --target N` | Press key on specific element |
| `cloak keydown --key Shift` | Hold a key down |
| `cloak keyup --key Shift` | Release a held key |
| `cloak scroll --direction down` | Scroll page |
| `cloak hover --target N` | Hover over element |
| `cloak select --target N --value "opt"` | Select dropdown option |

Keys: Enter, Tab, Escape, Backspace, ArrowDown, ArrowUp, Space, Delete, Home, End.
Combos: Control+a, Control+c, Control+v, Control+Shift+k, Alt+F4 (Playwright `+` syntax).

### Dialog Handling

Dialogs block all actions until handled. alert/beforeunload auto-accept; confirm/prompt need explicit handling.

| Command | Purpose |
|---------|---------|
| `cloak dialog status` | Check for pending dialog |
| `cloak dialog accept` | Accept (confirm -> OK) |
| `cloak dialog accept --text "reply"` | Accept with reply text (prompt) |
| `cloak dialog dismiss` | Dismiss (confirm -> Cancel) |

When any action returns `error: "blocked_by_dialog"`, it includes the dialog info -- you already know what it says without calling `dialog status`.

### Conditional Waiting

| Command | Purpose |
|---------|---------|
| `cloak wait --selector ".results"` | Wait for element to appear |
| `cloak wait --url "**/dashboard"` | Wait for URL to match |
| `cloak wait --load networkidle` | Wait for load state |
| `cloak wait --js "window.ready"` | Wait for JS condition |
| `cloak wait --ms 3000` | Sleep for milliseconds |
| Add `--timeout 60000` | Custom timeout (default 30s) |
| Add `--state hidden` | Wait for element to disappear |

### File Upload

| Command | Purpose |
|---------|---------|
| `cloak upload --index N --file /path/to/doc.pdf` | Upload single file |
| `cloak upload --index N --file a.pdf --file b.jpg` | Upload multiple files |

### Frame Switching

For pages with iframes. After switching, all actions/snapshots operate in that frame.

| Command | Purpose |
|---------|---------|
| `cloak frame list` | List all frames |
| `cloak frame focus --name "payment"` | Switch to named frame |
| `cloak frame focus --url "*checkout*"` | Switch by URL match |
| `cloak frame focus --main` | Back to main frame |

### Content & Network

| Command | Purpose |
|---------|---------|
| `cloak js eval "expression"` | Execute JS in page context |
| `cloak fetch URL` | HTTP GET with browser cookies |
| `cloak fetch URL --method POST --body '{...}'` | HTTP POST |
| `cloak network requests` | Recent network requests |
| `cloak network console` | Console log messages |

### Capture

| Command | Purpose |
|---------|---------|
| `cloak capture start` | Start recording traffic |
| `cloak capture stop` | Stop recording |
| `cloak capture export --format har -o out.har` | Export as HAR |

### Management

| Command | Purpose |
|---------|---------|
| `cloak profile list` | List saved browser profiles |
| `cloak profile create NAME` | Create persistent profile |
| `cloak profile launch NAME` | Start browser with saved profile |
| `cloak tab list` | List open tabs |
| `cloak tab new` / `tab close --id N` / `tab switch --id N` | Tab management |
| `cloak adapter list` / `adapter run NAME` | Run site adapters |
| `cloak doctor` | Self-check diagnostics |

## Output Format

Every command returns one JSON object on stdout:

```
{"ok": true, "seq": 3, "data": {...}}
{"ok": false, "error": "element_not_found", "hint": "...", "action": "..."}
```

`seq` tracks browser state changes. Error `action` field tells you what to try next.

Parse with jq: `cloak snapshot | jq -r '.data.tree_text'`

## Error Recovery

When `"ok": false`, read the `action` field for a concrete recovery step.

| Error | Recovery |
|-------|----------|
| `element_not_found` | Re-snapshot, `[N]` refs are stale |
| `navigation_timeout` | Retry with larger `--timeout`, or check URL |
| `blocked_by_dialog` | Call `cloak dialog accept` or `dismiss` first |
| `wait_timeout` | Increase `--timeout`, or verify the condition |
| `frame_not_found` | Use `cloak frame list` to see available frames |
| `daemon_not_running` | Should auto-start; if not, `cloak daemon start -b` |

## Recipes

### Search

```bash
cloak open "https://www.google.com"
cloak snapshot --mode compact
# find the search box [N] in output, then:
cloak fill --target N --text "search query"
cloak press --key Enter --target N
cloak snapshot  # re-snapshot after navigation
```

### Login and Save Session

```bash
cloak open "https://example.com/login"
cloak snapshot --mode compact
# identify fields from snapshot:
cloak fill --target N --text "username"
cloak fill --target M --text "password"
cloak click --target K  # submit
cloak snapshot
cloak profile create my-session  # persist cookies
```

### Handle a Dialog

```bash
cloak click --target 5
# response: {"ok": false, "error": "blocked_by_dialog", "dialog": {"type": "confirm", "message": "Delete item?"}}
cloak dialog accept   # or: cloak dialog dismiss
cloak snapshot        # continue
```

### Wait for Dynamic Content

```bash
cloak click --target 3     # triggers AJAX
cloak wait --selector ".results" --timeout 10000
cloak snapshot             # results are loaded
```

### Upload a File

```bash
cloak snapshot --mode compact  # find file input [N]
cloak upload --index N --file /tmp/document.pdf
```

### Work in an iframe

```bash
cloak frame list           # see all frames
cloak frame focus --name "payment"
cloak snapshot             # now shows iframe content
cloak fill --target N --text "4242..."
cloak frame focus --main   # back to main page
```

### Explore Large Page

```bash
cloak open "https://example.com/dashboard"
cloak snapshot --mode compact --max-nodes 50
# see summary of hidden elements, then zoom in:
cloak snapshot --focus 12  # expand area around element [12]
# or page through:
cloak snapshot --offset 50 --max-nodes 50
```

### Capture API Traffic

```bash
cloak capture start
cloak open "https://api-heavy-site.com"
# interact...
cloak capture stop
cloak capture export --format har -o traffic.har
```

## Key Principles

- **Snapshot before acting**: `[N]` refs are only valid for current page state
- **Read feedback fields**: `pending_requests`, `dialog`, `navigation` tell you what happened
- **Handle dialogs immediately**: they block everything until dismissed
- **Follow error `action` field**: it tells you exactly what to do next
- **Use compact mode**: `--mode compact` for focused interaction, less output
- **Use content mode**: `--mode content` for reading text, no refs needed
- **Progressive loading**: use `--focus=N` or `--offset=N` for large pages
- **Action on any ref**: even truncated refs work -- daemon keeps full mapping
