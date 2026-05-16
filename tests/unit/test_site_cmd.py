"""Tests for CLI spell commands and spell discovery."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from agentcloak.cli.app import app
from agentcloak.spells.registry import get_registry

runner = CliRunner()


def _parse_json(stdout: str) -> dict:
    """Extract the JSON object from CLI output, skipping any log lines."""
    for line in reversed(stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise ValueError(f"No JSON found in output: {stdout!r}")


class TestSpellList:
    def setup_method(self) -> None:
        get_registry().clear()

    def test_list_empty(self) -> None:
        result = runner.invoke(app, ["spell", "list"])
        assert result.exit_code == 0
        data = _parse_json(result.stdout)
        assert data["ok"] is True
        assert data["data"]["count"] >= 0

    def test_list_after_discovery(self) -> None:
        from agentcloak.spells.discovery import discover_spells

        discover_spells()
        result = runner.invoke(app, ["spell", "list"])
        assert result.exit_code == 0
        data = _parse_json(result.stdout)
        assert data["data"]["count"] >= 2


class TestSpellInfo:
    def setup_method(self) -> None:
        get_registry().clear()
        from agentcloak.spells.discovery import discover_spells

        discover_spells()

    def test_info_existing(self) -> None:
        result = runner.invoke(app, ["spell", "info", "httpbin/headers"])
        assert result.exit_code == 0
        data = _parse_json(result.stdout)
        assert data["ok"] is True
        assert data["data"]["site"] == "httpbin"
        assert data["data"]["name"] == "headers"
        assert data["data"]["strategy"] == "public"

    def test_info_missing(self) -> None:
        result = runner.invoke(app, ["spell", "info", "nonexist/cmd"])
        assert result.exit_code == 1

    def test_info_bad_format(self) -> None:
        result = runner.invoke(app, ["spell", "info", "noSlash"])
        assert result.exit_code == 1


class TestSpellRun:
    def setup_method(self) -> None:
        get_registry().clear()
        from agentcloak.spells.discovery import discover_spells

        discover_spells()

    def test_run_browser_required_spell_fails_without_daemon(self) -> None:
        result = runner.invoke(app, ["spell", "run", "example/title"])
        assert result.exit_code == 1


class TestDiscovery:
    def setup_method(self) -> None:
        get_registry().clear()

    def test_discover_builtin(self) -> None:
        from agentcloak.spells.discovery import discover_spells

        counts = discover_spells()
        assert counts["builtin"] >= 2
        assert counts["total"] >= 2

    def test_discover_idempotent(self) -> None:
        from agentcloak.spells.discovery import discover_spells

        discover_spells()
        count_first = len(get_registry())
        discover_spells()
        assert len(get_registry()) == count_first
