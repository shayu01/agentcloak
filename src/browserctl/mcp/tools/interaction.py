"""Interaction tools — click, fill, type, scroll, hover, select, press."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from browserctl.mcp.client import DaemonBridge

__all__ = ["register"]


def register(mcp: FastMCP, bridge: DaemonBridge) -> None:
    async def _action(kind: str, target: str, **extra: Any) -> str:
        body: dict[str, Any] = {"kind": kind, "target": target}
        body.update(extra)
        result = await bridge.request("POST", "/action", json_body=body)
        return bridge._format_result(result)

    @mcp.tool()
    async def browserctl_click(target: str) -> str:
        """Click an element by its [N] reference from the accessibility tree.

        Args:
            target: Element reference number from snapshot (e.g. '5' for [5])
        """
        return await _action("click", target)

    @mcp.tool()
    async def browserctl_fill(target: str, text: str) -> str:
        """Clear an input field and fill it with new text.

        Args:
            target: Element [N] reference from snapshot
            text: Text to fill in
        """
        return await _action("fill", target, text=text)

    @mcp.tool()
    async def browserctl_type(target: str, text: str) -> str:
        """Type text into an element character by character.

        Args:
            target: Element [N] reference from snapshot
            text: Text to type
        """
        return await _action("type", target, text=text)

    @mcp.tool()
    async def browserctl_scroll(direction: str = "down") -> str:
        """Scroll the page.

        Args:
            direction: Scroll direction — 'up' or 'down'
        """
        return await _action("scroll", "", direction=direction)

    @mcp.tool()
    async def browserctl_hover(target: str) -> str:
        """Hover over an element.

        Args:
            target: Element [N] reference from snapshot
        """
        return await _action("hover", target)

    @mcp.tool()
    async def browserctl_select(target: str, value: str) -> str:
        """Select an option from a dropdown.

        Args:
            target: Element [N] reference from snapshot
            value: Option value to select
        """
        return await _action("select", target, value=value)

    @mcp.tool()
    async def browserctl_press(key: str) -> str:
        """Press a keyboard key.

        Args:
            key: Key name (e.g. 'Enter', 'Tab', 'Escape', 'ArrowDown')
        """
        return await _action("press", "", key=key)

    @mcp.tool()
    async def browserctl_batch_actions(
        actions_json: str, sleep: float = 0.0
    ) -> str:
        """Execute multiple actions in sequence.

        Args:
            actions_json: JSON array of action objects, each with 'kind' and 'target'
            sleep: Seconds to wait between actions
        """
        actions: list[dict[str, Any]] = json.loads(actions_json)
        result = await bridge.request(
            "POST",
            "/action/batch",
            json_body={"actions": actions, "sleep": sleep},
        )
        return bridge._format_result(result)
