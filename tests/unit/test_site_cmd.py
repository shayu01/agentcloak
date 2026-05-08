"""Tests for CLI site commands and adapter discovery."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from browserctl.adapters.registry import get_registry
from browserctl.cli.app import app


runner = CliRunner()


class TestSiteList:
    def setup_method(self) -> None:
        get_registry().clear()

    def test_list_empty(self) -> None:
        result = runner.invoke(app, ["site", "list"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert data["data"]["count"] >= 0

    def test_list_after_discovery(self) -> None:
        from browserctl.adapters.discovery import discover_adapters

        discover_adapters()
        result = runner.invoke(app, ["site", "list"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["data"]["count"] >= 2


class TestSiteInfo:
    def setup_method(self) -> None:
        get_registry().clear()
        from browserctl.adapters.discovery import discover_adapters
        discover_adapters()

    def test_info_existing(self) -> None:
        result = runner.invoke(app, ["site", "info", "httpbin/headers"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert data["data"]["site"] == "httpbin"
        assert data["data"]["name"] == "headers"
        assert data["data"]["strategy"] == "public"

    def test_info_missing(self) -> None:
        result = runner.invoke(app, ["site", "info", "nonexist/cmd"])
        assert result.exit_code == 1

    def test_info_bad_format(self) -> None:
        result = runner.invoke(app, ["site", "info", "noSlash"])
        assert result.exit_code == 1


class TestSiteRun:
    def setup_method(self) -> None:
        get_registry().clear()
        from browserctl.adapters.discovery import discover_adapters
        discover_adapters()

    def test_run_browser_required_adapter_fails_without_daemon(self) -> None:
        result = runner.invoke(app, ["site", "run", "example/title"])
        assert result.exit_code == 1


class TestDiscovery:
    def setup_method(self) -> None:
        get_registry().clear()

    def test_discover_builtin(self) -> None:
        from browserctl.adapters.discovery import discover_adapters

        counts = discover_adapters()
        assert counts["builtin"] >= 2
        assert counts["total"] >= 2

    def test_discover_idempotent(self) -> None:
        from browserctl.adapters.discovery import discover_adapters

        discover_adapters()
        count_first = len(get_registry())
        discover_adapters()
        assert len(get_registry()) == count_first
