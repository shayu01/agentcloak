"""Tab commands — list, new, close, switch."""

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


@app.command("list")
def tab_list() -> None:
    """List all open tabs."""
    client = DaemonClient()
    result = _run(client.tab_list())
    data = result.get("data", result)
    seq = result.get("seq", 0)
    output_json(data, seq=seq)


@app.command("new")
def tab_new(
    url: str | None = typer.Argument(None, help="URL to navigate the new tab to."),
) -> None:
    """Create a new tab, optionally navigating to a URL."""
    client = DaemonClient()
    result = _run(client.tab_new(url=url))
    data = result.get("data", result)
    seq = result.get("seq", 0)
    output_json(data, seq=seq)


@app.command("close")
def tab_close(
    tab_id: int = typer.Argument(help="ID of the tab to close."),
) -> None:
    """Close a tab by ID."""
    client = DaemonClient()
    result = _run(client.tab_close(tab_id))
    data = result.get("data", result)
    seq = result.get("seq", 0)
    output_json(data, seq=seq)


@app.command("switch")
def tab_switch(
    tab_id: int = typer.Argument(help="ID of the tab to switch to."),
) -> None:
    """Switch the active tab."""
    client = DaemonClient()
    result = _run(client.tab_switch(tab_id))
    data = result.get("data", result)
    seq = result.get("seq", 0)
    output_json(data, seq=seq)
