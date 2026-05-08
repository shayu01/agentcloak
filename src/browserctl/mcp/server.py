"""MCP server — stdio bridge to browserctl daemon."""

from __future__ import annotations

import atexit
import logging
import sys

__all__ = ["create_server", "main"]


def _configure_logging() -> None:
    from browserctl.core.config import load_config

    _, cfg = load_config()
    level = getattr(logging, cfg.log_level.upper(), logging.WARNING)
    logging.basicConfig(
        level=level,
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
            "to browserctl_action. The daemon auto-starts on first use "
            "with the best available browser (CloakBrowser if installed, "
            "otherwise patchright). Use browserctl_launch to explicitly "
            "set tier or profile. For jshookmcp coordination: use "
            "browserctl_status(query='cdp_endpoint') to get the "
            "WebSocket URL, then call jshookmcp's browser_attach."
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


def _register_exit_hook() -> None:
    """Stop daemon on MCP server exit if configured."""
    from browserctl.core.config import load_config

    _, cfg = load_config()
    if not cfg.stop_on_exit:
        return

    def _stop() -> None:
        import httpx

        base = f"http://{cfg.daemon_host}:{cfg.daemon_port}"
        import contextlib

        with contextlib.suppress(Exception):
            httpx.post(f"{base}/shutdown", timeout=2.0)

    atexit.register(_stop)


def main() -> None:
    """Entry point for browserctl-mcp and python -m browserctl.mcp."""
    _configure_logging()
    _register_exit_hook()
    mcp = create_server()
    mcp.run()  # type: ignore[union-attr]
