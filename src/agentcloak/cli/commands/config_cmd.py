"""Config command — show merged configuration with sources."""

from __future__ import annotations

from typing import cast

import typer

from agentcloak.cli._dispatch import emit_envelope
from agentcloak.cli.output import is_json_mode, value
from agentcloak.core.config import dump_config, load_config

__all__ = ["app"]

app = typer.Typer()


def _format_value(val: object) -> str:
    """Render a config value as a stable, copy-pasteable token.

    Strings get TOML-style double quotes so an empty value (``""``) is
    visually distinct from a missing one. Booleans render lowercase to
    match the on-disk TOML form. Lists round-trip through ``repr`` which
    keeps brackets and quotes — agents can paste the line straight into
    ``config.toml`` without re-quoting.
    """
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, str):
        return f'"{val}"'
    if isinstance(val, list):
        # ``isinstance(val, list)`` narrows to ``list[Unknown]`` under strict
        # pyright; cast to a typed shape so ``repr`` sees a known element
        # type. The element type is ``object`` because ``dump_config`` returns
        # the dataclass field value as-is (str, int, bool, or list[str]).
        typed_list = cast("list[object]", val)
        return repr(typed_list)
    return str(val)


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

    # ``git config -l --show-origin``-style listing: each line is
    # ``key = value  [source]`` with source in brackets so it's grep-able.
    # ``dump_config`` returns ``{field_name: {"value": ..., "source": ...}}``
    # — iterate items, not the dict itself, so we get the value dicts.
    lines: list[str] = [f"# {paths.config_file}"]
    # Pad the key column so sources line up vertically — ``git config --list``
    # is unaligned but the reference page promised an aligned table. Calculate
    # once over all fields so adding a long key later doesn't require a
    # template update.
    width = max((len(name) for name in dumped), default=0)
    for field_name, info in dumped.items():
        raw_value: object = info.get("value")
        source: object = info.get("source", "default")
        formatted = _format_value(raw_value)
        lines.append(f"{field_name.ljust(width)} = {formatted}  [{source}]")
    value("\n".join(lines))
