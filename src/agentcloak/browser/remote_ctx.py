"""RemoteBridgeContext — operates a remote browser via bridge WebSocket."""

from __future__ import annotations

import asyncio
import base64
import json
import uuid
from typing import TYPE_CHECKING, Any

from agentcloak.browser.state import (
    INTERACTIVE_ROLES,
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


class RemoteBridgeContext:
    """BrowserContext backed by a remote Chrome via bridge WebSocket."""

    def __init__(self, *, bridge_ws: web.WebSocketResponse) -> None:
        self._ws = bridge_ws
        self._seq_counter = SeqCounter()
        self._ring_buffer = RingBuffer()
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}

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

    async def snapshot(
        self,
        *,
        mode: str = "accessible",
        max_nodes: int = 0,
        max_chars: int = 0,
        focus: int = 0,
        offset: int = 0,
    ) -> PageSnapshot:
        # Progressive loading params not supported in remote bridge
        if mode == "accessible":
            result = await self._send(
                "cdp",
                {"method": "Accessibility.getFullAXTree", "params": {"pierce": True}},
            )
            return self._parse_ax_tree(result)

        if mode == "content":
            result = await self._send(
                "evaluate", {"js": "document.body?.innerText || ''"}
            )
            js = "[document.URL, document.title]"
            tab_info = await self._send("evaluate", {"js": js})
            raw: list[str] = tab_info.get("result", ["", ""])
            url = str(raw[0]) if len(raw) > 0 else ""
            title = str(raw[1]) if len(raw) > 1 else ""
            return PageSnapshot(
                seq=self._seq_counter.value,
                url=url,
                title=title,
                mode="content",
                tree_text=str(result.get("result", "")),
            )

        raise BackendError(
            error="invalid_snapshot_mode",
            hint=f"Unknown mode: {mode}",
            action="use one of: accessible, content",
        )

    def _parse_ax_tree(self, cdp_result: dict[str, Any]) -> PageSnapshot:
        nodes = cdp_result.get("nodes", [])
        selector_map: dict[int, ElementRef] = {}
        lines: list[str] = []
        counter = 1
        interactive_roles = INTERACTIVE_ROLES
        skip_roles = {"none", "InlineTextBox", "LineBreak"}

        for node in nodes:
            role = node.get("role", {}).get("value", "")
            name = node.get("name", {}).get("value", "")
            if not role or role in skip_roles:
                continue
            if role.lower() in interactive_roles:
                selector_map[counter] = ElementRef(
                    index=counter,
                    tag=role,
                    role=role,
                    text=name,
                    attributes={},
                )
                lines.append(f"[{counter}] <{role}> {name}")
                counter += 1
            elif name:
                lines.append(f"{role}: {name}")

        return PageSnapshot(
            seq=self._seq_counter.value,
            url="",
            title="",
            mode="accessible",
            tree_text="\n".join(lines),
            selector_map=selector_map,
        )

    async def action(self, kind: str, target: str, **kw: Any) -> dict[str, Any]:
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

        if kind == "click":
            x = kw.get("x")
            y = kw.get("y")
            if x is not None and y is not None:
                mouse_p = {
                    "type": "mousePressed",
                    "x": float(x),
                    "y": float(y),
                    "button": "left",
                    "clickCount": 1,
                }
                mouse_r = {
                    "type": "mouseReleased",
                    "x": float(x),
                    "y": float(y),
                    "button": "left",
                    "clickCount": 1,
                }
                await self._send(
                    "cdp",
                    {
                        "method": "Input.dispatchMouseEvent",
                        "params": mouse_p,
                    },
                )
                await self._send(
                    "cdp",
                    {
                        "method": "Input.dispatchMouseEvent",
                        "params": mouse_r,
                    },
                )
            else:
                # Validate idx is strictly an integer to prevent JS injection
                idx = int(target)
                js = (
                    "document.querySelector("
                    f"'[data-agentcloak-idx=\"{idx}\"]'"
                    ")?.click()"
                )
                await self._send("evaluate", {"js": js})

        elif kind == "press":
            key = kw.get("key", "")
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

        elif kind in ("fill", "type"):
            text = kw.get("text", "")
            val = json.dumps(text)
            js = (
                f"(() => {{"
                f" const el = document.activeElement;"
                f" if (el) {{"
                f" el.value = {val};"
                f" el.dispatchEvent(new Event('input',"
                f" {{bubbles:true}}));"
                f" }}"
                f"}})()"
            )
            await self._send("evaluate", {"js": js})

        elif kind in ("keydown", "keyup"):
            key = kw.get("key", "")
            event_type = "keyDown" if kind == "keydown" else "keyUp"
            await self._send(
                "cdp",
                {
                    "method": "Input.dispatchKeyEvent",
                    "params": {"type": event_type, "key": key},
                },
            )

        new_seq = self._seq_counter.increment_action()
        self._ring_buffer.append(
            SeqEvent(
                seq=new_seq,
                kind="action",
                data={"action": kind, "target": target},
            )
        )
        return {"ok": True, "seq": new_seq, "action": kind}

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

    async def raw_cdp(
        self, method: str, params: dict[str, Any] | None = None
    ) -> Any:
        return await self.send_command(
            "cdp", {"method": method, "params": params or {}}
        )

    # ── Phase 5g Protocol stubs ──
    # RemoteBridge does not have Playwright page objects, so these
    # return minimal "not supported" responses rather than crashing.

    async def dialog_status(self) -> PendingDialog | None:
        return None

    async def dialog_handle(
        self, action_type: str, *, text: str | None = None
    ) -> dict[str, Any]:
        return {
            "ok": True,
            "handled": False,
            "message": "dialog handling not supported via remote bridge",
        }

    async def wait(
        self,
        *,
        condition: str,
        value: str = "",
        timeout: int = 30000,
        state: str = "visible",
    ) -> dict[str, Any]:
        if condition == "ms":
            await asyncio.sleep(int(value) / 1000)
            return {
                "ok": True,
                "action": "wait",
                "condition": "ms",
                "elapsed_ms": int(value),
                "seq": self._seq_counter.value,
            }
        raise BackendError(
            error="wait_not_supported",
            hint="Remote bridge only supports 'ms' wait condition",
            action="use 'ms' condition or switch to a local backend",
        )

    async def upload(
        self, index: int, files: list[str]
    ) -> dict[str, Any]:
        raise BackendError(
            error="upload_not_supported",
            hint="File upload not supported via remote bridge",
            action="use a local backend for file upload",
        )

    async def frame_list(self) -> list[FrameInfo]:
        return [FrameInfo(name="(main)", url="", is_current=True)]

    async def frame_focus(
        self,
        *,
        name: str | None = None,
        url: str | None = None,
        main: bool = False,
    ) -> dict[str, Any]:
        if main:
            return {
                "ok": True,
                "action": "frame_focus",
                "frame": "(main)",
                "url": "",
            }
        raise BackendError(
            error="frame_not_supported",
            hint="Frame switching not supported via remote bridge",
            action="use a local backend for frame switching",
        )

    async def close(self) -> None:
        if not self._ws.closed:
            await self._ws.close()
