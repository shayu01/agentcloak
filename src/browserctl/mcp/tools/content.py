"""Content tools — evaluate JS, fetch with cookies."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from browserctl.mcp.client import DaemonBridge

__all__ = ["register"]


def register(mcp: FastMCP, bridge: DaemonBridge) -> None:
    @mcp.tool()
    async def browserctl_evaluate(js: str) -> str:
        """Execute JavaScript in the browser page context.

        Args:
            js: JavaScript code to evaluate
        """
        result = await bridge.request(
            "POST", "/evaluate", json_body={"js": js}
        )
        return bridge._format_result(result)

    @mcp.tool()
    async def browserctl_fetch(
        url: str,
        method: str = "GET",
        body: str | None = None,
        headers_json: str | None = None,
        timeout: float = 30.0,
    ) -> str:
        """HTTP fetch using the browser's cookies and user agent.

        Args:
            url: Request URL
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            body: Request body for POST/PUT
            headers_json: JSON object of extra headers
            timeout: Request timeout in seconds
        """
        json_body: dict[str, object] = {
            "url": url,
            "method": method,
            "timeout": timeout,
        }
        if body is not None:
            json_body["body"] = body
        if headers_json is not None:
            json_body["headers"] = json.loads(headers_json)
        result = await bridge.request(
            "POST", "/fetch", json_body=json_body
        )
        return bridge._format_result(result)
