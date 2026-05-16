# Network capture and API analysis

The capture system records every meaningful HTTP request the browser makes, exports it as HAR 1.2, and can analyse the traffic to find API patterns you can turn into spells. Use it when you want to learn how a site talks to its backend before scripting against it.

## Quick start

```bash
cloak capture start                  # arm the recorder
cloak navigate "https://example.com" # browse, click, scroll — anything
cloak capture stop                   # disarm
cloak capture export -o traffic.har  # HAR 1.2 file you can open in DevTools
```

The recorder is on as long as it's armed — every subsequent navigation and `do` action will collect requests until you stop it.

## Recording

| Command | Purpose |
|---------|---------|
| `cloak capture start` | Start recording; clears nothing (entries from a previous session stay) |
| `cloak capture stop` | Stop recording; the buffer keeps everything until you `clear` |
| `cloak capture status` | Show whether recording is active and how many entries are stored |
| `cloak capture clear` | Drop every entry from the buffer |

The store has a 5000-entry rolling capacity. Once you cross that, the oldest entries are evicted first — for long sessions, export periodically.

### What gets recorded

Captured automatically:
- HTML, JSON, plain text, XML, form-urlencoded request and response bodies
- All request and response headers
- Method, URL, status, timing, resource type

Filtered out by default:
- Static assets: `.js`, `.css`, images, fonts, media, ico
- Manifests, generic "other" resource types
- Response bodies are truncated at 100 KB per entry

This filter is what keeps the 5000-entry buffer useful — pure API traffic stays, page chrome doesn't.

## Exporting

```bash
cloak capture export                       # HAR 1.2 on stdout
cloak capture export --format json         # raw JSON (request/response pairs)
cloak capture export --format har -o out.har
```

HAR exports load directly into Chrome DevTools (Network panel → right-click → Import HAR) and any HAR-aware tool (Charles, Fiddler, Postman). JSON exports are the format the analyser consumes.

## Analysis

```bash
cloak capture analyze              # all domains
cloak capture analyze --domain api.example.com
```

The analyser inspects captured traffic and reports:

- **Endpoint clusters** — URLs that share a path template (`/api/users/123`, `/api/users/456` → `/api/users/{id}`)
- **Path parameters** — segments that vary across calls vs constants
- **Authentication detected** — Bearer tokens, session cookies, custom headers
- **Request schema** — JSON body shape inferred from samples
- **Response schema** — JSON response shape

Output is structured JSON ready to drive code generation.

## Replay

```bash
cloak capture replay "https://api.example.com/data"
cloak capture replay "https://api.example.com/submit" --method POST
```

Re-issues the most recent captured request that matches URL + method. The agent's current cookies and headers are used, so you can replay after the session has refreshed.

## From capture to spell

Captures feed spell generation. The workflow:

```bash
# 1. Record real usage
cloak capture start
cloak navigate "https://target-site.com"
# log in, click around, do the workflow you want to automate
cloak capture stop

# 2. Inspect what was found
cloak capture analyze --domain target-site.com

# 3. Generate spell templates from the patterns
cloak spell scaffold target-site --domain target-site.com
```

`spell scaffold` writes Python files under `~/.config/agentcloak/spells/` with `@spell(...)` decorators pre-filled from the analyser's findings — endpoint URL, method, detected auth strategy, inferred request/response schema. You then refine the generated code, write a unit test, and `cloak spell run` it.

See the [spells guide](./spells.md) for the spell side of this pipeline.

## Troubleshooting

**"My request didn't show up"** — Check the resource type. Static assets (`.js`, `.css`, images) are filtered out. Run `cloak capture status` to confirm the recorder was on when you triggered the request.

**"Response body is empty or truncated"** — Bodies over 100 KB are truncated. Binary content types (images, video) are recorded as headers-only. If you need the full body, fetch it again with `cloak fetch URL`.

**"Capture survived a daemon restart"** — It shouldn't. The capture store is in-memory only. If `status` shows entries after a restart, the daemon didn't actually restart — check `cloak daemon health` for the PID.
