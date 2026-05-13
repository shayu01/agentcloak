"""Interaction tool — unified page actions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from browserctl.mcp.client import DaemonBridge

__all__ = ["register"]

ActionKind = Literal[
    "click", "fill", "type", "scroll", "hover", "select", "press"
]


def register(mcp: FastMCP, bridge: DaemonBridge) -> None:
    @mcp.tool(annotations={"destructiveHint": False, "readOnlyHint": False})
    async def browserctl_action(
        kind: ActionKind,
        target: str = "",
        text: str = "",
        key: str = "",
        value: str = "",
        direction: str = "down",
    ) -> str:
        """Interact with the page. Use [N] refs from browserctl_snapshot as target.

        Actions:
          click  — click element [N]
          fill   — clear input [N] and set text (use 'text' param)
          type   — type into [N] character by character (use 'text' param)
          scroll — scroll page (use 'direction': up/down)
          hover  — hover over element [N]
          select — pick dropdown option [N] (use 'value' param)
          press  — press keyboard key (use 'key': Enter/Tab/Escape/ArrowDown)

        Args:
            kind: Action type — click, fill, type, scroll, hover, select, press
            target: Element [N] reference from snapshot (empty for scroll/press)
            text: Text for fill/type actions
            key: Key name for press action (e.g. 'Enter', 'Tab')
            value: Option value for select action
            direction: Scroll direction — 'up' or 'down'

        Returns:
            JSON with action result and updated seq number.
            Call browserctl_snapshot after to see the new page state.
        """
        body: dict[str, Any] = {"kind": kind, "target": target}
        if kind in ("fill", "type") and text:
            body["text"] = text
        if kind == "press" and key:
            body["key"] = key
        if kind == "select" and value:
            body["value"] = value
        if kind == "scroll":
            body["direction"] = direction
        result = await bridge.request("POST", "/action", json_body=body)
        return bridge.format_result(result)
