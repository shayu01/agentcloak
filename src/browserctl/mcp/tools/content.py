"""Content tools — evaluate JS, fetch with cookies."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from browserctl.mcp.client import DaemonBridge

__all__ = ["register"]


def register(mcp: FastMCP, bridge: DaemonBridge) -> None:
    @mcp.tool(annotations={"destructiveHint": False, "readOnlyHint": False})
    async def browserctl_evaluate(
        js: str,
        world: str = "main",
        max_return_size: int = 50_000,
    ) -> str:
        """Execute JavaScript in the browser page context. Can modify page state.

        By default runs in the page's main world, so page globals (jQuery, Vue,
        React, etc.) are accessible. Use world='utility' for an isolated context.

        Note: if evaluate triggers async requests (AJAX/fetch), those requests
        are captured asynchronously. Use browserctl_network or capture tools
        to inspect them after a short delay.

        Args:
            js: JavaScript code to evaluate (runs in page context with full DOM access)
            world: Execution context — 'main' (page globals visible)
                or 'utility' (isolated)
            max_return_size: Max bytes of serialized result to return (default 50000).
                Large objects are truncated with a [truncated] marker.

        Returns:
            JSON with the evaluation result. Complex objects are serialized.
        """
        result = await bridge.request(
            "POST", "/evaluate", json_body={"js": js, "world": world, "max_return_size": max_return_size}
        )
        data = result.get("data", result)
        # Auto-unwrap: if JS returned a JSON.stringify() string, parse it so agent
        # receives the object directly instead of a double-encoded string.
        actual = data.get("result")
        if isinstance(actual, str) and len(actual) > 1 and actual[0] in ("{", "["):
            try:
                data = {**data, "result": json.loads(actual)}
            except (json.JSONDecodeError, ValueError):
                pass
        return json.dumps(data)

    @mcp.tool(annotations={"readOnlyHint": True})
    async def browserctl_fetch(
        url: str,
        method: str = "GET",
        body: str | None = None,
        headers_json: str | None = None,
        timeout: float = 30.0,
    ) -> str:
        """HTTP fetch using the browser's cookies and user agent.

        Makes a request as if the browser sent it — same cookies, same UA.
        For APIs that require browser authentication without full page interaction.

        Args:
            url: Request URL
            method: HTTP method (GET, POST, PUT, DELETE)
            body: Request body for POST/PUT
            headers_json: Extra headers as JSON object (e.g. '{"X-Custom": "value"}')
            timeout: Request timeout in seconds

        Returns:
            JSON with status, headers, and response body text.
        """
        json_body: dict[str, object] = {
            "url": url,
            "method": method,
            "timeout": timeout,
        }
        if body is not None:
            json_body["body"] = body
        if headers_json is not None:
            if isinstance(headers_json, str):
                json_body["headers"] = json.loads(headers_json)
            else:
                json_body["headers"] = headers_json
        result = await bridge.request("POST", "/fetch", json_body=json_body)
        return bridge._format_result(result)
