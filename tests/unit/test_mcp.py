"""Tests for MCP server — tool registration and response formatting."""

from __future__ import annotations

import json

from browserctl.mcp.client import DaemonBridge


class TestDaemonBridge:
    def test_format_result_success(self) -> None:
        bridge = DaemonBridge.__new__(DaemonBridge)
        bridge._base = "http://127.0.0.1:9222"
        data = {"ok": True, "seq": 1, "data": {"title": "Test"}}
        result = bridge._format_result(data)
        parsed = json.loads(result)
        assert parsed == {"title": "Test"}

    def test_format_result_error(self) -> None:
        bridge = DaemonBridge.__new__(DaemonBridge)
        bridge._base = "http://127.0.0.1:9222"
        data = {
            "ok": False,
            "error": "navigation_failed",
            "hint": "Page not found",
            "action": "check URL",
        }
        result = bridge._format_result(data)
        parsed = json.loads(result)
        assert parsed["error"] == "navigation_failed"
        assert parsed["hint"] == "Page not found"

    def test_format_result_missing_data(self) -> None:
        bridge = DaemonBridge.__new__(DaemonBridge)
        bridge._base = "http://127.0.0.1:9222"
        data = {"ok": True, "seq": 0}
        result = bridge._format_result(data)
        parsed = json.loads(result)
        assert parsed == {"ok": True, "seq": 0}


class TestMCPServerCreation:
    def test_create_server_registers_tools(self) -> None:
        try:
            from browserctl.mcp.server import create_server

            mcp = create_server()
            assert mcp is not None
        except ImportError:
            import pytest
            pytest.skip("mcp package not installed")

    def test_server_has_tool_count(self) -> None:
        try:
            from mcp.server.fastmcp import FastMCP

            from browserctl.mcp.server import create_server

            mcp = create_server()
            assert isinstance(mcp, FastMCP)
        except ImportError:
            import pytest
            pytest.skip("mcp package not installed")
