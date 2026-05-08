"""Management tool — health, CDP endpoint, cookies."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from browserctl.mcp.client import DaemonBridge

__all__ = ["register"]


def register(mcp: FastMCP, bridge: DaemonBridge) -> None:
    @mcp.tool(annotations={"readOnlyHint": True})
    async def browserctl_status(
        query: Literal[
            "health", "cdp_endpoint", "cookies"
        ] = "health",
        url: str = "",
    ) -> str:
        """Query daemon and browser status.

        Queries:
          health       — check daemon connection and proxy status
          cdp_endpoint — get CDP WebSocket URL (for jshookmcp browser_attach)
          cookies      — export browser cookies (requires remote bridge)

        Args:
            query: What to check — health, cdp_endpoint, or cookies
            url: Filter cookies by URL (only for 'cookies' query)

        Returns:
            health: daemon status.
            cdp_endpoint: ws_endpoint URL for CDP tools.
            cookies: list of browser cookies.
        """
        if query == "cdp_endpoint":
            result = await bridge.request("GET", "/cdp/endpoint")
        elif query == "cookies":
            json_body: dict[str, str] = {}
            if url:
                json_body["url"] = url
            result = await bridge.request(
                "POST", "/cookies/export", json_body=json_body
            )
        else:
            result = await bridge.request("GET", "/health")
        return bridge._format_result(result)
