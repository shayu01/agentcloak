# Troubleshooting

## Error Recovery Quick Reference

When `"ok": false`, read the `error` and `action` fields:

| Error | Cause | Recovery |
|-------|-------|----------|
| `element_not_found` | `[N]` ref is stale (page changed) | Auto-retried once; if still fails, re-snapshot and use new ref |
| `navigation_timeout` | Page took too long to load | Retry with `--timeout 60`, or check URL is correct |
| `blocked_by_dialog` | A dialog is blocking operations | `cloak dialog accept` or `dismiss`, then retry action |
| `wait_timeout` | Wait condition not met in time | Increase `--timeout`, or verify selector/condition |
| `frame_not_found` | Frame name/URL doesn't match | `cloak frame list` to see available frames |
| `daemon_not_running` | Daemon crashed or wasn't started | Should auto-start; if not, `cloak daemon start -b` |
| `spell_no_browser` | Spell needs browser but none launched | Navigate to a page first, then run spell |
| `spell_no_handler` | Spell definition is broken | Check spell code |

## Dialog Handling

Dialogs (alert, confirm, prompt, beforeunload) block all browser operations.

- **alert / beforeunload**: auto-accepted, you see them in action feedback as `auto_dialog`
- **confirm / prompt**: stored as pending, you must handle explicitly

```bash
cloak dialog status              # check for pending dialog
cloak dialog accept              # OK / confirm
cloak dialog accept --text "reply"  # answer a prompt dialog
cloak dialog dismiss             # Cancel
```

When any action returns `error: "blocked_by_dialog"`, it includes the dialog info — you already know what it says without calling `dialog status`.

## Daemon Issues

### Daemon won't start

```bash
cloak doctor           # comprehensive self-check
cloak daemon health    # quick health check
```

Common causes:
- Port conflict: daemon tries 18765-18774, all busy → check for zombie processes
- Browser binary missing: `cloak doctor` will tell you
- Xvfb required on headless Linux for stealth mode

### Daemon auto-start

The daemon starts on your first command and stops after idle timeout. You rarely need manual control:

```bash
cloak daemon start -b    # manual start (background)
cloak daemon stop        # manual stop
```

## Snapshot Issues

### Too much output

Use `--mode compact` (the default — interactive elements only) or `--limit 50` to truncate further.

### Missing elements

Some elements may be in iframes. Try `--frames` to include iframe content. Or `--mode dom` for raw HTML (large output, last resort).

### Stale refs

If `element_not_found` persists after auto-retry, the page may have changed significantly. Take a fresh snapshot and find the element again.

## RemoteBridge Issues

### Extension not connecting

1. Check extension is loaded: `chrome://extensions` → agentcloak should show "Active"
2. Check daemon is running: `cloak daemon health`
3. Check port: extension probes 18765-18774. If daemon is on a different port, the extension may not find it
4. Check network: extension connects via WebSocket to the daemon's IP

### CDP endpoint not available

```bash
cloak cdp endpoint
# If error: browser may not have CDP port exposed
# CloakBrowser backend always has CDP; RemoteBridge gets it from extension
```

## Performance Tips

- Use `--mode compact` instead of full `accessible` when you only need interactive elements
- Use `--include-snapshot` on actions to save a round trip
- Use `--diff` to only see changes since last snapshot
- Use batch mode (`cloak do batch --calls-file`) for multiple sequential actions
- Use `--max-chars` to limit output size when working with token budgets
