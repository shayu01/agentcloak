"""HTTP client for MCP server to communicate with the daemon."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from typing import Any

import httpx
import structlog

from agentcloak.core.config import load_config

__all__ = ["DaemonBridge"]

logger = structlog.get_logger()

_MAX_STARTUP_WAIT = 15.0
_POLL_INTERVAL = 0.5


class DaemonBridge:
    """Stateless HTTP bridge to the agentcloak daemon with auto-start."""

    def __init__(self) -> None:
        _, cfg = load_config()
        self._host = cfg.daemon_host
        self._port = cfg.daemon_port
        self._base = f"http://{self._host}:{self._port}"
        self._auto_started = False

    async def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        try:
            return await self._do_request(
                method, path, json_body=json_body, params=params
            )
        except httpx.ConnectError:
            if self._auto_started:
                return {
                    "ok": False,
                    "error": "daemon_unreachable",
                    "hint": f"Cannot connect to daemon at {self._host}:{self._port}",
                    "action": "use agentcloak_launch to start the daemon",
                }
            started = await self._auto_start_daemon()
            if not started:
                return {
                    "ok": False,
                    "error": "daemon_auto_start_failed",
                    "hint": "Failed to auto-start daemon",
                    "action": "start daemon manually: agentcloak daemon start -b",
                }
            return await self._do_request(
                method, path, json_body=json_body, params=params
            )
        except httpx.HTTPError as exc:
            return {
                "ok": False,
                "error": "daemon_request_failed",
                "hint": f"HTTP request to daemon failed: {exc}",
                "action": "check daemon status with agentcloak_status or restart",
            }

    async def _do_request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=self._base, timeout=120.0) as client:
            kwargs: dict[str, Any] = {}
            if json_body is not None:
                kwargs["json"] = json_body
            if params:
                kwargs["params"] = params
            resp = await client.request(method, path, **kwargs)
            data: dict[str, Any] = resp.json()
            return data

    async def _auto_start_daemon(
        self,
        *,
        headless: bool = True,
        stealth: bool = False,
        profile: str | None = None,
    ) -> bool:
        """Start daemon in background and wait for it to be ready."""
        logger.warning(
            "daemon_auto_starting",
            host=self._host,
            port=self._port,
        )

        cmd = [sys.executable, "-m", "agentcloak.daemon"]
        if not headless:
            cmd.append("--headed")
        if stealth:
            cmd.append("--stealth")
        if profile:
            cmd.extend(["--profile", profile])

        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        self._auto_started = True

        elapsed = 0.0
        while elapsed < _MAX_STARTUP_WAIT:
            await asyncio.sleep(_POLL_INTERVAL)
            elapsed += _POLL_INTERVAL
            try:
                async with httpx.AsyncClient(
                    base_url=self._base, timeout=2.0
                ) as client:
                    resp = await client.get("/health")
                    if resp.status_code == 200:
                        logger.warning(
                            "daemon_auto_started",
                            elapsed_s=round(elapsed, 1),
                            outcome="success",
                        )
                        return True
            except httpx.ConnectError:
                continue

        logger.warning(
            "daemon_auto_start_failed",
            elapsed_s=round(elapsed, 1),
            outcome="timeout",
        )
        return False

    async def launch_daemon(
        self,
        *,
        headless: bool = True,
        stealth: bool = False,
        profile: str = "",
    ) -> dict[str, Any]:
        """Explicitly launch daemon with specified options."""
        try:
            async with httpx.AsyncClient(base_url=self._base, timeout=2.0) as client:
                resp = await client.get("/health")
                if resp.status_code == 200:
                    await self._stop_daemon()
                    await asyncio.sleep(1.0)
        except httpx.ConnectError:
            pass

        self._auto_started = False
        ok = await self._auto_start_daemon(
            headless=headless,
            stealth=stealth,
            profile=profile or None,
        )
        if not ok:
            return {
                "ok": False,
                "error": "daemon_launch_failed",
                "hint": "Daemon failed to start within timeout",
                "action": "check logs or start manually",
            }
        health = await self._do_request("GET", "/health")
        return {"ok": True, "data": health}

    async def _stop_daemon(self) -> None:
        try:
            async with httpx.AsyncClient(base_url=self._base, timeout=5.0) as client:
                await client.post("/shutdown")
        except Exception:
            pass

    def format_result(self, data: dict[str, Any]) -> str:
        if not data.get("ok"):
            error = data.get("error", "unknown_error")
            hint = data.get("hint", "")
            action = data.get("action", "")
            return json.dumps({"error": error, "hint": hint, "action": action})
        return json.dumps(data.get("data", data))
