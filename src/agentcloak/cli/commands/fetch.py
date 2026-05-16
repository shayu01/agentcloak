"""Fetch command — HTTP request with browser cookies.

Exposed as a flat ``agentcloak fetch <URL>`` (no nested ``fetch fetch``) via
``@app.callback(invoke_without_command=True)`` — F3 from
dogfood-v0.2.0-pre-release.
"""

from __future__ import annotations

from pathlib import Path  # noqa: TC003 — Typer needs runtime access

import typer

from agentcloak.cli.output import output_json
from agentcloak.client import DaemonClient

__all__ = ["app"]

app = typer.Typer(invoke_without_command=True)


def _parse_header(raw: str) -> tuple[str, str]:
    """Parse 'Key: Value' into a (key, value) pair."""
    if ":" not in raw:
        msg = f"Invalid header format: '{raw}' (expected 'Key: Value')"
        raise typer.BadParameter(msg)
    key, _, value = raw.partition(":")
    return key.strip(), value.strip()


@app.callback(invoke_without_command=True)
def fetch_url(
    ctx: typer.Context,
    url: str | None = typer.Argument(None, help="URL to fetch."),
    method: str = typer.Option("GET", "--method", "-m", help="HTTP method."),
    body: str | None = typer.Option(None, "--body", "-b", help="Request body."),
    header: list[str] | None = typer.Option(
        None, "--header", "-H", help="Header in 'Key: Value' format (repeatable)."
    ),
    timeout: float | None = typer.Option(
        None,
        "--timeout",
        help="Request timeout in seconds (default: config.navigation_timeout).",
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Save response body to file."
    ),
) -> None:
    """HTTP fetch using browser cookies and user agent."""
    if ctx.invoked_subcommand is not None:
        return
    if url is None:
        # Argument is declared optional so ``--help`` works on the bare group;
        # missing URL on actual invocation is still a usage error.
        raise typer.BadParameter("URL argument is required")

    headers: dict[str, str] | None = None
    if header:
        headers = {}
        for h in header:
            k, v = _parse_header(h)
            headers[k] = v

    client = DaemonClient()
    result = client.fetch_sync(
        url,
        method=method,
        body=body,
        headers=headers,
        timeout=timeout,
    )
    data = result.get("data", result)
    seq = result.get("seq", data.get("seq", 0))

    if output:
        resp_body: str = data.get("body", "")
        output.write_text(resp_body, encoding="utf-8")
        output_json(
            {
                "saved": str(output),
                "status": data.get("status"),
                "content_type": data.get("content_type", ""),
                "truncated": data.get("truncated", False),
            },
            seq=seq,
        )
    else:
        output_json(data, seq=seq)
