"""Navigation tools — navigate, screenshot, snapshot."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import ToolAnnotations

from agentcloak.mcp._format import format_call

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from agentcloak.client import DaemonClient

__all__ = ["register"]


def register(mcp: FastMCP, client: DaemonClient) -> None:
    # All defaults shown in the tool docstrings are sourced from
    # AgentcloakConfig at request time, so flipping a value in config.toml
    # propagates without redeploying the MCP server.
    cfg = client.config  # single shared client snapshot.

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=False, readOnlyHint=False))
    async def agentcloak_navigate(
        url: str,
        timeout: float = float(cfg.navigation_timeout),
        include_snapshot: bool = False,
        snapshot_mode: str = "compact",
    ) -> str:
        """Navigate the browser to a URL. Changes page state.

        Args:
            url: Target URL (must start with http:// or https://)
            timeout: Max seconds to wait for page load
            include_snapshot: If true, attach a compact snapshot to the
                navigate result. Saves a round-trip when you need to see
                the page right after navigating.
            snapshot_mode: Snapshot mode when include_snapshot is true:
                'compact' (default, interactive + containers) or
                'accessible' (full a11y tree).

        Returns:
            JSON with page title, final URL, and seq number.
            When include_snapshot=true, includes a 'snapshot' object with
            tree_text, mode, total_nodes, and total_interactive.
        """
        return await format_call(
            client.navigate(
                url,
                timeout=timeout,
                include_snapshot=include_snapshot,
                snapshot_mode=snapshot_mode,
            )
        )

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def agentcloak_snapshot(
        mode: str = "accessible",
        max_chars: int = 0,
        max_nodes: int = 0,
        focus: int = 0,
        offset: int = 0,
        frames: bool = False,
        diff: bool = False,
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
            frames: Include iframe content in the snapshot. When true, child
                frame AX trees are merged under [frame "name"] context nodes.
                Opt-in to avoid performance penalty on simple pages.
            diff: Compare with the previous snapshot and mark changes.
                Added elements are prefixed with [+], changed with [~].
                Removed interactive refs are listed at the bottom.
                Useful for seeing what changed after an action.

        Returns:
            JSON with url, title, tree_text, tree_size, truncated,
            total_nodes, total_interactive, and diff (bool, when requested).
        """
        return await format_call(
            client.snapshot(
                mode=mode,
                max_chars=max_chars,
                max_nodes=max_nodes,
                focus=focus,
                offset=offset,
                frames=frames,
                diff=diff,
                # MCP omits selector_map by default to save tokens — agents
                # work with [N] refs from the tree, not the raw map.
                include_selector_map=False,
            )
        )

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def agentcloak_screenshot(
        full_page: bool = False,
        format: str = "jpeg",
        quality: int = cfg.mcp_screenshot_quality,
    ) -> str:
        """Take a screenshot of the current page.

        For understanding page layout or verifying visual state.
        For element interaction, prefer agentcloak_snapshot (a11y tree).

        Default format is JPEG at a lower quality than the CLI default to keep
        the base64 payload under MCP token budgets. Use format='png' when
        pixel-perfect fidelity is needed.

        Args:
            full_page: Capture the full scrollable page instead of viewport
            format: Image format — 'jpeg' (default, smaller) or 'png' (lossless)
            quality: JPEG quality 0-100 (default from config.mcp_screenshot_quality,
                ignored for png)

        Returns:
            JSON with base64-encoded screenshot, size in bytes, and format.
        """
        return await format_call(
            client.screenshot(full_page=full_page, format=format, quality=quality)
        )
