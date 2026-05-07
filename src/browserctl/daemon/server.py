"""Daemon lifecycle — start, stop, health check."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import sys
from typing import TYPE_CHECKING

import orjson
import structlog
from aiohttp import web

from browserctl.browser import create_context
from browserctl.core.config import Paths, load_config
from browserctl.core.types import StealthTier
from browserctl.daemon.middleware import error_middleware
from browserctl.daemon.routes import setup_routes

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["health", "start", "stop"]

logger = structlog.get_logger()


def _pid_file(paths: Paths) -> Path:
    return paths.root / "daemon.pid"


def _write_pid(paths: Paths) -> None:
    paths.ensure_dirs()
    _pid_file(paths).write_text(str(os.getpid()))


def _clear_pid(paths: Paths) -> None:
    pf = _pid_file(paths)
    if pf.exists():
        pf.unlink()


def _write_session(paths: Paths, *, port: int, tier: StealthTier) -> None:
    data = {
        "pid": os.getpid(),
        "port": port,
        "stealth_tier": tier.value,
    }
    paths.ensure_dirs()
    paths.active_session_file.write_bytes(orjson.dumps(data))


def _clear_session(paths: Paths) -> None:
    if paths.active_session_file.exists():
        paths.active_session_file.unlink()


def _check_stale_pid(paths: Paths) -> bool:
    pf = _pid_file(paths)
    if not pf.exists():
        return False
    try:
        pid = int(pf.read_text().strip())
        os.kill(pid, 0)
        return True
    except (ValueError, ProcessLookupError, PermissionError):
        _clear_pid(paths)
        _clear_session(paths)
        return False


async def start(
    *,
    host: str | None = None,
    port: int | None = None,
    headless: bool = True,
) -> None:
    """Start the daemon server (blocking)."""
    paths, cfg = load_config()

    actual_host = host or cfg.daemon_host
    actual_port = port or cfg.daemon_port

    if _check_stale_pid(paths):
        logger.error("daemon_already_running", pid_file=str(_pid_file(paths)))
        sys.exit(1)

    _write_pid(paths)
    _write_session(paths, port=actual_port, tier=StealthTier(cfg.default_tier))

    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.dev.ConsoleRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )

    app = web.Application(middlewares=[error_middleware])

    logger.info("launching_browser", tier=cfg.default_tier, headless=headless)
    ctx = await create_context(
        tier=StealthTier(cfg.default_tier),
        headless=headless,
        viewport_width=cfg.viewport_width,
        viewport_height=cfg.viewport_height,
    )
    app["browser_ctx"] = ctx

    setup_routes(app)

    async def on_shutdown(a: web.Application) -> None:
        logger.info("shutting_down")
        with contextlib.suppress(Exception):
            await ctx.close()
        _clear_pid(paths)
        _clear_session(paths)

    app.on_shutdown.append(on_shutdown)

    logger.info("daemon_starting", host=actual_host, port=actual_port)

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig, lambda: asyncio.ensure_future(_graceful_shutdown(app))
        )

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, actual_host, actual_port)
    await site.start()
    logger.info("daemon_ready", host=actual_host, port=actual_port)

    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()


async def _graceful_shutdown(app: web.Application) -> None:
    await app.shutdown()
    await app.cleanup()
    raise SystemExit(0)


async def stop(*, host: str | None = None, port: int | None = None) -> bool:
    """Send shutdown request to the daemon."""
    import aiohttp

    _, cfg = load_config()
    actual_host = host or cfg.daemon_host
    actual_port = port or cfg.daemon_port
    url = f"http://{actual_host}:{actual_port}/shutdown"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, timeout=aiohttp.ClientTimeout(total=5)):
                pass
    except Exception:
        pass
    return True


async def health(*, host: str | None = None, port: int | None = None) -> bool:
    """Check if daemon is reachable."""
    import aiohttp

    _, cfg = load_config()
    actual_host = host or cfg.daemon_host
    actual_port = port or cfg.daemon_port
    url = f"http://{actual_host}:{actual_port}/health"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                data = await resp.json()
                return bool(data.get("ok"))
    except Exception:
        return False
