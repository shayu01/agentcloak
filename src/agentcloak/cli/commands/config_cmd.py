"""Config command — show merged configuration with sources."""

from __future__ import annotations

from typing import Any

import typer

from agentcloak.cli._dispatch import emit_envelope
from agentcloak.cli.output import is_json_mode, value
from agentcloak.core.config import dump_config, load_config

__all__ = ["app"]

app = typer.Typer()


@app.callback(invoke_without_command=True)
def config_show(ctx: typer.Context) -> None:
    """Show merged configuration with value sources."""
    if ctx.invoked_subcommand is not None:
        return
    paths, cfg = load_config()
    dumped = dump_config(cfg, paths)

    if is_json_mode():
        emit_envelope(
            {
                "ok": True,
                "seq": 0,
                "data": {
                    "config_file": str(paths.config_file),
                    "config_file_exists": paths.config_file.is_file(),
                    "fields": dumped,
                },
            }
        )
        return

    # ``git config -l``-style listing: ``key = value (source)`` per line.
    lines: list[str] = [f"# {paths.config_file}"]
    for raw_field in dumped:
        if not isinstance(raw_field, dict):
            continue
        # dump_config returns ``list[dict[str, Any]]`` at runtime — narrow it
        # so pyright stops complaining about Unknown getters.
        field: dict[str, Any] = dict(raw_field)  # type: ignore[arg-type]
        key = field.get("key", "?")
        val = field.get("value", "")
        src = field.get("source", "")
        lines.append(f"{key} = {val} ({src})" if src else f"{key} = {val}")
    value("\n".join(lines))
