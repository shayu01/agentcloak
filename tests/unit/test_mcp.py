"""Tests for MCP server — tool registration, response formatting, tool count."""

from __future__ import annotations

import json

from agentcloak.mcp.client import DaemonBridge


class TestDaemonBridge:
    def test_format_result_success(self) -> None:
        bridge = DaemonBridge.__new__(DaemonBridge)
        bridge._base = "http://127.0.0.1:9222"
        data = {"ok": True, "seq": 1, "data": {"title": "Test"}}
        result = bridge.format_result(data)
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
        result = bridge.format_result(data)
        parsed = json.loads(result)
        assert parsed["error"] == "navigation_failed"


class TestMCPServerCreation:
    def test_create_server_returns_fastmcp(self) -> None:
        try:
            from mcp.server.fastmcp import FastMCP

            from agentcloak.mcp.server import create_server

            mcp = create_server()
            assert isinstance(mcp, FastMCP)
        except ImportError:
            import pytest

            pytest.skip("mcp package not installed")

    def test_tool_count_is_18(self) -> None:
        try:
            from agentcloak.mcp.server import create_server

            mcp = create_server()
            tools = mcp._tool_manager._tools  # type: ignore[union-attr]
            assert len(tools) == 18, (
                f"Expected 18 tools, got {len(tools)}: {sorted(tools.keys())}"
            )
        except ImportError:
            import pytest

            pytest.skip("mcp package not installed")

    def test_tool_names_have_prefix(self) -> None:
        try:
            from agentcloak.mcp.server import create_server

            mcp = create_server()
            tools = mcp._tool_manager._tools  # type: ignore[union-attr]
            for name in tools:
                assert name.startswith("agentcloak_"), (
                    f"Tool '{name}' missing agentcloak_ prefix"
                )
        except ImportError:
            import pytest

            pytest.skip("mcp package not installed")

    def test_expected_tools_present(self) -> None:
        try:
            from agentcloak.mcp.server import create_server

            mcp = create_server()
            tools = mcp._tool_manager._tools  # type: ignore[union-attr]
            expected = {
                "agentcloak_navigate",
                "agentcloak_snapshot",
                "agentcloak_screenshot",
                "agentcloak_action",
                "agentcloak_evaluate",
                "agentcloak_fetch",
                "agentcloak_network",
                "agentcloak_capture_control",
                "agentcloak_capture_query",
                "agentcloak_status",
                "agentcloak_launch",
                "agentcloak_adapter_run",
                "agentcloak_adapter_list",
                "agentcloak_profile",
                "agentcloak_cookies",
                "agentcloak_doctor",
                "agentcloak_tab",
                "agentcloak_resume",
            }
            assert set(tools.keys()) == expected
        except ImportError:
            import pytest

            pytest.skip("mcp package not installed")


class TestResolveTier:
    def test_patchright_maps_to_playwright(self) -> None:
        from agentcloak.core.config import resolve_tier

        assert resolve_tier("patchright") == "playwright"

    def test_playwright_passthrough(self) -> None:
        from agentcloak.core.config import resolve_tier

        assert resolve_tier("playwright") == "playwright"

    def test_cloak_passthrough(self) -> None:
        from agentcloak.core.config import resolve_tier

        assert resolve_tier("cloak") == "cloak"

    def test_auto_resolves_to_cloak(self) -> None:
        from agentcloak.core.config import resolve_tier

        assert resolve_tier("auto") == "cloak"
