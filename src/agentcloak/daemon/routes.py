"""FastAPI route definitions — thin shells over the service layer.

Each route handler does three things:
1. parse the Pydantic request body
2. delegate to a service in :mod:`agentcloak.daemon.services`
3. wrap the service's return value in the ``OkEnvelope`` shape

Business logic (stale-ref retry, snapshot diff, profile CRUD, capture export,
doctor checks) lives in the services. Routes intentionally avoid framework
specifics — when something goes wrong they either raise
:class:`AgentBrowserError` (caught by the global handler) or
:class:`HTTPException` with a structured detail dict.
"""

from __future__ import annotations

import secrets
from typing import Any

import orjson
import structlog
from fastapi import (
    APIRouter,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)

from agentcloak.browser.playwright_ctx import screenshot_to_base64
from agentcloak.core.errors import BackendError, ProfileError

# Annotated dependency aliases (BrowserCtxDep etc.) must be available at
# runtime so FastAPI can resolve `Depends()` markers when registering routes —
# placing them under TYPE_CHECKING would break the framework.
from agentcloak.daemon.dependencies import (  # noqa: TC001
    BrowserCtxDep,
    ConfigDep,
    ContextManagerDep,
    OptionalBrowserCtxDep,
    RemoteCtxDep,
    RequiredRemoteCtxDep,
)

# Pydantic Request *and* Response models must be runtime-resolvable so
# FastAPI can build OpenAPI schemas at startup — keep them out of
# TYPE_CHECKING. Each route declares ``response_model=OkEnvelope[XxxResponse]``
# (or a flat ``HealthResponse`` for the un-enveloped endpoints), which is
# what feeds the auto-generated OpenAPI spec consumed by T8.
from agentcloak.daemon.models import (
    ActionRequest,
    ActionResponse,
    BatchActionRequest,
    BatchActionResponse,
    BridgeClaimRequest,
    BridgeFinalizeRequest,
    BridgeOpResponse,
    BridgeTokenResetResponse,
    CaptureAnalyzeResponse,
    CaptureClearResponse,
    CaptureExportResponse,
    CaptureReplayRequest,
    CaptureReplayResponse,
    CaptureStatusResponse,
    CDPEndpointResponse,
    CookiesExportRequest,
    CookiesExportResponse,
    CookiesImportRequest,
    CookiesImportResponse,
    DialogHandleRequest,
    DialogHandleResponse,
    DialogStatusResponse,
    EvaluateRequest,
    EvaluateResponse,
    FetchRequest,
    FetchResponse,
    FrameFocusRequest,
    FrameFocusResponse,
    FrameListResponse,
    HealthResponse,
    LaunchRequest,
    LaunchResponse,
    NavigateRequest,
    NavigateResponse,
    NetworkResponse,
    OkEnvelope,
    ProfileCreateFromCurrentRequest,
    ProfileCreateFromCurrentResponse,
    ProfileCreateRequest,
    ProfileCreateResponse,
    ProfileDeleteRequest,
    ProfileListResponse,
    ResumeResponse,
    ScreenshotResponse,
    ShutdownResponse,
    SnapshotResponse,
    SpellListResponse,
    SpellRunRequest,
    SpellRunResponse,
    TabCloseRequest,
    TabListResponse,
    TabNewRequest,
    TabOpResponse,
    TabSwitchRequest,
    UploadRequest,
    UploadResponse,
    WaitRequest,
    WaitResponse,
)
from agentcloak.daemon.services import (
    ActionService,
    CaptureService,
    DiagnosticService,
    ProfileService,
    SnapshotService,
)

logger = structlog.get_logger()

__all__ = [
    "register_routers",
    "router",
]

router = APIRouter()


def _ok(data: Any, *, seq: int) -> dict[str, Any]:
    """Wrap a payload in the success envelope shared with the OkEnvelope model."""
    return {"ok": True, "seq": seq, "data": data}


def _profile_error_to_http(exc: ProfileError) -> HTTPException:
    """Translate a ProfileError into a FastAPI HTTPException with the right status."""
    status_map = {
        "missing_name": 400,
        "invalid_profile_name": 400,
        "invalid_profile_path": 400,
        "profile_exists": 409,
        "profile_not_found": 404,
        "profile_writer_failed": 500,
    }
    return HTTPException(
        status_code=status_map.get(exc.error, 400),
        detail=exc.to_dict(),
    )


def _profiles_dir():  # type: ignore[no-untyped-def]
    """Load the profiles directory from the daemon config snapshot."""
    from agentcloak.core.config import load_config

    paths, _ = load_config()
    return paths.profiles_dir


# --- Helpers ----------------------------------------------------------------


async def _update_resume(
    request: Request,
    ctx: Any,
    *,
    action_summary: dict[str, Any] | None = None,
) -> None:
    """Mark resume snapshot dirty (non-blocking, background task flushes)."""
    writer: Any = getattr(request.app.state, "resume_writer", None)
    if writer is None:
        return

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


# --- Health -----------------------------------------------------------------


@router.get("/health", response_model=HealthResponse)
async def handle_health(ctx: OptionalBrowserCtxDep, request: Request) -> dict[str, Any]:
    diagnostic = DiagnosticService()
    local_proxy = getattr(request.app.state, "local_proxy", None)
    active_tier = getattr(request.app.state, "active_tier", None)
    remote_connected = getattr(request.app.state, "remote_ctx", None) is not None
    return await diagnostic.health(
        ctx,
        local_proxy=local_proxy,
        active_tier=active_tier,
        remote_connected=remote_connected,
    )


# --- Navigate ---------------------------------------------------------------


@router.post("/navigate", response_model=OkEnvelope[NavigateResponse])
async def handle_navigate(
    body: NavigateRequest,
    ctx: BrowserCtxDep,
    request: Request,
) -> dict[str, Any]:
    result = await ctx.navigate(body.url, timeout=body.timeout)
    await _update_resume(
        request, ctx, action_summary={"kind": "navigate", "url": body.url}
    )

    if body.include_snapshot:
        try:
            snap = await ctx.snapshot(mode=body.snapshot_mode)
            SnapshotService.attach_snapshot_to_result(result, snap)
        except Exception:
            logger.debug("include_snapshot_failed", exc_info=True)

    return _ok(result, seq=ctx.seq)


# --- Screenshot -------------------------------------------------------------


@router.get("/screenshot", response_model=OkEnvelope[ScreenshotResponse])
async def handle_screenshot(
    ctx: BrowserCtxDep,
    config: ConfigDep,
    full_page: bool = False,
    format: str = "jpeg",
    quality: int | None = None,
) -> dict[str, Any]:
    # ``quality=None`` resolves to the configured default. CLI callers leave
    # this unset and inherit the file/env default; MCP tools pass an explicit
    # lower value so screenshots stay under MCP token budgets.
    if quality is None:
        quality = config.screenshot_quality
    raw = await ctx.screenshot(full_page=full_page, format=format, quality=quality)
    b64 = screenshot_to_base64(raw)
    return _ok(
        {"base64": b64, "size": len(raw), "format": format},
        seq=ctx.seq,
    )


# --- Snapshot ---------------------------------------------------------------


@router.get("/snapshot", response_model=OkEnvelope[SnapshotResponse])
async def handle_snapshot(
    ctx: BrowserCtxDep,
    request: Request,
    mode: str = "accessible",
    max_nodes: int = 0,
    max_chars: int = 0,
    focus: int = 0,
    offset: int = 0,
    include_selector_map: bool = True,
    frames: bool = False,
    diff: bool = False,
) -> dict[str, Any]:
    service = SnapshotService()
    prev_cache = getattr(request.app.state, "prev_snapshot_lines", None)

    data, cur_cache = await service.get(
        ctx,
        mode=mode,
        max_nodes=max_nodes,
        max_chars=max_chars,
        focus=focus,
        offset=offset,
        include_selector_map=include_selector_map,
        frames=frames,
        diff=diff,
        prev_cached_lines=prev_cache,
    )

    if cur_cache is not None:
        request.app.state.prev_snapshot_lines = cur_cache

    return _ok(data, seq=ctx.seq)


# --- Evaluate ---------------------------------------------------------------


@router.post("/evaluate", response_model=OkEnvelope[EvaluateResponse])
async def handle_evaluate(body: EvaluateRequest, ctx: BrowserCtxDep) -> dict[str, Any]:
    result = await ctx.evaluate(body.js, world=body.world)

    # Truncate large results before they exceed MCP token limits.
    result_bytes = orjson.dumps(result)
    total_size = len(result_bytes)
    if total_size > body.max_return_size:
        result_repr = (
            result_bytes[: body.max_return_size].decode("utf-8", errors="replace")
            + "\n[...truncated...]"
        )
        return _ok(
            {"result": result_repr, "truncated": True, "total_size": total_size},
            seq=ctx.seq,
        )

    return _ok(
        {"result": result, "truncated": False, "total_size": total_size}, seq=ctx.seq
    )


# --- Network ----------------------------------------------------------------


@router.get("/network", response_model=OkEnvelope[NetworkResponse])
async def handle_network(ctx: BrowserCtxDep, since: str = "0") -> dict[str, Any]:
    since_value: int | str = int(since) if since.isdigit() else since
    reqs = await ctx.network(since=since_value)
    return _ok({"requests": reqs, "count": len(reqs)}, seq=ctx.seq)


# --- Action -----------------------------------------------------------------


@router.post("/action", response_model=OkEnvelope[ActionResponse])
async def handle_action(
    body: ActionRequest,
    ctx: BrowserCtxDep,
    request: Request,
) -> dict[str, Any]:
    target = str(body.index) if body.index is not None else body.target
    extra = body.model_dump(exclude_unset=True)
    for known in ("kind", "index", "target", "include_snapshot", "snapshot_mode"):
        extra.pop(known, None)

    service = ActionService()
    # DialogBlockedError raised from ctx.action() bubbles up to the FastAPI
    # exception handler (409 with dialog metadata) — no special case needed.
    result, retried = await service.execute(ctx, body.kind, target, extra=extra)
    if retried:
        result["retried"] = True

    summary: dict[str, Any] = {"kind": body.kind, "target": target}
    if body.kind in ("fill", "type"):
        summary["text"] = extra.get("text", "")
    elif body.kind in ("press", "keydown", "keyup"):
        summary["key"] = extra.get("key", "")
    elif body.kind == "scroll":
        summary["direction"] = extra.get("direction", "down")
    elif body.kind == "select":
        summary["value"] = extra.get("value", "")
    await _update_resume(request, ctx, action_summary=summary)

    if body.include_snapshot:
        try:
            snap = await ctx.snapshot(mode=body.snapshot_mode)
            SnapshotService.attach_snapshot_to_result(result, snap)
        except Exception:
            logger.debug("include_snapshot_failed", exc_info=True)

    return _ok(result, seq=ctx.seq)


@router.post("/action/batch", response_model=OkEnvelope[BatchActionResponse])
async def handle_action_batch(
    body: BatchActionRequest,
    ctx: BrowserCtxDep,
    config: ConfigDep,
    request: Request,
) -> dict[str, Any]:
    settle_timeout = body.settle_timeout
    if not settle_timeout:
        settle_timeout = getattr(
            request.app.state, "batch_settle_timeout", config.batch_settle_timeout
        )

    service = ActionService()
    result = await service.execute_batch(
        ctx, body.actions, sleep_s=body.sleep, settle_timeout=settle_timeout
    )
    return _ok(result, seq=ctx.seq)


# --- Fetch ------------------------------------------------------------------


@router.post("/fetch", response_model=OkEnvelope[FetchResponse])
async def handle_fetch(body: FetchRequest, ctx: BrowserCtxDep) -> dict[str, Any]:
    result = await ctx.fetch(
        body.url,
        method=body.method,
        body=body.body,
        headers=body.headers,
        timeout=body.timeout,
    )
    return _ok(result, seq=ctx.seq)


# --- Shutdown ---------------------------------------------------------------


@router.post("/shutdown", response_model=OkEnvelope[ShutdownResponse])
async def handle_shutdown(request: Request) -> dict[str, Any]:
    event = getattr(request.app.state, "shutdown_event", None)
    if event is not None:
        event.set()
    return _ok({}, seq=0)


# --- Launch (tier hot-switch) -----------------------------------------------


@router.post("/launch", response_model=OkEnvelope[LaunchResponse])
async def handle_launch(
    body: LaunchRequest,
    manager: ContextManagerDep,
) -> dict[str, Any]:
    """Hot-switch the active browser tier without restarting the daemon.

    ``cloak``/``playwright`` create or re-use a local browser; remote_bridge
    waits for the Chrome extension to connect (if it isn't already).
    """
    from agentcloak.core.config import resolve_tier
    from agentcloak.core.types import StealthTier

    resolved = resolve_tier(body.tier)
    try:
        tier_enum = StealthTier(resolved)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "ok": False,
                "error": "invalid_tier",
                "hint": f"Unknown tier: {body.tier!r}",
                "action": "use one of: auto, cloak, playwright, remote_bridge",
            },
        ) from exc

    result = await manager.switch_tier(tier_enum, profile=body.profile)
    return _ok(result, seq=0)


# --- Bridge auth + WebSocket endpoints --------------------------------------


def _check_bridge_token(websocket: WebSocket) -> bool:
    """Verify bridge auth token. Localhost connections skip auth."""
    client = websocket.client
    if client and client.host in ("127.0.0.1", "::1", "localhost"):
        return True

    expected = getattr(websocket.app.state, "bridge_token", None)
    if not expected:
        return True

    auth = websocket.headers.get("Authorization", "")
    return secrets.compare_digest(auth, f"Bearer {expected}")


class _BridgeWSAdapter:
    """Adapter exposing FastAPI's :class:`WebSocket` under the narrow interface
    consumed by :class:`agentcloak.browser.remote_ctx.RemoteBridgeContext`.

    The browser layer only needs ``closed`` / ``send_str`` / ``close`` /
    ``receive_text`` to operate, so we expose just those. Keeping this shim
    isolates the browser code from any specific HTTP/WS framework — if the
    daemon transport ever changes we only have to provide a new adapter, not
    rewrite the remote backend. The contract is documented as the
    ``_BridgeWS`` Protocol in ``browser/remote_ctx.py``.
    """

    def __init__(self, ws: WebSocket) -> None:
        self._ws = ws
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    async def send_str(self, data: str) -> None:
        await self._ws.send_text(data)

    async def close(self) -> None:
        if not self._closed:
            self._closed = True
            await self._ws.close()

    async def receive_text(self) -> str:
        return await self._ws.receive_text()

    def mark_closed(self) -> None:
        self._closed = True


def _existing_remote_alive(app_state: Any) -> bool:
    """Return True if a remote_ctx is set and its underlying WS is still open."""
    existing = getattr(app_state, "remote_ctx", None)
    if existing is None:
        return False
    ws = getattr(existing, "_ws", None)
    if ws is None:
        return False
    # _BridgeWSAdapter exposes `closed`; treat unknown shape as alive to be safe.
    closed = getattr(ws, "closed", False)
    return not bool(closed)


def _cleanup_dead_remote(app_state: Any) -> None:
    """Drop a stale remote_ctx and its adapter handles before accepting a new one."""
    manager = getattr(app_state, "context_manager", None)
    if manager is not None:
        manager.on_extension_disconnected()
    else:
        app_state.remote_ctx = None
    app_state.bridge_ws = None
    app_state.ext_ws = None


def _notify_extension_connected(app_state: Any, remote_ctx: Any) -> None:
    """Inform the context manager (or fall back to direct state mutation)."""
    manager = getattr(app_state, "context_manager", None)
    if manager is not None:
        manager.on_extension_connected(remote_ctx)
    else:
        app_state.remote_ctx = remote_ctx


def _notify_extension_disconnected(app_state: Any) -> None:
    manager = getattr(app_state, "context_manager", None)
    if manager is not None:
        manager.on_extension_disconnected()
    else:
        app_state.remote_ctx = None


def _fail_pending_remote(remote_ctx: Any, reason: str) -> None:
    """Resolve every outstanding bridge future with a structured disconnect error.

    Without this, callers (CLI/MCP) wait the full 60s ``bridge_timeout`` after
    the extension drops the WebSocket. By failing futures eagerly we surface
    the disconnect on the next response cycle.
    """
    pending = getattr(remote_ctx, "_pending", None)
    if not pending:
        return
    err = BackendError(
        error="extension_disconnected",
        hint=f"Extension WebSocket closed: {reason}",
        action="reconnect the Chrome extension, then retry the command",
    )
    for fut in list(pending.values()):
        if not fut.done():
            fut.set_exception(err)
    pending.clear()


@router.websocket("/bridge/ws")
async def handle_bridge_ws(websocket: WebSocket) -> None:
    """WebSocket endpoint for bridge connection."""
    if not _check_bridge_token(websocket):
        await websocket.close(code=1008, reason="invalid bridge token")
        return

    # Mutex: only one remote_ctx may be active. Reject when an alive one exists.
    if _existing_remote_alive(websocket.app.state):
        await websocket.close(code=4002, reason="remote_ctx_in_use")
        logger.warning("bridge_ws_rejected", reason="remote_ctx_in_use")
        return

    _cleanup_dead_remote(websocket.app.state)

    from agentcloak.browser.remote_ctx import RemoteBridgeContext

    await websocket.accept()
    adapter = _BridgeWSAdapter(websocket)
    remote_ctx = RemoteBridgeContext(bridge_ws=adapter)  # type: ignore[arg-type]
    websocket.app.state.bridge_ws = adapter
    _notify_extension_connected(websocket.app.state, remote_ctx)

    try:
        while True:
            data = await websocket.receive_text()
            remote_ctx.feed_message(data)
    except WebSocketDisconnect:
        pass
    finally:
        adapter.mark_closed()
        _fail_pending_remote(remote_ctx, "bridge websocket closed")
        websocket.app.state.bridge_ws = None
        _notify_extension_disconnected(websocket.app.state)


@router.websocket("/ext")
async def handle_ext_ws(websocket: WebSocket) -> None:
    """Direct WebSocket endpoint for Chrome Extension.

    Browser WebSocket API cannot set custom headers, so token auth
    happens at the message level: accept first, then verify the token
    in the hello message from the extension.
    """
    from agentcloak.browser.remote_ctx import RemoteBridgeContext

    client = websocket.client
    is_local = client is not None and client.host in ("127.0.0.1", "::1", "localhost")

    await websocket.accept()

    # Wait for hello message and verify token (unless localhost).
    try:
        first_msg = await websocket.receive_text()
    except WebSocketDisconnect:
        return

    try:
        hello = orjson.loads(first_msg)
    except Exception:
        await websocket.close(code=1008, reason="invalid hello message")
        return

    if not is_local:
        expected = getattr(websocket.app.state, "bridge_token", None)
        if expected:
            ext_token = hello.get("token") or ""
            # Constant-time comparison to avoid leaking token info via timing.
            if not secrets.compare_digest(str(ext_token), str(expected)):
                logger.warning(
                    "ext_ws_auth_failed",
                    remote=client.host if client else None,
                )
                await websocket.close(code=4001, reason="invalid bridge token")
                return

    # /ext is exclusively used by the Chrome Extension. MV3 service workers
    # restart frequently — new connection always replaces old (no reject).
    if _existing_remote_alive(websocket.app.state):
        logger.info("ext_ws_replacing", remote=client.host if client else None)
        old_ws = getattr(websocket.app.state, "ext_ws", None)
        if old_ws and not getattr(old_ws, "closed", True):
            old_ws.mark_closed()

    _cleanup_dead_remote(websocket.app.state)

    adapter = _BridgeWSAdapter(websocket)
    remote_ctx = RemoteBridgeContext(bridge_ws=adapter)  # type: ignore[arg-type]
    websocket.app.state.ext_ws = adapter
    _notify_extension_connected(websocket.app.state, remote_ctx)

    logger.info("ext_ws_connected", remote=client.host if client else None)

    # Feed the hello message to remote_ctx in case it carries useful data.
    remote_ctx.feed_message(first_msg)

    try:
        while True:
            data = await websocket.receive_text()
            remote_ctx.feed_message(data)
    except WebSocketDisconnect:
        pass
    finally:
        adapter.mark_closed()
        _fail_pending_remote(remote_ctx, "extension websocket closed")
        websocket.app.state.ext_ws = None
        _notify_extension_disconnected(websocket.app.state)
        logger.info("ext_ws_disconnected")


# --- Bridge UX --------------------------------------------------------------


@router.post("/bridge/claim", response_model=OkEnvelope[BridgeOpResponse])
async def handle_bridge_claim(
    body: BridgeClaimRequest, remote_ctx: RequiredRemoteCtxDep
) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if body.tab_id is not None:
        params["tabId"] = body.tab_id
    if body.url_pattern is not None:
        params["urlPattern"] = body.url_pattern

    result = await remote_ctx.send_command("claim", params)
    return _ok(result, seq=0)


@router.post("/bridge/finalize", response_model=OkEnvelope[BridgeOpResponse])
async def handle_bridge_finalize(
    body: BridgeFinalizeRequest, remote_ctx: RequiredRemoteCtxDep
) -> dict[str, Any]:
    result = await remote_ctx.send_command("finalize", {"mode": body.mode})
    return _ok(result, seq=0)


@router.post(
    "/bridge/token/reset",
    response_model=OkEnvelope[BridgeTokenResetResponse],
)
async def handle_bridge_token_reset(request: Request) -> dict[str, Any]:
    """Rotate the persistent bridge auth token and hot-update the daemon.

    Persists the new token to ``~/.agentcloak/config.toml`` *and* replaces
    ``app.state.bridge_token`` so the previous value becomes invalid
    immediately — already-paired extensions will be rejected on their next
    reconnect (close code 4001). CLI ``agentcloak bridge token --reset``
    delegates here when a daemon is running so users don't need to restart
    just to rotate the credential.
    """
    from agentcloak.core.config import load_config, regenerate_bridge_token

    paths, cfg = load_config()
    new_token = regenerate_bridge_token(paths, cfg)
    request.app.state.bridge_token = new_token
    logger.info("bridge_token_rotated", token_suffix=new_token[-4:])
    return _ok({"token": new_token, "rotated": True}, seq=0)


# --- Cookies ----------------------------------------------------------------


@router.post("/cookies/export", response_model=OkEnvelope[CookiesExportResponse])
async def handle_cookies_export(
    body: CookiesExportRequest,
    ctx: BrowserCtxDep,
    remote_ctx: RemoteCtxDep,
) -> dict[str, Any]:
    if remote_ctx is not None:
        from agentcloak.browser.remote_ctx import RemoteBridgeContext

        if not isinstance(remote_ctx, RemoteBridgeContext):
            raise RuntimeError("remote_ctx is not a RemoteBridgeContext instance")
        params: dict[str, Any] = {}
        if body.url:
            params["url"] = body.url
        result = await remote_ctx.send_command("cookies", params)
        return _ok({"cookies": result}, seq=0)

    browser_context = ctx._get_browser_context()
    if body.url:
        cookies = await browser_context.cookies(body.url)
    else:
        cookies = await browser_context.cookies()
    # Field names use camelCase (httpOnly, sameSite) because these are passed
    # straight through from the Playwright / CDP Cookie spec — re-serializing
    # to snake_case would force agents to translate twice when feeding cookies
    # back into ``cookies/import`` or generic devtools clients.
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


@router.post("/cookies/import", response_model=OkEnvelope[CookiesImportResponse])
async def handle_cookies_import(
    body: CookiesImportRequest, ctx: BrowserCtxDep
) -> dict[str, Any]:
    if not body.cookies:
        raise HTTPException(
            status_code=400,
            detail={
                "ok": False,
                "error": "no_cookies",
                "hint": "No cookies provided",
                "action": "pass cookies as JSON array in 'cookies' field",
            },
        )
    browser_context = ctx._get_browser_context()
    await browser_context.add_cookies(body.cookies)
    return _ok({"imported": len(body.cookies)}, seq=ctx.seq)


# --- Capture ----------------------------------------------------------------


@router.post("/capture/start", response_model=OkEnvelope[CaptureStatusResponse])
async def handle_capture_start(ctx: BrowserCtxDep) -> dict[str, Any]:
    # ctx.capture_start() runs the backend's ``_capture_setup_impl`` hook
    # (no-op for Playwright, ``Network.enable`` for RemoteBridge) so capture
    # works uniformly across both backends.
    result = await ctx.capture_start()
    return _ok(result, seq=ctx.seq)


@router.post("/capture/stop", response_model=OkEnvelope[CaptureStatusResponse])
async def handle_capture_stop(ctx: BrowserCtxDep) -> dict[str, Any]:
    result = await ctx.capture_stop()
    return _ok(result, seq=ctx.seq)


@router.get("/capture/status", response_model=OkEnvelope[CaptureStatusResponse])
async def handle_capture_status(ctx: BrowserCtxDep) -> dict[str, Any]:
    service = CaptureService(ctx.capture_store)
    return _ok(service.status(), seq=ctx.seq)


@router.get("/capture/export", response_model=OkEnvelope[CaptureExportResponse])
async def handle_capture_export(
    ctx: BrowserCtxDep, format: str = "har"
) -> dict[str, Any]:
    service = CaptureService(ctx.capture_store)
    return _ok(service.export(fmt=format), seq=ctx.seq)


@router.get("/capture/analyze", response_model=OkEnvelope[CaptureAnalyzeResponse])
async def handle_capture_analyze(
    ctx: BrowserCtxDep, domain: str | None = None
) -> dict[str, Any]:
    service = CaptureService(ctx.capture_store)
    try:
        return _ok(service.analyze(domain=domain), seq=ctx.seq)
    except Exception as exc:
        from agentcloak.daemon.services.capture_service import CaptureReplayError

        if isinstance(exc, CaptureReplayError):
            raise HTTPException(status_code=500, detail=exc.to_dict()) from exc
        raise


@router.post("/capture/clear", response_model=OkEnvelope[CaptureClearResponse])
async def handle_capture_clear(ctx: BrowserCtxDep) -> dict[str, Any]:
    service = CaptureService(ctx.capture_store)
    return _ok(service.clear(), seq=ctx.seq)


@router.post("/capture/replay", response_model=OkEnvelope[CaptureReplayResponse])
async def handle_capture_replay(
    body: CaptureReplayRequest, ctx: BrowserCtxDep
) -> dict[str, Any]:
    from agentcloak.daemon.services.capture_service import CaptureReplayError

    service = CaptureService(ctx.capture_store)
    try:
        result = await service.replay(ctx, url=body.url, method=body.method)
    except CaptureReplayError as exc:
        status = {
            "missing_url": 400,
            "capture_entry_not_found": 404,
        }.get(exc.error, 400)
        raise HTTPException(status_code=status, detail=exc.to_dict()) from exc
    return _ok(result, seq=ctx.seq)


# --- CDP --------------------------------------------------------------------


@router.get("/cdp/endpoint", response_model=OkEnvelope[CDPEndpointResponse])
async def handle_cdp_endpoint(ctx: BrowserCtxDep) -> dict[str, Any]:
    """Return the CDP WebSocket URL for jshookmcp browser_attach."""
    import httpx

    cdp_port: int | None = getattr(ctx, "_cdp_port", None)
    if not cdp_port:
        raise HTTPException(
            status_code=503,
            detail={
                "ok": False,
                "error": "no_cdp_port",
                "hint": "No CDP port available",
                "action": "restart daemon — CDP port is allocated at browser launch",
            },
        )

    http_url = f"http://127.0.0.1:{cdp_port}"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{http_url}/json/version")
            info = resp.json()
        ws_endpoint: str = info.get("webSocketDebuggerUrl", "")
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "ok": False,
                "error": "cdp_unreachable",
                "hint": f"DevTools HTTP API at port {cdp_port} unreachable: {exc}",
                "action": "ensure browser is running and CDP port is open",
            },
        ) from exc

    return _ok(
        {"ws_endpoint": ws_endpoint, "http_url": http_url, "port": cdp_port},
        seq=ctx.seq,
    )


# --- Tabs -------------------------------------------------------------------


@router.get("/tabs", response_model=OkEnvelope[TabListResponse])
async def handle_tab_list(ctx: BrowserCtxDep) -> dict[str, Any]:
    tabs = await ctx.tab_list()
    data = [
        {"tab_id": t.tab_id, "url": t.url, "title": t.title, "active": t.active}
        for t in tabs
    ]
    return _ok({"tabs": data, "count": len(data)}, seq=ctx.seq)


@router.post("/tab/new", response_model=OkEnvelope[TabOpResponse])
async def handle_tab_new(body: TabNewRequest, ctx: BrowserCtxDep) -> dict[str, Any]:
    result = await ctx.tab_new(body.url)
    return _ok(result, seq=ctx.seq)


@router.post("/tab/close", response_model=OkEnvelope[TabOpResponse])
async def handle_tab_close(body: TabCloseRequest, ctx: BrowserCtxDep) -> dict[str, Any]:
    result = await ctx.tab_close(body.tab_id)
    return _ok(result, seq=ctx.seq)


@router.post("/tab/switch", response_model=OkEnvelope[TabOpResponse])
async def handle_tab_switch(
    body: TabSwitchRequest, ctx: BrowserCtxDep
) -> dict[str, Any]:
    result = await ctx.tab_switch(body.tab_id)
    return _ok(result, seq=ctx.seq)


# --- Resume -----------------------------------------------------------------


@router.get("/resume", response_model=OkEnvelope[ResumeResponse])
async def handle_resume(ctx: BrowserCtxDep, request: Request) -> dict[str, Any]:
    writer = getattr(request.app.state, "resume_writer", None)
    if writer is None:
        raise HTTPException(
            status_code=503,
            detail={
                "ok": False,
                "error": "resume_unavailable",
                "hint": "Resume writer not initialized",
                "action": "restart the daemon",
            },
        )
    # Persisted resume snapshot only updates on navigate/action (via
    # _update_resume). Runtime-mutable fields like ``capture_active`` and
    # ``stealth_tier`` need to be re-read from the live context, otherwise
    # ``resume`` returns stale values when the agent toggled capture between
    # actions (dogfood F2).
    data = writer.current_snapshot.to_dict()
    data["capture_active"] = ctx.capture_store.recording
    data["stealth_tier"] = ctx.stealth_tier.value
    return _ok(data, seq=ctx.seq)


# --- Spells -----------------------------------------------------------------


@router.post("/spell/run", response_model=OkEnvelope[SpellRunResponse])
async def handle_spell_run(body: SpellRunRequest, ctx: BrowserCtxDep) -> dict[str, Any]:
    """Run a registered spell with the daemon's live browser context."""
    from agentcloak.spells.discovery import discover_spells
    from agentcloak.spells.executor import execute_spell
    from agentcloak.spells.registry import get_registry

    parts = body.name.split("/", 1)
    if len(parts) != 2:
        raise HTTPException(
            status_code=400,
            detail={
                "ok": False,
                "error": "invalid_spell_name",
                "hint": f"Expected 'site/command', got '{body.name}'",
                "action": "use format like 'httpbin/headers'",
            },
        )

    discover_spells()
    registry = get_registry()
    entry = registry.get(parts[0], parts[1])
    if entry is None:
        available = [e.meta.full_name for e in registry.list_all()]
        raise HTTPException(
            status_code=404,
            detail={
                "ok": False,
                "error": "spell_not_found",
                "hint": f"No spell '{body.name}'",
                "action": f"available: {', '.join(available[:10])}",
            },
        )

    result = await execute_spell(entry, args=body.args, browser=ctx)
    return _ok({"result": result}, seq=ctx.seq)


@router.get("/spell/list", response_model=OkEnvelope[SpellListResponse])
async def handle_spell_list(ctx: BrowserCtxDep) -> dict[str, Any]:
    """List all registered spells."""
    from agentcloak.spells.discovery import discover_spells
    from agentcloak.spells.registry import get_registry

    discover_spells()
    registry = get_registry()
    spells = [
        {
            "full_name": e.meta.full_name,
            "strategy": e.meta.strategy.value,
            "access": e.meta.access,
            "description": e.meta.description,
        }
        for e in registry.list_all()
    ]
    return _ok({"spells": spells, "count": len(spells)}, seq=ctx.seq)


# --- Profile ----------------------------------------------------------------


@router.post(
    "/profile/create-from-current",
    response_model=OkEnvelope[ProfileCreateFromCurrentResponse],
)
async def handle_profile_create_from_current(
    body: ProfileCreateFromCurrentRequest,
    ctx: BrowserCtxDep,
    remote_ctx: RemoteCtxDep,
) -> dict[str, Any]:
    """Create a profile from the current browser session's cookies."""
    service = ProfileService(_profiles_dir())

    try:
        service.validate_name(body.name)
    except ProfileError as exc:
        raise _profile_error_to_http(exc) from exc

    cookies: list[dict[str, Any]]
    if remote_ctx is not None:
        from agentcloak.browser.remote_ctx import RemoteBridgeContext

        if not isinstance(remote_ctx, RemoteBridgeContext):
            raise RuntimeError("remote_ctx is not a RemoteBridgeContext instance")
        # The bridge ``cookies`` command returns either a list of cookie dicts
        # directly or a ``{"cookies": [...]}`` envelope depending on extension
        # version. Normalise to a list either way.
        raw_response: Any = await remote_ctx.send_command("cookies", {})
        cookies = []
        if isinstance(raw_response, list):
            cookies = list(raw_response)  # type: ignore[arg-type]
        elif isinstance(raw_response, dict):
            inner = raw_response.get("cookies", [])  # type: ignore[arg-type]
            if isinstance(inner, list):
                cookies = list(inner)  # type: ignore[arg-type]
    else:
        browser_context = ctx._get_browser_context()
        cookies = await browser_context.cookies()

    try:
        result = await service.create_from_cookies(body.name, cookies)
    except ProfileError as exc:
        raise _profile_error_to_http(exc) from exc
    return _ok(result, seq=ctx.seq)


@router.get("/profile/list", response_model=OkEnvelope[ProfileListResponse])
async def handle_profile_list(ctx: BrowserCtxDep) -> dict[str, Any]:
    service = ProfileService(_profiles_dir())
    names = service.list_profiles()
    return _ok({"profiles": names, "count": len(names)}, seq=ctx.seq)


@router.post("/profile/create", response_model=OkEnvelope[ProfileCreateResponse])
async def handle_profile_create(
    body: ProfileCreateRequest, ctx: BrowserCtxDep
) -> dict[str, Any]:
    service = ProfileService(_profiles_dir())
    try:
        name = service.create(body.name)
    except ProfileError as exc:
        raise _profile_error_to_http(exc) from exc
    return _ok({"created": name}, seq=ctx.seq)


@router.post("/profile/delete", response_model=OkEnvelope[ProfileCreateResponse])
async def handle_profile_delete(
    body: ProfileDeleteRequest, ctx: BrowserCtxDep
) -> dict[str, Any]:
    service = ProfileService(_profiles_dir())
    try:
        name = service.delete(body.name)
    except ProfileError as exc:
        raise _profile_error_to_http(exc) from exc
    return _ok({"deleted": name}, seq=ctx.seq)


# --- Dialog -----------------------------------------------------------------


@router.get("/dialog/status", response_model=OkEnvelope[DialogStatusResponse])
async def handle_dialog_status(ctx: BrowserCtxDep) -> dict[str, Any]:
    dialog = await ctx.dialog_status()
    if dialog is None:
        return _ok({"pending": False}, seq=ctx.seq)
    return _ok(
        {
            "pending": True,
            "dialog": {
                "type": dialog.dialog_type,
                "message": dialog.message,
                "default_value": dialog.default_value,
                "url": dialog.url,
            },
        },
        seq=ctx.seq,
    )


@router.post("/dialog/handle", response_model=OkEnvelope[DialogHandleResponse])
async def handle_dialog_handle(
    body: DialogHandleRequest, ctx: BrowserCtxDep
) -> dict[str, Any]:
    result = await ctx.dialog_handle(body.action, text=body.text)
    return _ok(result, seq=ctx.seq)


# --- Wait -------------------------------------------------------------------


@router.post("/wait", response_model=OkEnvelope[WaitResponse])
async def handle_wait(body: WaitRequest, ctx: BrowserCtxDep) -> dict[str, Any]:
    result = await ctx.wait(
        condition=body.condition,
        value=body.value,
        timeout=body.timeout,
        state=body.state,
    )
    return _ok(result, seq=ctx.seq)


# --- Upload -----------------------------------------------------------------


@router.post("/upload", response_model=OkEnvelope[UploadResponse])
async def handle_upload(body: UploadRequest, ctx: BrowserCtxDep) -> dict[str, Any]:
    if not body.files:
        raise HTTPException(
            status_code=400,
            detail={
                "ok": False,
                "error": "missing_files",
                "hint": "No files provided for upload",
                "action": "provide 'files' as a list of file paths",
            },
        )
    result = await ctx.upload(body.index, body.files)
    return _ok(result, seq=ctx.seq)


# --- Frame ------------------------------------------------------------------


@router.get("/frame/list", response_model=OkEnvelope[FrameListResponse])
async def handle_frame_list(ctx: BrowserCtxDep) -> dict[str, Any]:
    frames = await ctx.frame_list()
    data = [{"name": f.name, "url": f.url, "is_current": f.is_current} for f in frames]
    return _ok({"frames": data, "count": len(data)}, seq=ctx.seq)


@router.post("/frame/focus", response_model=OkEnvelope[FrameFocusResponse])
async def handle_frame_focus(
    body: FrameFocusRequest, ctx: BrowserCtxDep
) -> dict[str, Any]:
    result = await ctx.frame_focus(name=body.name, url=body.url, main=body.main)
    return _ok(result, seq=ctx.seq)


# --- Registration -----------------------------------------------------------


def register_routers(app: Any) -> None:
    """Register all routes on the FastAPI app."""
    app.include_router(router)


# --- Test-facing helper re-exports ------------------------------------------
# These three callables live on ``ActionService`` and are re-exported here so
# the route-level unit tests can exercise the parsing logic without going
# through the full daemon stack.

_batch_has_refs = ActionService.has_refs
_resolve_action_refs = ActionService.resolve_refs
_traverse = ActionService.traverse
