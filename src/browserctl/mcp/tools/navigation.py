"""Navigation tools — navigate, screenshot, snapshot."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from browserctl.mcp.client import DaemonBridge

__all__ = ["register"]


def register(mcp: FastMCP, bridge: DaemonBridge) -> None:
    @mcp.tool(annotations={"destructiveHint": False, "readOnlyHint": False})
    async def browserctl_navigate(
        url: str, timeout: float = 30.0
    ) -> str:
        """Navigate the browser to a URL. Changes page state.

        Args:
            url: Target URL (must start with http:// or https://)
            timeout: Max seconds to wait for page load

        Returns:
            JSON with page title, final URL, and seq number.
            After navigating, use browserctl_snapshot to see the page.
        """
        result = await bridge.request(
            "POST", "/navigate", json_body={"url": url, "timeout": timeout}
        )
        return bridge._format_result(result)

    @mcp.tool(annotations={"readOnlyHint": True})
    async def browserctl_snapshot(mode: str = "accessible") -> str:
        """Get page content as an accessibility tree with [N] element references.

        This is the primary way to see what's on the page. Each interactive
        element gets a [N] reference number — use that number as the target
        in browserctl_action.

        Args:
            mode: 'accessible' (a11y tree with [N] refs), 'dom', or 'content'

        Returns:
            JSON with url, title, tree_text (the a11y tree), and selector_map.
        """
        result = await bridge.request(
            "GET", "/snapshot", params={"mode": mode}
        )
        return bridge._format_result(result)

    @mcp.tool(annotations={"readOnlyHint": True})
    async def browserctl_screenshot(full_page: bool = False) -> str:
        """Take a screenshot of the current page.

        For understanding page layout or verifying visual state.
        For element interaction, prefer browserctl_snapshot (a11y tree).

        Args:
            full_page: Capture the full scrollable page instead of viewport

        Returns:
            JSON with base64-encoded PNG screenshot and size in bytes.
        """
        params: dict[str, str] = {}
        if full_page:
            params["full_page"] = "true"
        result = await bridge.request("GET", "/screenshot", params=params)
        return bridge._format_result(result)
