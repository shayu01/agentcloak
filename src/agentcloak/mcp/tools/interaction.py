"""Interaction tool — unified page actions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from agentcloak.mcp.client import DaemonBridge

__all__ = ["register"]

ActionKind = Literal[
    "click", "fill", "type", "scroll", "hover", "select", "press",
    "keydown", "keyup",
]


def register(mcp: FastMCP, bridge: DaemonBridge) -> None:
    @mcp.tool(annotations={"destructiveHint": False, "readOnlyHint": False})
    async def agentcloak_action(
        kind: ActionKind,
        target: str = "",
        text: str = "",
        key: str = "",
        value: str = "",
        direction: str = "down",
    ) -> str:
        """Interact with the page. Use [N] refs from agentcloak_snapshot as target.

        Actions:
          click   — click element [N]
          fill    — clear input [N] and set text (use 'text' param)
          type    — type into [N] character by character (use 'text' param)
          scroll  — scroll page (use 'direction': up/down)
          hover   — hover over element [N]
          select  — pick dropdown option [N] (use 'value' param)
          press   — press keyboard key (use 'key': Enter/Tab/Control+a)
          keydown — hold a key down (use 'key': Shift/Control/Alt)
          keyup   — release a held key (use 'key')

        Returns include proactive state feedback:
          pending_requests — count of in-flight network requests (if > 0)
          dialog — pending dialog info (if a dialog appeared)
          navigation — new URL if page navigated
          current_value — current value after fill/select

        If a dialog is blocking, returns error='blocked_by_dialog'.
        Handle it with agentcloak_dialog before retrying.

        Args:
            kind: Action type
            target: Element [N] ref from snapshot (empty for scroll/press/key*)
            text: Text for fill/type actions
            key: Key name for press/keydown/keyup (e.g. 'Enter', 'Control+a', 'Shift')
            value: Option value for select action
            direction: Scroll direction — 'up' or 'down'

        Returns:
            JSON with action result, seq number, and state feedback fields.
        """
        body: dict[str, Any] = {"kind": kind, "target": target}
        if kind in ("fill", "type") and text:
            body["text"] = text
        if kind in ("press", "keydown", "keyup") and key:
            body["key"] = key
        if kind == "select" and value:
            body["value"] = value
        if kind == "scroll":
            body["direction"] = direction
        result = await bridge.request("POST", "/action", json_body=body)
        return bridge.format_result(result)
