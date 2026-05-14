"""Frame tool — frame listing and switching."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from agentcloak.mcp.client import DaemonBridge

__all__ = ["register"]


def register(mcp: FastMCP, bridge: DaemonBridge) -> None:
    @mcp.tool(annotations={"readOnlyHint": False})
    async def agentcloak_frame(
        kind: Literal["list", "focus"] = "list",
        name: str = "",
        url: str = "",
        main: bool = False,
    ) -> str:
        """List or switch between page frames (iframes).

        After switching frames, actions and snapshots operate within
        the focused frame. Use kind='focus' with main=True to return
        to the main frame.

        Args:
            kind: 'list' to show all frames, 'focus' to switch
            name: Frame name to switch to (for focus)
            url: URL substring to match frame (for focus)
            main: Switch back to main frame (for focus)

        Returns:
            JSON with frame list or focus confirmation.
        """
        if kind == "list":
            result = await bridge.request("GET", "/frame/list")
        else:
            body: dict[str, Any] = {"main": main}
            if name:
                body["name"] = name
            if url:
                body["url"] = url
            result = await bridge.request("POST", "/frame/focus", json_body=body)
        return bridge.format_result(result)
