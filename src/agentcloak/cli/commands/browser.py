"""Browser commands — open, screenshot, snapshot, state."""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path  # noqa: TC003 — Typer needs runtime access
from typing import Any

import typer

from agentcloak.cli.client import DaemonClient
from agentcloak.cli.output import output_json

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
    format: str = typer.Option(
        "jpeg", "--format", "-f", help="Image format: jpeg or png."
    ),
    quality: int = typer.Option(
        80, "--quality", "-q", help="JPEG quality 0-100 (ignored for png)."
    ),
) -> None:
    """Take a screenshot."""
    client = DaemonClient()
    result = _run(
        client.screenshot(full_page=full_page, format=format, quality=quality)
    )
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
        "accessible",
        "--mode",
        "-m",
        help="Snapshot mode: accessible, compact, dom, content.",
    ),
    max_chars: int = typer.Option(
        0,
        "--max-chars",
        help="Truncate tree_text to this many characters (0 = no limit).",
    ),
    max_nodes: int = typer.Option(
        0,
        "--max-nodes",
        help="Truncate after N nodes (0 = no limit).",
    ),
    focus: int = typer.Option(
        0,
        "--focus",
        help="Expand subtree around element [N] from cached snapshot.",
    ),
    offset: int = typer.Option(
        0,
        "--offset",
        help="Start output from Nth element (pagination).",
    ),
) -> None:
    """Get page snapshot (accessible tree, DOM, or text content)."""
    client = DaemonClient()
    result = _run(
        client.snapshot(
            mode=mode,
            max_chars=max_chars,
            max_nodes=max_nodes,
            focus=focus,
            offset=offset,
        )
    )
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
