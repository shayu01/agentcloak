"""Wait command — conditional waiting."""

from __future__ import annotations

import typer

from agentcloak.cli.output import output_json
from agentcloak.client import DaemonClient

__all__ = ["app"]

app = typer.Typer(invoke_without_command=True)


@app.callback(invoke_without_command=True)
def do_wait(
    selector: str | None = typer.Option(
        None, "--selector", "-s", help="CSS selector to wait for."
    ),
    url: str | None = typer.Option(
        None, "--url", help="URL pattern to wait for (glob)."
    ),
    load: str | None = typer.Option(
        None,
        "--load",
        help="Load state: load, domcontentloaded, networkidle.",
    ),
    js: str | None = typer.Option(
        None, "--js", help="JS expression that must return truthy."
    ),
    ms: int | None = typer.Option(None, "--ms", help="Milliseconds to sleep."),
    timeout: int | None = typer.Option(
        None,
        "--timeout",
        help="Timeout in milliseconds (default: config.action_timeout).",
    ),
    state: str = typer.Option(
        "visible",
        "--state",
        help="Element state: visible/hidden/attached/detached.",
    ),
) -> None:
    """Wait for a condition before continuing."""
    # Determine condition from flags
    if selector is not None:
        condition, value = "selector", selector
    elif url is not None:
        condition, value = "url", url
    elif load is not None:
        condition, value = "load", load
    elif js is not None:
        condition, value = "js", js
    elif ms is not None:
        condition, value = "ms", str(ms)
    else:
        typer.echo(
            "Error: provide one of --selector, --url, --load, --js, or --ms",
            err=True,
        )
        raise typer.Exit(2)

    client = DaemonClient()
    result = client.wait_sync(
        condition=condition,
        value=value,
        timeout=timeout,
        state=state,
    )
    data = result.get("data", result)
    seq = result.get("seq", data.get("seq", 0))
    output_json(data, seq=seq)
