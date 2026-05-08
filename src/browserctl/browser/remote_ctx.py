"""RemoteBridgeContext — operates a remote browser via bridge WebSocket."""

from __future__ import annotations

import asyncio
import base64
import json
import uuid
from typing import TYPE_CHECKING, Any

from browserctl.browser.state import ElementRef, PageSnapshot
from browserctl.core.errors import BackendError, BrowserTimeoutError
from browserctl.core.seq import RingBuffer, SeqCounter, SeqEvent
from browserctl.core.types import StealthTier

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
        fut: asyncio.Future[dict[str, Any]] = asyncio.get_event_loop().create_future()
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

    async def snapshot(self, *, mode: str = "accessible") -> PageSnapshot:
        if mode == "accessible":
            result = await self._send(
                "cdp",
                {"method": "Accessibility.getFullAXTree", "params": {}},
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
        interactive_roles = {
            "button",
            "checkbox",
            "combobox",
            "link",
            "menuitem",
            "option",
            "radio",
            "searchbox",
            "slider",
            "spinbutton",
            "switch",
            "tab",
            "textbox",
            "treeitem",
        }

        for node in nodes:
            role = node.get("role", {}).get("value", "")
            name = node.get("name", {}).get("value", "")
            if not role or role == "none":
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
                idx = target
                js = (
                    "document.querySelector("
                    f"'[data-browserctl-idx=\"{idx}\"]'"
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

        new_seq = self._seq_counter.increment_action()
        self._ring_buffer.append(
            SeqEvent(
                seq=new_seq,
                kind="action",
                data={"action": kind, "target": target},
            )
        )
        return {"ok": True, "seq": new_seq, "action": kind}

    async def evaluate(self, js: str) -> Any:
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

    async def screenshot(self, *, full_page: bool = False) -> bytes:
        result = await self._send("screenshot", {})
        b64 = result.get("base64", "")
        return base64.b64decode(b64)

    async def close(self) -> None:
        if not self._ws.closed:
            await self._ws.close()
