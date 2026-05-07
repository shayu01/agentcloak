"""Daemon lifecycle commands — start, stop, health."""

from __future__ import annotations

import asyncio
import subprocess
import sys

import typer

from browserctl.cli.output import output_error, output_json
from browserctl.core.errors import DaemonConnectionError

__all__ = ["app"]

app = typer.Typer()


@app.command("start")
def daemon_start(
    background: bool = typer.Option(
        False, "--background", "-b", help="Run in background."
    ),
    headless: bool = typer.Option(
        True, "--headless/--headed", help="Browser headless mode."
    ),
    host: str | None = typer.Option(None, "--host", help="Bind host."),
    port: int | None = typer.Option(None, "--port", help="Bind port."),
    profile: str | None = typer.Option(
        None, "--profile", "-p", help="Browser profile name."
    ),
    stealth: bool = typer.Option(
        False, "--stealth", "-s", help="Enable CloakBrowser stealth mode."
    ),
) -> None:
    """Start the browserctl daemon."""
    if background:
        cmd = [sys.executable, "-m", "browserctl.daemon"]
        if host:
            cmd.extend(["--host", host])
        if port:
            cmd.extend(["--port", str(port)])
        if not headless:
            cmd.append("--headed")
        if profile:
            cmd.extend(["--profile", profile])
        if stealth:
            cmd.append("--stealth")
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        output_json(
            {
                "pid": proc.pid,
                "background": True,
                "profile": profile,
                "stealth": stealth,
            },
            seq=0,
        )
        return

    from browserctl.daemon.server import start

    asyncio.run(
        start(host=host, port=port, headless=headless, profile=profile, stealth=stealth)
    )


@app.command("stop")
def daemon_stop(
    host: str | None = typer.Option(None, "--host"),
    port: int | None = typer.Option(None, "--port"),
) -> None:
    """Stop the running daemon."""
    from browserctl.daemon.server import stop

    asyncio.run(stop(host=host, port=port))
    output_json({"stopped": True}, seq=0)


@app.command("health")
def daemon_health(
    host: str | None = typer.Option(None, "--host"),
    port: int | None = typer.Option(None, "--port"),
) -> None:
    """Check daemon connectivity."""
    from browserctl.daemon.server import health

    ok = asyncio.run(health(host=host, port=port))
    if ok:
        output_json({"daemon": "running"}, seq=0)
    else:
        output_error(
            DaemonConnectionError(
                error="daemon_unreachable",
                hint="Cannot connect to daemon",
                action="run 'browserctl daemon start' first",
            )
        )
        raise typer.Exit(1)
