"""Fetch command — HTTP request with browser cookies."""

from __future__ import annotations

import asyncio
from pathlib import Path  # noqa: TC003 — Typer needs runtime access
from typing import Any

import typer

from agentcloak.cli.client import DaemonClient
from agentcloak.cli.output import output_json

__all__ = ["app"]

app = typer.Typer()


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _parse_header(raw: str) -> tuple[str, str]:
    """Parse 'Key: Value' into a (key, value) pair."""
    if ":" not in raw:
        msg = f"Invalid header format: '{raw}' (expected 'Key: Value')"
        raise typer.BadParameter(msg)
    key, _, value = raw.partition(":")
    return key.strip(), value.strip()


@app.command("fetch")
def fetch_url(
    url: str = typer.Argument(help="URL to fetch."),
    method: str = typer.Option("GET", "--method", "-m", help="HTTP method."),
    body: str | None = typer.Option(None, "--body", "-b", help="Request body."),
    header: list[str] | None = typer.Option(
        None, "--header", "-H", help="Header in 'Key: Value' format (repeatable)."
    ),
    timeout: float = typer.Option(
        30.0, "--timeout", help="Request timeout in seconds."
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Save response body to file."
    ),
) -> None:
    """HTTP fetch using browser cookies and user agent."""
    headers: dict[str, str] | None = None
    if header:
        headers = {}
        for h in header:
            k, v = _parse_header(h)
            headers[k] = v

    client = DaemonClient()
    result = _run(
        client.fetch(
            url,
            method=method,
            body=body,
            headers=headers,
            timeout=timeout,
        )
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
