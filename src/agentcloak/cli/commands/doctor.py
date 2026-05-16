"""Self-check and diagnostics command.

The actual checks live in :class:`DiagnosticService` so CLI / MCP / daemon
all run exactly the same probes. The CLI surface only adds one extra check
(can we reach a running daemon?) which is naturally CLI-specific — the MCP
tool exposes the same probe through :meth:`DaemonClient.health`.
"""

from __future__ import annotations

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
        "hint": "run 'agentcloak daemon start' to launch",
    }


@app.callback(invoke_without_command=True)
def run_doctor() -> None:
    """Run all diagnostic checks and report status."""
    paths, cfg = load_config()

    diagnostic = DiagnosticService()
    report = diagnostic.doctor(data_dir=paths.root)
    daemon_check = _check_daemon(cfg.daemon_host, cfg.daemon_port)
    report["checks"].append(daemon_check)
    report["healthy"] = all(c["ok"] for c in report["checks"])

    output_json(report, seq=0)
    if not report["healthy"]:
        raise typer.Exit(1)
