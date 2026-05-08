"""Network tools — request monitoring."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from browserctl.mcp.client import DaemonBridge

__all__ = ["register"]


def register(mcp: FastMCP, bridge: DaemonBridge) -> None:
    @mcp.tool()
    async def browserctl_network(since: str = "0") -> str:
        """List captured network requests.

        Args:
            since: Filter requests after this seq number (or 'last_action')
        """
        result = await bridge.request(
            "GET", "/network", params={"since": since}
        )
        return bridge._format_result(result)
