"""Upload command — file upload to input elements."""

from __future__ import annotations

import asyncio
from typing import Any

import typer

from agentcloak.cli.client import DaemonClient
from agentcloak.cli.output import output_json

__all__ = ["app"]

app = typer.Typer(invoke_without_command=True)


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


@app.callback(invoke_without_command=True)
def do_upload(
    index: int = typer.Option(
        ..., "--index", "-i", help="Element index [N] of file input."
    ),
    file: list[str] = typer.Option(
        ..., "--file", "-f", help="File path(s) to upload."
    ),
) -> None:
    """Upload file(s) to a file input element."""
    client = DaemonClient()
    result = _run(client.upload(index=index, files=file))
    data = result.get("data", result)
    seq = result.get("seq", data.get("seq", 0))
    output_json(data, seq=seq)
