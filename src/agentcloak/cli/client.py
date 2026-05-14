"""HTTP client for communicating with the daemon."""

from __future__ import annotations

import asyncio
import subprocess
import sys
import time
from typing import Any

import aiohttp
import orjson
import structlog

from agentcloak.core.config import load_config
from agentcloak.core.errors import AgentBrowserError, DaemonConnectionError

__all__ = ["DaemonClient"]

logger = structlog.get_logger()

_MAX_STARTUP_WAIT = 15.0
_POLL_INTERVAL = 0.5


class DaemonClient:
    """HTTP client wrapping daemon API calls with transparent auto-start."""

    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        auto_start: bool = True,
    ) -> None:
        _, cfg = load_config()
        self._host = host or cfg.daemon_host
        self._port = port or cfg.daemon_port
        self._base = f"http://{self._host}:{self._port}"
        self._auto_start = auto_start
        self._auto_started = False

    async def _ensure_daemon(self) -> bool:
        """Start daemon in background and wait for it to be ready."""
        if self._auto_started:
            return False

        t0 = time.monotonic()
        logger.warning(
            "daemon_auto_starting",
            host=self._host,
            port=self._port,
        )

        cmd = [sys.executable, "-m", "agentcloak.daemon"]
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
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{self._base}/health",
                        timeout=aiohttp.ClientTimeout(total=2),
                    ) as resp:
                        if resp.status == 200:
                            total = time.monotonic() - t0
                            logger.warning(
                                "daemon_auto_started",
                                elapsed_s=round(total, 1),
                                outcome="success",
                            )
                            return True
            except aiohttp.ClientConnectorError:
                continue

        total = time.monotonic() - t0
        logger.warning(
            "daemon_auto_start_failed",
            elapsed_s=round(total, 1),
            outcome="timeout",
        )
        return False

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url = f"{self._base}{path}"
        try:
            return await self._do_request(
                method, url, json_body=json_body, params=params
            )
        except aiohttp.ClientConnectorError as exc:
            if not self._auto_start:
                raise DaemonConnectionError(
                    error="daemon_unreachable",
                    hint=(f"Cannot connect to daemon at {self._host}:{self._port}"),
                    action="run 'agentcloak daemon start' first",
                ) from exc

            started = await self._ensure_daemon()
            if not started:
                raise DaemonConnectionError(
                    error="daemon_auto_start_failed",
                    hint=(
                        f"Cannot connect to daemon"
                        f" at {self._host}:{self._port}"
                        " and auto-start failed"
                    ),
                    action=("start daemon manually: agentcloak daemon start -b"),
                ) from exc

            try:
                return await self._do_request(
                    method,
                    url,
                    json_body=json_body,
                    params=params,
                )
            except aiohttp.ClientConnectorError as retry_exc:
                raise DaemonConnectionError(
                    error="daemon_unreachable",
                    hint=(
                        "Daemon started but still"
                        f" unreachable at"
                        f" {self._host}:{self._port}"
                    ),
                    action=("check daemon logs for startup errors"),
                ) from retry_exc

    async def _do_request(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Execute a single HTTP request to the daemon."""
        try:
            async with aiohttp.ClientSession() as session:
                kwargs: dict[str, Any] = {"timeout": aiohttp.ClientTimeout(total=120)}
                if json_body is not None:
                    kwargs["data"] = orjson.dumps(json_body)
                    kwargs["headers"] = {"Content-Type": "application/json"}
                if params:
                    kwargs["params"] = params

                async with session.request(method, url, **kwargs) as resp:
                    raw = await resp.read()
                    data: dict[str, Any] = orjson.loads(raw)

                    if not data.get("ok") and "error" in data:
                        raise AgentBrowserError(
                            error=data["error"],
                            hint=data.get("hint", ""),
                            action=data.get("action", ""),
                        )
                    return data
        except AgentBrowserError:
            raise
        except aiohttp.ClientConnectorError:
            raise
        except Exception as exc:
            raise DaemonConnectionError(
                error="daemon_request_failed",
                hint=str(exc),
                action="check daemon status with 'agentcloak daemon health'",
            ) from exc

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/health")

    async def navigate(self, url: str, *, timeout: float = 30.0) -> dict[str, Any]:
        return await self._request(
            "POST", "/navigate", json_body={"url": url, "timeout": timeout}
        )

    async def screenshot(
        self,
        *,
        full_page: bool = False,
        format: str = "jpeg",
        quality: int = 80,
    ) -> dict[str, Any]:
        params: dict[str, str] = {"format": format, "quality": str(quality)}
        if full_page:
            params["full_page"] = "true"
        return await self._request("GET", "/screenshot", params=params)

    async def snapshot(
        self,
        *,
        mode: str = "accessible",
        max_chars: int = 0,
        max_nodes: int = 0,
        focus: int = 0,
        offset: int = 0,
        frames: bool = False,
        diff: bool = False,
    ) -> dict[str, Any]:
        params: dict[str, str] = {"mode": mode}
        if max_chars:
            params["max_chars"] = str(max_chars)
        if max_nodes:
            params["max_nodes"] = str(max_nodes)
        if focus:
            params["focus"] = str(focus)
        if offset:
            params["offset"] = str(offset)
        if frames:
            params["frames"] = "true"
        if diff:
            params["diff"] = "true"
        return await self._request("GET", "/snapshot", params=params)

    async def state(self) -> dict[str, Any]:
        return await self._request("GET", "/state")

    async def evaluate(self, js: str, *, world: str = "main") -> dict[str, Any]:
        return await self._request(
            "POST", "/evaluate", json_body={"js": js, "world": world}
        )

    async def network(self, *, since: int = 0) -> dict[str, Any]:
        return await self._request("GET", "/network", params={"since": str(since)})

    async def action(
        self,
        kind: str,
        *,
        index: int | None = None,
        target: str | None = None,
        include_snapshot: bool = False,
        snapshot_mode: str = "compact",
        **kwargs: Any,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"kind": kind}
        if index is not None:
            body["index"] = index
        if target is not None:
            body["target"] = target
        if include_snapshot:
            body["include_snapshot"] = True
            body["snapshot_mode"] = snapshot_mode
        body.update(kwargs)
        return await self._request("POST", "/action", json_body=body)

    async def action_batch(
        self,
        actions: list[dict[str, Any]],
        *,
        sleep: float = 0.0,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/action/batch",
            json_body={"actions": actions, "sleep": sleep},
        )

    async def fetch(
        self,
        url: str,
        *,
        method: str = "GET",
        body: str | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        json_body: dict[str, Any] = {"url": url, "method": method, "timeout": timeout}
        if body is not None:
            json_body["body"] = body
        if headers is not None:
            json_body["headers"] = headers
        return await self._request("POST", "/fetch", json_body=json_body)

    async def shutdown(self) -> dict[str, Any]:
        try:
            return await self._request("POST", "/shutdown")
        except Exception:
            return {"ok": True}

    async def capture_start(self) -> dict[str, Any]:
        return await self._request("POST", "/capture/start")

    async def capture_stop(self) -> dict[str, Any]:
        return await self._request("POST", "/capture/stop")

    async def capture_status(self) -> dict[str, Any]:
        return await self._request("GET", "/capture/status")

    async def capture_export(self, *, fmt: str = "har") -> dict[str, Any]:
        return await self._request("GET", "/capture/export", params={"format": fmt})

    async def capture_analyze(self, *, domain: str = "") -> dict[str, Any]:
        params: dict[str, str] = {}
        if domain:
            params["domain"] = domain
        return await self._request("GET", "/capture/analyze", params=params)

    async def capture_clear(self) -> dict[str, Any]:
        return await self._request("POST", "/capture/clear")

    async def capture_replay(self, *, url: str, method: str = "GET") -> dict[str, Any]:
        return await self._request(
            "POST", "/capture/replay", json_body={"url": url, "method": method}
        )

    async def profile_create_from_current(self, *, name: str) -> dict[str, Any]:
        return await self._request(
            "POST", "/profile/create-from-current", json_body={"name": name}
        )

    async def cdp_endpoint(self) -> dict[str, Any]:
        return await self._request("GET", "/cdp/endpoint")

    async def tab_list(self) -> dict[str, Any]:
        return await self._request("GET", "/tabs")

    async def tab_new(self, *, url: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if url:
            body["url"] = url
        return await self._request("POST", "/tab/new", json_body=body)

    async def tab_close(self, tab_id: int) -> dict[str, Any]:
        return await self._request("POST", "/tab/close", json_body={"tab_id": tab_id})

    async def tab_switch(self, tab_id: int) -> dict[str, Any]:
        return await self._request("POST", "/tab/switch", json_body={"tab_id": tab_id})

    async def resume(self) -> dict[str, Any]:
        return await self._request("GET", "/resume")

    async def cookies_export(self, *, url: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if url:
            body["url"] = url
        return await self._request("POST", "/cookies/export", json_body=body)

    # Phase 5g: dialog, wait, upload, frame

    async def dialog_status(self) -> dict[str, Any]:
        return await self._request("GET", "/dialog/status")

    async def dialog_handle(
        self, action_type: str, *, text: str | None = None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"action": action_type}
        if text is not None:
            body["text"] = text
        return await self._request("POST", "/dialog/handle", json_body=body)

    async def wait(
        self,
        *,
        condition: str,
        value: str = "",
        timeout: int = 30000,
        state: str = "visible",
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "condition": condition,
            "value": value,
            "timeout": timeout,
            "state": state,
        }
        return await self._request("POST", "/wait", json_body=body)

    async def upload(self, *, index: int, files: list[str]) -> dict[str, Any]:
        return await self._request(
            "POST", "/upload", json_body={"index": index, "files": files}
        )

    async def frame_list(self) -> dict[str, Any]:
        return await self._request("GET", "/frame/list")

    async def frame_focus(
        self,
        *,
        name: str | None = None,
        url: str | None = None,
        main: bool = False,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"main": main}
        if name is not None:
            body["name"] = name
        if url is not None:
            body["url"] = url
        return await self._request("POST", "/frame/focus", json_body=body)
