"""HTTP client for communicating with the daemon."""

from __future__ import annotations

from typing import Any

import aiohttp
import orjson

from browserctl.core.config import load_config
from browserctl.core.errors import AgentBrowserError, DaemonConnectionError

__all__ = ["DaemonClient"]


class DaemonClient:
    """Thin HTTP client wrapping daemon API calls."""

    def __init__(self, *, host: str | None = None, port: int | None = None) -> None:
        _, cfg = load_config()
        self._host = host or cfg.daemon_host
        self._port = port or cfg.daemon_port
        self._base = f"http://{self._host}:{self._port}"

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
        except aiohttp.ClientConnectorError as exc:
            raise DaemonConnectionError(
                error="daemon_unreachable",
                hint=f"Cannot connect to daemon at {self._host}:{self._port}",
                action="run 'browserctl daemon start' first",
            ) from exc
        except Exception as exc:
            raise DaemonConnectionError(
                error="daemon_request_failed",
                hint=str(exc),
                action="check daemon status with 'browserctl daemon health'",
            ) from exc

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/health")

    async def navigate(self, url: str, *, timeout: float = 30.0) -> dict[str, Any]:
        return await self._request(
            "POST", "/navigate", json_body={"url": url, "timeout": timeout}
        )

    async def screenshot(self, *, full_page: bool = False) -> dict[str, Any]:
        params = {"full_page": "true"} if full_page else {}
        return await self._request("GET", "/screenshot", params=params)

    async def snapshot(self, *, mode: str = "accessible") -> dict[str, Any]:
        return await self._request("GET", "/snapshot", params={"mode": mode})

    async def state(self) -> dict[str, Any]:
        return await self._request("GET", "/state")

    async def evaluate(self, js: str) -> dict[str, Any]:
        return await self._request("POST", "/evaluate", json_body={"js": js})

    async def network(self, *, since: int = 0) -> dict[str, Any]:
        return await self._request("GET", "/network", params={"since": str(since)})

    async def action(
        self,
        kind: str,
        *,
        index: int | None = None,
        target: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"kind": kind}
        if index is not None:
            body["index"] = index
        if target is not None:
            body["target"] = target
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
