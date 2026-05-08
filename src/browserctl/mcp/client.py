"""HTTP client for MCP server to communicate with the daemon."""

from __future__ import annotations

import json
from typing import Any

import httpx

from browserctl.core.config import load_config

__all__ = ["DaemonBridge"]


class DaemonBridge:
    """Stateless HTTP bridge to the browserctl daemon."""

    def __init__(self) -> None:
        _, cfg = load_config()
        self._base = f"http://{cfg.daemon_host}:{cfg.daemon_port}"

    async def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(
            base_url=self._base, timeout=120.0
        ) as client:
            kwargs: dict[str, Any] = {}
            if json_body is not None:
                kwargs["json"] = json_body
            if params:
                kwargs["params"] = params

            resp = await client.request(method, path, **kwargs)
            data: dict[str, Any] = resp.json()
            return data

    def _format_result(self, data: dict[str, Any]) -> str:
        if not data.get("ok"):
            error = data.get("error", "unknown_error")
            hint = data.get("hint", "")
            action = data.get("action", "")
            return json.dumps(
                {"error": error, "hint": hint, "action": action}
            )
        return json.dumps(data.get("data", data))
