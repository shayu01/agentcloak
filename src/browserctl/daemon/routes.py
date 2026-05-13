"""Endpoint catalog — one route per browser command."""

from __future__ import annotations

import asyncio
from typing import Any

import orjson
import structlog
from aiohttp import WSMsgType, web
from aiohttp.web import Request, Response

from browserctl.browser.patchright_ctx import screenshot_to_base64
from browserctl.core.types import PROFILE_NAME_RE as _PROFILE_NAME_RE

logger = structlog.get_logger()

__all__ = ["setup_routes"]


def _json(data: dict[str, Any], *, status: int = 200) -> Response:
    return Response(
        body=orjson.dumps(data),
        status=status,
        content_type="application/json",
    )


def _ok(data: dict[str, Any], *, seq: int) -> Response:
    return _json({"ok": True, "seq": seq, "data": data})


def setup_routes(app: web.Application) -> None:
    app.router.add_get("/health", handle_health)
    app.router.add_post("/navigate", handle_navigate)
    app.router.add_get("/screenshot", handle_screenshot)
    app.router.add_get("/snapshot", handle_snapshot)
    app.router.add_get("/state", handle_state)
    app.router.add_post("/evaluate", handle_evaluate)
    app.router.add_get("/network", handle_network)
    app.router.add_post("/action", handle_action)
    app.router.add_post("/action/batch", handle_action_batch)
    app.router.add_post("/fetch", handle_fetch)
    app.router.add_post("/shutdown", handle_shutdown)
    app.router.add_get("/bridge/ws", handle_bridge_ws)
    app.router.add_post("/cookies/export", handle_cookies_export)
    app.router.add_post("/cookies/import", handle_cookies_import)
    app.router.add_post("/capture/start", handle_capture_start)
    app.router.add_post("/capture/stop", handle_capture_stop)
    app.router.add_get("/capture/status", handle_capture_status)
    app.router.add_get("/capture/export", handle_capture_export)
    app.router.add_get("/capture/analyze", handle_capture_analyze)
    app.router.add_post("/capture/clear", handle_capture_clear)
    app.router.add_get("/cdp/endpoint", handle_cdp_endpoint)
    app.router.add_get("/tabs", handle_tab_list)
    app.router.add_post("/tab/new", handle_tab_new)
    app.router.add_post("/tab/close", handle_tab_close)
    app.router.add_post("/tab/switch", handle_tab_switch)
    app.router.add_get("/resume", handle_resume)
    app.router.add_post("/site/run", handle_site_run)
    app.router.add_get("/site/list", handle_site_list)
    app.router.add_post("/capture/replay", handle_capture_replay)
    app.router.add_post(
        "/profile/create-from-current", handle_profile_create_from_current
    )
    app.router.add_get("/profile/list", handle_profile_list)
    app.router.add_post("/profile/create", handle_profile_create)
    app.router.add_post("/profile/delete", handle_profile_delete)


def _ctx(request: Request) -> Any:
    return request.app["browser_ctx"]


async def handle_health(request: Request) -> Response:
    data: dict[str, Any] = {"ok": True}
    ctx = _ctx(request)
    data["stealth_tier"] = ctx.stealth_tier.value
    data["seq"] = ctx.seq
    data["capture_recording"] = ctx.capture_store.recording
    data["capture_entries"] = len(ctx.capture_store)

    try:
        snap = await ctx.snapshot(mode="accessible")
        data["current_url"] = snap.url
        data["current_title"] = snap.title
    except Exception:
        data["current_url"] = None
        data["current_title"] = None

    local_proxy = request.app.get("local_proxy")
    if local_proxy is not None:
        try:
            data["local_proxy"] = {
                "running": local_proxy.is_running,
                "url": local_proxy.proxy_url,
            }
        except Exception:
            data["local_proxy"] = {"running": False}
    return _json(data)


async def handle_navigate(request: Request) -> Response:
    body = await request.json()
    url: str = body["url"]
    timeout: float = body.get("timeout", 30.0)
    ctx = _ctx(request)
    result = await ctx.navigate(url, timeout=timeout)
    await _update_resume(request, action_summary={"kind": "navigate", "url": url})
    return _ok(result, seq=ctx.seq)


async def handle_screenshot(request: Request) -> Response:
    ctx = _ctx(request)
    full_page = request.query.get("full_page", "false") == "true"
    fmt = request.query.get("format", "jpeg")
    quality_raw = request.query.get("quality", "80")
    try:
        quality = int(quality_raw)
    except ValueError:
        quality = 80
    raw = await ctx.screenshot(full_page=full_page, format=fmt, quality=quality)
    b64 = screenshot_to_base64(raw)
    return _ok(
        {"base64": b64, "size": len(raw), "format": fmt},
        seq=ctx.seq,
    )


async def handle_snapshot(request: Request) -> Response:
    ctx = _ctx(request)
    mode = request.query.get("mode", "accessible")
    max_chars_raw = request.query.get("max_chars", "0")
    max_chars = int(max_chars_raw) if max_chars_raw.isdigit() else 0

    include_sm = request.query.get(
        "include_selector_map", "true"
    ).lower() != "false"

    snap = await ctx.snapshot(mode=mode)
    tree_text = snap.tree_text
    truncated = False
    if max_chars and len(tree_text) > max_chars:
        tree_text = tree_text[:max_chars] + "\n[...truncated...]"
        truncated = True

    data: dict[str, Any] = {
        "url": snap.url,
        "title": snap.title,
        "mode": snap.mode,
        "tree_text": tree_text,
        "tree_size": len(snap.tree_text),
        "truncated": truncated,
    }
    if include_sm:
        data["selector_map"] = {
            str(k): {
                "index": v.index,
                "tag": v.tag,
                "role": v.role,
                "text": v.text,
            }
            for k, v in snap.selector_map.items()
        }
    if snap.security_warnings:
        data["security_warnings"] = snap.security_warnings
    return _ok(data, seq=ctx.seq)


async def handle_state(request: Request) -> Response:
    ctx = _ctx(request)
    snap = await ctx.snapshot(mode="accessible")
    raw_screenshot = await ctx.screenshot(format="jpeg", quality=80)
    b64 = screenshot_to_base64(raw_screenshot)
    network_reqs = await ctx.network(since=0)

    data: dict[str, Any] = {
        "seq": ctx.seq,
        "url": snap.url,
        "title": snap.title,
        "tree_text": snap.tree_text,
        "selector_map": {
            str(k): {"index": v.index, "tag": v.tag, "role": v.role, "text": v.text}
            for k, v in snap.selector_map.items()
        },
        "screenshot_b64": b64,
        "stealth_tier": ctx.stealth_tier.value,
        "pending_network_requests": network_reqs[-20:],
    }
    return _ok(data, seq=ctx.seq)


async def handle_evaluate(request: Request) -> Response:
    body = await request.json()
    js: str = body["js"]
    world: str = body.get("world", "main")
    max_return_size: int = int(body.get("max_return_size", 50_000))
    ctx = _ctx(request)
    result = await ctx.evaluate(js, world=world)

    # Truncate large results before they exceed MCP token limits.
    result_bytes = orjson.dumps(result)
    total_size = len(result_bytes)
    if total_size > max_return_size:
        result_repr = (
            result_bytes[:max_return_size].decode("utf-8", errors="replace")
            + "\n[...truncated...]"
        )
        return _ok(
            {"result": result_repr, "truncated": True, "total_size": total_size},
            seq=ctx.seq,
        )

    return _ok(
        {"result": result, "truncated": False, "total_size": total_size}, seq=ctx.seq
    )


async def handle_network(request: Request) -> Response:
    ctx = _ctx(request)
    since_raw = request.query.get("since", "0")
    since: int | str = int(since_raw) if since_raw.isdigit() else since_raw
    reqs = await ctx.network(since=since)
    return _ok({"requests": reqs, "count": len(reqs)}, seq=ctx.seq)


async def handle_action(request: Request) -> Response:
    body = await request.json()
    kind: str = body["kind"]
    index = body.get("index")
    target = str(index) if index is not None else body.get("target", "")
    extra = {k: v for k, v in body.items() if k not in ("kind", "index", "target")}
    ctx = _ctx(request)
    result = await ctx.action(kind, target, **extra)
    summary: dict[str, Any] = {"kind": kind, "target": target}
    if kind in ("fill", "type"):
        summary["text"] = extra.get("text", "")
    elif kind == "press":
        summary["key"] = extra.get("key", "")
    elif kind == "scroll":
        summary["direction"] = extra.get("direction", "down")
    elif kind == "select":
        summary["value"] = extra.get("value", "")
    await _update_resume(request, action_summary=summary)
    return _ok(result, seq=ctx.seq)


async def handle_action_batch(request: Request) -> Response:
    body = await request.json()
    actions: list[dict[str, Any]] = body.get("actions", [])
    sleep: float = body.get("sleep", 0.0)
    ctx = _ctx(request)
    result = await ctx.action_batch(actions, sleep=sleep)
    return _ok(result, seq=ctx.seq)


async def handle_fetch(request: Request) -> Response:
    body = await request.json()
    url: str = body["url"]
    method: str = body.get("method", "GET")
    req_body: str | None = body.get("body")
    headers: dict[str, str] | None = body.get("headers")
    timeout: float = body.get("timeout", 30.0)
    ctx = _ctx(request)
    result = await ctx.fetch(
        url, method=method, body=req_body, headers=headers, timeout=timeout
    )
    return _ok(result, seq=ctx.seq)


async def handle_shutdown(request: Request) -> Response:
    # Localhost check is now handled by error_middleware for all endpoints.
    request.app["shutdown_event"].set()
    return _ok({}, seq=0)


def _check_bridge_token(request: Request) -> bool:
    """Verify bridge auth token. Localhost connections skip auth."""
    peername = request.transport and request.transport.get_extra_info("peername")
    if peername and peername[0] in ("127.0.0.1", "::1"):
        return True

    expected = request.app.get("bridge_token")
    if not expected:
        return True

    auth = request.headers.get("Authorization", "")
    return auth == f"Bearer {expected}"


async def handle_bridge_ws(request: Request) -> web.WebSocketResponse:
    """WebSocket endpoint for bridge connection."""
    if not _check_bridge_token(request):
        raise web.HTTPUnauthorized(text="invalid bridge token")

    from browserctl.browser.remote_ctx import RemoteBridgeContext

    ws = web.WebSocketResponse(heartbeat=30.0)
    await ws.prepare(request)

    remote_ctx = RemoteBridgeContext(bridge_ws=ws)
    request.app["bridge_ws"] = ws
    request.app["remote_ctx"] = remote_ctx

    async for msg in ws:
        if msg.type == WSMsgType.TEXT:
            remote_ctx.feed_message(msg.data)
        elif msg.type in (WSMsgType.CLOSE, WSMsgType.ERROR):
            break

    request.app.pop("bridge_ws", None)
    request.app.pop("remote_ctx", None)
    return ws


async def handle_cookies_export(request: Request) -> Response:
    """Export cookies from local browser or remote bridge."""
    body = await request.json()
    url: str | None = body.get("url")

    remote_ctx = request.app.get("remote_ctx")
    if remote_ctx is not None:
        from browserctl.browser.remote_ctx import RemoteBridgeContext

        if not isinstance(remote_ctx, RemoteBridgeContext):
            raise RuntimeError("remote_ctx is not a RemoteBridgeContext instance")
        params: dict[str, Any] = {}
        if url:
            params["url"] = url
        result = await remote_ctx.send_command("cookies", params)
        return _ok({"cookies": result}, seq=0)

    ctx = _ctx(request)
    browser_context = ctx._get_browser_context()
    if url:
        cookies = await browser_context.cookies(url)
    else:
        cookies = await browser_context.cookies()
    serializable = [
        {
            "name": c.get("name", ""),
            "value": c.get("value", ""),
            "domain": c.get("domain", ""),
            "path": c.get("path", "/"),
            "expires": c.get("expires", -1),
            "httpOnly": c.get("httpOnly", False),
            "secure": c.get("secure", False),
            "sameSite": c.get("sameSite", "None"),
        }
        for c in cookies
    ]
    return _ok({"cookies": serializable, "count": len(serializable)}, seq=ctx.seq)


async def handle_cookies_import(request: Request) -> Response:
    """Import cookies into the local browser context."""
    body = await request.json()
    cookies: list[dict[str, Any]] = body.get("cookies", [])
    if not cookies:
        return _json(
            {
                "ok": False,
                "error": "no_cookies",
                "hint": "No cookies provided",
                "action": "pass cookies as JSON array in 'cookies' field",
            },
            status=400,
        )
    ctx = _ctx(request)
    browser_context = ctx._get_browser_context()
    await browser_context.add_cookies(cookies)
    return _ok({"imported": len(cookies)}, seq=ctx.seq)


async def handle_capture_start(request: Request) -> Response:
    ctx = _ctx(request)
    ctx.capture_store.start()
    return _ok({"recording": True}, seq=ctx.seq)


async def handle_capture_stop(request: Request) -> Response:
    ctx = _ctx(request)
    ctx.capture_store.stop()
    return _ok({"recording": False, "entries": len(ctx.capture_store)}, seq=ctx.seq)


async def handle_capture_status(request: Request) -> Response:
    ctx = _ctx(request)
    store = ctx.capture_store
    return _ok({"recording": store.recording, "entries": len(store)}, seq=ctx.seq)


async def handle_capture_export(request: Request) -> Response:
    from browserctl.core.har import to_har

    ctx = _ctx(request)
    fmt = request.query.get("format", "har")
    entries = ctx.capture_store.entries()

    if fmt == "json":
        return _ok(
            {"entries": ctx.capture_store.to_dict_list(), "count": len(entries)},
            seq=ctx.seq,
        )

    har = to_har(entries)
    return _ok(har, seq=ctx.seq)


async def handle_capture_analyze(request: Request) -> Response:
    from browserctl.adapters.analyzer import PatternAnalyzer

    ctx = _ctx(request)
    domain = request.query.get("domain")
    if domain:
        entries = ctx.capture_store.entries_by_domain(domain)
    else:
        entries = ctx.capture_store.api_entries()

    try:
        analyzer = PatternAnalyzer(entries)
        patterns = analyzer.analyze()
    except Exception:
        logger.exception("capture_analyze_failed")
        return _json(
            {
                "ok": False,
                "error": "analyze_failed",
                "hint": "PatternAnalyzer raised an exception; check daemon logs",
                "action": "try capture export --format json to inspect raw entries",
            },
            status=500,
        )

    patterns_data: list[dict[str, Any]] = []
    for p in patterns:
        # Ensure status_codes keys are strings for JSON serialization
        status_codes = {str(k): v for k, v in p.status_codes.items()}
        patterns_data.append(
            {
                "method": p.method,
                "path": p.path,
                "domain": p.domain,
                "call_count": p.call_count,
                "query_params": p.query_params,
                "status_codes": status_codes,
                "auth_headers": p.auth_headers,
                "content_type": p.content_type,
                "category": p.category,
                "strategy": p.strategy.value,
                "request_schema": p.request_schema,
                "response_schema": p.response_schema,
                "example_urls": p.example_urls,
            }
        )

    return _ok({"patterns": patterns_data, "count": len(patterns_data)}, seq=ctx.seq)


async def handle_capture_clear(request: Request) -> Response:
    ctx = _ctx(request)
    ctx.capture_store.clear()
    return _ok({"cleared": True}, seq=ctx.seq)


async def handle_cdp_endpoint(request: Request) -> Response:
    """Return the CDP WebSocket URL for jshookmcp browser_attach."""
    import aiohttp

    ctx = _ctx(request)
    cdp_port: int | None = getattr(ctx, "_cdp_port", None)
    if not cdp_port:
        return _json(
            {
                "ok": False,
                "error": "no_cdp_port",
                "hint": "No CDP port available",
                "action": "restart daemon — CDP port is allocated at browser launch",
            },
            status=503,
        )

    http_url = f"http://127.0.0.1:{cdp_port}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{http_url}/json/version", timeout=aiohttp.ClientTimeout(total=3)
            ) as resp:
                info = await resp.json(content_type=None)
        ws_endpoint: str = info.get("webSocketDebuggerUrl", "")
    except Exception as exc:
        return _json(
            {
                "ok": False,
                "error": "cdp_unreachable",
                "hint": f"DevTools HTTP API at port {cdp_port} unreachable: {exc}",
                "action": "ensure browser is running and CDP port is open",
            },
            status=503,
        )

    return _ok(
        {"ws_endpoint": ws_endpoint, "http_url": http_url, "port": cdp_port},
        seq=ctx.seq,
    )


async def handle_tab_list(request: Request) -> Response:
    ctx = _ctx(request)
    tabs = await ctx.tab_list()
    data = [
        {"tab_id": t.tab_id, "url": t.url, "title": t.title, "active": t.active}
        for t in tabs
    ]
    return _ok({"tabs": data, "count": len(data)}, seq=ctx.seq)


async def handle_tab_new(request: Request) -> Response:
    body = await request.json()
    url: str | None = body.get("url")
    ctx = _ctx(request)
    result = await ctx.tab_new(url)
    return _ok(result, seq=ctx.seq)


async def handle_tab_close(request: Request) -> Response:
    body = await request.json()
    tab_id: int = body["tab_id"]
    ctx = _ctx(request)
    result = await ctx.tab_close(tab_id)
    return _ok(result, seq=ctx.seq)


async def handle_tab_switch(request: Request) -> Response:
    body = await request.json()
    tab_id: int = body["tab_id"]
    ctx = _ctx(request)
    result = await ctx.tab_switch(tab_id)
    return _ok(result, seq=ctx.seq)


async def _update_resume(
    request: Request,
    *,
    action_summary: dict[str, Any] | None = None,
) -> None:
    """Mark resume snapshot dirty (non-blocking, background task flushes)."""
    writer: Any = request.app.get("resume_writer")
    if writer is None:
        return
    ctx = _ctx(request)

    url = ""
    title = ""
    tabs: list[dict[str, Any]] = []
    try:
        inner = getattr(ctx, "_inner", ctx)
        page = getattr(inner, "_page", None)
        if page is not None:
            url = str(page.url)
            try:
                title = str(await page.title())
            except Exception:
                title = ""
        tab_dict: dict[int, Any] = getattr(inner, "_tabs", {})
        for tid, pg in tab_dict.items():
            try:
                tabs.append({"tab_id": tid, "url": str(pg.url)})
            except Exception:
                tabs.append({"tab_id": tid, "url": ""})
    except Exception:
        logger.debug("resume_state_extraction_failed", exc_info=True)

    writer.mark_dirty(
        url=url,
        title=title,
        tabs=tabs,
        action_summary=action_summary,
        capture_active=ctx.capture_store.recording,
        stealth_tier=ctx.stealth_tier.value,
    )


async def handle_resume(request: Request) -> Response:
    """Return the current resume snapshot for agent session recovery."""
    writer = request.app.get("resume_writer")
    if writer is None:
        return _json(
            {
                "ok": False,
                "error": "resume_unavailable",
                "hint": "Resume writer not initialized",
                "action": "restart the daemon",
            },
            status=503,
        )
    snap = writer.current_snapshot
    return _ok(snap.to_dict(), seq=_ctx(request).seq)


async def handle_site_run(request: Request) -> Response:
    """Run a registered adapter with the daemon's live browser context."""
    from browserctl.adapters.discovery import discover_adapters
    from browserctl.adapters.executor import execute_adapter
    from browserctl.adapters.registry import get_registry

    body = await request.json()
    name: str = body.get("name", "")
    args: dict[str, Any] = body.get("args", {})
    ctx = _ctx(request)

    parts = name.split("/", 1)
    if len(parts) != 2:
        return _json(
            {
                "ok": False,
                "error": "invalid_adapter_name",
                "hint": f"Expected 'site/command', got '{name}'",
                "action": "use format like 'httpbin/headers'",
            },
            status=400,
        )

    discover_adapters()
    registry = get_registry()
    entry = registry.get(parts[0], parts[1])
    if entry is None:
        available = [e.meta.full_name for e in registry.list_all()]
        return _json(
            {
                "ok": False,
                "error": "adapter_not_found",
                "hint": f"No adapter '{name}'",
                "action": f"available: {', '.join(available[:10])}",
            },
            status=404,
        )

    result = await execute_adapter(entry, args=args, browser=ctx)
    return _ok({"result": result}, seq=ctx.seq)


async def handle_site_list(request: Request) -> Response:
    """List all registered adapters."""
    from browserctl.adapters.discovery import discover_adapters
    from browserctl.adapters.registry import get_registry

    discover_adapters()
    registry = get_registry()
    adapters = [
        {
            "full_name": e.meta.full_name,
            "strategy": e.meta.strategy.value,
            "access": e.meta.access,
            "description": e.meta.description,
        }
        for e in registry.list_all()
    ]
    return _ok({"adapters": adapters, "count": len(adapters)}, seq=_ctx(request).seq)


_HOP_BY_HOP = frozenset({
    "host", "content-length", "connection", "transfer-encoding",
    "keep-alive", "te", "trailer", "upgrade",
    "proxy-authorization", "proxy-authenticate",
})


async def handle_capture_replay(request: Request) -> Response:
    """Replay the most recent captured entry matching url+method."""
    body = await request.json()
    url: str = body.get("url", "")
    method: str = body.get("method", "GET")
    ctx = _ctx(request)

    if not url:
        return _json(
            {"ok": False, "error": "missing_url", "hint": "url is required",
             "action": "provide a URL to replay"},
            status=400,
        )

    entry = ctx.capture_store.find_latest(url, method)
    if entry is None:
        return _json(
            {
                "ok": False,
                "error": "capture_entry_not_found",
                "hint": f"No captured {method.upper()} {url}",
                "action": "run 'capture start', navigate to trigger the request, then replay",  # noqa: E501
            },
            status=404,
        )

    replay_headers = {
        k: v for k, v in entry.request_headers.items()
        if k.lower() not in _HOP_BY_HOP
    }

    result = await ctx.fetch(
        url,
        method=entry.method,
        body=entry.request_body,
        headers=replay_headers if replay_headers else None,
    )
    result["replayed_from"] = {
        "url": entry.url, "method": entry.method, "seq": entry.seq
    }
    return _ok(result, seq=ctx.seq)


async def handle_profile_create_from_current(request: Request) -> Response:
    """Create a profile from the current browser session's cookies."""
    body = await request.json()
    name: str = body.get("name", "")
    ctx = _ctx(request)

    if not name:
        return _json(
            {"ok": False, "error": "missing_name", "hint": "name is required",
             "action": "provide 'name' parameter"},
            status=400,
        )
    if not _PROFILE_NAME_RE.match(name):
        return _json(
            {
                "ok": False,
                "error": "invalid_profile_name",
                "hint": f"Profile name '{name}' is not valid",
                "action": "use lowercase alphanumeric and hyphens",
            },
            status=400,
        )

    from browserctl.core.config import load_config

    paths, _ = load_config()
    profiles_dir = paths.profiles_dir
    profiles_dir.mkdir(parents=True, exist_ok=True)

    # Resolve name — auto-increment if exists
    actual_name = name
    renamed = False
    if (profiles_dir / actual_name).exists():
        counter = 2
        while (profiles_dir / f"{name}-{counter}").exists():
            counter += 1
        actual_name = f"{name}-{counter}"
        renamed = True

    profile_dir = profiles_dir / actual_name

    # Export cookies from current session (local or bridge)
    remote_ctx = request.app.get("remote_ctx")
    if remote_ctx is not None:
        from browserctl.browser.remote_ctx import RemoteBridgeContext
        if not isinstance(remote_ctx, RemoteBridgeContext):
            raise RuntimeError("remote_ctx is not a RemoteBridgeContext instance")
        cookies: list[dict[str, Any]] = await remote_ctx.send_command("cookies", {})
    else:
        browser_context = ctx._get_browser_context()
        cookies = await browser_context.cookies()

    # Write cookies into a new persistent profile via subprocess (keeps daemon stable)
    import json as _json_mod
    import os as _os
    import sys
    import tempfile as _tempfile

    profile_dir.mkdir(parents=True, exist_ok=True)

    exec_path: str | None = None
    try:
        import cloakbrowser as _cb
        info = _cb.binary_info()
        if info.get("installed"):
            exec_path = info["binary_path"]
    except ImportError:
        pass

    # Write cookies to a temp file (mode 0o600) to avoid leaking via /proc cmdline
    fd, cookies_file = _tempfile.mkstemp(suffix=".json", prefix="bctl-cookies-")
    try:
        with _os.fdopen(fd, "w") as f:
            _json_mod.dump(cookies, f)
        _os.chmod(cookies_file, 0o600)

        cmd = [
            sys.executable, "-m", "browserctl.browser._profile_writer",
            "--profile-dir", str(profile_dir),
            "--cookies-file", cookies_file,
        ]
        if exec_path:
            cmd.extend(["--executable-path", exec_path])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr_bytes = await proc.communicate()
    finally:
        # Always clean up the temp file
        import contextlib
        with contextlib.suppress(OSError):
            _os.unlink(cookies_file)
    if proc.returncode != 0:
        err_msg = stderr_bytes.decode(errors="replace")[:300]
        return _json(
            {"ok": False, "error": "profile_writer_failed", "hint": err_msg},
            status=500,
        )

    return _ok(
        {"profile": actual_name, "renamed": renamed, "cookie_count": len(cookies)},
        seq=ctx.seq,
    )


async def handle_profile_list(request: Request) -> Response:
    from browserctl.core.config import load_config

    paths, _ = load_config()
    profiles_dir = paths.profiles_dir
    profiles_dir.mkdir(parents=True, exist_ok=True)
    names = sorted(d.name for d in profiles_dir.iterdir() if d.is_dir())
    return _json({"ok": True, "profiles": names, "count": len(names)})


async def handle_profile_create(request: Request) -> Response:
    from browserctl.core.config import load_config

    body = await request.json()
    name: str = body.get("name", "")
    if not name:
        return _json(
            {
                "ok": False,
                "error": "missing_name",
                "hint": "Profile name is required",
                "action": "provide 'name' parameter",
            },
            status=400,
        )
    if not _PROFILE_NAME_RE.match(name):
        return _json(
            {
                "ok": False,
                "error": "invalid_profile_name",
                "hint": f"Profile name '{name}' is not valid",
                "action": "use lowercase alphanumeric and hyphens",
            },
            status=400,
        )
    paths, _ = load_config()
    profile_path = paths.profiles_dir / name
    if profile_path.exists():
        return _json(
            {
                "ok": False,
                "error": "profile_exists",
                "hint": f"Profile '{name}' already exists",
                "action": "use a different name or delete first",
            },
            status=409,
        )
    profile_path.mkdir(parents=True)
    return _json({"ok": True, "created": name})


async def handle_profile_delete(request: Request) -> Response:
    import shutil

    from browserctl.core.config import load_config

    body = await request.json()
    name: str = body.get("name", "")
    if not name:
        return _json(
            {
                "ok": False,
                "error": "missing_name",
                "hint": "Profile name is required",
                "action": "provide 'name' parameter",
            },
            status=400,
        )
    if not _PROFILE_NAME_RE.match(name):
        return _json(
            {
                "ok": False,
                "error": "invalid_profile_name",
                "hint": f"Profile name '{name}' is not valid",
                "action": "use lowercase alphanumeric and hyphens",
            },
            status=400,
        )
    paths, _ = load_config()
    profiles_dir = paths.profiles_dir
    profile_path = profiles_dir / name
    if not profile_path.resolve().is_relative_to(profiles_dir.resolve()):
        return _json(
            {
                "ok": False,
                "error": "invalid_profile_path",
                "hint": "Profile path escapes profiles directory",
                "action": "use a simple profile name without path separators",
            },
            status=400,
        )
    if not profile_path.exists():
        return _json(
            {
                "ok": False,
                "error": "profile_not_found",
                "hint": f"Profile '{name}' does not exist",
                "action": "use profile list to see available",
            },
            status=404,
        )
    shutil.rmtree(profile_path)
    return _json({"ok": True, "deleted": name})
