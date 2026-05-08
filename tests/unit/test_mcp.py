"""Tests for MCP server — tool registration, response formatting, tool count."""

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
    def test_create_server_returns_fastmcp(self) -> None:
        try:
            from mcp.server.fastmcp import FastMCP

            from browserctl.mcp.server import create_server

            mcp = create_server()
            assert isinstance(mcp, FastMCP)
        except ImportError:
            import pytest
            pytest.skip("mcp package not installed")

    def test_tool_count_is_10(self) -> None:
        try:
            from browserctl.mcp.server import create_server

            mcp = create_server()
            tools = mcp._tool_manager._tools  # type: ignore[union-attr]
            assert len(tools) == 10, (
                f"Expected 10 tools, got {len(tools)}: "
                f"{sorted(tools.keys())}"
            )
        except ImportError:
            import pytest
            pytest.skip("mcp package not installed")

    def test_tool_names_have_prefix(self) -> None:
        try:
            from browserctl.mcp.server import create_server

            mcp = create_server()
            tools = mcp._tool_manager._tools  # type: ignore[union-attr]
            for name in tools:
                assert name.startswith("browserctl_"), (
                    f"Tool '{name}' missing browserctl_ prefix"
                )
        except ImportError:
            import pytest
            pytest.skip("mcp package not installed")

    def test_expected_tools_present(self) -> None:
        try:
            from browserctl.mcp.server import create_server

            mcp = create_server()
            tools = mcp._tool_manager._tools  # type: ignore[union-attr]
            expected = {
                "browserctl_navigate",
                "browserctl_snapshot",
                "browserctl_screenshot",
                "browserctl_action",
                "browserctl_evaluate",
                "browserctl_fetch",
                "browserctl_network",
                "browserctl_capture_control",
                "browserctl_capture_query",
                "browserctl_status",
            }
            assert set(tools.keys()) == expected
        except ImportError:
            import pytest
            pytest.skip("mcp package not installed")
