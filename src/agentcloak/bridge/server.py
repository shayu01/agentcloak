"""Bridge server — WS hub between Chrome extension and remote daemon.

The bridge sits between a user's Chrome browser (via a custom extension) and
the agentcloak daemon running on a different machine. It exposes:

- A WebSocket endpoint at ``/ext`` for the Chrome extension to connect to.
- A health endpoint at ``/health`` for monitoring.
- A long-lived WebSocket client that connects to the daemon's ``/bridge/ws``
  and relays commands between the two sides.

The transport stack is **Starlette + uvicorn** (server side) and the
``websockets`` library (client side). One WebSocket toolchain ships across
the whole project — daemon, bridge, and remote backend all share it.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
import uvicorn
import websockets
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from agentcloak.bridge.config import BridgeConfig, load_bridge_config

if TYPE_CHECKING:
    from starlette.requests import Request

__all__ = ["start_bridge"]

logger = structlog.get_logger()

RECONNECT_BASE = 2.0
RECONNECT_MAX = 30.0
_PORT_RANGE_SIZE = 10
_EXTENSION_COMMAND_TIMEOUT = 60.0
_DAEMON_PING_INTERVAL = 30.0


def _is_localhost(remote: str | None) -> bool:
    """Check if a request comes from localhost (bypass token auth)."""
    if not remote:
        return False
    return remote in ("127.0.0.1", "::1", "localhost")


class BridgeHub:
    """Routes commands between daemon and Chrome extension.

    The hub holds two long-lived WebSocket handles:

    - ``_ext_ws``: a Starlette :class:`WebSocket` accepted from the Chrome
      extension. Lifecycle is owned by the request handler.
    - ``_daemon_ws``: a ``websockets`` client connection to the daemon.
      Lifecycle is owned by :func:`_connect_to_daemon`.
    """

    def __init__(self, cfg: BridgeConfig) -> None:
        self._cfg = cfg
        self._ext_ws: WebSocket | None = None
        self._daemon_ws: Any = None  # websockets.ClientConnection
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._connected_event = asyncio.Event()
        self._ext_authenticated = False

    @property
    def extension_connected(self) -> bool:
        return self._ext_ws is not None

    @property
    def daemon_connected(self) -> bool:
        if self._daemon_ws is None:
            return False
        # websockets exposes a ``state`` enum; OPEN == 1.
        state = getattr(self._daemon_ws, "state", None)
        if state is None:
            return True
        try:
            from websockets.protocol import State as _State

            return state is _State.OPEN
        except Exception:
            return True

    def set_daemon_ws(self, ws: Any) -> None:
        self._daemon_ws = ws

    async def wait_for_extension(self) -> None:
        """Wait until the extension connects and authenticates."""
        await self._connected_event.wait()

    async def handle_extension_ws(self, websocket: WebSocket) -> None:
        await websocket.accept()

        # Replace any prior connection (extension reconnects).
        if self._ext_ws is not None:
            with contextlib.suppress(Exception):
                await self._ext_ws.close()

        self._ext_ws = websocket
        self._ext_authenticated = False

        client = websocket.client
        remote = client.host if client else None
        is_local = _is_localhost(remote)

        # If no token configured, or connection is from localhost, skip auth.
        if not self._cfg.token or is_local:
            self._ext_authenticated = True
            self._connected_event.set()
            logger.info(
                "extension_connected",
                remote=remote,
                auth="bypass" if is_local and self._cfg.token else "none",
            )
        else:
            logger.info("extension_connected_pending_auth", remote=remote)

        try:
            while True:
                try:
                    data = await websocket.receive_text()
                except WebSocketDisconnect:
                    break
                should_close = await self._handle_ext_message(data, is_local)
                if should_close:
                    with contextlib.suppress(Exception):
                        await websocket.close(code=4001, reason="invalid token")
                    break
        finally:
            self._ext_ws = None
            self._ext_authenticated = False
            self._connected_event.clear()
            logger.info("extension_disconnected")

    async def _handle_ext_message(self, data: str, is_local: bool) -> bool:
        """Handle a message from the extension.

        Returns ``True`` if the connection should be closed (auth failure).
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

        fut: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[msg_id] = fut

        try:
            if self._ext_ws is None:
                raise RuntimeError("extension WebSocket is not connected")
            await self._ext_ws.send_text(json.dumps(message))
            result = await asyncio.wait_for(fut, timeout=_EXTENSION_COMMAND_TIMEOUT)
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
        from agentcloak.core.discovery import discover_daemon

        discovered = discover_daemon(timeout=2.0)
        if discovered and discovered not in candidates:
            candidates.insert(0, discovered)
            logger.info("mdns_candidate_added", url=discovered)
    except Exception:
        pass
    return candidates


async def _connect_to_daemon(hub: BridgeHub, cfg: BridgeConfig) -> None:
    """Maintain a long-lived WS connection to the daemon with backoff retry."""
    delay = RECONNECT_BASE

    while True:
        candidates = _build_candidates(cfg)
        for candidate in candidates:
            try:
                logger.info("daemon_connecting", url=candidate)
                headers: list[tuple[str, str]] = []
                if cfg.token:
                    headers.append(("Authorization", f"Bearer {cfg.token}"))

                async with websockets.connect(
                    candidate,
                    additional_headers=headers or None,
                    ping_interval=_DAEMON_PING_INTERVAL,
                    open_timeout=10.0,
                ) as ws:
                    logger.info("daemon_connected", url=candidate)
                    delay = RECONNECT_BASE
                    hub.set_daemon_ws(ws)

                    try:
                        async for raw in ws:
                            text = raw if isinstance(raw, str) else raw.decode()
                            response = await hub.handle_daemon_command(text)
                            await ws.send(response)
                    except websockets.ConnectionClosed:
                        pass

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
    """Write bridge connection info to ~/.agentcloak/bridge.json (atomic)."""
    info_dir = Path.home() / ".agentcloak"
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
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, str(info_path))
    except Exception:
        # Clean up on failure
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def _print_bridge_info(host: str, port: int, token: str | None) -> None:
    """Print structured bridge connection info to stderr."""
    display_host = _get_display_host(host)
    config_json = json.dumps(
        {"host": display_host, "port": port, "token": token}, ensure_ascii=False
    )
    sys.stderr.write("\n")
    sys.stderr.write("  agentcloak bridge ready\n")
    sys.stderr.write(f"    address: {display_host}:{port}\n")
    sys.stderr.write(f"    token:   {token or '(none)'}\n")
    sys.stderr.write(f"    config:  {config_json}\n")
    sys.stderr.write("\n")
    sys.stderr.flush()  # ensure output visible in background processes (BUG-9)


def _build_app(hub: BridgeHub) -> Starlette:
    async def handle_health(_: Request) -> JSONResponse:
        return JSONResponse(
            {
                "ok": True,
                "service": "agentcloak-bridge",
                "extension": hub.extension_connected,
                "daemon": hub.daemon_connected,
            }
        )

    routes = [
        WebSocketRoute("/ext", hub.handle_extension_ws),
        Route("/health", handle_health, methods=["GET"]),
    ]
    return Starlette(routes=routes)


async def _try_bind_port(
    *, config: uvicorn.Config, host: str, base_port: int
) -> tuple[uvicorn.Server, int]:
    """Probe ports and return a configured uvicorn.Server bound to a free one."""
    last_error: OSError | None = None
    for offset in range(_PORT_RANGE_SIZE):
        try_port = base_port + offset
        loop = asyncio.get_running_loop()
        try:
            sock_server = await loop.create_server(
                lambda: asyncio.Protocol(), host, try_port
            )
        except OSError as exc:
            last_error = exc
            if offset < _PORT_RANGE_SIZE - 1:
                logger.info(
                    "port_in_use",
                    port=try_port,
                    next_port=try_port + 1,
                )
            continue
        sock_server.close()
        await sock_server.wait_closed()

        config.port = try_port
        server = uvicorn.Server(config=config)
        return server, try_port

    assert last_error is not None
    raise last_error


async def start_bridge(*, host: str = "127.0.0.1", port: int | None = None) -> None:
    """Start the bridge process (blocking)."""
    cfg = load_bridge_config()

    actual_host = host
    base_port = port or cfg.bridge_port
    hub = BridgeHub(cfg)
    app = _build_app(hub)

    uvicorn_config = uvicorn.Config(
        app,
        host=actual_host,
        port=base_port,
        log_level="warning",
        access_log=False,
        loop="asyncio",
        ws="websockets",
    )

    try:
        server, actual_port = await _try_bind_port(
            config=uvicorn_config, host=actual_host, base_port=base_port
        )
    except OSError:
        logger.error(
            "all_ports_exhausted",
            range_start=base_port,
            range_end=base_port + _PORT_RANGE_SIZE - 1,
        )
        raise

    logger.info("bridge_started", host=actual_host, port=actual_port)

    # Write bridge.json and print connection info
    try:
        _write_bridge_info(actual_host, actual_port, cfg.token)
    except Exception as exc:
        logger.warning("bridge_json_write_failed", error=str(exc))

    _print_bridge_info(actual_host, actual_port, cfg.token)

    # Background tasks: extension prompt + daemon reconnect loop
    extension_task = asyncio.create_task(_wait_for_extension(hub))
    daemon_task = asyncio.create_task(_connect_to_daemon(hub, cfg))

    try:
        await server.serve()
    finally:
        extension_task.cancel()
        daemon_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await extension_task
        with contextlib.suppress(asyncio.CancelledError):
            await daemon_task
        # Clean up bridge.json on shutdown
        with contextlib.suppress(Exception):
            (Path.home() / ".agentcloak" / "bridge.json").unlink(missing_ok=True)


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
