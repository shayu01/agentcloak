"""Action commands — click, fill, type, scroll, hover, select, press, batch."""

from __future__ import annotations

import asyncio
from pathlib import Path  # noqa: TC003 — Typer needs runtime access
from typing import Any

import orjson
import typer

from agentcloak.cli.client import DaemonClient
from agentcloak.cli.output import output_json

__all__ = ["app"]

app = typer.Typer()


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


@app.command("click")
def do_click(
    index: int | None = typer.Option(None, "--index", "-i", help="Element index [N]."),
    target: int | None = typer.Option(None, "--target", help="Alias for --index."),
    x: float | None = typer.Option(None, "--x", help="X coordinate (fallback)."),
    y: float | None = typer.Option(None, "--y", help="Y coordinate (fallback)."),
    button: str = typer.Option("left", "--button", help="Mouse button."),
    click_count: int = typer.Option(1, "--click-count", help="Number of clicks."),
) -> None:
    """Click an element by index or coordinates."""
    resolved = target if index is None else index
    client = DaemonClient()
    kwargs: dict[str, Any] = {
        "button": button,
        "click_count": click_count,
    }
    if x is not None:
        kwargs["x"] = x
    if y is not None:
        kwargs["y"] = y
    result = _run(client.action("click", index=resolved, **kwargs))
    data = result.get("data", result)
    seq = result.get("seq", data.get("seq", 0))
    output_json(data, seq=seq)


@app.command("fill")
def do_fill(
    index: int | None = typer.Option(None, "--index", "-i", help="Element index [N]."),
    target: int | None = typer.Option(None, "--target", help="Alias for --index."),
    text: str = typer.Option(..., "--text", "-t", help="Text to fill."),
) -> None:
    """Fill an input element (clear then set value)."""
    resolved = target if index is None else index
    if resolved is None:
        typer.echo("Error: provide --target or --index", err=True)
        raise typer.Exit(2)
    client = DaemonClient()
    result = _run(client.action("fill", index=resolved, text=text))
    data = result.get("data", result)
    seq = result.get("seq", data.get("seq", 0))
    output_json(data, seq=seq)


@app.command("type")
def do_type(
    index: int | None = typer.Option(None, "--index", "-i", help="Element index [N]."),
    target: int | None = typer.Option(None, "--target", help="Alias for --index."),
    text: str = typer.Option(..., "--text", "-t", help="Text to type."),
    delay: float = typer.Option(0, "--delay", help="Delay between keystrokes in ms."),
) -> None:
    """Type text character by character (per-key events)."""
    resolved = target if index is None else index
    if resolved is None:
        typer.echo("Error: provide --target or --index", err=True)
        raise typer.Exit(2)
    client = DaemonClient()
    result = _run(client.action("type", index=resolved, text=text, delay=delay))
    data = result.get("data", result)
    seq = result.get("seq", data.get("seq", 0))
    output_json(data, seq=seq)


@app.command("scroll")
def do_scroll(
    index: int | None = typer.Option(None, "--index", "-i", help="Element to scroll."),
    target: int | None = typer.Option(None, "--target", help="Alias for --index."),
    direction: str = typer.Option(
        "down", "--direction", "-d", help="up/down/left/right."
    ),
    amount: int = typer.Option(300, "--amount", help="Scroll amount in pixels."),
) -> None:
    """Scroll the page or an element into view."""
    resolved = target if index is None else index
    client = DaemonClient()
    result = _run(
        client.action(
            "scroll",
            index=resolved,
            direction=direction,
            amount=amount,
        )
    )
    data = result.get("data", result)
    seq = result.get("seq", data.get("seq", 0))
    output_json(data, seq=seq)


@app.command("hover")
def do_hover(
    index: int | None = typer.Option(None, "--index", "-i", help="Element index [N]."),
    target: int | None = typer.Option(None, "--target", help="Alias for --index."),
    x: float | None = typer.Option(None, "--x", help="X coordinate (fallback)."),
    y: float | None = typer.Option(None, "--y", help="Y coordinate (fallback)."),
) -> None:
    """Hover over an element or coordinates."""
    resolved = target if index is None else index
    client = DaemonClient()
    kwargs: dict[str, Any] = {}
    if x is not None:
        kwargs["x"] = x
    if y is not None:
        kwargs["y"] = y
    result = _run(client.action("hover", index=resolved, **kwargs))
    data = result.get("data", result)
    seq = result.get("seq", data.get("seq", 0))
    output_json(data, seq=seq)


@app.command("select")
def do_select(
    index: int | None = typer.Option(None, "--index", "-i", help="Element index [N]."),
    target: int | None = typer.Option(None, "--target", help="Alias for --index."),
    value: str | None = typer.Option(None, "--value", help="Option value."),
    label: str | None = typer.Option(None, "--label", help="Option display text."),
) -> None:
    """Select a dropdown option."""
    resolved = target if index is None else index
    if resolved is None:
        typer.echo("Error: provide --target or --index", err=True)
        raise typer.Exit(2)
    client = DaemonClient()
    kwargs: dict[str, Any] = {}
    if value is not None:
        kwargs["value"] = value
    if label is not None:
        kwargs["label"] = label
    result = _run(client.action("select", index=resolved, **kwargs))
    data = result.get("data", result)
    seq = result.get("seq", data.get("seq", 0))
    output_json(data, seq=seq)


@app.command("press")
def do_press(
    key: str = typer.Option(..., "--key", "-k", help="Key to press (Enter, etc.)."),
    target: int | None = typer.Option(
        None, "--target", help="Element index [N] to focus before pressing."
    ),
) -> None:
    """Press a keyboard key."""
    client = DaemonClient()
    result = _run(client.action("press", index=target, key=key))
    data = result.get("data", result)
    seq = result.get("seq", data.get("seq", 0))
    output_json(data, seq=seq)


@app.command("batch")
def do_batch(
    calls_file: Path = typer.Option(
        ..., "--calls-file", help="JSONL file with actions."
    ),
    sleep: float = typer.Option(0.15, "--sleep", help="Seconds between actions."),
) -> None:
    """Execute a batch of actions from a JSONL file."""
    if not calls_file.exists():
        typer.echo(f"File not found: {calls_file}", err=True)
        raise typer.Exit(2)

    actions: list[dict[str, Any]] = []
    raw = calls_file.read_text(encoding="utf-8").strip()
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        actions.append(orjson.loads(line))

    client = DaemonClient()
    result = _run(client.action_batch(actions, sleep=sleep))
    data = result.get("data", result)
    seq = result.get("seq", data.get("seq", 0))
    output_json(data, seq=seq)
