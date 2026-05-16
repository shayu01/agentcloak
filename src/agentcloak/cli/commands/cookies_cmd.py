"""Cookie commands — export and import browser cookies."""

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


@app.command("import")
def cookies_import(
    cookies_json: str = typer.Option(
        ...,
        "--cookies",
        "-c",
        help='JSON array of cookie objects, e.g. \'[{"name":"k","value":"v","domain":".example.com","path":"/"}]\'.',
    ),
) -> None:
    """Import cookies into the browser (supports httpOnly)."""
    import orjson

    cookies = orjson.loads(cookies_json)
    client = DaemonClient()
    result = client.cookies_import_sync(cookies=cookies)
    data = result.get("data", result)
    output_json(data, seq=result.get("seq", 0))
