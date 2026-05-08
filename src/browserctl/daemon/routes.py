"""Endpoint catalog — one route per browser command."""

from __future__ import annotations

from typing import Any

import orjson
from aiohttp import WSMsgType, web
from aiohttp.web import Request, Response

from browserctl.browser.patchright_ctx import PatchrightContext, screenshot_to_base64

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
    app.router.add_post("/capture/start", handle_capture_start)
    app.router.add_post("/capture/stop", handle_capture_stop)
    app.router.add_get("/capture/status", handle_capture_status)
    app.router.add_get("/capture/export", handle_capture_export)
    app.router.add_get("/capture/analyze", handle_capture_analyze)
    app.router.add_post("/capture/clear", handle_capture_clear)
    app.router.add_get("/cdp/endpoint", handle_cdp_endpoint)


def _ctx(request: Request) -> PatchrightContext:
    ctx: PatchrightContext = request.app["browser_ctx"]
    return ctx


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
    return _ok(result, seq=ctx.seq)


async def handle_screenshot(request: Request) -> Response:
    ctx = _ctx(request)
    full_page = request.query.get("full_page", "false") == "true"
    raw = await ctx.screenshot(full_page=full_page)
    b64 = screenshot_to_base64(raw)
    return _ok({"base64": b64, "size": len(raw)}, seq=ctx.seq)


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
    return _ok(data, seq=ctx.seq)


async def handle_state(request: Request) -> Response:
    ctx = _ctx(request)
    snap = await ctx.snapshot(mode="accessible")
    raw_screenshot = await ctx.screenshot()
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
    ctx = _ctx(request)
    result = await ctx.evaluate(js)
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
    """Export cookies from remote Chrome via bridge."""
    body = await request.json()
    url: str | None = body.get("url")

    remote_ctx = request.app.get("remote_ctx")
    if remote_ctx is None:
        return _json(
            {
                "ok": False,
                "error": "no_bridge",
                "hint": "No bridge connected",
                "action": "start bridge process on the remote machine",
            },
            status=503,
        )

    from browserctl.browser.remote_ctx import RemoteBridgeContext

    assert isinstance(remote_ctx, RemoteBridgeContext)
    params: dict[str, Any] = {}
    if url:
        params["url"] = url
    result = await remote_ctx.send_command("cookies", params)
    return _ok({"cookies": result}, seq=0)


async def handle_capture_start(request: Request) -> Response:
    ctx = _ctx(request)
    ctx.capture_store.start()
    return _ok({"recording": True}, seq=ctx.seq)


async def handle_capture_stop(request: Request) -> Response:
    ctx = _ctx(request)
    ctx.capture_store.stop()
    return _ok(
        {"recording": False, "entries": len(ctx.capture_store)}, seq=ctx.seq
    )


async def handle_capture_status(request: Request) -> Response:
    ctx = _ctx(request)
    store = ctx.capture_store
    return _ok(
        {"recording": store.recording, "entries": len(store)}, seq=ctx.seq
    )


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

    analyzer = PatternAnalyzer(entries)
    patterns = analyzer.analyze()

    patterns_data: list[dict[str, Any]] = []
    for p in patterns:
        patterns_data.append(
            {
                "method": p.method,
                "path": p.path,
                "domain": p.domain,
                "call_count": p.call_count,
                "query_params": p.query_params,
                "status_codes": p.status_codes,
                "auth_headers": p.auth_headers,
                "content_type": p.content_type,
                "category": p.category,
                "strategy": p.strategy.value,
                "request_schema": p.request_schema,
                "response_schema": p.response_schema,
                "example_urls": p.example_urls,
            }
        )

    return _ok(
        {"patterns": patterns_data, "count": len(patterns_data)}, seq=ctx.seq
    )


async def handle_capture_clear(request: Request) -> Response:
    ctx = _ctx(request)
    ctx.capture_store.clear()
    return _ok({"cleared": True}, seq=ctx.seq)


async def handle_cdp_endpoint(request: Request) -> Response:
    """Return the CDP WebSocket URL for jshookmcp browser_attach."""
    ctx = _ctx(request)
    browser = getattr(ctx, "_browser", None)
    if browser is None:
        return _json(
            {
                "ok": False,
                "error": "no_browser",
                "hint": "No browser instance available",
                "action": "navigate to a URL first to initialize the browser",
            },
            status=503,
        )
    try:
        ws_endpoint: str = browser.contexts[0].browser.ws_endpoint  # type: ignore[union-attr]
    except (AttributeError, IndexError):
        ws_endpoint = getattr(browser, "ws_endpoint", "")
    return _ok({"ws_endpoint": ws_endpoint}, seq=ctx.seq)
