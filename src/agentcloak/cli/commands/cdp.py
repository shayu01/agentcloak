"""CDP commands — endpoint."""

from __future__ import annotations

import typer

from agentcloak.cli.output import output_json
from agentcloak.client import DaemonClient

__all__ = ["app"]

app = typer.Typer()


@app.command("endpoint")
def cdp_endpoint() -> None:
    """Get the CDP WebSocket endpoint URL for jshookmcp browser_attach."""
    client = DaemonClient()
    result = client.cdp_endpoint_sync()
    data = result.get("data", result)
    seq = result.get("seq", 0)
    output_json(data, seq=seq)
