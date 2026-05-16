"""Capture commands — record, export, and analyze network traffic."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003 — Typer needs runtime access

import orjson
import typer

from agentcloak.cli.output import output_json
from agentcloak.client import DaemonClient

__all__ = ["app"]

app = typer.Typer()


@app.command("start")
def capture_start() -> None:
    """Start recording network traffic."""
    client = DaemonClient()
    result = client.capture_start_sync()
    output_json(result.get("data", result), seq=result.get("seq", 0))


@app.command("stop")
def capture_stop() -> None:
    """Stop recording network traffic."""
    client = DaemonClient()
    result = client.capture_stop_sync()
    output_json(result.get("data", result), seq=result.get("seq", 0))


@app.command("status")
def capture_status() -> None:
    """Show capture recording status."""
    client = DaemonClient()
    result = client.capture_status_sync()
    output_json(result.get("data", result), seq=result.get("seq", 0))


@app.command("export")
def capture_export(
    format: str = typer.Option("har", help="Export format: har or json."),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Write the export to a file instead of stdout (HAR can be large).",
    ),
) -> None:
    """Export captured traffic as HAR or JSON."""
    client = DaemonClient()
    result = client.capture_export_sync(fmt=format)
    data = result.get("data", result)
    seq = int(result.get("seq", 0) or 0)

    if output is not None:
        # HAR exports easily blow past the agent's context window; writing to
        # disk keeps the stdout payload small and aligns with the existing
        # ``screenshot -o`` ergonomic (F5 from dogfood-v0.2.0-pre-release).
        output.write_bytes(orjson.dumps(data))
        output_json(
            {
                "saved": str(output),
                "format": format,
                "bytes": output.stat().st_size,
            },
            seq=seq,
        )
        return

    output_json(data, seq=seq)


@app.command("analyze")
def capture_analyze(
    domain: str = typer.Option("", help="Filter by domain."),
) -> None:
    """Analyze captured traffic for API patterns."""
    client = DaemonClient()
    result = client.capture_analyze_sync(domain=domain)
    output_json(result.get("data", result), seq=result.get("seq", 0))


@app.command("clear")
def capture_clear() -> None:
    """Clear all captured traffic data."""
    client = DaemonClient()
    result = client.capture_clear_sync()
    output_json(result.get("data", result), seq=result.get("seq", 0))


@app.command("replay")
def capture_replay(
    url: str = typer.Argument(..., help="URL of the request to replay."),
    method: str = typer.Option("GET", "--method", "-m", help="HTTP method."),
) -> None:
    """Replay the most recent captured request matching url+method."""
    client = DaemonClient()
    result = client.capture_replay_sync(url=url, method=method)
    output_json(result.get("data", result), seq=result.get("seq", 0))
