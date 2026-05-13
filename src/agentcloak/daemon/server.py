"""Daemon lifecycle — start, stop, health check."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import secrets
import signal
import sys
from typing import TYPE_CHECKING, Any

import orjson
import structlog
from aiohttp import web

from agentcloak.browser import create_context
from agentcloak.browser.cloak_ctx import TURNSTILE_PATCH_DIR
from agentcloak.browser.xvfb import XvfbManager
from agentcloak.core.config import Paths, load_config
from agentcloak.core.types import StealthTier
from agentcloak.daemon.middleware import error_middleware
from agentcloak.daemon.routes import setup_routes

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


def _generate_token() -> str:
    return secrets.token_urlsafe(32)


def _write_session(
    paths: Paths,
    *,
    port: int,
    tier: StealthTier,
    profile: str | None = None,
    bridge_token: str | None = None,
) -> None:
    data: dict[str, object] = {
        "pid": os.getpid(),
        "port": port,
        "stealth_tier": tier.value,
        "profile": profile,
        "bridge_token": bridge_token,
    }
    paths.ensure_dirs()
    paths.active_session_file.write_bytes(orjson.dumps(data))
    os.chmod(str(paths.active_session_file), 0o600)


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
    except (ValueError, ProcessLookupError, PermissionError):
        _clear_pid(paths)
        _clear_session(paths)
        return False

    # Process exists — verify it's actually a agentcloak daemon via health endpoint
    import json
    import urllib.request

    try:
        session_data = json.loads(paths.active_session_file.read_text())
        host = session_data.get("host", "127.0.0.1")
        port = session_data.get("port", 9222)
        url = f"http://{host}:{port}/health"
        with urllib.request.urlopen(url, timeout=1) as resp:
            data = json.loads(resp.read())
            if data.get("ok"):
                return True  # genuinely running
    except Exception:
        pass
    # Process exists but not responding as agentcloak — stale
    _clear_pid(paths)
    _clear_session(paths)
    return False


async def start(
    *,
    host: str | None = None,
    port: int | None = None,
    headless: bool = True,
    profile: str | None = None,
    stealth: bool = False,
    humanize: bool | None = None,
) -> None:
    """Start the daemon server (blocking)."""
    paths, cfg = load_config()

    if stealth:
        logger.warning(
            "stealth_flag_deprecated",
            hint="--stealth is deprecated and will be removed in a future version; "
            "CloakBrowser is now the default backend",
        )

    actual_host = host or cfg.daemon_host
    actual_port = port or cfg.daemon_port

    if _check_stale_pid(paths):
        logger.error("daemon_already_running", pid_file=str(_pid_file(paths)))
        sys.exit(1)

    from agentcloak.core.config import resolve_tier

    resolved = resolve_tier(cfg.default_tier)
    tier = StealthTier(resolved)
    actual_headless = headless
    actual_humanize = humanize if humanize is not None else cfg.humanize
    extensions: list[str] | None = None
    xvfb_mgr: XvfbManager | None = None

    local_proxy: Any = None
    proxy_url: str | None = None

    if tier == StealthTier.CLOAK:
        extensions = [str(TURNSTILE_PATCH_DIR)]
        if not actual_headless and not os.environ.get("DISPLAY"):
            xvfb_mgr = XvfbManager(width=cfg.viewport_width, height=cfg.viewport_height)
            await xvfb_mgr.ensure_display()

        try:
            from httpcloak import LocalProxy  # pyright: ignore[reportMissingImports,reportUnknownVariableType]  # noqa: I001

            local_proxy = LocalProxy(  # pyright: ignore[reportUnknownVariableType]
                port=0, preset="chrome-146", tls_only=True
            )
            proxy_url = str(local_proxy.proxy_url)  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
            logger.info("local_proxy_started", url=proxy_url)
        except ImportError:
            logger.warning(
                "httpcloak_not_installed",
                hint="fetch requests will use plain httpx (TLS fingerprint exposed)",
            )
        except Exception as exc:
            logger.warning("local_proxy_failed", error=str(exc))

    bridge_token = _generate_token()

    _write_pid(paths)
    _write_session(
        paths,
        port=actual_port,
        tier=tier,
        profile=profile,
        bridge_token=bridge_token,
    )

    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.dev.ConsoleRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )

    idle_timeout = cfg.idle_timeout_min * 60
    app = web.Application(middlewares=[error_middleware])

    # Resolve profile directory if a profile name is specified
    profile_dir: Path | None = None
    if profile:
        profile_dir = paths.profiles_dir / profile
        profile_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        "launching_browser",
        tier=tier.value,
        headless=actual_headless,
        humanize=actual_humanize,
        profile=profile,
    )
    raw_ctx = await create_context(
        tier=tier,
        headless=actual_headless,
        viewport_width=cfg.viewport_width,
        viewport_height=cfg.viewport_height,
        profile_dir=profile_dir,
        humanize=actual_humanize,
        extensions=extensions,
        proxy_url=proxy_url,
    )

    from agentcloak.browser.secure_ctx import SecureBrowserContext

    ctx = SecureBrowserContext(raw_ctx, cfg)
    app["browser_ctx"] = ctx
    app["local_proxy"] = local_proxy
    app["bridge_token"] = bridge_token

    logger.info("bridge_token_generated", token_suffix=bridge_token[-4:])

    from agentcloak.core.discovery import register_daemon

    register_daemon(actual_port, token=bridge_token)

    from agentcloak.core.resume import ResumeWriter

    resume_writer = ResumeWriter(paths)
    app["resume_writer"] = resume_writer

    app["idle_timeout"] = idle_timeout
    import time as _time

    app["last_request_time"] = _time.monotonic()
    setup_routes(app)

    async def on_shutdown(a: web.Application) -> None:
        logger.info("shutting_down")
        from agentcloak.core.discovery import unregister_daemon

        unregister_daemon()
        with contextlib.suppress(Exception):
            await ctx.close()
        if local_proxy is not None:
            with contextlib.suppress(Exception):
                local_proxy.close()  # pyright: ignore[reportUnknownMemberType]
        if xvfb_mgr is not None:
            xvfb_mgr.cleanup()
        resume_writer.clear()
        _clear_pid(paths)
        _clear_session(paths)

    app.on_shutdown.append(on_shutdown)

    # Shutdown signal: set by handle_shutdown route or OS signals
    shutdown_event = asyncio.Event()
    app["shutdown_event"] = shutdown_event

    logger.info("daemon_starting", host=actual_host, port=actual_port)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig, lambda: asyncio.ensure_future(_graceful_shutdown(app))
        )

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, actual_host, actual_port)
    await site.start()
    logger.info("daemon_ready", host=actual_host, port=actual_port, tier=tier.value)

    resume_writer.start_background()

    if idle_timeout > 0:
        _watchdog = asyncio.ensure_future(_idle_watchdog(app, idle_timeout))
        app["_idle_watchdog"] = _watchdog

    try:
        await shutdown_event.wait()  # woken by handle_shutdown or _graceful_shutdown
    finally:
        await runner.cleanup()


async def _idle_watchdog(app: web.Application, timeout: float) -> None:
    """Shut down daemon after idle_timeout seconds of inactivity."""
    import time as _time

    while True:
        await asyncio.sleep(30)
        elapsed = _time.monotonic() - app["last_request_time"]
        if elapsed >= timeout:
            logger.info("idle_timeout_reached", seconds=int(elapsed))
            await _graceful_shutdown(app)
            return


async def _graceful_shutdown(app: web.Application) -> None:
    event: asyncio.Event | None = app.get("shutdown_event")
    if event is not None:
        event.set()
    else:
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
