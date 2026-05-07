"""Network request monitoring command."""

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


@app.command("network")
def network_list(
    since: int = typer.Option(
        0, "--since", help="Filter requests after this seq number."
    ),
) -> None:
    """List captured network requests."""
    client = DaemonClient()
    result = _run(client.network(since=since))
    data = result.get("data", result)
    seq = result.get("seq", 0)
    output_json(data, seq=seq)
