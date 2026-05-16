"""Config command — show merged configuration with sources."""

from __future__ import annotations

import typer

from agentcloak.cli.output import output_json
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
    output_json(
        {
            "config_file": str(paths.config_file),
            "config_file_exists": paths.config_file.is_file(),
            "fields": dumped,
        },
        seq=0,
    )
