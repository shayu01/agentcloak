"""RemoteBridgeContext — operates a remote browser via bridge WebSocket.

This adapter speaks WebSocket+CDP. All shared behavior (action dispatch,
snapshot caching, dialog handling, batch, wait orchestration, frame state) is
inherited from BrowserContextBase. The atomic methods translate each
operation into the appropriate ``cdp``/``evaluate``/``screenshot`` bridge
command.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import time
import uuid
from typing import Any, Protocol

import structlog

from agentcloak.browser._snapshot_builder import FrameData
from agentcloak.browser.base import BrowserContextBase
from agentcloak.browser.state import (
    FrameInfo,
    PageSnapshot,
    PendingDialog,
    TabInfo,
)
from agentcloak.core.errors import BackendError, BrowserTimeoutError
from agentcloak.core.types import StealthTier

__all__ = ["RemoteBridgeContext"]

logger = structlog.get_logger()


class _BridgeWS(Protocol):
    """The minimal WebSocket interface the bridge context speaks to.

    Implemented by :class:`agentcloak.daemon.routes._BridgeWSAdapter`, which
    wraps a Starlette/FastAPI ``WebSocket`` object. Defined as a Protocol so
    the browser layer never imports a specific server framework — the daemon
    can swap transports without rippling into ``remote_ctx``.
    """

    @property
    def closed(self) -> bool: ...

    async def send_str(self, data: str) -> None: ...

    async def close(self) -> None: ...


class RemoteBridgeContext(BrowserContextBase):
    """BrowserContext backed by a remote Chrome via bridge WebSocket."""

    def __init__(self, *, bridge_ws: _BridgeWS) -> None:
        super().__init__()
        self._ws = bridge_ws
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        # _active_frame is set to a frameId string (or None for main) on this
        # backend. The base class declares the slot but stores Any.
        self._active_frame_id: str | None = None

    @property
    def stealth_tier(self) -> StealthTier:
        return StealthTier.REMOTE_BRIDGE

    # ------------------------------------------------------------------
    # Bridge plumbing — send command + read response
    # ------------------------------------------------------------------

    async def send_command(
        self, cmd: str, params: dict[str, Any] | None = None, **kw: Any
    ) -> dict[str, Any]:
        return await self._send(cmd, params, **kw)

    async def _send(
        self, cmd: str, params: dict[str, Any] | None = None, **kw: Any
    ) -> dict[str, Any]:
        if self._ws.closed:
            raise BackendError(
                error="bridge_disconnected",
                hint="Bridge WebSocket is closed",
                action="check bridge process on the remote machine",
            )

        msg_id = str(uuid.uuid4())[:8]
        message: dict[str, Any] = {"id": msg_id, "cmd": cmd}
        if params:
            message["params"] = params
        message.update(kw)

        await self._ws.send_str(json.dumps(message))

        try:
            response = await asyncio.wait_for(self._wait_response(msg_id), timeout=60.0)
        except TimeoutError as exc:
            raise BrowserTimeoutError(
                error="bridge_timeout",
                hint=f"Bridge command '{cmd}' timed out after 60s",
                action="check bridge and extension connectivity",
            ) from exc

        if not response.get("ok"):
            raise BackendError(
                error="bridge_command_failed",
                hint=response.get("error", "unknown error"),
                action=f"check command '{cmd}' parameters",
            )

        return response.get("data", {})

    async def _wait_response(self, msg_id: str) -> dict[str, Any]:
        fut: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[msg_id] = fut
        try:
            return await fut
        finally:
            self._pending.pop(msg_id, None)

    def feed_message(self, data: str) -> None:
        try:
            msg = json.loads(data)
        except json.JSONDecodeError:
            return

        if msg.get("type") == "cdp_event":
            method = msg.get("method", "")
            params = msg.get("params", {})
            if method == "Page.javascriptDialogOpening":
                self._handle_dialog_event(params)
            return

        msg_id = msg.get("id")
        if msg_id and msg_id in self._pending:
            self._pending[msg_id].set_result(msg)

    # ------------------------------------------------------------------
    # Atomic: navigation + page info
    # ------------------------------------------------------------------

    async def _navigate_impl(self, url: str, *, timeout: float) -> dict[str, Any]:
        return await self._send("navigate", {"url": url})

    async def _get_page_info(self) -> tuple[str, str]:
        result = await self._send("evaluate", {"js": "[document.URL, document.title]"})
        raw = result.get("result")
        if not isinstance(raw, list):
            return "", ""
        url = str(raw[0]) if len(raw) > 0 else ""
        title = str(raw[1]) if len(raw) > 1 else ""
        return url, title

    # ------------------------------------------------------------------
    # Atomic: AX tree + DOM/content snapshots
    # ------------------------------------------------------------------

    async def _get_ax_tree(self, *, frames: bool = False) -> list[dict[str, Any]]:
        cdp_result = await self._send(
            "cdp",
            {"method": "Accessibility.getFullAXTree", "params": {"pierce": True}},
        )
        return cdp_result.get("nodes", [])

    async def _get_child_frame_trees(self) -> list[FrameData]:
        child_frames: list[FrameData] = []
        try:
            result = await self._send(
                "cdp",
                {"method": "Page.getFrameTree", "params": {}},
            )
        except BackendError:
            return child_frames

        frame_tree = result.get("frameTree", {})
        for child in frame_tree.get("childFrames", []):
            frame_info = child.get("frame", {})
            frame_id = frame_info.get("id", "")
            frame_name = frame_info.get("name", "")
            frame_url = frame_info.get("url", "")
            if not frame_id:
                continue
            try:
                ax_result = await self._send(
                    "cdp",
                    {
                        "method": "Accessibility.getFullAXTree",
                        "params": {"frameId": frame_id},
                    },
                )
                nodes = ax_result.get("nodes", [])
                if nodes:
                    child_frames.append(
                        FrameData(
                            frame_id=frame_id,
                            name=frame_name,
                            url=frame_url,
                            nodes=nodes,
                        )
                    )
            except Exception:
                logger.debug(
                    "frame_ax_tree_failed",
                    frame_id=frame_id,
                    frame_name=frame_name,
                    exc_info=True,
                )
        return child_frames

    async def _snapshot_dom_impl(self) -> str:
        # Remote bridge currently doesn't ship a full-HTML snapshot — fall back
        # to raising invalid_snapshot_mode so callers can degrade to text or
        # accessible mode (historical behavior preserved across the FastAPI
        # rewrite).
        raise BackendError(
            error="invalid_snapshot_mode",
            hint="DOM snapshot not supported on the remote bridge backend",
            action="use accessible, compact, or content",
        )

    async def _snapshot_content_impl(self) -> str:
        text_result = await self._send(
            "evaluate", {"js": "document.body?.innerText || ''"}
        )
        return str(text_result.get("result", ""))

    async def _network_entries(self, *, since_seq: int) -> list[dict[str, Any]]:
        # Remote bridge doesn't surface a dedicated network queue today; the
        # ring buffer (populated via CDP events when added) is the source.
        return []

    async def snapshot(
        self,
        *,
        mode: str = "accessible",
        max_nodes: int = 0,
        max_chars: int = 0,
        focus: int = 0,
        offset: int = 0,
        frames: bool = False,
    ) -> PageSnapshot:
        # Remote bridge only supports accessible / compact / content modes.
        if mode == "dom":
            raise BackendError(
                error="invalid_snapshot_mode",
                hint=f"Unknown mode: {mode}",
                action="use one of: accessible, compact, content",
            )
        return await super().snapshot(
            mode=mode,
            max_nodes=max_nodes,
            max_chars=max_chars,
            focus=focus,
            offset=offset,
            frames=frames,
        )

    # ------------------------------------------------------------------
    # Element resolution via backendDOMNodeId
    # ------------------------------------------------------------------

    async def _resolve_element_center(self, ref: int) -> tuple[float, float]:
        """Resolve [N] ref to element center coordinates via backendDOMNodeId."""
        self._require_snapshot(ref)
        backend_id = self._backend_node_map.get(ref)
        if backend_id is None:
            raise BackendError(
                error="element_not_found",
                hint=f"Ref [{ref}] not in current snapshot",
                action="re-snapshot and use a valid [N] ref",
            )
        desc = await self._send(
            "cdp",
            {
                "method": "DOM.describeNode",
                "params": {"backendNodeId": backend_id},
            },
        )
        node_id = desc.get("node", {}).get("nodeId", 0)
        if not node_id:
            resolve_result = await self._send(
                "cdp",
                {
                    "method": "DOM.resolveNode",
                    "params": {"backendNodeId": backend_id},
                },
            )
            object_id = resolve_result.get("object", {}).get("objectId")
            if not object_id:
                raise BackendError(
                    error="element_not_resolved",
                    hint=(
                        f"Could not resolve backendNodeId {backend_id} for ref [{ref}]"
                    ),
                    action=(
                        "re-snapshot and retry — the element may have been removed"
                    ),
                )
            box = await self._send(
                "cdp",
                {
                    "method": "Runtime.callFunctionOn",
                    "params": {
                        "objectId": object_id,
                        "functionDeclaration": (
                            "function(){"
                            "const r=this.getBoundingClientRect();"
                            "return JSON.stringify("
                            "{x:r.x,y:r.y,w:r.width,h:r.height})}"
                        ),
                        "returnByValue": True,
                    },
                },
            )
            rect = json.loads(box.get("result", {}).get("value", "{}"))
            cx = rect.get("x", 0) + rect.get("w", 0) / 2
            cy = rect.get("y", 0) + rect.get("h", 0) / 2
            return float(cx), float(cy)
        box_model = await self._send(
            "cdp",
            {"method": "DOM.getBoxModel", "params": {"nodeId": node_id}},
        )
        content = box_model.get("model", {}).get("content", [0] * 8)
        cx = (content[0] + content[4]) / 2
        cy = (content[1] + content[5]) / 2
        return float(cx), float(cy)

    async def _dispatch_click(self, x: float, y: float) -> None:
        """Send mousePressed + mouseReleased via CDP at the given coordinates."""
        for event_type in ("mousePressed", "mouseReleased"):
            await self._send(
                "cdp",
                {
                    "method": "Input.dispatchMouseEvent",
                    "params": {
                        "type": event_type,
                        "x": x,
                        "y": y,
                        "button": "left",
                        "clickCount": 1,
                    },
                },
            )

    # ------------------------------------------------------------------
    # Atomic: actions
    # ------------------------------------------------------------------

    async def _click_impl(
        self,
        *,
        target: str,
        x: float | None,
        y: float | None,
        button: str,
        click_count: int,
    ) -> dict[str, Any]:
        if x is not None and y is not None:
            cx, cy = float(x), float(y)
        else:
            cx, cy = await self._resolve_element_center(int(target))
        await self._dispatch_click(cx, cy)
        return {"clicked": True}

    async def _fill_impl(self, *, target: str, text: str) -> dict[str, Any]:
        if target:
            cx, cy = await self._resolve_element_center(int(target))
            await self._dispatch_click(cx, cy)
        await self._set_active_value(text)
        return {"filled": True, "text": text}

    async def _type_impl(
        self, *, target: str, text: str, delay: float
    ) -> dict[str, Any]:
        if target:
            cx, cy = await self._resolve_element_center(int(target))
            await self._dispatch_click(cx, cy)
        await self._set_active_value(text)
        return {"typed": True, "text": text}

    async def _set_active_value(self, text: str) -> None:
        val = json.dumps(text)
        js = (
            f"(() => {{"
            f" const el = document.activeElement;"
            f" if (el) {{"
            f" el.value = {val};"
            f" el.dispatchEvent(new Event('input',"
            f" {{bubbles:true}}));"
            f" el.dispatchEvent(new Event('change',"
            f" {{bubbles:true}}));"
            f" }}"
            f"}})()"
        )
        await self._send("evaluate", {"js": js})

    async def _scroll_impl(
        self,
        *,
        target: str,
        direction: str,
        amount: int,
    ) -> dict[str, Any]:
        delta_x, delta_y = 0, 0
        if direction == "down":
            delta_y = amount
        elif direction == "up":
            delta_y = -amount
        elif direction == "right":
            delta_x = amount
        elif direction == "left":
            delta_x = -amount
        if target:
            cx, cy = await self._resolve_element_center(int(target))
        else:
            cx, cy = 640.0, 400.0
        await self._send(
            "cdp",
            {
                "method": "Input.dispatchMouseEvent",
                "params": {
                    "type": "mouseWheel",
                    "x": cx,
                    "y": cy,
                    "deltaX": delta_x,
                    "deltaY": delta_y,
                },
            },
        )
        return {"scrolled": True, "direction": direction, "amount": amount}

    async def _hover_impl(
        self,
        *,
        target: str,
        x: float | None,
        y: float | None,
    ) -> dict[str, Any]:
        if x is not None and y is not None:
            cx, cy = float(x), float(y)
        else:
            if not target:
                raise BackendError(
                    error="element_not_found",
                    hint="hover requires a target element",
                    action=(
                        "provide 'target' as '[N]' ref from snapshot,"
                        " or use (x, y) coordinates"
                    ),
                )
            cx, cy = await self._resolve_element_center(int(target))
        await self._send(
            "cdp",
            {
                "method": "Input.dispatchMouseEvent",
                "params": {"type": "mouseMoved", "x": cx, "y": cy},
            },
        )
        return {"hovered": True}

    async def _select_impl(
        self,
        *,
        target: str,
        value: str | None,
        label: str | None,
    ) -> dict[str, Any]:
        if not target:
            raise BackendError(
                error="element_not_found",
                hint="select requires a target element",
                action="provide 'target' as '[N]' ref from snapshot",
            )
        self._require_snapshot(int(target))
        backend_id = self._backend_node_map.get(int(target))
        if backend_id is None:
            raise BackendError(
                error="element_not_found",
                hint=f"Ref [{target}] not in current snapshot",
                action="re-snapshot and use a valid [N] ref",
            )
        resolve_result = await self._send(
            "cdp",
            {
                "method": "DOM.resolveNode",
                "params": {"backendNodeId": backend_id},
            },
        )
        object_id = resolve_result.get("object", {}).get("objectId")
        if not object_id:
            raise BackendError(
                error="element_not_resolved",
                hint=(
                    f"Could not resolve backendNodeId {backend_id} for ref [{target}]"
                ),
                action="re-snapshot and retry — the element may have been removed",
            )
        if value is not None:
            set_js = (
                "function() {"
                f"  this.value = {json.dumps(value)};"
                "  this.dispatchEvent(new Event('input', {bubbles:true}));"
                "  this.dispatchEvent(new Event('change', {bubbles:true}));"
                "}"
            )
        else:
            set_js = (
                "function() {"
                "  const opts = Array.from(this.options);"
                "  const opt = opts.find("
                f"o => o.text === {json.dumps(label)});"
                "  if (opt) { this.value = opt.value; }"
                "  this.dispatchEvent(new Event('input', {bubbles:true}));"
                "  this.dispatchEvent(new Event('change', {bubbles:true}));"
                "}"
            )
        await self._send(
            "cdp",
            {
                "method": "Runtime.callFunctionOn",
                "params": {
                    "objectId": object_id,
                    "functionDeclaration": set_js,
                    "returnByValue": True,
                },
            },
        )
        return {"selected": True, "value": value, "label": label}

    async def _press_impl(self, *, target: str, key: str) -> dict[str, Any]:
        # Note: target is intentionally ignored on remote bridge — the CDP key
        # event dispatches at the focused element. Callers wanting to focus
        # first should issue a click or fill on the target before pressing.
        await self._send(
            "cdp",
            {
                "method": "Input.dispatchKeyEvent",
                "params": {"type": "keyDown", "key": key},
            },
        )
        await self._send(
            "cdp",
            {
                "method": "Input.dispatchKeyEvent",
                "params": {"type": "keyUp", "key": key},
            },
        )
        return {"pressed": True, "key": key}

    async def _keydown_impl(self, *, key: str) -> dict[str, Any]:
        await self._send(
            "cdp",
            {
                "method": "Input.dispatchKeyEvent",
                "params": {"type": "keyDown", "key": key},
            },
        )
        return {"keydown": True, "key": key}

    async def _keyup_impl(self, *, key: str) -> dict[str, Any]:
        await self._send(
            "cdp",
            {
                "method": "Input.dispatchKeyEvent",
                "params": {"type": "keyUp", "key": key},
            },
        )
        return {"keyup": True, "key": key}

    # ------------------------------------------------------------------
    # Atomic: wait (polling CDP loop)
    # ------------------------------------------------------------------

    async def _wait_impl(
        self,
        *,
        condition: str,
        value: str,
        timeout: int,
        state: str,
    ) -> dict[str, Any]:
        t0 = time.monotonic()
        deadline = t0 + timeout / 1000

        if condition == "ms":
            await asyncio.sleep(int(value) / 1000)
            return {}

        if condition == "selector":
            state_check = ""
            if state == "visible":
                state_check = (
                    " && el.offsetParent !== null"
                    " && getComputedStyle(el).visibility !== 'hidden'"
                )
            elif state == "hidden":
                state_check = (
                    " && (el.offsetParent === null"
                    " || getComputedStyle(el).visibility === 'hidden')"
                )
            elif state == "attached":
                state_check = ""
            elif state == "detached":
                await self._poll_js(
                    f"!document.querySelector({json.dumps(value)})",
                    deadline,
                    condition,
                    timeout,
                )
                return {}

            js_expr = (
                f"(() => {{"
                f"  const el = document.querySelector({json.dumps(value)});"
                f"  return !!(el{state_check});"
                f"}})()"
            )
            await self._poll_js(js_expr, deadline, condition, timeout)

        elif condition == "url":
            while True:
                if time.monotonic() >= deadline:
                    raise BrowserTimeoutError(
                        error="wait_timeout",
                        hint=f"Wait condition 'url' timed out after {timeout}ms",
                        action="increase timeout or check the URL pattern",
                    )
                url, _ = await self._get_page_info()
                if value in url:
                    break
                await asyncio.sleep(0.25)

        elif condition == "load":
            js_expr = (
                "document.readyState === 'complete'"
                if value != "domcontentloaded"
                else "document.readyState !== 'loading'"
            )
            await self._poll_js(js_expr, deadline, condition, timeout)

        elif condition == "js":
            await self._poll_js(value, deadline, condition, timeout)

        else:
            raise BackendError(
                error="invalid_wait_condition",
                hint=f"Unknown condition: '{condition}'",
                action="use one of: selector, url, load, js, ms",
            )

        return {}

    async def _poll_js(
        self,
        expression: str,
        deadline: float,
        condition: str,
        timeout: int,
    ) -> None:
        while True:
            if time.monotonic() >= deadline:
                raise BrowserTimeoutError(
                    error="wait_timeout",
                    hint=f"Wait condition '{condition}' timed out after {timeout}ms",
                    action="increase timeout or check the condition",
                )
            try:
                result = await self._send("evaluate", {"js": expression})
                if result.get("result"):
                    return
            except BackendError:
                raise
            except Exception:
                pass
            await asyncio.sleep(0.25)

    # ------------------------------------------------------------------
    # Atomic: upload
    # ------------------------------------------------------------------

    async def _upload_impl(self, index: int, files: list[str]) -> dict[str, Any]:
        self._require_snapshot(index)
        backend_id = self._backend_node_map.get(index)
        if backend_id is None:
            raise BackendError(
                error="element_not_found",
                hint=f"Ref [{index}] not in current snapshot",
                action="re-snapshot and use a valid [N] ref for a file input",
            )
        await self._send(
            "cdp",
            {
                "method": "DOM.setFileInputFiles",
                "params": {
                    "files": files,
                    "backendNodeId": backend_id,
                },
            },
        )
        return {"uploaded": True}

    # ------------------------------------------------------------------
    # Atomic: dialog
    # ------------------------------------------------------------------

    def _handle_dialog_event(self, params: dict[str, Any]) -> None:
        dialog_type = params.get("type", "alert")
        message = params.get("message", "")
        default_prompt = params.get("defaultPrompt", "")

        if dialog_type in ("alert", "beforeunload"):
            _task = asyncio.ensure_future(self._auto_accept_dialog())
            _task.add_done_callback(lambda t: None)
            logger.info(
                "dialog_auto_accepted",
                dialog_type=dialog_type,
                message=message[:100],
            )
        else:
            self._pending_dialog = PendingDialog(
                dialog_type=dialog_type,
                message=message,
                default_value=default_prompt,
                url="(remote)",
            )
            logger.info(
                "dialog_pending",
                dialog_type=dialog_type,
                message=message[:100],
            )

    async def _auto_accept_dialog(self) -> None:
        try:
            await self._send(
                "cdp",
                {
                    "method": "Page.handleJavaScriptDialog",
                    "params": {"accept": True},
                },
            )
        except Exception:
            logger.debug("auto_accept_dialog_failed", exc_info=True)

    async def _dialog_handle_impl(
        self, action: str, *, text: str | None = None
    ) -> dict[str, Any]:
        accept = action == "accept"
        params: dict[str, Any] = {"accept": accept}
        if text is not None and accept:
            params["promptText"] = text
        try:
            await self._send(
                "cdp",
                {"method": "Page.handleJavaScriptDialog", "params": params},
            )
        except Exception as exc:
            logger.debug("dialog_handle_error", error=str(exc))
        return {}

    # ------------------------------------------------------------------
    # Atomic: evaluate / screenshot
    # ------------------------------------------------------------------

    async def _evaluate_impl(self, js: str, *, world: str) -> Any:
        result = await self._send("evaluate", {"js": js})
        return result.get("result")

    async def _screenshot_impl(
        self, *, full_page: bool, fmt: str, quality: int
    ) -> bytes:
        result = await self._send("screenshot", {})
        b64 = result.get("base64", "")
        return base64.b64decode(b64)

    # ------------------------------------------------------------------
    # Atomic: fetch via Playwright API (browser cookies + UA)
    # ------------------------------------------------------------------

    async def _fetch_impl(
        self,
        url: str,
        *,
        method: str,
        body: str | None,
        headers: dict[str, str] | None,
        timeout: float,
    ) -> dict[str, Any]:
        # Remote backend has no local cookie jar — bridge does a fetch-from-page.
        # For now we route via JS evaluate so cookies/UA come from the remote
        # browser context. This mirrors the spec described in the API surface.
        import json as _json

        params: dict[str, Any] = {
            "url": url,
            "method": method,
            "headers": headers or {},
        }
        if body is not None:
            params["body"] = body
        params["timeout"] = timeout

        result = await self._send("fetch", params)
        # Some bridges return parsed result, fall back to raw payload if not.
        if "body" not in result:
            with contextlib.suppress(Exception):
                result = _json.loads(_json.dumps(result))
        return result

    # ------------------------------------------------------------------
    # Atomic: tabs
    # ------------------------------------------------------------------

    async def _tab_list_impl(self) -> list[TabInfo]:
        # Remote bridge currently exposes one logical tab; if it grows multi-tab,
        # this should query the bridge for the list.
        url, title = await self._get_page_info()
        return [TabInfo(tab_id=0, url=url, title=title, active=True)]

    async def _tab_new_impl(self, url: str | None) -> dict[str, Any]:
        result = await self._send("tab_new", {"url": url} if url else {})
        return result

    async def _tab_close_impl(self, tab_id: int) -> dict[str, Any]:
        return await self._send("tab_close", {"tab_id": tab_id})

    async def _tab_switch_impl(self, tab_id: int) -> dict[str, Any]:
        return await self._send("tab_switch", {"tab_id": tab_id})

    # ------------------------------------------------------------------
    # Atomic: frames
    # ------------------------------------------------------------------

    async def _frame_list_impl(self) -> list[FrameInfo]:
        try:
            result = await self._send(
                "cdp",
                {"method": "Page.getFrameTree", "params": {}},
            )
        except BackendError:
            return [FrameInfo(name="(main)", url="", is_current=True)]

        frames: list[FrameInfo] = []
        self._collect_frames(result.get("frameTree", {}), frames)
        return frames

    def _collect_frames(
        self,
        frame_tree: dict[str, Any],
        out: list[FrameInfo],
    ) -> None:
        frame = frame_tree.get("frame", {})
        frame_id = frame.get("id", "")
        frame_name = frame.get("name", "")
        frame_url = frame.get("url", "")
        is_main = frame.get("parentId") is None or frame.get("parentId") == ""

        if is_main and not frame_name:
            frame_name = "(main)"

        is_current = (self._active_frame_id is None and is_main) or (
            self._active_frame_id == frame_id
        )
        out.append(
            FrameInfo(
                name=frame_name or frame_id,
                url=frame_url,
                is_current=is_current,
            )
        )
        for child in frame_tree.get("childFrames", []):
            self._collect_frames(child, out)

    async def _frame_focus_impl(
        self, *, name: str | None, url: str | None, main: bool
    ) -> dict[str, Any]:
        if main:
            self._active_frame_id = None
            self._active_frame = None
            return {
                "ok": True,
                "action": "frame_focus",
                "frame": "(main)",
                "url": "",
            }
        try:
            result = await self._send(
                "cdp",
                {"method": "Page.getFrameTree", "params": {}},
            )
        except BackendError as exc:
            raise BackendError(
                error="frame_not_supported",
                hint="Could not retrieve frame tree via CDP",
                action="ensure the Page domain is available on the extension",
            ) from exc
        target = self._find_frame(result.get("frameTree", {}), name=name, url=url)
        if target is None:
            frames_list = await self._frame_list_impl()
            available = [f.name or f.url[:60] for f in frames_list]
            raise BackendError(
                error="frame_not_found",
                hint=f"No frame matching name={name!r} url={url!r}",
                action=f"available frames: {available}",
            )
        self._active_frame_id = target["id"]
        self._active_frame = target["id"]
        return {
            "ok": True,
            "action": "frame_focus",
            "frame": target.get("name") or "(unnamed)",
            "url": target.get("url", ""),
        }

    def _find_frame(
        self,
        frame_tree: dict[str, Any],
        *,
        name: str | None = None,
        url: str | None = None,
    ) -> dict[str, Any] | None:
        frame = frame_tree.get("frame", {})
        if name and frame.get("name") == name:
            return frame
        if url and url in frame.get("url", ""):
            return frame
        for child in frame_tree.get("childFrames", []):
            found = self._find_frame(child, name=name, url=url)
            if found:
                return found
        return None

    # ------------------------------------------------------------------
    # Atomic: raw CDP / close
    # ------------------------------------------------------------------

    async def _raw_cdp_impl(self, method: str, params: dict[str, Any] | None) -> Any:
        return await self.send_command(
            "cdp", {"method": method, "params": params or {}}
        )

    async def _close_impl(self) -> None:
        if not self._ws.closed:
            await self._ws.close()
