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


def _ctx(request: Request) -> PatchrightContext:
    ctx: PatchrightContext = request.app["browser_ctx"]
    return ctx


async def handle_health(request: Request) -> Response:
    data: dict[str, Any] = {"ok": True}
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


async def handle_bridge_ws(request: Request) -> web.WebSocketResponse:
    """WebSocket endpoint for bridge connection."""
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
