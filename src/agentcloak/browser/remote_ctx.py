"""RemoteBridgeContext — operates a remote browser via bridge WebSocket."""

from __future__ import annotations

import asyncio
import base64
import json
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from agentcloak.browser._snapshot_builder import FrameData, build_snapshot
from agentcloak.browser.state import (
    ElementRef,
    FrameInfo,
    PageSnapshot,
    PendingDialog,
)
from agentcloak.core.errors import BackendError, BrowserTimeoutError
from agentcloak.core.seq import RingBuffer, SeqCounter, SeqEvent
from agentcloak.core.types import StealthTier

if TYPE_CHECKING:
    from aiohttp import web

__all__ = ["RemoteBridgeContext"]

logger = structlog.get_logger()


class RemoteBridgeContext:
    """BrowserContext backed by a remote Chrome via bridge WebSocket."""

    def __init__(self, *, bridge_ws: web.WebSocketResponse) -> None:
        self._ws = bridge_ws
        self._seq_counter = SeqCounter()
        self._ring_buffer = RingBuffer()
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._selector_map: dict[int, ElementRef] = {}
        self._backend_node_map: dict[int, int] = {}
        self._cached_lines: list[tuple[int, str, int | None]] = []
        # Dialog handling state (mirrors PlaywrightContext pattern)
        self._pending_dialog: PendingDialog | None = None
        # Frame switching — active frameId (None = main frame)
        self._active_frame_id: str | None = None

    @property
    def seq(self) -> int:
        return self._seq_counter.value

    @property
    def stealth_tier(self) -> StealthTier:
        return StealthTier.REMOTE_BRIDGE

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

        # Handle CDP event forwarding from extension
        if msg.get("type") == "cdp_event":
            method = msg.get("method", "")
            params = msg.get("params", {})
            if method == "Page.javascriptDialogOpening":
                self._handle_dialog_event(params)
            return

        msg_id = msg.get("id")
        if msg_id and msg_id in self._pending:
            self._pending[msg_id].set_result(msg)

    async def navigate(self, url: str, *, timeout: float = 30.0) -> dict[str, Any]:
        result = await self._send("navigate", {"url": url})
        new_seq = self._seq_counter.increment_action()
        self._ring_buffer.append(
            SeqEvent(seq=new_seq, kind="navigate", data={"url": url})
        )
        result["seq"] = new_seq
        return result

    async def _resolve_element_center(self, ref: int) -> tuple[float, float]:
        """Resolve [N] ref to element center coordinates via backendDOMNodeId."""
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
            # DOM.describeNode didn't return a usable nodeId; fall back to
            # DOM.resolveNode -> getBoundingClientRect via Runtime.callFunctionOn
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
                        f"Could not resolve backendNodeId"
                        f" {backend_id} for ref [{ref}]"
                    ),
                    action=(
                        "re-snapshot and retry"
                        " — the element may have been removed"
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

    async def _get_tab_info(self) -> tuple[str, str]:
        """Get current page URL and title via JS evaluate."""
        result = await self._send("evaluate", {"js": "[document.URL, document.title]"})
        raw: list[str] = result.get("result", ["", ""])
        url = str(raw[0]) if len(raw) > 0 else ""
        title = str(raw[1]) if len(raw) > 1 else ""
        return url, title

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
        if mode in ("accessible", "compact"):
            cdp_result = await self._send(
                "cdp",
                {"method": "Accessibility.getFullAXTree", "params": {"pierce": True}},
            )
            raw_nodes: list[dict[str, Any]] = cdp_result.get("nodes", [])
            url, title = await self._get_tab_info()

            # Gather child frame AX trees when requested
            frame_trees: list[FrameData] | None = None
            if frames:
                frame_trees = await self._get_child_frame_trees()

            result = build_snapshot(
                raw_nodes,
                mode=mode,
                max_nodes=max_nodes,
                max_chars=max_chars,
                focus=focus,
                offset=offset,
                seq=self._seq_counter.value,
                url=url,
                title=title,
                frame_trees=frame_trees,
            )
            self._selector_map = result.selector_map
            self._backend_node_map = result.backend_node_map
            self._cached_lines = result.cached_lines
            return result.snapshot

        if mode == "content":
            text_result = await self._send(
                "evaluate", {"js": "document.body?.innerText || ''"}
            )
            url, title = await self._get_tab_info()
            return PageSnapshot(
                seq=self._seq_counter.value,
                url=url,
                title=title,
                mode="content",
                tree_text=str(text_result.get("result", "")),
            )

        raise BackendError(
            error="invalid_snapshot_mode",
            hint=f"Unknown mode: {mode}",
            action="use one of: accessible, compact, content",
        )

    async def action(self, kind: str, target: str, **kw: Any) -> dict[str, Any]:
        # Block if there is a pending dialog (mirrors PlaywrightContext)
        if self._pending_dialog is not None:
            d = self._pending_dialog
            return {
                "ok": False,
                "error": "blocked_by_dialog",
                "seq": self._seq_counter.value,
                "dialog": {
                    "type": d.dialog_type,
                    "message": d.message,
                    **({"default_value": d.default_value} if d.default_value else {}),
                },
                "hint": "A dialog is pending — handle it before continuing",
                "action": "use 'dialog accept' or 'dialog dismiss'",
            }

        valid_kinds = {
            "click",
            "fill",
            "type",
            "scroll",
            "hover",
            "select",
            "press",
            "keydown",
            "keyup",
        }
        if kind not in valid_kinds:
            raise BackendError(
                error="invalid_action_kind",
                hint=f"Unknown action kind: '{kind}'",
                action=f"use one of: {', '.join(sorted(valid_kinds))}",
            )

        result: dict[str, Any] = {}

        if kind == "click":
            x = kw.get("x")
            y = kw.get("y")
            if x is not None and y is not None:
                cx, cy = float(x), float(y)
            else:
                cx, cy = await self._resolve_element_center(int(target))
            await self._dispatch_click(cx, cy)
            result["clicked"] = True

        elif kind == "press":
            key = kw.get("key", "")
            if not key:
                raise BackendError(
                    error="press_missing_key",
                    hint="press requires 'key' parameter",
                    action="provide 'key' (e.g. 'Enter', 'Tab', 'Escape')",
                )
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
            result["pressed"] = True
            result["key"] = key

        elif kind in ("fill", "type"):
            text = kw.get("text", "")
            if target:
                # Click the target element first to focus it
                cx, cy = await self._resolve_element_center(int(target))
                await self._dispatch_click(cx, cy)
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
            result["filled" if kind == "fill" else "typed"] = True
            result["text"] = text

        elif kind == "scroll":
            direction = kw.get("direction", "down")
            amount = int(kw.get("amount", 300))
            delta_x, delta_y = 0, 0
            if direction == "down":
                delta_y = amount
            elif direction == "up":
                delta_y = -amount
            elif direction == "right":
                delta_x = amount
            elif direction == "left":
                delta_x = -amount
            # If target element specified, scroll it into view first
            if target:
                cx, cy = await self._resolve_element_center(int(target))
            else:
                # Default to viewport center
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
            result["scrolled"] = True
            result["direction"] = direction
            result["amount"] = amount

        elif kind == "hover":
            x = kw.get("x")
            y = kw.get("y")
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
                    "params": {
                        "type": "mouseMoved",
                        "x": cx,
                        "y": cy,
                    },
                },
            )
            result["hovered"] = True

        elif kind == "select":
            if not target:
                raise BackendError(
                    error="element_not_found",
                    hint="select requires a target element",
                    action="provide 'target' as '[N]' ref from snapshot",
                )
            value = kw.get("value")
            label = kw.get("label")
            if value is None and label is None:
                raise BackendError(
                    error="select_missing_option",
                    hint="select requires 'value' or 'label' parameter",
                    action="provide 'value' (option value) or 'label' (visible text)",
                )
            backend_id = self._backend_node_map.get(int(target))
            if backend_id is None:
                raise BackendError(
                    error="element_not_found",
                    hint=f"Ref [{target}] not in current snapshot",
                    action="re-snapshot and use a valid [N] ref",
                )
            # Resolve to remote object for JS manipulation
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
                        f"Could not resolve backendNodeId"
                        f" {backend_id} for ref [{target}]"
                    ),
                    action="re-snapshot and retry — the element may have been removed",
                )
            # Build JS to set value/label and dispatch events
            if value is not None:
                set_js = (
                    "function() {"
                    f"  this.value = {json.dumps(str(value))};"
                    "  this.dispatchEvent(new Event('input', {bubbles:true}));"
                    "  this.dispatchEvent(new Event('change', {bubbles:true}));"
                    "}"
                )
            else:
                # Select by visible label text
                set_js = (
                    "function() {"
                    "  const opts = Array.from(this.options);"
                    "  const opt = opts.find("
                    f"o => o.text === {json.dumps(str(label))});"
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
            result["selected"] = True
            result["value"] = value
            result["label"] = label

        elif kind in ("keydown", "keyup"):
            key = kw.get("key", "")
            if not key:
                raise BackendError(
                    error=f"{kind}_missing_key",
                    hint=f"{kind} requires 'key' parameter",
                    action="provide 'key' (e.g. 'Shift', 'Control', 'Alt')",
                )
            event_type = "keyDown" if kind == "keydown" else "keyUp"
            await self._send(
                "cdp",
                {
                    "method": "Input.dispatchKeyEvent",
                    "params": {"type": event_type, "key": key},
                },
            )
            result[kind] = True
            result["key"] = key

        new_seq = self._seq_counter.increment_action()
        self._ring_buffer.append(
            SeqEvent(
                seq=new_seq,
                kind="action",
                data={"action": kind, "target": target},
            )
        )
        result["ok"] = True
        result["seq"] = new_seq
        result["action"] = kind
        return result

    async def evaluate(self, js: str, *, world: str = "main") -> Any:
        # Remote bridge always evaluates in page context (main world)
        result = await self._send("evaluate", {"js": js})
        new_seq = self._seq_counter.increment_action()
        self._ring_buffer.append(
            SeqEvent(
                seq=new_seq,
                kind="evaluate",
                data={"js": js[:200]},
            )
        )
        return result.get("result")

    async def network(
        self, *, since: int | str = "last_action"
    ) -> list[dict[str, Any]]:
        if since == "last_action":
            since_seq = self._seq_counter.last_action_seq
        else:
            since_seq = int(since)
        events = self._ring_buffer.since(since_seq)
        return [e.data for e in events if e.kind == "network"]

    async def screenshot(
        self,
        *,
        full_page: bool = False,
        format: str = "jpeg",
        quality: int = 80,
    ) -> bytes:
        # Remote bridge screenshot; format/quality not applicable
        result = await self._send("screenshot", {})
        b64 = result.get("base64", "")
        return base64.b64decode(b64)

    async def raw_cdp(self, method: str, params: dict[str, Any] | None = None) -> Any:
        return await self.send_command(
            "cdp", {"method": method, "params": params or {}}
        )

    # ── Dialog handling via CDP Page domain ──

    def _handle_dialog_event(self, params: dict[str, Any]) -> None:
        """Handle Page.javascriptDialogOpening CDP event from extension."""
        dialog_type = params.get("type", "alert")
        message = params.get("message", "")
        default_prompt = params.get("defaultPrompt", "")

        if dialog_type in ("alert", "beforeunload"):
            # Auto-accept, same as local backend
            _task = asyncio.ensure_future(self._auto_accept_dialog())
            _task.add_done_callback(lambda t: None)  # prevent GC
            logger.info(
                "dialog_auto_accepted",
                dialog_type=dialog_type,
                message=message[:100],
            )
        else:
            # confirm / prompt — store as pending for agent
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
        """Auto-accept alert/beforeunload dialogs via CDP."""
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

    async def dialog_status(self) -> PendingDialog | None:
        return self._pending_dialog

    async def dialog_handle(
        self, action_type: str, *, text: str | None = None
    ) -> dict[str, Any]:
        if self._pending_dialog is None:
            return {"ok": True, "handled": False, "message": "no pending dialog"}

        dialog_info = {
            "type": self._pending_dialog.dialog_type,
            "message": self._pending_dialog.message,
        }

        accept = action_type == "accept"
        params: dict[str, Any] = {"accept": accept}
        if text is not None and accept:
            params["promptText"] = text

        try:
            await self._send(
                "cdp",
                {
                    "method": "Page.handleJavaScriptDialog",
                    "params": params,
                },
            )
        except Exception as exc:
            logger.debug("dialog_handle_error", error=str(exc))

        self._pending_dialog = None

        new_seq = self._seq_counter.increment_action()
        self._ring_buffer.append(
            SeqEvent(
                seq=new_seq,
                kind="dialog",
                data={"action": action_type, **dialog_info},
            )
        )
        return {
            "ok": True,
            "handled": True,
            "action": action_type,
            "dialog": dialog_info,
            "seq": new_seq,
        }

    # ── Conditional wait via CDP ──

    async def wait(
        self,
        *,
        condition: str,
        value: str = "",
        timeout: int = 30000,
        state: str = "visible",
    ) -> dict[str, Any]:
        t0 = time.monotonic()
        deadline = t0 + timeout / 1000

        if condition == "ms":
            await asyncio.sleep(int(value) / 1000)
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            return {
                "ok": True,
                "action": "wait",
                "condition": "ms",
                "elapsed_ms": elapsed_ms,
                "seq": self._seq_counter.value,
            }

        if condition == "selector":
            # Polling: check document.querySelector until found
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
                state_check = ""  # just needs to exist in DOM
            elif state == "detached":
                # Wait until NOT in DOM
                await self._poll_js(
                    f"!document.querySelector({json.dumps(value)})",
                    deadline,
                    condition,
                    timeout,
                )
                elapsed_ms = int((time.monotonic() - t0) * 1000)
                new_seq = self._seq_counter.increment_action()
                self._ring_buffer.append(
                    SeqEvent(
                        seq=new_seq,
                        kind="wait",
                        data={"condition": condition, "value": value},
                    )
                )
                return {
                    "ok": True,
                    "action": "wait",
                    "condition": condition,
                    "elapsed_ms": elapsed_ms,
                    "seq": new_seq,
                }

            js_expr = (
                f"(() => {{"
                f"  const el = document.querySelector({json.dumps(value)});"
                f"  return !!(el{state_check});"
                f"}})()"
            )
            await self._poll_js(js_expr, deadline, condition, timeout)

        elif condition == "url":
            # Poll tab URL until it matches (substring match)
            while True:
                if time.monotonic() >= deadline:
                    raise BrowserTimeoutError(
                        error="wait_timeout",
                        hint=f"Wait condition 'url' timed out after {timeout}ms",
                        action="increase timeout or check the URL pattern",
                    )
                url, _ = await self._get_tab_info()
                if value in url:
                    break
                await asyncio.sleep(0.25)

        elif condition == "load":
            # Use JS document.readyState polling as a reliable approach
            # since we don't have direct CDP event listeners via bridge
            js_expr = (
                "document.readyState === 'complete'"
                if value != "domcontentloaded"
                else "document.readyState !== 'loading'"
            )
            await self._poll_js(js_expr, deadline, condition, timeout)

        elif condition == "js":
            # Poll Runtime.evaluate until truthy
            await self._poll_js(value, deadline, condition, timeout)

        else:
            raise BackendError(
                error="invalid_wait_condition",
                hint=f"Unknown condition: '{condition}'",
                action="use one of: selector, url, load, js, ms",
            )

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        new_seq = self._seq_counter.increment_action()
        self._ring_buffer.append(
            SeqEvent(
                seq=new_seq,
                kind="wait",
                data={"condition": condition, "value": value},
            )
        )
        return {
            "ok": True,
            "action": "wait",
            "condition": condition,
            "elapsed_ms": elapsed_ms,
            "seq": new_seq,
        }

    async def _poll_js(
        self,
        expression: str,
        deadline: float,
        condition: str,
        timeout: int,
    ) -> None:
        """Poll a JS expression via CDP Runtime.evaluate until truthy."""
        while True:
            if time.monotonic() >= deadline:
                raise BrowserTimeoutError(
                    error="wait_timeout",
                    hint=f"Wait condition '{condition}' timed out after {timeout}ms",
                    action="increase timeout or check the condition",
                )
            try:
                result = await self._send(
                    "evaluate", {"js": expression}
                )
                if result.get("result"):
                    return
            except BackendError:
                raise
            except Exception:
                pass
            await asyncio.sleep(0.25)

    # ── File upload via CDP DOM.setFileInputFiles ──

    async def upload(self, index: int, files: list[str]) -> dict[str, Any]:
        backend_id = self._backend_node_map.get(index)
        if backend_id is None:
            raise BackendError(
                error="element_not_found",
                hint=f"Ref [{index}] not in current snapshot",
                action="re-snapshot and use a valid [N] ref for a file input",
            )

        # Validate files exist locally
        validated: list[str] = []
        for f in files:
            p = Path(f)
            if not p.is_file():
                raise BackendError(
                    error="upload_file_not_found",
                    hint=f"File not found: {f}",
                    action="check the file path and permissions",
                )
            validated.append(str(p.resolve()))

        await self._send(
            "cdp",
            {
                "method": "DOM.setFileInputFiles",
                "params": {
                    "files": validated,
                    "backendNodeId": backend_id,
                },
            },
        )

        new_seq = self._seq_counter.increment_action()
        self._ring_buffer.append(
            SeqEvent(
                seq=new_seq,
                kind="upload",
                data={"index": index, "files": [Path(f).name for f in validated]},
            )
        )
        logger.info(
            "audit_action",
            action="upload",
            seq=new_seq,
            files=[Path(f).name for f in validated],
            ref=f"[{index}]",
        )
        return {
            "ok": True,
            "action": "upload",
            "ref": f"[{index}]",
            "files": [Path(f).name for f in validated],
            "seq": new_seq,
        }

    # ── Frame switching via CDP Page.getFrameTree ──

    async def frame_list(self) -> list[FrameInfo]:
        try:
            result = await self._send(
                "cdp",
                {"method": "Page.getFrameTree", "params": {}},
            )
        except BackendError:
            # Fallback if Page domain not available
            return [FrameInfo(name="(main)", url="", is_current=True)]

        frames: list[FrameInfo] = []
        self._collect_frames(result.get("frameTree", {}), frames)
        return frames

    def _collect_frames(
        self,
        frame_tree: dict[str, Any],
        out: list[FrameInfo],
    ) -> None:
        """Recursively collect FrameInfo from CDP Page.getFrameTree result."""
        frame = frame_tree.get("frame", {})
        frame_id = frame.get("id", "")
        frame_name = frame.get("name", "")
        frame_url = frame.get("url", "")
        is_main = frame.get("parentId") is None or frame.get("parentId") == ""

        if is_main and not frame_name:
            frame_name = "(main)"

        is_current = (
            (self._active_frame_id is None and is_main)
            or (self._active_frame_id == frame_id)
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

    async def frame_focus(
        self,
        *,
        name: str | None = None,
        url: str | None = None,
        main: bool = False,
    ) -> dict[str, Any]:
        if main:
            self._active_frame_id = None
            return {
                "ok": True,
                "action": "frame_focus",
                "frame": "(main)",
                "url": "",
            }

        # Get frame tree to find matching frame
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
            frames_list = await self.frame_list()
            available = [f.name or f.url[:60] for f in frames_list]
            raise BackendError(
                error="frame_not_found",
                hint=f"No frame matching name={name!r} url={url!r}",
                action=f"available frames: {available}",
            )

        self._active_frame_id = target["id"]
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
        """Find a frame in the tree by name or URL substring."""
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

    async def _get_child_frame_trees(self) -> list[FrameData]:
        """Fetch AX trees from child frames via CDP Page.getFrameTree."""
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

    async def close(self) -> None:
        if not self._ws.closed:
            await self._ws.close()
