"""Shared HTTP client for the agentcloak daemon.

This package provides a single typed client used by both the CLI (sync calls)
and the MCP server (async calls). It replaces the previously duplicated
``agentcloak.cli.client.DaemonClient`` and ``agentcloak.mcp.client.DaemonBridge``
— both auto-start logic and subprocess spawning live here in one place,
implemented on top of :mod:`httpx`.
"""

from agentcloak.client.daemon_client import DaemonClient

__all__ = ["DaemonClient"]
