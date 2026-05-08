"""Management tools — health, cookies, CDP endpoint."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from browserctl.mcp.client import DaemonBridge

__all__ = ["register"]


def register(mcp: FastMCP, bridge: DaemonBridge) -> None:
    @mcp.tool()
    async def browserctl_health() -> str:
        """Check daemon health and connection status."""
        result = await bridge.request("GET", "/health")
        return bridge._format_result(result)

    @mcp.tool()
    async def browserctl_cookies_export(url: str = "") -> str:
        """Export cookies from the browser (requires remote bridge).

        Args:
            url: Filter cookies by URL (optional)
        """
        json_body: dict[str, str] = {}
        if url:
            json_body["url"] = url
        result = await bridge.request(
            "POST", "/cookies/export", json_body=json_body
        )
        return bridge._format_result(result)

    @mcp.tool()
    async def browserctl_cdp_endpoint() -> str:
        """Get the CDP WebSocket URL for the current browser.

        Use this to share the browser session with jshookmcp
        via browser_attach(wsEndpoint=<returned URL>).
        """
        result = await bridge.request("GET", "/cdp/endpoint")
        return bridge._format_result(result)
