"""Tests for MCP server — tool registration, response formatting, tool count."""

from __future__ import annotations

import orjson
import pytest

from agentcloak.core.errors import AgentBrowserError
from agentcloak.mcp._format import error_json, format_envelope


class TestFormatHelpers:
    """The MCP format helpers replace the old DaemonBridge.format_result."""

    def test_format_envelope_unwraps_data(self) -> None:
        data = {"ok": True, "seq": 1, "data": {"title": "Test"}}
        rendered = format_envelope(data)
        assert orjson.loads(rendered) == {"title": "Test"}

    def test_error_json_renders_three_field_envelope(self) -> None:
        exc = AgentBrowserError(
            error="navigation_failed",
            hint="Page not found",
            action="check URL",
        )
        rendered = error_json(exc)
        assert orjson.loads(rendered) == {
            "error": "navigation_failed",
            "hint": "Page not found",
            "action": "check URL",
        }


class TestMCPServerCreation:
    def test_create_server_returns_fastmcp(self) -> None:
        try:
            from mcp.server.fastmcp import FastMCP

            from agentcloak.mcp.server import create_server

            mcp = create_server()
            assert isinstance(mcp, FastMCP)
        except ImportError:
            pytest.skip("mcp package not installed")

    def test_tool_count_is_23(self) -> None:
        try:
            from agentcloak.mcp.server import create_server

            mcp = create_server()
            tools = mcp._tool_manager._tools  # type: ignore[union-attr]
            assert len(tools) == 23, (
                f"Expected 23 tools, got {len(tools)}: {sorted(tools.keys())}"
            )
        except ImportError:
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
                "agentcloak_spell_run",
                "agentcloak_spell_list",
                "agentcloak_profile",
                "agentcloak_cookies",
                "agentcloak_doctor",
                "agentcloak_tab",
                "agentcloak_resume",
                "agentcloak_dialog",
                "agentcloak_wait",
                "agentcloak_upload",
                "agentcloak_frame",
                "agentcloak_bridge",
            }
            assert set(tools.keys()) == expected
        except ImportError:
            pytest.skip("mcp package not installed")


class TestResolveTier:
    def test_playwright_passthrough(self) -> None:
        from agentcloak.core.config import resolve_tier

        assert resolve_tier("playwright") == "playwright"

    def test_cloak_passthrough(self) -> None:
        from agentcloak.core.config import resolve_tier

        assert resolve_tier("cloak") == "cloak"

    def test_auto_resolves_to_cloak(self) -> None:
        from agentcloak.core.config import resolve_tier

        assert resolve_tier("auto") == "cloak"
