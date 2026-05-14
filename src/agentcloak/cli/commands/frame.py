"""Frame commands — list, focus."""

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


@app.command("list")
def frame_list() -> None:
    """List all frames on the current page."""
    client = DaemonClient()
    result = _run(client.frame_list())
    data = result.get("data", result)
    seq = result.get("seq", 0)
    output_json(data, seq=seq)


@app.command("focus")
def frame_focus(
    name: str | None = typer.Option(
        None, "--name", "-n", help="Frame name to switch to."
    ),
    url: str | None = typer.Option(
        None, "--url", help="URL substring to match frame."
    ),
    main: bool = typer.Option(
        False, "--main", help="Switch back to main frame."
    ),
) -> None:
    """Switch focus to a frame."""
    if not main and name is None and url is None:
        typer.echo(
            "Error: provide --name, --url, or --main",
            err=True,
        )
        raise typer.Exit(2)

    client = DaemonClient()
    result = _run(client.frame_focus(name=name, url=url, main=main))
    data = result.get("data", result)
    seq = result.get("seq", data.get("seq", 0))
    output_json(data, seq=seq)
