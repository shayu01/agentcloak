"""Frame commands — list, focus."""

from __future__ import annotations

import typer

from agentcloak.cli.output import output_json
from agentcloak.client import DaemonClient

__all__ = ["app"]

app = typer.Typer()


@app.command("list")
def frame_list() -> None:
    """List all frames on the current page."""
    client = DaemonClient()
    result = client.frame_list_sync()
    data = result.get("data", result)
    seq = result.get("seq", 0)
    output_json(data, seq=seq)


@app.command("focus")
def frame_focus(
    name: str | None = typer.Option(
        None, "--name", "-n", help="Frame name to switch to."
    ),
    url: str | None = typer.Option(None, "--url", help="URL substring to match frame."),
    main: bool = typer.Option(False, "--main", help="Switch back to main frame."),
) -> None:
    """Switch focus to a frame."""
    if not main and name is None and url is None:
        typer.echo(
            "Error: provide --name, --url, or --main",
            err=True,
        )
        raise typer.Exit(2)

    client = DaemonClient()
    result = client.frame_focus_sync(name=name, url=url, main=main)
    data = result.get("data", result)
    seq = result.get("seq", data.get("seq", 0))
    output_json(data, seq=seq)
