# Recipes

Common usage patterns. Each recipe shows the exact command sequence.

## Search

```bash
cloak navigate "https://www.google.com"
cloak snapshot --mode compact
# find the search box [N] in output
cloak fill --target N --text "search query"
cloak press --key Enter --target N
cloak snapshot  # re-snapshot after navigation
```

## Login and Save Session

```bash
cloak navigate "https://example.com/login"
cloak snapshot --mode compact
# identify fields from snapshot:
cloak fill --target N --text "username"
cloak fill --target M --text "password"
cloak click --target K  # submit
cloak snapshot
cloak profile create my-session  # persist cookies for reuse
# Next time: cloak profile launch my-session
```

## Handle a Dialog

```bash
cloak click --target 5
# response: {"ok": false, "error": "blocked_by_dialog",
#   "dialog": {"type": "confirm", "message": "Delete item?"}}
cloak dialog accept   # or: cloak dialog dismiss
cloak snapshot        # continue
```

## Wait for Dynamic Content

```bash
cloak click --target 3     # triggers AJAX
cloak wait --selector ".results" --timeout 10000
cloak snapshot             # results are loaded
```

Wait options: `--selector`, `--url "**/path"`, `--load networkidle`, `--js "window.ready"`, `--ms 3000`. Add `--state hidden` to wait for disappearance.

## Upload a File

```bash
cloak snapshot --mode compact  # find file input [N]
cloak upload --index N --file /tmp/document.pdf
# Multiple files:
cloak upload --index N --file a.pdf --file b.jpg
```

## Work in an iframe

```bash
cloak frame list           # see all frames
cloak frame focus --name "payment"
cloak snapshot             # now shows iframe content
cloak fill --target N --text "4242..."
cloak frame focus --main   # back to main page
```

Frame targeting: `--name`, `--url "*pattern*"`, or `--main`.

## Explore Large Page

```bash
cloak navigate "https://example.com/dashboard"
cloak snapshot --mode compact --max-nodes 50
# output shows: --- not shown: [13]-[24] 12 elements ---
# zoom into an area:
cloak snapshot --focus 12  # expand around element [12]
# or page through:
cloak snapshot --offset 50 --max-nodes 50
```

You can action on any `[N]` ref even if not visible in truncated output — the daemon keeps the full ref mapping.

## Track Changes with Diff

```bash
cloak snapshot              # take baseline
cloak click --target 5      # make some change
cloak snapshot --diff       # shows [+] added, [~] changed, removed summary
```

## Action with Snapshot (save a round trip)

```bash
cloak click --target 5 --include-snapshot
# response includes both action result AND compact snapshot
# no need for a separate cloak snapshot call
```
