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
    headless: bool | None = typer.Option(
        None, "--headless/--headed", help="Headless mode (default: config)."
    ),
    host: str | None = typer.Option(None, "--host", help="Bind host."),
    port: int | None = typer.Option(None, "--port", help="Bind port."),
    profile: str | None = typer.Option(
        None, "--profile", "-p", help="Browser profile name."
    ),
    stealth: bool = typer.Option(
        False,
        "--stealth",
        "-s",
        help="[Deprecated] CloakBrowser is now the default.",
        hidden=True,
    ),
    humanize: bool = typer.Option(
        False, "--humanize", help="Enable humanize behavioral layer."
    ),
    no_humanize: bool = typer.Option(
        False,
        "--no-humanize",
        help="Explicitly disable humanize layer.",
        hidden=True,
    ),
) -> None:
    """Start the agentcloak daemon."""
    import warnings

    if stealth:
        warnings.warn(
            "--stealth is deprecated: CloakBrowser is now the default backend. "
            "This flag will be removed in a future version.",
            DeprecationWarning,
            stacklevel=1,
        )

    resolved_humanize: bool | None = None
    if humanize:
        resolved_humanize = True
    elif no_humanize:
        resolved_humanize = False

    if background:
        cmd = [sys.executable, "-m", "agentcloak.daemon"]
        if host:
            cmd.extend(["--host", host])
        if port:
            cmd.extend(["--port", str(port)])
        if headless is True:
            cmd.append("--headless")
        elif headless is False:
            cmd.append("--headed")
        if profile:
            cmd.extend(["--profile", profile])
        if resolved_humanize is True:
            cmd.append("--humanize")
        elif resolved_humanize is False:
            cmd.append("--no-humanize")
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        from agentcloak.core.config import load_config, resolve_tier

        _, cfg = load_config()
        resolved_tier = resolve_tier(cfg.default_tier)
        output_json(
            {
                "pid": proc.pid,
                "background": True,
                "profile": profile,
                "tier": resolved_tier,
            },
            seq=0,
        )
        return

    from agentcloak.daemon.server import start

    asyncio.run(
        start(
            host=host,
            port=port,
            headless=headless,
            profile=profile,
            stealth=stealth,
            humanize=resolved_humanize,
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
