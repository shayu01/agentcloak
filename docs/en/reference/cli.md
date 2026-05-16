# CLI reference

agentcloak provides two equivalent CLI entry points: `agentcloak` and `cloak` (shorthand). All examples use `cloak`.

Every command outputs one JSON object to stdout with the format:

```json
{"ok": true, "seq": 3, "data": {...}}
```

Errors include recovery hints:

```json
{"ok": false, "error": "error_code", "hint": "description", "action": "suggested next step"}
```

## Navigation and observation

### navigate

Navigate the browser to a URL.

```bash
cloak navigate URL [--timeout SECONDS] [--snapshot] [--snapshot-mode MODE]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--timeout` | `30` | Max seconds to wait for page load |
| `--snapshot` | off | Include accessibility tree snapshot in response |
| `--snapshot-mode` | `compact` | Snapshot mode when `--snapshot` is used |

### snapshot

Get the page as an accessibility tree with `[N]` element references.

```bash
cloak snapshot [--mode MODE] [--max-nodes N] [--focus N] [--offset N] [--frames] [--diff]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--mode` | `accessible` | `accessible`, `compact`, `content`, or `dom` |
| `--max-nodes` | `0` | Truncate after N nodes (0 = no limit) |
| `--focus` | `0` | Expand subtree around element `[N]` |
| `--offset` | `0` | Start output from Nth element (pagination) |
| `--frames` | off | Include iframe content |
| `--diff` | off | Mark changes since previous snapshot |

### screenshot

Take a screenshot of the current page.

```bash
cloak screenshot [--output FILE] [--full-page] [--format FORMAT] [--quality N]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--output` | stdout | Save to file instead of base64 in JSON |
| `--full-page` | off | Capture full scrollable page |
| `--format` | `jpeg` | `jpeg` or `png` |
| `--quality` | `80` | JPEG quality 0-100 (ignored for PNG) |

### resume

Get session state for context recovery.

```bash
cloak resume
```

Returns current URL, open tabs, last 5 actions, capture state, and stealth tier.

## Interaction

### click

Click an element by `[N]` reference.

```bash
cloak click --target N [--snapshot]
```

### fill

Clear an input field and set its value.

```bash
cloak fill --target N --text "value" [--snapshot]
```

### type

Type text character by character (triggers key events).

```bash
cloak type --target N --text "value" [--snapshot]
```

### press

Press a keyboard key or key combination.

```bash
cloak press --key KEY [--target N] [--snapshot]
```

Key names use Playwright syntax: `Enter`, `Tab`, `Escape`, `Control+a`, `Shift+ArrowDown`.

### scroll

Scroll the page.

```bash
cloak scroll --direction DIRECTION [--snapshot]
```

Direction: `up` or `down`.

### hover

Hover over an element.

```bash
cloak hover --target N [--snapshot]
```

### select

Select a dropdown option.

```bash
cloak select --target N --value "option" [--snapshot]
```

> [!NOTE]
> All interaction commands support `--snapshot` to include a compact snapshot in the response, saving a round-trip.

## Content and network

### js evaluate

Execute JavaScript in the page context.

```bash
cloak js evaluate "expression"
```

Runs in the page's main world by default. Page globals (jQuery, Vue, React, etc.) are accessible.

### fetch

HTTP request using the browser's cookies and user agent.

```bash
cloak fetch URL [--method METHOD] [--body BODY] [--headers-json JSON]
```

### network requests

List recent network requests.

```bash
cloak network requests [--since SEQ]
```

Use `--since last_action` to see requests triggered by the most recent action.

### network console

List console messages.

```bash
cloak network console [--since SEQ]
```

## Dialog handling

### dialog status

Check for pending browser dialogs.

```bash
cloak dialog status
```

### dialog accept / dismiss

Handle a pending dialog.

```bash
cloak dialog accept [--text "reply"]
cloak dialog dismiss
```

## Waiting

### wait

Wait for a condition before continuing.

```bash
cloak wait --selector "CSS_SELECTOR"
cloak wait --url "**/dashboard"
cloak wait --load networkidle
cloak wait --js "document.readyState === 'complete'"
cloak wait --ms 2000
```

| Flag | Description |
|------|-------------|
| `--selector` | Wait for CSS selector to appear |
| `--url` | Wait for URL pattern (glob) |
| `--load` | Wait for load state (`load`, `domcontentloaded`, `networkidle`) |
| `--js` | Wait for JS expression to return truthy |
| `--ms` | Sleep for N milliseconds |
| `--timeout` | Max wait time in ms (default 30000) |

## File upload

### upload

Upload files to a file input element.

```bash
cloak upload --index N --file /path/to/file [--file /path/to/another]
```

## Frame management

### frame list

List all frames on the page.

```bash
cloak frame list
```

### frame focus

Switch to a specific frame.

```bash
cloak frame focus --name "frame-name"
cloak frame focus --url "partial-url"
cloak frame focus --main
```

## Capture and spells

### capture start / stop

Control network traffic recording.

```bash
cloak capture start
cloak capture stop
```

### capture status

Check recording state.

```bash
cloak capture status
```

### capture export

Export captured traffic.

```bash
cloak capture export --format har [-o output.har]
cloak capture export --format json
```

### capture analyze

Auto-detect API patterns from captured traffic.

```bash
cloak capture analyze [--domain example.com]
```

### capture clear

Delete all captured data.

```bash
cloak capture clear
```

### spell list

List all registered spells.

```bash
cloak spell list
```

### spell run

Run a named spell.

```bash
cloak spell run NAME [--args-json '{"key": "value"}']
```

### spell info

Get details about a spell.

```bash
cloak spell info NAME
```

### spell scaffold

Generate a spell template.

```bash
cloak spell scaffold SITE COMMAND
```

## Profile management

### profile create

Create a named browser profile.

```bash
cloak profile create NAME [--from-current]
```

`--from-current` copies cookies from the active browser session.

### profile list

List all saved profiles.

```bash
cloak profile list
```

### profile launch

Launch the browser with a saved profile.

```bash
cloak profile launch NAME
```

### profile delete

Delete a saved profile.

```bash
cloak profile delete NAME
```

## Tab management

### tab list

List open browser tabs.

```bash
cloak tab list
```

### tab new

Open a new tab.

```bash
cloak tab new [--url URL]
```

### tab close

Close a tab by ID.

```bash
cloak tab close --tab-id N
```

### tab switch

Switch to a tab by ID.

```bash
cloak tab switch --tab-id N
```

## Bridge commands

### bridge claim

Take control of a user-opened tab (RemoteBridge only).

```bash
cloak bridge claim --tab-id N
cloak bridge claim --url-pattern "dashboard"
```

### bridge finalize

End the agent session (RemoteBridge only).

```bash
cloak bridge finalize --mode close        # close agent tabs
cloak bridge finalize --mode handoff      # leave tabs for user
cloak bridge finalize --mode deliverable  # rename group to "results"
```

## Cookie management

### cookies export

Export cookies from the browser (local or RemoteBridge).

```bash
cloak cookies export
```

### cookies import

Import cookies into the browser. Supports httpOnly cookies.

```bash
cloak cookies import -c '[{"name":"token","value":"abc","domain":".example.com","path":"/"}]'
```

## Daemon management

### daemon start

Start the background daemon.

```bash
cloak daemon start [--host HOST] [--port PORT] [--headed] [--profile NAME]
```

### daemon stop

Stop the running daemon.

```bash
cloak daemon stop
```

### daemon health

Check daemon status.

```bash
cloak daemon health
```

## Configuration

### config

Show merged configuration with value sources. Each field shows whether it came from `default`, `config.toml`, or an environment variable.

```bash
cloak config
```

## Diagnostics

### doctor

Run diagnostic checks.

```bash
cloak doctor
```

Checks Python version, CloakBrowser status, daemon connectivity, and configuration.

### cdp endpoint

Get the CDP WebSocket URL (for jshookmcp or other CDP tools).

```bash
cloak cdp endpoint
```
