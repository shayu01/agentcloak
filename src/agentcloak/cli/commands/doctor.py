"""Self-check and diagnostics command."""

from __future__ import annotations

import sys
from typing import Any

import typer

from agentcloak.cli._dispatch import emit_envelope
from agentcloak.cli.output import is_json_mode, value
from agentcloak.core.config import load_config
from agentcloak.daemon.services import DiagnosticService

__all__ = ["app"]

app = typer.Typer()


def _check_daemon(host: str, port: int) -> dict[str, Any]:
    """CLI-only probe: try the daemon ``/health`` endpoint without spawning.

    Daemon-down is reported as ``level="info"`` rather than a hard ``fail``
    because the daemon auto-starts on the first real command — the absence of
    a running daemon during a one-off ``doctor`` invocation is the expected
    fresh-install state, not a broken environment.
    """
    from agentcloak.client import DaemonClient

    client = DaemonClient(host=host, port=port, auto_start=False)
    try:
        result = client.health_sync()
        if result.get("ok"):
            return {
                "name": "daemon",
                "ok": True,
                "level": "ok",
                "detail": f"{host}:{port}",
                "hint": "",
            }
    except Exception:
        pass
    return {
        "name": "daemon",
        "ok": True,
        "level": "info",
        "detail": f"{host}:{port}",
        "hint": "not running (auto-starts on first command)",
    }


@app.callback(invoke_without_command=True)
def run_doctor(
    fix: bool = typer.Option(
        False,
        "--fix",
        help=(
            "Run in-process repairs (CloakBrowser binary download, data dir) "
            "and print a one-liner for the rest."
        ),
    ),
    sudo: bool = typer.Option(
        False,
        "--sudo",
        help=(
            "With --fix, execute the synthesised system command via sudo. "
            "Ignored when --fix is not set."
        ),
    ),
) -> None:
    """Run all diagnostic checks and report status."""
    paths, cfg = load_config()
    diagnostic = DiagnosticService()

    if fix:
        report = diagnostic.doctor_fix(data_dir=paths.root, execute_sudo=sudo)
    else:
        report = diagnostic.doctor(data_dir=paths.root)

    daemon_check = _check_daemon(cfg.daemon_host, cfg.daemon_port)
    report["checks"].append(daemon_check)
    report["healthy"] = all(c["ok"] for c in report["checks"])

    if is_json_mode():
        emit_envelope({"ok": True, "seq": 0, "data": report})
    else:
        # ``[ok] / [info] / [fail]`` lines for each check, one per line.
        # ``level`` is optional — when absent we derive it from ``ok`` so the
        # render stays backwards-compatible with every check in
        # :class:`DiagnosticService` (none of which set ``level``).
        for check in report["checks"]:
            level = str(check.get("level") or ("ok" if check["ok"] else "fail"))
            line = f"[{level}] {check['name']} | {check['detail']}"
            # Show the hint whenever it's set and the check isn't a flat "ok"
            # — info and fail both benefit from the explanatory text.
            if level != "ok" and check.get("hint"):
                line += f" | hint: {check['hint']}"
            value(line)

    if fix and not report["healthy"] and not sudo:
        # Help text on stderr so the JSON envelope / text on stdout stays
        # parseable for scripts.
        cmd = report.get("fix", {}).get("command", "")
        if cmd:
            sys.stderr.write("\n--- Run this to finish fixing the environment ---\n")
            sys.stderr.write(f"{cmd}\n")
            sys.stderr.write("(or re-run with: agentcloak doctor --fix --sudo)\n\n")

    if not report["healthy"]:
        raise typer.Exit(1)
