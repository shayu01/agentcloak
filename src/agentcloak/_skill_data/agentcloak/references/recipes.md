# Recipes

Common usage patterns. Each recipe shows the exact command sequence.

Actions take the element index positionally — `cloak click 5`, `cloak fill 3 "text"` — or via `--index N`. See `SKILL.md` "Interaction" for the full list.

## Search

```bash
cloak navigate "https://www.google.com" --snap
# find the search box [N] in the snapshot output
cloak fill N "search query"
cloak press Enter
cloak snapshot  # re-snapshot after navigation
```

## Login and Save Session

```bash
cloak navigate "https://example.com/login" --snap
# identify fields from snapshot:
cloak fill N "username"
cloak fill M "password"
cloak click K            # submit
cloak snapshot
cloak profile create my-session  # persist cookies for reuse
# Next time: cloak profile launch my-session
```

## Handle a Dialog

```bash
cloak click 5
# stderr: Error: blocked by dialog (confirm) — "Delete item?"
cloak dialog accept      # or: cloak dialog dismiss
cloak snapshot           # continue
```

## Wait for Dynamic Content

```bash
cloak click 3            # triggers AJAX
cloak wait --selector ".results" --timeout 10000
cloak snapshot           # results are loaded
```

Wait options: `--selector`, `--url "**/path"`, `--load networkidle`, `--js "window.ready"`, `--ms 3000`. Add `--state hidden` to wait for disappearance.

## Upload a File

```bash
cloak snapshot           # find file input [N] (compact is the default)
cloak upload --index N --file /tmp/document.pdf
# Multiple files:
cloak upload --index N --file a.pdf --file b.jpg
```

## Work in an iframe

```bash
cloak frame list           # see all frames
cloak frame focus --name "payment"
cloak snapshot             # now shows iframe content
cloak fill N "4242..."
cloak frame focus --main   # back to main page
```

Frame targeting: `--name`, `--url "*pattern*"`, or `--main`.

## Explore Large Page

```bash
cloak navigate "https://example.com/dashboard" --snap
# compact mode defaults to 80 nodes — output shows: --- not shown: [13]-[24] 12 elements ---
cloak snapshot --limit 50          # tighter cap for fewer tokens
cloak snapshot --focus 12          # expand subtree around [12] (with ancestor breadcrumbs)
cloak snapshot --offset 50         # paginate from the 50th element
cloak snapshot --limit 0           # disable the cap and see the full compact tree
```

You can action on any `[N]` ref even when it's truncated from the printed tree — the daemon keeps the full ref mapping.

## Track Changes with Diff

```bash
cloak snapshot              # take baseline
cloak click 5               # make some change
cloak snapshot --diff       # shows [+] added, [~] changed, removed summary
```

## Action with Snapshot (save a round trip)

```bash
cloak click 5 --snap
# stdout includes both the action confirmation AND a compact snapshot
# (header line: # Title | url | N nodes) — no need for a separate cloak snapshot call
```
