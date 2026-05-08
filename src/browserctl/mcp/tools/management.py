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
          health       — daemon status, stealth tier, current URL, capture state
          cdp_endpoint — CDP WebSocket URL (for jshookmcp browser_attach)
          cookies      — export browser cookies (requires remote bridge)

        Args:
            query: What to check — health, cdp_endpoint, or cookies
            url: Filter cookies by URL (only for 'cookies' query)

        Returns:
            health: stealth_tier, current_url, current_title, capture_recording, seq.
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
