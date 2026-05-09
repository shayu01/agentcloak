"""Endpoint catalog — one route per browser command."""

from __future__ import annotations

from typing import Any

import orjson
import structlog
from aiohttp import WSMsgType, web
from aiohttp.web import Request, Response

from browserctl.browser.patchright_ctx import screenshot_to_base64

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
    _update_resume(request, action_summary={"kind": "navigate", "url": url})
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
    snap = await ctx.snapshot(mode=mode)
    data: dict[str, Any] = {
        "url": snap.url,
        "title": snap.title,
        "mode": snap.mode,
        "tree_text": snap.tree_text,
        "selector_map": {
            str(k): {"index": v.index, "tag": v.tag, "role": v.role, "text": v.text}
            for k, v in snap.selector_map.items()
        },
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
    ctx = _ctx(request)
    result = await ctx.evaluate(js, world=world)
    return _ok({"result": result}, seq=ctx.seq)


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
    _update_resume(request, action_summary={"kind": kind, "target": target})
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
    await request.app["browser_ctx"].close()
    raise web.GracefulExit


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

        assert isinstance(remote_ctx, RemoteBridgeContext)
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


def _update_resume(
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
    tabs: list[dict[str, Any]] = []
    try:
        inner = getattr(ctx, "_inner", ctx)
        page = getattr(inner, "_page", None)
        if page is not None:
            url = str(page.url)
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
        title="",
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
