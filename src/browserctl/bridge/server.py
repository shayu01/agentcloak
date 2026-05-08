"""Bridge server — WS hub between Chrome extension and remote daemon."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import structlog
from aiohttp import ClientSession, WSMsgType, web

from browserctl.bridge.config import BridgeConfig, load_bridge_config

__all__ = ["start_bridge"]

logger = structlog.get_logger()

RECONNECT_BASE = 2.0
RECONNECT_MAX = 30.0


class BridgeHub:
    """Routes commands between daemon and Chrome extension."""

    def __init__(self) -> None:
        self._ext_ws: web.WebSocketResponse | None = None
        self._daemon_ws: Any = None
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._connected_event = asyncio.Event()

    @property
    def extension_connected(self) -> bool:
        return self._ext_ws is not None and not self._ext_ws.closed

    @property
    def daemon_connected(self) -> bool:
        return self._daemon_ws is not None and not self._daemon_ws.closed

    def set_daemon_ws(self, ws: Any) -> None:
        self._daemon_ws = ws

    async def handle_extension_ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        if self._ext_ws and not self._ext_ws.closed:
            await self._ext_ws.close()

        self._ext_ws = ws
        self._connected_event.set()
        logger.info("extension_connected")

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    await self._handle_ext_message(msg.data)
                elif msg.type == WSMsgType.ERROR:
                    break
        finally:
            self._ext_ws = None
            self._connected_event.clear()
            logger.info("extension_disconnected")

        return ws

    async def _handle_ext_message(self, data: str) -> None:
        try:
            msg = json.loads(data)
        except json.JSONDecodeError:
            return

        msg_id = msg.get("id")
        if msg_id and msg_id in self._pending:
            self._pending[msg_id].set_result(msg)
            return

        if msg.get("type") == "hello":
            logger.info("extension_hello", agent=msg.get("agent"))

    async def send_to_extension(
        self, cmd: str, params: dict[str, Any] | None = None, **kw: Any
    ) -> dict[str, Any]:
        if not self.extension_connected:
            return {"ok": False, "error": "extension not connected"}

        msg_id = str(uuid.uuid4())[:8]
        message: dict[str, Any] = {"id": msg_id, "cmd": cmd}
        if params:
            message["params"] = params
        message.update(kw)

        fut: asyncio.Future[dict[str, Any]] = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = fut

        try:
            assert self._ext_ws is not None
            await self._ext_ws.send_str(json.dumps(message))
            result = await asyncio.wait_for(fut, timeout=60.0)
            return result
        except TimeoutError:
            return {"ok": False, "error": "extension command timeout"}
        finally:
            self._pending.pop(msg_id, None)

    async def handle_daemon_command(self, data: str) -> str:
        try:
            msg = json.loads(data)
        except json.JSONDecodeError:
            return json.dumps({"ok": False, "error": "invalid json"})

        cmd = msg.get("cmd")
        if cmd == "ping":
            return json.dumps(
                {
                    "id": msg.get("id"),
                    "ok": True,
                    "data": {
                        "extension": self.extension_connected,
                    },
                }
            )

        if cmd == "status":
            return json.dumps(
                {
                    "id": msg.get("id"),
                    "ok": True,
                    "data": {
                        "extension_connected": self.extension_connected,
                    },
                }
            )

        result = await self.send_to_extension(
            cmd=cmd,
            params=msg.get("params"),
            tabId=msg.get("tabId"),
        )
        result["id"] = msg.get("id")
        return json.dumps(result)


async def _connect_to_daemon(hub: BridgeHub, cfg: BridgeConfig) -> None:
    delay = RECONNECT_BASE

    while True:
        for candidate in cfg.daemon_candidates:
            try:
                logger.info("daemon_connecting", url=candidate)
                async with ClientSession() as session:
                    headers: dict[str, str] = {}
                    if cfg.token:
                        headers["Authorization"] = f"Bearer {cfg.token}"

                    async with session.ws_connect(
                        candidate, headers=headers, heartbeat=30.0
                    ) as ws:
                        logger.info("daemon_connected", url=candidate)
                        delay = RECONNECT_BASE
                        hub.set_daemon_ws(ws)

                        async for msg in ws:
                            if msg.type == WSMsgType.TEXT:
                                response = await hub.handle_daemon_command(msg.data)
                                await ws.send_str(response)
                            elif msg.type in (WSMsgType.CLOSE, WSMsgType.ERROR):
                                break

                        hub.set_daemon_ws(None)
                        logger.info("daemon_disconnected", url=candidate)

            except Exception as exc:
                logger.debug("daemon_connect_failed", url=candidate, error=str(exc))
                continue

        logger.info("daemon_reconnecting", delay=delay)
        await asyncio.sleep(delay)
        delay = min(delay * 1.5, RECONNECT_MAX)


async def start_bridge(*, host: str = "127.0.0.1", port: int | None = None) -> None:
    """Start the bridge process (blocking)."""
    cfg = load_bridge_config()
    actual_port = port or cfg.bridge_port
    hub = BridgeHub()

    async def handle_health(_: web.Request) -> web.Response:
        return web.json_response({
            "ok": True,
            "extension": hub.extension_connected,
            "daemon": hub.daemon_connected,
        })

    app = web.Application()
    app.router.add_get("/ext", hub.handle_extension_ws)
    app.router.add_get("/health", handle_health)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, actual_port)
    await site.start()

    logger.info("bridge_started", host=host, port=actual_port)
    logger.info(
        "extension_hint",
        message="Install the browserctl extension in Chrome and it will auto-connect",
    )

    daemon_task = asyncio.create_task(_connect_to_daemon(hub, cfg))

    try:
        await asyncio.Event().wait()
    finally:
        daemon_task.cancel()
        await runner.cleanup()
