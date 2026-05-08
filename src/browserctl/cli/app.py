"""Root Typer app, global flags, and structlog setup."""

from __future__ import annotations

import logging
import sys

import structlog
import typer

from browserctl import __version__
from browserctl.cli.output import set_pretty
from browserctl.core.errors import AgentBrowserError

__all__ = ["app", "main"]

app = typer.Typer(
    name="browserctl",
    help="Browser CLI toolchain for AI agents.",
    no_args_is_help=True,
    add_completion=False,
)


def _configure_logging(*, verbosity: int) -> None:
    level = {0: logging.WARNING, 1: logging.INFO}.get(verbosity, logging.DEBUG)
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(level),
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.dev.ConsoleRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"browserctl {__version__}")
        raise typer.Exit


@app.callback()
def _root_callback(  # pyright: ignore[reportUnusedFunction]
    verbose: int = typer.Option(
        0, "--verbose", "-v", count=True, help="Increase log verbosity."
    ),
    pretty: bool = typer.Option(False, "--pretty", help="Pretty-print JSON output."),
    _version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version.",
    ),
) -> None:
    set_pretty(enabled=pretty)
    _configure_logging(verbosity=verbose)


def _register_commands() -> None:
    from browserctl.cli.commands import (
        action,
        bridge_cmd,
        browser,
        capture_cmd,
        cookies_cmd,
        daemon_cmd,
        doctor,
        fetch,
        js,
        network,
        profile,
        site_cmd,
    )

    app.add_typer(doctor.app, name="doctor", help="Self-check and diagnostics.")
    app.add_typer(daemon_cmd.app, name="daemon", help="Daemon lifecycle management.")
    app.add_typer(
        browser.app, name="browser", help="Browser navigation and inspection."
    )
    app.add_typer(js.app, name="js", help="JavaScript execution.")
    app.add_typer(network.app, name="network", help="Network request monitoring.")
    app.add_typer(
        action.app,
        name="do",
        help="Page actions: click, fill, type, scroll, hover, select, press.",
    )
    app.add_typer(
        profile.app,
        name="profile",
        help="Browser profile management: create, list, delete, launch.",
    )
    app.add_typer(
        fetch.app,
        name="fetch",
        help="HTTP fetch with browser cookies.",
    )
    app.add_typer(
        bridge_cmd.app,
        name="bridge",
        help="Remote bridge: connect Chrome extension to daemon.",
    )
    app.add_typer(
        cookies_cmd.app,
        name="cookies",
        help="Cookie management: export from remote Chrome.",
    )
    app.add_typer(
        capture_cmd.app,
        name="capture",
        help="Network traffic capture: record, export, analyze.",
    )
    app.add_typer(
        site_cmd.app,
        name="adapter",
        help="Adapters: list, info, run, scaffold.",
    )


_register_commands()


def main() -> None:
    from browserctl.cli.output import output_error

    try:
        app()
    except AgentBrowserError as exc:
        output_error(exc)
        raise typer.Exit(1) from exc
