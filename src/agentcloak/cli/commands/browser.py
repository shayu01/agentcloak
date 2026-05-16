"""Browser commands — open, screenshot, snapshot, state."""

from __future__ import annotations

import base64
from pathlib import Path  # noqa: TC003 — Typer needs runtime access

import typer

from agentcloak.cli.output import output_json
from agentcloak.client import DaemonClient

__all__ = ["app"]

app = typer.Typer()


@app.command("navigate")
def browser_navigate(
    url: str = typer.Argument(help="URL to navigate to."),
    timeout: float | None = typer.Option(
        None,
        "--timeout",
        help="Navigation timeout in seconds (default: config.navigation_timeout).",
    ),
    snapshot: bool = typer.Option(
        False,
        "--snapshot",
        help="Attach compact snapshot to navigate result.",
    ),
    snapshot_mode: str = typer.Option(
        "compact",
        "--snapshot-mode",
        help="Snapshot mode when --snapshot is used: compact, accessible.",
    ),
) -> None:
    """Navigate to a URL."""
    client = DaemonClient()
    result = client.navigate_sync(
        url,
        timeout=timeout,
        include_snapshot=snapshot,
        snapshot_mode=snapshot_mode,
    )
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
    quality: int | None = typer.Option(
        None,
        "--quality",
        "-q",
        help=(
            "JPEG quality 0-100 (default: config.screenshot_quality, ignored for png)."
        ),
    ),
) -> None:
    """Take a screenshot."""
    client = DaemonClient()
    result = client.screenshot_sync(full_page=full_page, format=format, quality=quality)
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
    frames: bool = typer.Option(
        False,
        "--frames",
        help="Include iframe content in the snapshot (merges child frame AX trees).",
    ),
    diff: bool = typer.Option(
        False,
        "--diff",
        help="Compare with previous snapshot, mark [+] added and [~] changed.",
    ),
) -> None:
    """Get page snapshot (accessible tree, DOM, or text content)."""
    client = DaemonClient()
    result = client.snapshot_sync(
        mode=mode,
        max_chars=max_chars,
        max_nodes=max_nodes,
        focus=focus,
        offset=offset,
        frames=frames,
        diff=diff,
    )
    data = result.get("data", result)
    seq = result.get("seq", 0)
    output_json(data, seq=seq)


@app.command("resume")
def browser_resume() -> None:
    """Get resume snapshot for session recovery."""
    client = DaemonClient()
    result = client.resume_sync()
    data = result.get("data", result)
    seq = result.get("seq", 0)
    output_json(data, seq=seq)
