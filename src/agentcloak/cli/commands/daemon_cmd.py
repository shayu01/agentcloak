"""Daemon lifecycle commands — start, stop, health."""

from __future__ import annotations

import asyncio
import subprocess
import sys

import typer

from agentcloak.cli.output import output_error, output_json
from agentcloak.core.errors import DaemonConnectionError

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
    no_humanize: bool = typer.Option(
        False, "--no-humanize", help="Disable humanize layer in stealth mode."
    ),
) -> None:
    """Start the agentcloak daemon."""
    humanize: bool | None = False if no_humanize else None

    if background:
        cmd = [sys.executable, "-m", "agentcloak.daemon"]
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
        if no_humanize:
            cmd.append("--no-humanize")
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        from agentcloak.core.config import load_config, resolve_tier

        _, cfg = load_config()
        raw_tier = "cloak" if stealth else cfg.default_tier
        resolved_tier = resolve_tier(raw_tier)
        output_json(
            {
                "pid": proc.pid,
                "background": True,
                "profile": profile,
                "stealth": stealth,
                "tier": resolved_tier,
            },
            seq=0,
        )
        return

    # Acceptable exception to layer isolation: CLI starts daemon in-process
    # for foreground mode (no HTTP API to call when daemon isn't running yet).
    from agentcloak.daemon.server import start

    asyncio.run(
        start(
            host=host,
            port=port,
            headless=headless,
            profile=profile,
            stealth=stealth,
            humanize=humanize,
        )
    )


@app.command("stop")
def daemon_stop(
    host: str | None = typer.Option(None, "--host"),
    port: int | None = typer.Option(None, "--port"),
) -> None:
    """Stop the running daemon."""
    from agentcloak.cli.client import DaemonClient

    client = DaemonClient(host=host, port=port, auto_start=False)
    asyncio.run(client.shutdown())
    output_json({"stopped": True}, seq=0)


@app.command("cdp-endpoint")
def daemon_cdp_endpoint(
    host: str | None = typer.Option(None, "--host"),
    port: int | None = typer.Option(None, "--port"),
) -> None:
    """Get the CDP WebSocket URL for the current browser."""
    from agentcloak.cli.client import DaemonClient

    client = DaemonClient(host=host, port=port)
    result = asyncio.run(client.cdp_endpoint())
    output_json(result.get("data", result), seq=result.get("seq", 0))


@app.command("health")
def daemon_health(
    host: str | None = typer.Option(None, "--host"),
    port: int | None = typer.Option(None, "--port"),
) -> None:
    """Check daemon connectivity."""
    from agentcloak.cli.client import DaemonClient

    client = DaemonClient(host=host, port=port, auto_start=False)
    try:
        result = asyncio.run(client.health())
        if result.get("ok"):
            output_json({"daemon": "running"}, seq=0)
        else:
            output_error(
                DaemonConnectionError(
                    error="daemon_unreachable",
                    hint="Cannot connect to daemon",
                    action="run 'agentcloak daemon start' first",
                )
            )
            raise typer.Exit(1)
    except DaemonConnectionError as e:
        output_error(e)
        raise typer.Exit(1) from e
