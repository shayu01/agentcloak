"""CDP commands — endpoint."""

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


@app.command("endpoint")
def cdp_endpoint() -> None:
    """Get the CDP WebSocket endpoint URL for jshookmcp browser_attach."""
    client = DaemonClient()
    result = _run(client.cdp_endpoint())
    data = result.get("data", result)
    seq = result.get("seq", 0)
    output_json(data, seq=seq)
