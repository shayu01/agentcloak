"""Navigation tools — navigate, screenshot, snapshot, state."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from browserctl.mcp.client import DaemonBridge

__all__ = ["register"]


def register(mcp: FastMCP, bridge: DaemonBridge) -> None:
    @mcp.tool()
    async def browserctl_navigate(
        url: str, timeout: float = 30.0
    ) -> str:
        """Navigate the browser to a URL.

        Args:
            url: Target URL (must start with http:// or https://)
            timeout: Max seconds to wait for page load
        """
        result = await bridge.request(
            "POST", "/navigate", json_body={"url": url, "timeout": timeout}
        )
        return bridge._format_result(result)

    @mcp.tool()
    async def browserctl_screenshot(full_page: bool = False) -> str:
        """Take a screenshot of the current page.

        Args:
            full_page: Capture the full scrollable page
        """
        params: dict[str, str] = {}
        if full_page:
            params["full_page"] = "true"
        result = await bridge.request("GET", "/screenshot", params=params)
        return bridge._format_result(result)

    @mcp.tool()
    async def browserctl_snapshot(mode: str = "accessible") -> str:
        """Get page content as an accessibility tree with [N] element references.

        Args:
            mode: Snapshot mode — 'accessible' (a11y tree), 'dom', or 'content'
        """
        result = await bridge.request(
            "GET", "/snapshot", params={"mode": mode}
        )
        return bridge._format_result(result)

    @mcp.tool()
    async def browserctl_state() -> str:
        """Get full page state: a11y tree, screenshot, and recent network activity."""
        result = await bridge.request("GET", "/state")
        return bridge._format_result(result)
