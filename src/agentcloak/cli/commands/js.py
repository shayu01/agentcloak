"""JavaScript execution command."""

from __future__ import annotations

import typer

from agentcloak.cli.output import output_json
from agentcloak.client import DaemonClient

__all__ = ["app"]

app = typer.Typer()


@app.command("evaluate")
def js_evaluate(
    code: str = typer.Argument(help="JavaScript code to evaluate."),
    world: str = typer.Option(
        "main", help="Execution context: 'main' (page globals) or 'utility' (isolated)."
    ),
) -> None:
    """Evaluate JavaScript in the page context."""
    client = DaemonClient()
    result = client.evaluate_sync(code, world=world)
    data = result.get("data", result)
    seq = result.get("seq", 0)
    output_json(data, seq=seq)
