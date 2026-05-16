"""Self-check and diagnostics command.

The actual checks live in :class:`DiagnosticService` so CLI / MCP / daemon
all run exactly the same probes. The CLI surface adds two extras:

1. A daemon liveness probe (only the CLI knows about the local host:port
   we'd point at — the daemon process itself doesn't need to ping itself).
2. ``--fix`` and ``--fix --sudo`` flags. ``--fix`` runs the in-process repairs
   the service can do (download CloakBrowser binary, create data dir) and
   prints a one-liner shell command for the remaining system-level work.
   ``--sudo`` actually executes that command if sudo/root is available.
"""

from __future__ import annotations

import sys
from typing import Any

import typer

from agentcloak.cli.output import output_json
from agentcloak.core.config import load_config
from agentcloak.daemon.services import DiagnosticService

__all__ = ["app"]

app = typer.Typer()


def _check_daemon(host: str, port: int) -> dict[str, Any]:
    """CLI-only probe: try the daemon ``/health`` endpoint without spawning."""
    from agentcloak.client import DaemonClient

    client = DaemonClient(host=host, port=port, auto_start=False)
    try:
        result = client.health_sync()
        if result.get("ok"):
            return {
                "name": "daemon",
                "ok": True,
                "detail": f"{host}:{port}",
                "hint": "",
            }
    except Exception:
        pass
    return {
        "name": "daemon",
        "ok": False,
        "detail": f"{host}:{port}",
        "hint": "run 'agentcloak daemon start -b' to launch",
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
    """Run all diagnostic checks and report status.

    Without flags this is a read-only inspection.

    With ``--fix`` the doctor first tries to repair things the running process
    can fix on its own (downloads the CloakBrowser binary, creates the data
    directory). For system-level work it can't do alone — installing Xvfb or
    Playwright's libs — it prints a single combined shell command.

    With ``--fix --sudo`` that command is actually executed if sudo (or root)
    is available; otherwise the response includes a ``reason`` field
    explaining why we didn't run it.
    """
    paths, cfg = load_config()
    diagnostic = DiagnosticService()

    if fix:
        report = diagnostic.doctor_fix(data_dir=paths.root, execute_sudo=sudo)
        # The fix-mode response can include long package-manager output;
        # callers that want the daemon check can still infer it from the
        # subsequent doctor-without-fix run. Keep this response focused.
    else:
        report = diagnostic.doctor(data_dir=paths.root)

    daemon_check = _check_daemon(cfg.daemon_host, cfg.daemon_port)
    report["checks"].append(daemon_check)
    report["healthy"] = all(c["ok"] for c in report["checks"])

    output_json(report, seq=0)

    if fix and not report["healthy"] and not sudo:
        # Help text on stderr so the JSON envelope on stdout stays parseable
        # for scripts. ``output_json`` writes to stdout; this complementary
        # banner lands on stderr.
        cmd = report.get("fix", {}).get("command", "")
        if cmd:
            sys.stderr.write("\n--- Run this to finish fixing the environment ---\n")
            sys.stderr.write(f"{cmd}\n")
            sys.stderr.write("(or re-run with: agentcloak doctor --fix --sudo)\n\n")

    if not report["healthy"]:
        raise typer.Exit(1)
