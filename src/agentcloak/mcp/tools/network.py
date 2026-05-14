"""Network tool — request monitoring."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from agentcloak.mcp.client import DaemonBridge

__all__ = ["register"]


def register(mcp: FastMCP, bridge: DaemonBridge) -> None:
    @mcp.tool(annotations={"readOnlyHint": True})
    async def agentcloak_network(since: str = "0") -> str:
        """List captured network requests since a given seq number.

        Use since='last_action' to see requests triggered by the most recent
        action (click, navigate, etc.).

        Args:
            since: Seq number to filter from, or 'last_action' for latest

        Returns:
            JSON with requests array (method, url, status, resource_type) and count.
        """
        result = await bridge.request("GET", "/network", params={"since": since})
        return bridge.format_result(result)
