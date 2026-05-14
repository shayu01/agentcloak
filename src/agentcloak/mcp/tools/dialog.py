"""Dialog tool — handle browser dialogs (alert, confirm, prompt)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from agentcloak.mcp.client import DaemonBridge

__all__ = ["register"]


def register(mcp: FastMCP, bridge: DaemonBridge) -> None:
    @mcp.tool(annotations={"readOnlyHint": False})
    async def agentcloak_dialog(
        kind: Literal["status", "accept", "dismiss"] = "status",
        text: str = "",
    ) -> str:
        """Handle browser dialogs (alert, confirm, prompt).

        alert/beforeunload dialogs are auto-accepted. confirm/prompt
        dialogs are held as pending until you call accept or dismiss.

        When a dialog is pending, all other actions return
        'blocked_by_dialog' — handle the dialog first.

        Args:
            kind: 'status' to check, 'accept' to confirm, 'dismiss' to cancel
            text: Reply text for prompt dialogs (only used with accept)

        Returns:
            JSON with dialog info (type, message) or handled status.
        """
        if kind == "status":
            result = await bridge.request("GET", "/dialog/status")
        else:
            body = {"action": kind}
            if text and kind == "accept":
                body["text"] = text
            result = await bridge.request("POST", "/dialog/handle", json_body=body)
        return bridge.format_result(result)
