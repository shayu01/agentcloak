"""Navigation tools — navigate, screenshot, snapshot."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from agentcloak.mcp.client import DaemonBridge

__all__ = ["register"]


def register(mcp: FastMCP, bridge: DaemonBridge) -> None:
    @mcp.tool(annotations={"destructiveHint": False, "readOnlyHint": False})
    async def agentcloak_navigate(url: str, timeout: float = 30.0) -> str:
        """Navigate the browser to a URL. Changes page state.

        Args:
            url: Target URL (must start with http:// or https://)
            timeout: Max seconds to wait for page load

        Returns:
            JSON with page title, final URL, and seq number.
            After navigating, use agentcloak_snapshot to see the page.
        """
        result = await bridge.request(
            "POST", "/navigate", json_body={"url": url, "timeout": timeout}
        )
        return bridge.format_result(result)

    @mcp.tool(annotations={"readOnlyHint": True})
    async def agentcloak_snapshot(
        mode: str = "accessible",
        max_chars: int = 0,
        max_nodes: int = 0,
        focus: int = 0,
        offset: int = 0,
    ) -> str:
        """Get page content as an accessibility tree with [N] element references.

        This is the primary way to see what's on the page. Each interactive
        element gets a [N] reference number -- use that number as the target
        in agentcloak_action.

        The tree shows ARIA states (checked, disabled, expanded, focused),
        current input values, heading levels, and hierarchical indentation.
        Password fields are redacted as value="••••".

        Args:
            mode: 'accessible' (a11y tree with [N] refs -- default, includes
                  ARIA states and values), 'compact' (interactive elements +
                  named containers only -- much smaller output), 'dom'
                  (raw HTML), or 'content' (text extraction)
            max_chars: Truncate tree_text to this many characters (0 = no limit).
            max_nodes: Truncate after N nodes (0 = no limit).
                Node-level truncation is more precise than char truncation.
                Truncated output includes a summary of hidden elements.
            focus: Expand subtree around element [N] from cached snapshot.
                Use when you need details about a specific area of the page.
            offset: Start output from Nth element (pagination for large pages).

        Returns:
            JSON with url, title, tree_text, tree_size, truncated,
            total_nodes, total_interactive, and selector_map.
        """
        params: dict[str, str] = {
            "mode": mode,
            "include_selector_map": "false",
        }
        if max_chars:
            params["max_chars"] = str(max_chars)
        if max_nodes:
            params["max_nodes"] = str(max_nodes)
        if focus:
            params["focus"] = str(focus)
        if offset:
            params["offset"] = str(offset)
        result = await bridge.request("GET", "/snapshot", params=params)
        return bridge.format_result(result)

    @mcp.tool(annotations={"readOnlyHint": True})
    async def agentcloak_screenshot(
        full_page: bool = False,
        format: str = "jpeg",
        quality: int = 80,
    ) -> str:
        """Take a screenshot of the current page.

        For understanding page layout or verifying visual state.
        For element interaction, prefer agentcloak_snapshot (a11y tree).

        Default format is JPEG at quality 80, which is ~75-85% smaller than
        PNG. Use format='png' when pixel-perfect fidelity is needed.

        Args:
            full_page: Capture the full scrollable page instead of viewport
            format: Image format — 'jpeg' (default, smaller) or 'png' (lossless)
            quality: JPEG quality 0-100 (default 80, ignored for png)

        Returns:
            JSON with base64-encoded screenshot, size in bytes, and format.
        """
        params: dict[str, str] = {"format": format, "quality": str(quality)}
        if full_page:
            params["full_page"] = "true"
        result = await bridge.request("GET", "/screenshot", params=params)
        return bridge.format_result(result)
