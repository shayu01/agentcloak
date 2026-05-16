"""Tests for cli/commands/doctor.py — JSON output format and fix mode."""

import json
import tempfile
from pathlib import Path

from typer.testing import CliRunner

from agentcloak.cli.app import app
from agentcloak.daemon.services.diagnostic_service import (
    DiagnosticService,
    _detect_linux_distro,
)

runner = CliRunner()


class TestDoctorCommand:
    # CLI defaults to text output; tests assert against the legacy JSON
    # envelope via ``--json`` (still the contract for scripts and MCP).
    def test_outputs_valid_json(self) -> None:
        result = runner.invoke(app, ["--json", "doctor"])
        data = json.loads(result.stdout)
        assert "ok" in data
        assert data["ok"] is True
        assert "data" in data

    def test_has_checks_array(self) -> None:
        result = runner.invoke(app, ["--json", "doctor"])
        data = json.loads(result.stdout)
        checks = data["data"]["checks"]
        assert isinstance(checks, list)
        assert len(checks) > 0

    def test_each_check_has_required_fields(self) -> None:
        result = runner.invoke(app, ["--json", "doctor"])
        data = json.loads(result.stdout)
        for check in data["data"]["checks"]:
            assert "name" in check
            assert "ok" in check
            assert "detail" in check
            assert "hint" in check

    def test_python_version_check_passes(self) -> None:
        result = runner.invoke(app, ["--json", "doctor"])
        data = json.loads(result.stdout)
        checks = data["data"]["checks"]
        py_check = next(c for c in checks if c["name"] == "python_version")
        assert py_check["ok"] is True

    def test_has_seq_field(self) -> None:
        result = runner.invoke(app, ["--json", "doctor"])
        data = json.loads(result.stdout)
        assert "seq" in data
        assert data["seq"] == 0

    def test_path_entry_check_present(self) -> None:
        # ``path_entry`` warns when ``agentcloak``/``cloak`` aren't on PATH.
        # In CI/dev runs the venv's scripts dir is always on PATH, so this is
        # a smoke test confirming the check is wired up.
        result = runner.invoke(app, ["--json", "doctor"])
        data = json.loads(result.stdout)
        names = {c["name"] for c in data["data"]["checks"]}
        assert "path_entry" in names

    def test_playwright_libs_check_present(self) -> None:
        result = runner.invoke(app, ["--json", "doctor"])
        data = json.loads(result.stdout)
        names = {c["name"] for c in data["data"]["checks"]}
        assert "playwright_libs" in names

    def test_fix_flag_returns_fix_section(self) -> None:
        # ``--fix`` adds a ``fix`` dict to the response (actions, command,
        # executed). On an already-healthy environment ``command`` is empty.
        result = runner.invoke(app, ["--json", "doctor", "--fix"])
        data = json.loads(result.stdout)
        assert "fix" in data["data"]
        assert "actions" in data["data"]["fix"]
        assert "command" in data["data"]["fix"]
        assert "executed" in data["data"]["fix"]
        # No daemon running in test env → not healthy, but the fix dict
        # itself is still present.

    def test_fix_help_advertises_sudo(self) -> None:
        result = runner.invoke(app, ["doctor", "--help"])
        assert "--fix" in result.stdout
        assert "--sudo" in result.stdout


class TestDiagnosticServiceDirect:
    """Direct calls into DiagnosticService — exercises code paths the CLI
    layer doesn't easily reach without mocking the whole filesystem."""

    def test_doctor_smoke(self) -> None:
        ds = DiagnosticService()
        with tempfile.TemporaryDirectory() as td:
            report = ds.doctor(data_dir=Path(td))
        assert "healthy" in report
        assert "checks" in report
        assert "extras" in report
        # extras structure: ``available`` is True when no extras run or all pass.
        assert "available" in report["extras"]
        assert "checks" in report["extras"]

    def test_doctor_fix_creates_data_dir(self) -> None:
        ds = DiagnosticService()
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "nested" / "agentcloak"
            assert not target.exists()
            report = ds.doctor_fix(data_dir=target, execute_sudo=False)
            # Assertions must run inside the ``with`` block — the temp dir
            # gets recursively deleted when we leave the context, which would
            # make every ``.exists()`` check trivially fail.
            assert target.exists()
            assert (target / "profiles").exists()
            assert (target / "logs").exists()
            actions = report["fix"]["actions"]
            names = {a["name"] for a in actions}
            assert "data_directory" in names

    def test_distro_detection_returns_tuple(self) -> None:
        # Just confirm the function returns the expected 3-tuple shape and
        # the falls-back-to-debian behaviour doesn't crash on unknown distros.
        name, mgr_argv, pkg = _detect_linux_distro()
        assert isinstance(name, str) and name
        assert isinstance(mgr_argv, list) and mgr_argv
        assert isinstance(pkg, str) and pkg
