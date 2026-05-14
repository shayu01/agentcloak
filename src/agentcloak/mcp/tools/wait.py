"""Wait tool — conditional waiting."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from agentcloak.mcp.client import DaemonBridge

__all__ = ["register"]


def register(mcp: FastMCP, bridge: DaemonBridge) -> None:
    @mcp.tool(annotations={"readOnlyHint": True})
    async def agentcloak_wait(
        condition: Literal["selector", "url", "load", "js", "ms"],
        value: str = "",
        timeout: int = 30000,
        state: str = "visible",
    ) -> str:
        """Wait for a condition before continuing.

        Args:
            condition: What to wait for:
                - selector: CSS selector to appear (use 'state' for visibility)
                - url: URL pattern (glob, e.g. '**/dashboard')
                - load: Page load state (load, domcontentloaded, networkidle)
                - js: JS expression that must return truthy
                - ms: Sleep for N milliseconds
            value: The selector/url/state/expression/milliseconds value
            timeout: Max wait time in milliseconds (default 30000)
            state: Element state for selector condition:
                visible (default), hidden, attached, detached

        Returns:
            JSON with condition matched and elapsed_ms.
        """
        body = {
            "condition": condition,
            "value": value,
            "timeout": timeout,
            "state": state,
        }
        result = await bridge.request("POST", "/wait", json_body=body)
        return bridge.format_result(result)
