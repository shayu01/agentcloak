"""MCP server — stdio bridge to browserctl daemon."""

from __future__ import annotations

import logging
import sys

__all__ = ["create_server", "main"]


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        stream=sys.stderr,
    )


def create_server() -> object:
    """Create and configure the FastMCP server with all tools."""
    from mcp.server.fastmcp import FastMCP

    from browserctl.mcp.client import DaemonBridge
    from browserctl.mcp.tools import (
        capture,
        content,
        interaction,
        management,
        navigation,
        network,
    )

    mcp = FastMCP(
        "browserctl",
        instructions=(
            "browserctl provides browser automation for AI agents. "
            "Core workflow: browserctl_navigate → browserctl_snapshot → "
            "browserctl_action. The snapshot shows an accessibility tree "
            "with [N] element references — pass those numbers as 'target' "
            "to browserctl_action. The daemon must be running first: "
            "'browserctl daemon start' in a terminal. "
            "For jshookmcp coordination: use browserctl_status(query="
            "'cdp_endpoint') to get the WebSocket URL, then call "
            "jshookmcp's browser_attach with that URL."
        ),
    )

    bridge = DaemonBridge()

    navigation.register(mcp, bridge)
    interaction.register(mcp, bridge)
    content.register(mcp, bridge)
    network.register(mcp, bridge)
    capture.register(mcp, bridge)
    management.register(mcp, bridge)

    return mcp


def main() -> None:
    """Entry point for browserctl-mcp and python -m browserctl.mcp."""
    _configure_logging()
    mcp = create_server()
    mcp.run()  # type: ignore[union-attr]
