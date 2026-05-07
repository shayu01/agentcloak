"""Tests for cli/commands/doctor.py — JSON output format."""

import json

from typer.testing import CliRunner

from browserctl.cli.app import app

runner = CliRunner()


class TestDoctorCommand:
    def test_outputs_valid_json(self) -> None:
        result = runner.invoke(app, ["doctor"])
        data = json.loads(result.stdout)
        assert "ok" in data
        assert data["ok"] is True
        assert "data" in data

    def test_has_checks_array(self) -> None:
        result = runner.invoke(app, ["doctor"])
        data = json.loads(result.stdout)
        checks = data["data"]["checks"]
        assert isinstance(checks, list)
        assert len(checks) > 0

    def test_each_check_has_required_fields(self) -> None:
        result = runner.invoke(app, ["doctor"])
        data = json.loads(result.stdout)
        for check in data["data"]["checks"]:
            assert "name" in check
            assert "ok" in check
            assert "detail" in check
            assert "hint" in check

    def test_python_version_check_passes(self) -> None:
        result = runner.invoke(app, ["doctor"])
        data = json.loads(result.stdout)
        checks = data["data"]["checks"]
        py_check = next(c for c in checks if c["name"] == "python_version")
        assert py_check["ok"] is True

    def test_has_seq_field(self) -> None:
        result = runner.invoke(app, ["doctor"])
        data = json.loads(result.stdout)
        assert "seq" in data
        assert data["seq"] == 0
