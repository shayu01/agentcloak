"""Cookie commands — export cookies from remote Chrome."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003 — Typer needs runtime access

import typer

from agentcloak.cli.output import output_json
from agentcloak.client import DaemonClient

__all__ = ["app"]

app = typer.Typer()


@app.command("export")
def cookies_export(
    url: str | None = typer.Option(None, "--url", "-u", help="URL to get cookies for."),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Save cookies to file."
    ),
) -> None:
    """Export cookies from remote Chrome via bridge."""
    client = DaemonClient()
    result = client.cookies_export_sync(url=url)
    data = result.get("data", result)
    seq = result.get("seq", 0)

    if output:
        import orjson

        output.write_bytes(orjson.dumps(data, option=orjson.OPT_INDENT_2))
        output_json(
            {"saved": str(output), "count": len(data.get("cookies", []))},
            seq=seq,
        )
    else:
        output_json(data, seq=seq)
