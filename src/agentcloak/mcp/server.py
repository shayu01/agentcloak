"""MCP server — stdio bridge to agentcloak daemon."""

from __future__ import annotations

import atexit
import logging
import sys

__all__ = ["create_server", "main"]


def _configure_logging() -> None:
    from agentcloak.core.config import load_config

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

    from agentcloak.mcp.client import DaemonBridge
    from agentcloak.mcp.tools import (
        capture,
        content,
        dialog,
        frame,
        interaction,
        management,
        navigation,
        network,
        upload,
        wait,
    )

    mcp = FastMCP(
        "agentcloak",
        instructions=(
            "agentcloak provides browser automation for AI agents. "
            "Core workflow: agentcloak_navigate → agentcloak_snapshot → "
            "agentcloak_action. The snapshot shows an accessibility tree "
            "with [N] element references — pass those numbers as 'target' "
            "to agentcloak_action. The daemon auto-starts on first use "
            "with CloakBrowser (default stealth backend). "
            "Use agentcloak_launch to explicitly "
            "set tier or profile. For jshookmcp coordination: use "
            "agentcloak_status(query='cdp_endpoint') to get the "
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
    dialog.register(mcp, bridge)
    wait.register(mcp, bridge)
    upload.register(mcp, bridge)
    frame.register(mcp, bridge)

    return mcp


def _register_exit_hook() -> None:
    """Stop daemon on MCP server exit if configured."""
    from agentcloak.core.config import load_config

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
    """Entry point for agentcloak-mcp and python -m agentcloak.mcp."""
    _configure_logging()
    _register_exit_hook()
    mcp = create_server()
    mcp.run()  # type: ignore[union-attr]
