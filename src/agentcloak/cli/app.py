"""Root Typer app, global flags, and structlog setup."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import structlog
import typer

from agentcloak import __version__
from agentcloak.cli.output import set_pretty
from agentcloak.core.errors import AgentBrowserError

__all__ = ["app", "main"]

app = typer.Typer(
    name="agentcloak",
    help="Browser CLI toolchain for AI agents.",
    no_args_is_help=True,
    add_completion=False,
)


def _maybe_emit_first_run_banner() -> None:
    """Nudge new users toward ``doctor`` on the very first invocation.

    The data directory (``~/.agentcloak``) is created on first daemon launch.
    Its absence is therefore a reliable "this is run #1" signal — we don't
    want to add a separate state file just for the banner, and we can't gate
    on the daemon being up because the user might be running ``--version`` or
    ``--help``. The banner only prints to stderr (stdout stays a clean JSON
    envelope for scripts) and never blocks execution.

    Suppress with ``AGENTCLOAK_SKIP_FIRST_RUN_BANNER=1`` for CI / scripted
    environments.
    """
    if os.environ.get("AGENTCLOAK_SKIP_FIRST_RUN_BANNER", "").lower() in (
        "1",
        "true",
        "yes",
    ):
        return
    data_dir = Path.home() / ".agentcloak"
    if data_dir.exists():
        return
    sys.stderr.write(
        "agentcloak: first-run detected — verify your environment with "
        "'agentcloak doctor --fix' (one-time; suppress with "
        "AGENTCLOAK_SKIP_FIRST_RUN_BANNER=1).\n"
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
        typer.echo(f"agentcloak {__version__}")
        raise typer.Exit


def _extract_global_flags(argv: list[str]) -> tuple[list[str], dict[str, object]]:
    """Strip global flags from ``argv`` and return ``(cleaned, state)``.

    The recognised globals are ``--pretty``, ``--verbose`` / ``-v`` (counted),
    and ``--version``. Adding a new one means appending a branch here *and*
    declaring it on :func:`_root_callback` so ``--help`` documents it — keep
    the two in sync.

    Click parses options per-command — a flag declared on the root callback is
    invisible to subcommand parsers, so ``agentcloak doctor --pretty`` fails
    with "No such option: --pretty". Rather than duplicating ``--pretty`` on
    every subcommand (and every nested group), we lift these globals out of
    ``argv`` before Typer ever sees it, apply their effects up-front, and pass
    the cleaned argument list down. The root callback still declares them so
    ``agentcloak --help`` documents them, but they never need to reach Click.

    ``--version`` is honoured here too because it has to short-circuit
    execution; if we let Typer handle it from the root callback, it would only
    fire when placed before the subcommand.
    """
    cleaned: list[str] = []
    pretty = False
    verbose = 0
    version = False
    for arg in argv:
        if arg == "--pretty":
            pretty = True
        elif arg in ("--verbose", "-v"):
            verbose += 1
        elif arg == "--version":
            version = True
        else:
            cleaned.append(arg)
    state: dict[str, object] = {
        "pretty": pretty,
        "verbose": verbose,
        "version": version,
    }
    return cleaned, state


@app.callback()
def _root_callback(  # pyright: ignore[reportUnusedFunction]
    verbose: int = typer.Option(
        0, "--verbose", "-v", count=True, help="Increase log verbosity."
    ),
    pretty: bool = typer.Option(
        False, "--pretty", help="Pretty-print JSON output."
    ),
    _version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version.",
    ),
) -> None:
    # All effects of the declared options are applied in ``main()`` via
    # ``_extract_global_flags`` before Typer dispatches here. Keeping the
    # parameters listed makes ``--help`` discover them; their values are
    # ignored because the same flags have already been stripped from argv.
    return


def _register_commands() -> None:
    from agentcloak.cli.commands import (
        action,
        bridge_cmd,
        browser,
        capture_cmd,
        cdp,
        config_cmd,
        cookies_cmd,
        daemon_cmd,
        dialog,
        doctor,
        fetch,
        frame,
        js,
        network,
        profile,
        spell_cmd,
        tab,
        upload,
        wait_cmd,
    )

    app.add_typer(
        config_cmd.app,
        name="config",
        help="Show merged configuration with sources.",
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
        help="Page actions: click, fill, type, scroll, hover, "
        "select, press, keydown, keyup.",
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
        spell_cmd.app,
        name="spell",
        help="Spells: list, info, run, scaffold.",
    )
    app.add_typer(
        tab.app,
        name="tab",
        help="Tab management: list, new, close, switch.",
    )
    app.add_typer(
        cdp.app,
        name="cdp",
        help="Chrome DevTools Protocol: endpoint.",
    )
    app.add_typer(
        dialog.app,
        name="dialog",
        help="Dialog handling: status, accept, dismiss.",
    )
    app.add_typer(
        wait_cmd.app,
        name="wait",
        help="Conditional waiting: selector, URL, load state, JS, time.",
    )
    app.add_typer(
        upload.app,
        name="upload",
        help="File upload to input elements.",
    )
    app.add_typer(
        frame.app,
        name="frame",
        help="Frame switching: list, focus.",
    )


_register_commands()


def _register_shortcuts() -> None:
    """Top-level shortcut commands (cloak open, cloak snapshot, cloak click, etc.)."""
    from agentcloak.cli.commands.action import (
        do_click,
        do_fill,
        do_hover,
        do_keydown,
        do_keyup,
        do_press,
        do_scroll,
        do_select,
        do_type,
    )
    from agentcloak.cli.commands.browser import (
        browser_navigate,
        browser_resume,
        browser_screenshot,
        browser_snapshot,
    )

    app.command("navigate", hidden=True)(browser_navigate)
    app.command("snapshot", hidden=True)(browser_snapshot)
    app.command("screenshot", hidden=True)(browser_screenshot)
    app.command("resume", hidden=True)(browser_resume)
    app.command("click", hidden=True)(do_click)
    app.command("fill", hidden=True)(do_fill)
    app.command("type", hidden=True)(do_type)
    app.command("press", hidden=True)(do_press)
    app.command("scroll", hidden=True)(do_scroll)
    app.command("hover", hidden=True)(do_hover)
    app.command("select", hidden=True)(do_select)
    app.command("keydown", hidden=True)(do_keydown)
    app.command("keyup", hidden=True)(do_keyup)


_register_shortcuts()


def main() -> None:
    from agentcloak.cli.output import output_error

    _maybe_emit_first_run_banner()
    # Lift ``--pretty``/``--verbose``/``--version`` out of argv before Typer
    # sees it (see :func:`_extract_global_flags`). This is what makes these
    # flags work in any position — including after a subcommand name.
    cleaned_argv, state = _extract_global_flags(sys.argv[1:])
    if state["version"]:
        typer.echo(f"agentcloak {__version__}")
        return
    verbose = state["verbose"]
    pretty = state["pretty"]
    set_pretty(enabled=bool(pretty))
    _configure_logging(verbosity=int(verbose))  # type: ignore[arg-type]

    try:
        app(args=cleaned_argv)
    except AgentBrowserError as exc:
        # We've already serialised the error envelope to stdout via
        # ``output_error``. Use ``sys.exit`` rather than ``raise typer.Exit
        # from exc`` so Python doesn't dump the original exception chain to
        # stderr — agents already have the structured envelope they need
        # and the traceback would just burn ~800 tokens per failure.
        output_error(exc)
        sys.exit(1)
