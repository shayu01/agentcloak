"""Bridge server — WS hub between Chrome extension and remote daemon."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

import structlog
from aiohttp import ClientSession, WSMsgType, web

from browserctl.bridge.config import BridgeConfig, load_bridge_config

__all__ = ["start_bridge"]

logger = structlog.get_logger()

RECONNECT_BASE = 2.0
RECONNECT_MAX = 30.0
_PORT_RANGE_SIZE = 10


def _is_localhost(remote: str | None) -> bool:
    """Check if a request comes from localhost (bypass token auth)."""
    if not remote:
        return False
    return remote in ("127.0.0.1", "::1", "localhost")


class BridgeHub:
    """Routes commands between daemon and Chrome extension."""

    def __init__(self, cfg: BridgeConfig) -> None:
        self._cfg = cfg
        self._ext_ws: web.WebSocketResponse | None = None
        self._daemon_ws: Any = None
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._connected_event = asyncio.Event()
        self._ext_authenticated = False

    @property
    def extension_connected(self) -> bool:
        return self._ext_ws is not None and not self._ext_ws.closed

    @property
    def daemon_connected(self) -> bool:
        return self._daemon_ws is not None and not self._daemon_ws.closed

    def set_daemon_ws(self, ws: Any) -> None:
        self._daemon_ws = ws

    async def wait_for_extension(self) -> None:
        """Wait until the extension connects and authenticates."""
        await self._connected_event.wait()

    async def handle_extension_ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        if self._ext_ws and not self._ext_ws.closed:
            await self._ext_ws.close()

        self._ext_ws = ws
        self._ext_authenticated = False
        is_local = _is_localhost(request.remote)

        # If no token configured, or connection is from localhost, skip auth
        if not self._cfg.token or is_local:
            self._ext_authenticated = True
            self._connected_event.set()
            logger.info(
                "extension_connected",
                remote=request.remote,
                auth="bypass" if is_local and self._cfg.token else "none",
            )
        else:
            logger.info(
                "extension_connected_pending_auth", remote=request.remote
            )

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    should_close = await self._handle_ext_message(
                        msg.data, is_local
                    )
                    if should_close:
                        await ws.close(code=4001, message=b"invalid token")
                        break
                elif msg.type == WSMsgType.ERROR:
                    break
        finally:
            self._ext_ws = None
            self._ext_authenticated = False
            self._connected_event.clear()
            logger.info("extension_disconnected")

        return ws

    async def _handle_ext_message(self, data: str, is_local: bool) -> bool:
        """Handle a message from the extension.

        Returns True if the connection should be closed (auth failure).
        """
        try:
            msg = json.loads(data)
        except json.JSONDecodeError:
            return False

        msg_id = msg.get("id")
        if msg_id and msg_id in self._pending:
            self._pending[msg_id].set_result(msg)
            return False

        if msg.get("type") == "hello":
            agent = msg.get("agent")
            # Token verification for remote connections
            if self._cfg.token and not is_local:
                ext_token = msg.get("token")
                if ext_token != self._cfg.token:
                    logger.warning(
                        "extension_auth_failed",
                        agent=agent,
                        reason="invalid or missing token",
                    )
                    return True  # signal to close connection
                logger.info("extension_auth_ok", agent=agent)

            self._ext_authenticated = True
            self._connected_event.set()
            logger.info("extension_hello", agent=agent)

        return False

    async def send_to_extension(
        self, cmd: str, params: dict[str, Any] | None = None, **kw: Any
    ) -> dict[str, Any]:
        if not self.extension_connected or not self._ext_authenticated:
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


def _build_candidates(cfg: BridgeConfig) -> list[str]:
    candidates = list(cfg.daemon_candidates)
    try:
        from browserctl.core.discovery import discover_daemon

        discovered = discover_daemon(timeout=2.0)
        if discovered and discovered not in candidates:
            candidates.insert(0, discovered)
            logger.info("mdns_candidate_added", url=discovered)
    except Exception:
        pass
    return candidates


async def _connect_to_daemon(hub: BridgeHub, cfg: BridgeConfig) -> None:
    delay = RECONNECT_BASE

    while True:
        candidates = _build_candidates(cfg)
        for candidate in candidates:
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


def _get_display_host(host: str) -> str:
    """Return actual LAN IP when binding to 0.0.0.0 (wildcard)."""
    if host != "0.0.0.0":
        return host
    import socket as _socket
    try:
        with _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return host


def _write_bridge_info(host: str, port: int, token: str | None) -> None:
    """Write bridge connection info to ~/.browserctl/bridge.json (atomic)."""
    info_dir = Path.home() / ".browserctl"
    info_dir.mkdir(parents=True, exist_ok=True)
    info_path = info_dir / "bridge.json"

    display_host = _get_display_host(host)
    data = {"host": display_host, "port": port, "token": token}

    # Atomic write: write to tmp file in same dir, then rename
    fd, tmp_path = tempfile.mkstemp(dir=str(info_dir), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp_path, str(info_path))
    except Exception:
        # Clean up on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _print_bridge_info(host: str, port: int, token: str | None) -> None:
    """Print structured bridge connection info to stderr."""
    display_host = _get_display_host(host)
    config_json = json.dumps(
        {"host": display_host, "port": port, "token": token}, ensure_ascii=False
    )
    sys.stderr.write("\n")
    sys.stderr.write("  browserctl bridge ready\n")
    sys.stderr.write(f"    address: {display_host}:{port}\n")
    sys.stderr.write(f"    token:   {token or '(none)'}\n")
    sys.stderr.write(f"    config:  {config_json}\n")
    sys.stderr.write("\n")
    sys.stderr.flush()  # ensure output visible in background processes (BUG-9)


async def start_bridge(*, host: str = "127.0.0.1", port: int | None = None) -> None:
    """Start the bridge process (blocking)."""
    cfg = load_bridge_config()

    actual_host = host
    base_port = port or cfg.bridge_port
    hub = BridgeHub(cfg)

    async def handle_health(_: web.Request) -> web.Response:
        return web.json_response(
            {
                "ok": True,
                "service": "browserctl-bridge",
                "extension": hub.extension_connected,
                "daemon": hub.daemon_connected,
            }
        )

    app = web.Application()
    app.router.add_get("/ext", hub.handle_extension_ws)
    app.router.add_get("/health", handle_health)

    runner = web.AppRunner(app)
    await runner.setup()

    # Auto-port: try base_port, then base_port+1, ..., up to base_port+9
    actual_port = base_port
    last_error: OSError | None = None
    for offset in range(_PORT_RANGE_SIZE):
        try_port = base_port + offset
        try:
            site = web.TCPSite(runner, actual_host, try_port)
            await site.start()
            actual_port = try_port
            last_error = None
            break
        except OSError as exc:
            last_error = exc
            if offset < _PORT_RANGE_SIZE - 1:
                logger.info(
                    "port_in_use",
                    port=try_port,
                    next_port=try_port + 1,
                )
            continue

    if last_error is not None:
        logger.error(
            "all_ports_exhausted",
            range_start=base_port,
            range_end=base_port + _PORT_RANGE_SIZE - 1,
        )
        await runner.cleanup()
        raise last_error

    logger.info("bridge_started", host=actual_host, port=actual_port)

    # Write bridge.json and print connection info
    try:
        _write_bridge_info(actual_host, actual_port, cfg.token)
    except Exception as exc:
        logger.warning("bridge_json_write_failed", error=str(exc))

    _print_bridge_info(actual_host, actual_port, cfg.token)

    # Wait for extension connection with first-run guidance
    await _wait_for_extension(hub)

    daemon_task = asyncio.create_task(_connect_to_daemon(hub, cfg))

    try:
        await asyncio.Event().wait()
    finally:
        daemon_task.cancel()
        # Clean up bridge.json on shutdown
        try:
            (Path.home() / ".browserctl" / "bridge.json").unlink(missing_ok=True)
        except Exception:
            pass
        await runner.cleanup()


async def _wait_for_extension(hub: BridgeHub) -> None:
    """Wait for extension with install guidance on first run."""
    if hub.extension_connected:
        logger.info("extension_already_connected")
        return

    ext_dir = Path(__file__).parent / "extension"

    sys.stderr.write("\n")
    sys.stderr.write("  Chrome extension not connected yet.\n")
    sys.stderr.write("  Install it to enable browser control:\n\n")
    sys.stderr.write("  1. Open chrome://extensions in Chrome\n")
    sys.stderr.write("  2. Enable 'Developer mode' (top-right toggle)\n")
    sys.stderr.write("  3. Click 'Load unpacked' and select:\n")
    sys.stderr.write(f"     {ext_dir.resolve()}\n\n")
    sys.stderr.write("  Waiting for extension to connect...\n\n")
    sys.stderr.flush()

    try:
        import webbrowser

        webbrowser.open("chrome://extensions")
    except Exception:
        pass

    try:
        await asyncio.wait_for(hub.wait_for_extension(), timeout=120.0)
        logger.info("extension_connected_after_install")
    except TimeoutError:
        logger.warning("extension_connect_timeout")
