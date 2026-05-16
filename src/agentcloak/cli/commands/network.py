"""Network request monitoring command.

Exposed as a flat ``agentcloak network`` (no nested ``network network``) via
the same ``@app.callback(invoke_without_command=True)`` pattern used by
``doctor`` — F3 from dogfood-v0.2.0-pre-release.
"""

from __future__ import annotations

import typer

from agentcloak.cli.output import output_json
from agentcloak.client import DaemonClient

__all__ = ["app"]

app = typer.Typer(invoke_without_command=True)


@app.callback(invoke_without_command=True)
def network_list(
    ctx: typer.Context,
    since: int = typer.Option(
        0, "--since", help="Filter requests after this seq number."
    ),
) -> None:
    """List captured network requests."""
    # A registered subcommand (none today) would take precedence; otherwise we
    # run the callback. Keep the check so future subcommands can opt out.
    if ctx.invoked_subcommand is not None:
        return
    client = DaemonClient()
    result = client.network_sync(since=since)
    data = result.get("data", result)
    seq = result.get("seq", 0)
    output_json(data, seq=seq)
