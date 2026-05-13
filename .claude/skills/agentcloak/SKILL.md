---
name: agentcloak
description: "Browser automation via cloak CLI. Navigates pages with anti-bot stealth, snapshots accessibility tree with [N] element refs for interaction, takes screenshots, evaluates JS, fetches HTTP with cookies, captures network traffic, manages profiles/tabs. Use this skill whenever the task involves ANY web page interaction: opening URLs, reading page content, filling forms, clicking buttons, taking screenshots, extracting data from websites, logging into sites, checking what a page shows, scraping, or automating browser workflows. Also use when the user mentions a URL and wants to see or interact with its content, even if they don't say 'browser'. This skill provides stealth bypass for anti-bot protections."
---

# agentcloak

Stealth browser automation for AI agents. Daemon auto-starts on first command.

Use `cloak` (short for `agentcloak`). High-frequency commands have top-level shortcuts — `cloak open`, `cloak snapshot`, `cloak click` etc.

## Core Workflow

Observe-then-act. Snapshot first because `[N]` refs are only valid for the current page state.

1. **Navigate**: `cloak open "https://example.com"`
2. **Observe**: `cloak snapshot` — get a11y tree with `[N]` element refs
3. **Act**: `cloak click --target 5` or `cloak fill --target 3 --text "query"`
4. **Re-observe if page changed**: when `caused_navigation: true` in response, snapshot again
5. **Repeat** steps 2-4

## Element Addressing

`cloak snapshot` returns an accessibility tree with `[N]` indexed elements:

```
[1] <link> About
[2] <button> Settings
[3] <combobox> Search
[4] <button> Google Search
```

Use the number as `--target` in action commands. Numbers are **page-specific and change on navigation/DOM update** — always re-snapshot for fresh refs.

Snapshot modes:
- `accessible` (default) — full a11y tree with `[N]`, best for interaction
- `compact` — interactive elements only, smaller output
- `content` — text extraction, no `[N]` refs
- `dom` — raw HTML, very large, rarely needed

## Command Reference

### Navigation & Observation

| Command | Purpose |
|---------|---------|
| `cloak open URL` | Navigate to URL |
| `cloak snapshot` | Get a11y tree with `[N]` refs |
| `cloak snapshot --mode compact` | Interactive elements only |
| `cloak snapshot --mode content` | Text extraction |
| `cloak snapshot --max-chars 5000` | Limit output size |
| `cloak screenshot` | Take page screenshot |
| `cloak resume` | Current state: URL, tabs, last 5 actions |

### Interaction

All actions use `--target N` where N comes from the most recent snapshot.

| Command | Purpose |
|---------|---------|
| `cloak click --target N` | Click element |
| `cloak fill --target N --text "value"` | Clear input, set value |
| `cloak type --target N --text "value"` | Type character by character |
| `cloak press --key Enter` | Press keyboard key |
| `cloak press --key Tab --target N` | Press key on specific element |
| `cloak scroll --direction down` | Scroll page |
| `cloak hover --target N` | Hover over element |
| `cloak select --target N --value "opt"` | Select dropdown option |

Keys: Enter, Tab, Escape, Backspace, ArrowDown, ArrowUp, Space, Delete, Home, End.

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
| `daemon_not_running` | Should auto-start; if not, `cloak daemon start -b` |
| `fill` with empty text | Provide `--text` parameter |

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

### Read Page Content

```bash
cloak open "https://example.com/article"
cloak snapshot --mode content
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
- **Follow `caused_navigation`**: when `true`, re-snapshot
- **Follow error `action` field**: it tells you exactly what to do next
- **Use compact mode**: `--mode compact` for focused interaction, less output
- **Use content mode**: `--mode content` for reading text, no refs needed
- **Default snapshot limit is 30000 chars**: adjust with `--max-chars`
