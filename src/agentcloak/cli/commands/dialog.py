"""Dialog commands — status, accept, dismiss."""

from __future__ import annotations

import asyncio
from typing import Any

import typer

from agentcloak.cli.client import DaemonClient
from agentcloak.cli.output import output_json

__all__ = ["app"]

app = typer.Typer()


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


@app.command("status")
def dialog_status() -> None:
    """Check for a pending dialog."""
    client = DaemonClient()
    result = _run(client.dialog_status())
    data = result.get("data", result)
    seq = result.get("seq", 0)
    output_json(data, seq=seq)


@app.command("accept")
def dialog_accept(
    text: str | None = typer.Option(
        None, "--text", "-t", help="Reply text for prompt dialogs."
    ),
) -> None:
    """Accept the pending dialog."""
    client = DaemonClient()
    result = _run(client.dialog_handle("accept", text=text))
    data = result.get("data", result)
    seq = result.get("seq", data.get("seq", 0))
    output_json(data, seq=seq)


@app.command("dismiss")
def dialog_dismiss() -> None:
    """Dismiss the pending dialog."""
    client = DaemonClient()
    result = _run(client.dialog_handle("dismiss"))
    data = result.get("data", result)
    seq = result.get("seq", data.get("seq", 0))
    output_json(data, seq=seq)
