"""Capture commands — record, export, and analyze network traffic."""

from __future__ import annotations

import asyncio
from typing import Any

import typer

from browserctl.cli.client import DaemonClient
from browserctl.cli.output import output_json

__all__ = ["app"]

app = typer.Typer()


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


@app.command("start")
def capture_start() -> None:
    """Start recording network traffic."""
    client = DaemonClient()
    result = _run(client.capture_start())
    output_json(result.get("data", result), seq=result.get("seq", 0))


@app.command("stop")
def capture_stop() -> None:
    """Stop recording network traffic."""
    client = DaemonClient()
    result = _run(client.capture_stop())
    output_json(result.get("data", result), seq=result.get("seq", 0))


@app.command("status")
def capture_status() -> None:
    """Show capture recording status."""
    client = DaemonClient()
    result = _run(client.capture_status())
    output_json(result.get("data", result), seq=result.get("seq", 0))


@app.command("export")
def capture_export(
    format: str = typer.Option("har", help="Export format: har or json."),
) -> None:
    """Export captured traffic as HAR or JSON."""
    client = DaemonClient()
    result = _run(client.capture_export(fmt=format))
    output_json(result.get("data", result), seq=result.get("seq", 0))


@app.command("analyze")
def capture_analyze(
    domain: str = typer.Option("", help="Filter by domain."),
) -> None:
    """Analyze captured traffic for API patterns."""
    client = DaemonClient()
    result = _run(client.capture_analyze(domain=domain))
    output_json(result.get("data", result), seq=result.get("seq", 0))


@app.command("clear")
def capture_clear() -> None:
    """Clear all captured traffic data."""
    client = DaemonClient()
    result = _run(client.capture_clear())
    output_json(result.get("data", result), seq=result.get("seq", 0))


@app.command("replay")
def capture_replay(
    url: str = typer.Argument(..., help="URL of the request to replay."),
    method: str = typer.Option("GET", "--method", "-m", help="HTTP method."),
) -> None:
    """Replay the most recent captured request matching url+method."""
    client = DaemonClient()
    result = _run(client.capture_replay(url=url, method=method))
    output_json(result.get("data", result), seq=result.get("seq", 0))
