"""Daemon lifecycle commands — start, stop, health."""

from __future__ import annotations

import asyncio
import time

import httpx
import typer

from agentcloak.cli.output import output_error, output_json
from agentcloak.core.errors import DaemonConnectionError

__all__ = ["app"]

app = typer.Typer()

# When ``daemon start -b`` returns, the daemon is launched but uvicorn is still
# binding the socket. The first subsequent CLI/MCP request then races the
# spawn and triggers the auto-start path's "daemon_auto_starting" warning. Poll
# /health for a short budget so we only return once the daemon is reachable.
_BG_READY_BUDGET_S = 3.0
_BG_READY_POLL_INTERVAL_S = 0.2
_BG_READY_PROBE_TIMEOUT_S = 0.5


def _wait_for_daemon_ready(base_url: str) -> bool:
    """Poll ``GET /health`` until 200 or budget elapses. Returns ``True`` on success."""
    deadline = time.monotonic() + _BG_READY_BUDGET_S
    while time.monotonic() < deadline:
        try:
            with httpx.Client(
                base_url=base_url, timeout=_BG_READY_PROBE_TIMEOUT_S
            ) as client:
                resp = client.get("/health")
                if resp.status_code == 200:
                    return True
        except httpx.HTTPError:
            pass
        time.sleep(_BG_READY_POLL_INTERVAL_S)
    return False


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
    resolved_humanize: bool | None = None
    if humanize:
        resolved_humanize = True
    elif no_humanize:
        resolved_humanize = False

    if background:
        from agentcloak.client import DaemonClient
        from agentcloak.core.config import load_config, resolve_tier

        client = DaemonClient(host=host, port=port, auto_start=False)
        pid = client.spawn_background(
            host=host,
            port=port,
            headless=headless,
            profile=profile,
            humanize=resolved_humanize,
        )
        _, cfg = load_config()
        resolved_tier = resolve_tier(cfg.default_tier)

        # Block until daemon is reachable so subsequent CLI/MCP requests don't
        # race the spawn and trigger the auto-start warning path.
        bind_host = host or cfg.daemon_host
        bind_port = port or cfg.daemon_port
        ready = _wait_for_daemon_ready(f"http://{bind_host}:{bind_port}")

        output_json(
            {
                "pid": pid,
                "background": True,
                "profile": profile,
                "tier": resolved_tier,
                "ready": ready,
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
            humanize=resolved_humanize,
        )
    )


@app.command("stop")
def daemon_stop(
    host: str | None = typer.Option(None, "--host"),
    port: int | None = typer.Option(None, "--port"),
) -> None:
    """Stop the running daemon."""
    from agentcloak.client import DaemonClient

    client = DaemonClient(host=host, port=port, auto_start=False)
    client.shutdown_sync()
    output_json({"stopped": True}, seq=0)


@app.command("cdp-endpoint")
def daemon_cdp_endpoint(
    host: str | None = typer.Option(None, "--host"),
    port: int | None = typer.Option(None, "--port"),
) -> None:
    """Get the CDP WebSocket URL for the current browser."""
    from agentcloak.client import DaemonClient

    client = DaemonClient(host=host, port=port)
    result = client.cdp_endpoint_sync()
    output_json(result.get("data", result), seq=result.get("seq", 0))


@app.command("health")
def daemon_health(
    host: str | None = typer.Option(None, "--host"),
    port: int | None = typer.Option(None, "--port"),
) -> None:
    """Show daemon health including stealth tier, current URL, capture state.

    Mirrors MCP ``agentcloak_status(query='health')`` so both surfaces report
    the same diagnostic detail (F4 from dogfood-v0.2.0-pre-release).
    """
    from agentcloak.client import DaemonClient

    client = DaemonClient(host=host, port=port, auto_start=False)
    try:
        result = client.health_sync()
    except DaemonConnectionError as e:
        output_error(e)
        raise typer.Exit(1) from e

    # ``/health`` is a flat dict (DiagnosticService.health does not wrap in
    # ``_ok``). Strip ``ok`` from the data payload since the envelope already
    # carries it; surface ``seq`` and the rest of the rich health details.
    seq = int(result.get("seq", 0) or 0)
    payload = {k: v for k, v in result.items() if k != "ok"}
    output_json(payload, seq=seq)
