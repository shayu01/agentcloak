"""Launch command — hot-switch the daemon's active browser tier.

Before v0.3.0 ``agentcloak launch`` was a synonym for "restart the daemon
with these flags". As of the dynamic-tier-switch work it just POSTs to
``/launch``: the daemon stays up, only the active context swaps.
"""

from __future__ import annotations

import typer

from agentcloak.cli.output import output_json

__all__ = ["app", "launch"]

app = typer.Typer()


def _do_launch(tier: str, profile: str | None) -> None:
    from agentcloak.client import DaemonClient

    client = DaemonClient()
    result = client.launch_sync(tier=tier, profile=profile)
    data = result.get("data", result)
    seq = result.get("seq", 0)
    output_json(data, seq=seq)


@app.callback(invoke_without_command=True)
def launch(
    tier: str = typer.Option(
        "auto",
        "--tier",
        "-t",
        help=("Browser tier: auto (default: cloak), cloak, playwright, remote_bridge."),
    ),
    profile: str | None = typer.Option(
        None,
        "--profile",
        "-p",
        help=(
            "Named browser profile for persistent cookies/state. Only "
            "applies to local tiers."
        ),
    ),
) -> None:
    """Hot-switch the daemon's active browser tier (no restart)."""
    _do_launch(tier, profile)
