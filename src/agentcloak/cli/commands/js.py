"""JavaScript execution command."""

from __future__ import annotations

import asyncio
from typing import Any

import typer

from agentcloak.cli.client import DaemonClient
from agentcloak.cli.output import output_json

__all__ = ["app"]

app = typer.Typer()


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


@app.command("execute-js")
def execute_js(
    code: str = typer.Argument(help="JavaScript code to evaluate."),
    world: str = typer.Option(
        "main", help="Execution context: 'main' (page globals) or 'utility' (isolated)."
    ),
) -> None:
    """Execute JavaScript in the page context."""
    client = DaemonClient()
    result = _run(client.evaluate(code, world=world))
    data = result.get("data", result)
    seq = result.get("seq", 0)
    output_json(data, seq=seq)
