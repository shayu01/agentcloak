"""Frame commands — list, focus."""

from __future__ import annotations

import typer

from agentcloak.cli._dispatch import dispatch_text_or_json
from agentcloak.cli.output import error
from agentcloak.client import DaemonClient

__all__ = ["app"]

app = typer.Typer()


@app.command("list")
def frame_list() -> None:
    """List all frames on the current page."""
    dispatch_text_or_json(DaemonClient(), "GET", "/frame/list")


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
        error("missing frame selector", "provide --name, --url, or --main")
    body: dict[str, object] = {"main": main}
    if name is not None:
        body["name"] = name
    if url is not None:
        body["url"] = url
    dispatch_text_or_json(DaemonClient(), "POST", "/frame/focus", json_body=body)
