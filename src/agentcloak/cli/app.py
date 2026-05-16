"""Root Typer app, global flags, and structlog setup."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import structlog
import typer

from agentcloak import __version__
from agentcloak.cli.output import (
    _detect_env_json_mode,
    is_json_mode,
    set_json_mode,
    set_pretty,
)
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
    ``--json``, and ``--version``. Adding a new one means appending a branch
    here *and* declaring it on :func:`_root_callback` so ``--help`` documents
    it — keep the two in sync.

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
    json_mode = False
    for arg in argv:
        if arg == "--pretty":
            pretty = True
        elif arg in ("--verbose", "-v"):
            verbose += 1
        elif arg == "--version":
            version = True
        elif arg == "--json":
            json_mode = True
        else:
            cleaned.append(arg)
    state: dict[str, object] = {
        "pretty": pretty,
        "verbose": verbose,
        "version": version,
        "json": json_mode,
    }
    return cleaned, state


@app.callback()
def _root_callback(  # pyright: ignore[reportUnusedFunction]
    verbose: int = typer.Option(
        0, "--verbose", "-v", count=True, help="Increase log verbosity."
    ),
    pretty: bool = typer.Option(
        False, "--pretty", help="Pretty-print JSON output (requires --json)."
    ),
    json: bool = typer.Option(
        False,
        "--json",
        help=(
            "Emit full JSON envelopes on stdout (backwards-compat mode). "
            "Equivalent to AGENTCLOAK_OUTPUT=json."
        ),
    ),
    _version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version.",
    ),
) -> None:
    # ``main()`` strips these globals from argv via ``_extract_global_flags``
    # before Typer dispatches, so during normal CLI use the parameters arrive
    # here as their defaults (False) — the flag has already been consumed and
    # applied to the module-level state.
    #
    # For ``CliRunner`` invocations (tests, programmatic use) ``main()`` never
    # runs and Typer parses ``--json`` itself. We OR-merge so a True coming
    # from either path wins; we never *clear* an already-enabled flag because
    # ``main()`` may have set it from argv or AGENTCLOAK_OUTPUT before us.
    if json or _detect_env_json_mode():
        set_json_mode(enabled=True)
    if pretty:
        set_pretty(enabled=True)


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
        launch,
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
        launch.app,
        name="launch",
        help="Hot-switch the daemon's active browser tier.",
    )
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
    from agentcloak.cli.output import error_from_exception

    _maybe_emit_first_run_banner()
    # Lift ``--pretty``/``--verbose``/``--version``/``--json`` out of argv
    # before Typer sees it (see :func:`_extract_global_flags`). This is what
    # makes these flags work in any position — including after a subcommand
    # name.
    cleaned_argv, state = _extract_global_flags(sys.argv[1:])
    if state["version"]:
        typer.echo(f"agentcloak {__version__}")
        return
    verbose = state["verbose"]
    pretty = state["pretty"]
    json_flag = bool(state["json"])
    # AGENTCLOAK_OUTPUT=json is the escape hatch for scripts that can't pass
    # CLI flags (cron jobs, CI tools that wrap the binary, etc.). Either path
    # sets the same module-level flag.
    json_enabled = json_flag or _detect_env_json_mode()
    set_json_mode(enabled=json_enabled)
    set_pretty(enabled=bool(pretty))
    _configure_logging(verbosity=int(verbose))  # type: ignore[arg-type]

    # ``--pretty`` without ``--json`` is a no-op (text output isn't JSON).
    # Warn so the user doesn't think their formatting is broken.
    if bool(pretty) and not json_enabled:
        sys.stderr.write(
            "warning: --pretty has no effect without --json (text output mode)\n"
        )

    try:
        app(args=cleaned_argv)
    except AgentBrowserError as exc:
        # In JSON mode the envelope was serialised to stdout. In text mode we
        # emit ``Error: <hint>`` to stderr. Either way the call exits with 1.
        # Using ``sys.exit`` rather than ``raise typer.Exit from exc`` keeps
        # Python from dumping the exception chain — agents already have the
        # structured info they need and a traceback would burn ~800 tokens.
        # ``error_from_exception`` will raise SystemExit(1) itself; the catch
        # below just guards against the rare path where it doesn't.
        try:
            error_from_exception(exc)
        except SystemExit:
            raise
        # Reached only if error_from_exception returns normally (it shouldn't).
        sys.exit(1)
    # Surface the post-call json mode to anyone calling main() in-process so
    # they see the flag was honoured (kept silent under normal CLI use).
    _ = is_json_mode()
