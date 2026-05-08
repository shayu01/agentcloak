"""Browser commands — open, screenshot, snapshot, state."""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path  # noqa: TC003 — Typer needs runtime access
from typing import Any

import typer

from browserctl.cli.client import DaemonClient
from browserctl.cli.output import output_json

__all__ = ["app"]

app = typer.Typer()


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


@app.command("open")
def browser_open(
    url: str = typer.Argument(help="URL to navigate to."),
    timeout: float = typer.Option(
        30.0, "--timeout", help="Navigation timeout in seconds."
    ),
) -> None:
    """Navigate to a URL."""
    client = DaemonClient()
    result = _run(client.navigate(url, timeout=timeout))
    data = result.get("data", result)
    seq = result.get("seq", data.get("seq", 0))
    output_json(data, seq=seq)


@app.command("screenshot")
def browser_screenshot(
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Save to file instead of base64."
    ),
    full_page: bool = typer.Option(
        False, "--full-page", help="Capture full scrollable page."
    ),
) -> None:
    """Take a screenshot."""
    client = DaemonClient()
    result = _run(client.screenshot(full_page=full_page))
    data = result.get("data", result)
    seq = result.get("seq", 0)

    if output:
        b64_str: str = data["base64"]
        output.write_bytes(base64.b64decode(b64_str))
        output_json({"saved": str(output), "size": data.get("size", 0)}, seq=seq)
    else:
        output_json(data, seq=seq)


@app.command("snapshot")
def browser_snapshot(
    mode: str = typer.Option(
        "accessible", "--mode", "-m", help="Snapshot mode: accessible, dom, content."
    ),
) -> None:
    """Get page snapshot (accessible tree, DOM, or text content)."""
    client = DaemonClient()
    result = _run(client.snapshot(mode=mode))
    data = result.get("data", result)
    seq = result.get("seq", 0)
    output_json(data, seq=seq)


@app.command("state")
def browser_state() -> None:
    """Get full browser state."""
    client = DaemonClient()
    result = _run(client.state())
    data = result.get("data", result)
    seq = result.get("seq", 0)
    output_json(data, seq=seq)


@app.command("resume")
def browser_resume() -> None:
    """Get resume snapshot for session recovery."""
    client = DaemonClient()
    result = _run(client.resume())
    data = result.get("data", result)
    seq = result.get("seq", 0)
    output_json(data, seq=seq)
