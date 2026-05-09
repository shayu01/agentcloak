"""Capture tools — traffic recording (write) and querying (read)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from browserctl.mcp.client import DaemonBridge

__all__ = ["register"]


def register(mcp: FastMCP, bridge: DaemonBridge) -> None:
    @mcp.tool(annotations={"destructiveHint": False, "readOnlyHint": False})
    async def browserctl_capture_control(
        action: Literal["start", "stop", "clear", "replay"],
        url: str = "",
        method: str = "GET",
    ) -> str:
        """Control network traffic recording for API analysis.

        Actions:
          start  — begin recording all network requests
          stop   — pause recording (data preserved)
          clear  — delete all captured data
          replay — replay the most recent captured request matching url+method

        Args:
            action: Recording control — start, stop, clear, or replay
            url: Request URL to replay (required for 'replay' action)
            method: HTTP method for replay (default GET)

        Returns:
            JSON with recording status and entry count, or replay response.
        """
        if action == "clear":
            result = await bridge.request("POST", "/capture/clear")
        elif action == "stop":
            result = await bridge.request("POST", "/capture/stop")
        elif action == "replay":
            result = await bridge.request(
                "POST", "/capture/replay", json_body={"url": url, "method": method}
            )
        else:
            result = await bridge.request("POST", "/capture/start")
        return bridge._format_result(result)

    @mcp.tool(annotations={"readOnlyHint": True})
    async def browserctl_capture_query(
        action: Literal["status", "export", "analyze"] = "status",
        format: str = "har",
        domain: str = "",
    ) -> str:
        """Query captured traffic data.

        Actions:
          status  — check if recording is active and entry count
          export  — export captured data as HAR 1.2 or JSON
          analyze — detect API endpoint patterns from traffic

        Args:
            action: Query type — status, export, or analyze
            format: Export format for 'export' action — 'har' or 'json'
            domain: Filter by domain for 'analyze' action

        Returns:
            status: recording state + entry count.
            export: HAR 1.2 JSON or raw entry list.
            analyze: detected API patterns with method, path, auth, schema.
        """
        if action == "export":
            result = await bridge.request(
                "GET", "/capture/export", params={"format": format}
            )
        elif action == "analyze":
            params: dict[str, str] = {}
            if domain:
                params["domain"] = domain
            result = await bridge.request(
                "GET", "/capture/analyze", params=params
            )
        else:
            result = await bridge.request("GET", "/capture/status")
        return bridge._format_result(result)
