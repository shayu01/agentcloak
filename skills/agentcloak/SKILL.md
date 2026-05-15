---
name: agentcloak
description: "Browser automation via cloak CLI. Navigates pages with anti-bot stealth, snapshots accessibility tree with [N] element refs for interaction, takes screenshots, evaluates JS, fetches HTTP with cookies, captures network traffic, manages profiles/tabs. Use this skill whenever the task involves ANY web page interaction: opening URLs, reading page content, filling forms, clicking buttons, taking screenshots, extracting data from websites, logging into sites, checking what a page shows, scraping, or automating browser workflows. Also use when the user mentions a URL and wants to see or interact with its content, even if they don't say 'browser'. This skill provides stealth bypass for anti-bot protections."
---

# agentcloak

Stealth browser automation for AI agents. Daemon auto-starts on first command.

Use `cloak` (short for `agentcloak`). High-frequency commands have top-level shortcuts -- `cloak navigate`, `cloak snapshot`, `cloak click` etc.

First-time setup: read `references/getting-started.md`.

## Core Workflow

Observe-then-act. Snapshot first because `[N]` refs are only valid for the current page state.

1. **Navigate**: `cloak navigate "https://example.com" --snapshot` -- navigate and get snapshot in one step
2. **Observe**: `cloak snapshot` -- get a11y tree with `[N]` element refs (or use `--snapshot` on navigate/action)
3. **Act**: `cloak click --target 5` or `cloak fill --target 3 --text "query"`
4. **Handle feedback**: check action return for `pending_requests`, `dialog`, `navigation`
5. **Re-observe if needed**: when `caused_navigation: true` or `dom_changed: true`, snapshot again
6. **Repeat** steps 2-5

Every action returns state changes (`pending_requests`, `dialog`, `navigation`, `download`, `current_value`). Fields appear only when relevant. When `error: "blocked_by_dialog"`, handle with `cloak dialog accept/dismiss` before retrying.

## Element Addressing

`cloak snapshot` returns an indented a11y tree with `[N]` indexed elements:

```
navigation "Main Nav"
  [1] link "Home"
  [2] link "Shop"
  [3] textbox "Search" value="shoes" focused
main "Content"
  [4] link "Item 1 - $29.99"
  [5] button "Add to cart"
form "Login"
  [6] textbox "Email" required
  [7] textbox "Password" value="~~~~" required
  [8] button "Submit"
```

Numbers are `--target` values for actions. They change on navigation/DOM update -- always re-snapshot for fresh refs. ARIA states shown: `checked`, `disabled`, `expanded`, `selected`, `pressed`, `invalid`, `required`, `focused`. Passwords redacted as `~~~~`.

Snapshot modes: `accessible` (default, full tree) | `compact` (interactive + containers only) | `content` (text extraction) | `dom` (raw HTML).

## Command Reference

### Navigation & Observation

| Command | Purpose |
|---------|---------|
| `cloak navigate URL` | Navigate to URL (add `--snapshot` to get a11y tree in one step) |
| `cloak snapshot` | Get a11y tree with `[N]` refs |
| `cloak snapshot --mode compact` | Interactive elements + containers only |
| `cloak snapshot --mode content` | Text extraction |
| `cloak snapshot --max-nodes 50` | Limit node count (summary of hidden) |
| `cloak snapshot --focus N` | Expand subtree around element [N] |
| `cloak snapshot --offset 50` | Paginate from 50th element |
| `cloak snapshot --frames` | Include iframe content |
| `cloak snapshot --diff` | Mark `[+]` added, `[~]` changed vs previous |
| `cloak screenshot` | Take page screenshot |
| `cloak resume` | Session state: URL, tabs, recent actions |

### Interaction

All actions use `--target N` from the most recent snapshot.

| Command | Purpose |
|---------|---------|
| `cloak click --target N` | Click element |
| `cloak fill --target N --text "value"` | Clear and set input value |
| `cloak type --target N --text "value"` | Type character by character |
| `cloak press --key Enter` | Press key (Enter, Tab, Escape, Backspace, ArrowDown, Space...) |
| `cloak press --key "Control+a"` | Combo key (Playwright `+` syntax) |
| `cloak scroll --direction down` | Scroll page |
| `cloak hover --target N` | Hover over element |
| `cloak select --target N --value "opt"` | Select dropdown option |
| `cloak keydown/keyup --key Shift` | Hold/release key |
| `cloak dialog accept` / `dismiss` | Handle confirm/prompt dialog |
| `cloak wait --selector ".results"` | Wait for element / URL / JS condition / time |
| `cloak upload --index N --file path` | Upload file to input element |
| `cloak frame focus --name "x"` | Switch to iframe (`--main` to return) |
| Add `--include-snapshot` to any action | Get compact snapshot with result (saves round trip) |

### Content & Network

| Command | Purpose |
|---------|---------|
| `cloak js evaluate "expression"` | Execute JS in page |
| `cloak fetch URL` | HTTP GET with browser cookies |
| `cloak fetch URL --method POST --body '{...}'` | HTTP POST with cookies |
| `cloak network requests` | Recent network requests |
| `cloak capture start` / `stop` / `export` | Record and export network traffic |

### Management

| Command | Purpose |
|---------|---------|
| `cloak profile list` / `create` / `launch` / `delete` | Browser profile management |
| `cloak tab list` / `new` / `close` / `switch` | Tab management |
| `cloak spell list` / `info` / `run NAME` / `scaffold` | Spells (reusable site automation) |
| `cloak cookies export` / `import` | Cookie management |
| `cloak cdp endpoint` | Get CDP WebSocket URL (for jshookmcp) |
| `cloak doctor` | Self-check diagnostics |
| `cloak bridge start` / `claim` / `finalize` | RemoteBridge (real browser) |

## Output Format

Every command returns JSON on stdout:

```json
{"ok": true, "seq": 3, "data": {...}}
{"ok": false, "error": "element_not_found", "hint": "...", "action": "..."}
```

`seq` is a monotonic counter for state changes. Error `action` field tells you what to try next. Parse with jq: `cloak snapshot | jq -r '.data.tree_text'`

## Smart Behaviors

These work automatically:
- **Stale ref auto-retry**: `element_not_found` triggers one automatic re-snapshot + retry
- **`--include-snapshot`**: add to any action to get a compact snapshot back, saving a round trip
- **`--snapshot` on navigate**: `cloak navigate URL --snapshot` returns page + a11y tree in one call
- **`$N.path` batch refs**: in `--calls-file` batch mode, reference prior results (e.g. `"$0.url"`)
- **Tab group**: RemoteBridge auto-groups agent tabs under blue "agentcloak" Chrome tab group

## Key Principles

- **Snapshot before acting**: `[N]` refs are only valid for current page state
- **Read feedback fields**: `pending_requests`, `dialog`, `navigation` tell you what happened
- **Handle dialogs immediately**: they block everything until dismissed
- **Follow error `action` field**: it tells you exactly what to do next
- **Use compact mode**: `--mode compact` for focused interaction
- **Progressive loading**: `--focus=N` or `--offset=N` for large pages; action on any ref works even if truncated

## References

Read these when you need deeper guidance:

| Reference | When to read |
|-----------|-------------|
| `references/getting-started.md` | First-time setup, installation, configuration |
| `references/recipes.md` | Usage examples: search, login, dialog, upload, iframe, large pages |
| `references/data-and-spells.md` | Capture traffic, run spells, batch operations, fetch with cookies |
| `references/remote-bridge.md` | Operate user's real Chrome browser via extension |
| `references/troubleshooting.md` | Error recovery, dialog handling, daemon issues |
