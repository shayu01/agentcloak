"""Capture tools — record, export, and analyze traffic."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from browserctl.mcp.client import DaemonBridge

__all__ = ["register"]


def register(mcp: FastMCP, bridge: DaemonBridge) -> None:
    @mcp.tool()
    async def browserctl_capture_start() -> str:
        """Start recording network traffic for API analysis."""
        result = await bridge.request("POST", "/capture/start")
        return bridge._format_result(result)

    @mcp.tool()
    async def browserctl_capture_stop() -> str:
        """Stop recording network traffic."""
        result = await bridge.request("POST", "/capture/stop")
        return bridge._format_result(result)

    @mcp.tool()
    async def browserctl_capture_status() -> str:
        """Check if traffic recording is active and entry count."""
        result = await bridge.request("GET", "/capture/status")
        return bridge._format_result(result)

    @mcp.tool()
    async def browserctl_capture_export(format: str = "har") -> str:
        """Export captured traffic as HAR or JSON.

        Args:
            format: Export format — 'har' (standard HAR 1.2) or 'json'
        """
        result = await bridge.request(
            "GET", "/capture/export", params={"format": format}
        )
        return bridge._format_result(result)

    @mcp.tool()
    async def browserctl_capture_analyze(domain: str = "") -> str:
        """Analyze captured traffic for API endpoint patterns.

        Args:
            domain: Filter analysis to a specific domain (optional)
        """
        params: dict[str, str] = {}
        if domain:
            params["domain"] = domain
        result = await bridge.request(
            "GET", "/capture/analyze", params=params
        )
        return bridge._format_result(result)
