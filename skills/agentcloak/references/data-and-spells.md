# Data Extraction & Spells

## JavaScript Evaluation

```bash
cloak js evaluate "document.title"
cloak js evaluate "document.querySelectorAll('a').length"
cloak js evaluate "JSON.stringify(window.__NEXT_DATA__)" # extract Next.js data
```

Use `--world utility` for isolated context (no page globals pollution).

## HTTP Fetch with Browser Cookies

Fetch URLs using the browser's authenticated session:

```bash
cloak fetch "https://api.example.com/data"
cloak fetch "https://api.example.com/submit" --method POST --body '{"key": "value"}'
```

Cookies and headers are synced from the browser session automatically.

## Network Capture

Record all network traffic, then export or analyze:

```bash
cloak capture start
cloak navigate "https://api-heavy-site.com"
# interact with the site...
cloak capture stop
cloak capture export --format har -o traffic.har
cloak capture analyze    # pattern detection: endpoint clustering, auth detection
cloak capture replay --url "https://api.example.com/data"  # replay a captured request
cloak capture clear      # clear recorded data
```

The analyzer detects: path parameters, endpoint clusters, authentication methods, and request schemas.

## Spells (Reusable Site Automation)

Spells are pre-built commands for specific websites. Think of them as "refined recipes" — crafted once, cast with one line.

```bash
cloak spell list                        # see available spells
cloak spell info httpbin/headers        # show spell details
cloak spell run httpbin/headers         # execute a spell
cloak spell run github/repos --arg owner=torvalds  # with arguments
cloak spell scaffold mysite             # generate template for a new spell
```

### Creating Spells

Two modes:

**Pipeline mode** (declarative, for API calls):
```python
@spell(site="httpbin", name="headers", strategy=Strategy.PUBLIC,
       pipeline=[{"fetch": "https://httpbin.org/headers"}, {"select": "headers"}])
```

**Function mode** (code, for browser interaction):
```python
@spell(site="example", name="title", strategy=Strategy.COOKIE)
async def get_title(ctx: SpellContext):
    title = await ctx.evaluate("document.title")
    return [{"title": title}]
```

Spells are discovered from built-in `spells/sites/` and user directory `~/.config/agentcloak/spells/`.

### Capture-to-Spell Pipeline

Observe API traffic → auto-generate spell:

```bash
cloak capture start
# browse the site, let it make API calls...
cloak capture stop
cloak capture analyze           # identifies API patterns
cloak spell scaffold mysite     # generates spell code from analysis
```

## Batch Operations

Execute multiple actions in one call with `--calls-file`:

```bash
echo '[
  {"action": "fill", "target": "3", "text": "hello"},
  {"action": "click", "target": "5"},
  {"action": "wait", "selector": ".result"}
]' > batch.json
cloak do batch --calls-file batch.json
```

Use `$N.path` to reference prior action results:
```json
[
  {"action": "click", "target": "3"},
  {"action": "fill", "target": "5", "text": "$0.data.url"}
]
```

Batch stops on URL change, focus change, or dialog — returns partial results.
