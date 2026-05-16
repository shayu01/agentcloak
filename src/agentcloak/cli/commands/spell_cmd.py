"""Spell commands — list, info, run, and scaffold spells."""

from __future__ import annotations

import asyncio
from typing import Any

import typer

from agentcloak.cli.output import output_json
from agentcloak.client import DaemonClient
from agentcloak.core.errors import AgentBrowserError
from agentcloak.spells.discovery import discover_spells
from agentcloak.spells.registry import get_registry

__all__ = ["app"]

app = typer.Typer()


def _ensure_discovered() -> None:
    if len(get_registry()) == 0:
        discover_spells()


@app.command("list")
def spell_list() -> None:
    """List all registered spells."""
    _ensure_discovered()
    registry = get_registry()
    spells: list[dict[str, Any]] = []
    for entry in registry.list_all():
        m = entry.meta
        spells.append(
            {
                "site": m.site,
                "name": m.name,
                "full_name": m.full_name,
                "strategy": m.strategy.value,
                "access": m.access,
                "description": m.description,
                "domain": m.domain,
                "needs_browser": m.needs_browser,
                "mode": "pipeline" if entry.is_pipeline else "function",
            }
        )
    output_json({"spells": spells, "count": len(spells)}, seq=0)


@app.command("info")
def spell_info(
    name: str = typer.Argument(help="Spell name as site/command."),
) -> None:
    """Show detailed info for a spell."""
    _ensure_discovered()
    parts = name.split("/", 1)
    if len(parts) != 2:
        raise AgentBrowserError(
            error="invalid_spell_name",
            hint=f"Expected 'site/name' format, got '{name}'",
            action="use format like 'httpbin/headers'",
        )
    registry = get_registry()
    entry = registry.get(parts[0], parts[1])
    if entry is None:
        raise AgentBrowserError(
            error="spell_not_found",
            hint=f"No spell registered as '{name}'",
            action="run 'agentcloak spell list' to see available spells",
        )
    m = entry.meta
    info: dict[str, Any] = {
        "site": m.site,
        "name": m.name,
        "full_name": m.full_name,
        "strategy": m.strategy.value,
        "access": m.access,
        "description": m.description,
        "domain": m.domain,
        "needs_browser": m.needs_browser,
        "navigate_before": m.navigate_before,
        "mode": "pipeline" if entry.is_pipeline else "function",
        "args": [
            {
                "name": a.name,
                "type": a.type.__name__,
                "default": a.default,
                "required": a.required,
                "help": a.help,
            }
            for a in m.args
        ],
        "columns": list(m.columns) if m.columns else None,
    }
    output_json(info, seq=0)


@app.command("run")
def spell_run(
    name: str = typer.Argument(help="Spell name as site/command."),
    args: list[str] = typer.Argument(
        default=None, help="Spell arguments as key=value pairs."
    ),
) -> None:
    """Execute a spell."""
    _ensure_discovered()
    parts = name.split("/", 1)
    if len(parts) != 2:
        raise AgentBrowserError(
            error="invalid_spell_name",
            hint=f"Expected 'site/name' format, got '{name}'",
            action="use format like 'httpbin/headers'",
        )
    registry = get_registry()
    entry = registry.get(parts[0], parts[1])
    if entry is None:
        raise AgentBrowserError(
            error="spell_not_found",
            hint=f"No spell registered as '{name}'",
            action="run 'agentcloak spell list' to see available spells",
        )

    parsed_args = _parse_args(args or [])
    # Local spell execution stays async (executor + pipeline are async); we
    # only need asyncio.run here, not a daemon round-trip.
    result = asyncio.run(_execute(entry, parsed_args))
    output_json({"result": result}, seq=0)


async def _execute(entry: Any, args: dict[str, Any]) -> list[dict[str, Any]]:
    from agentcloak.spells.executor import execute_spell

    if entry.meta.needs_browser:
        raise AgentBrowserError(
            error="browser_required",
            hint=f"Spell '{entry.meta.full_name}' requires a browser "
            f"(strategy={entry.meta.strategy})",
            action="start daemon first, then use spell run",
        )

    return await execute_spell(entry, args=args)


def _parse_args(raw: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in raw:
        if "=" in item:
            key, val = item.split("=", 1)
            result[key] = val
        else:
            result[item] = True
    return result


@app.command("scaffold")
def spell_scaffold(
    site: str = typer.Argument(help="Site name for generated spells."),
    domain: str = typer.Option("", help="Filter patterns by domain."),
) -> None:
    """Generate spell code from captured traffic analysis."""
    client = DaemonClient()
    analyze_result = client.capture_analyze_sync(domain=domain)

    patterns_data: list[dict[str, Any]] = analyze_result.get("data", {}).get(
        "patterns", []
    )

    if not patterns_data:
        output_json(
            {"code": "", "message": "No API patterns found in captured traffic."},
            seq=0,
        )
        return

    from agentcloak.core.types import Strategy
    from agentcloak.spells.analyzer import EndpointPattern
    from agentcloak.spells.generator import generate_spells

    patterns: list[EndpointPattern] = []
    for p in patterns_data:
        patterns.append(
            EndpointPattern(
                method=p.get("method", "GET"),
                path=p.get("path", "/"),
                domain=p.get("domain", ""),
                call_count=p.get("call_count", 0),
                query_params=p.get("query_params", []),
                status_codes={int(k): v for k, v in p.get("status_codes", {}).items()},
                auth_headers=p.get("auth_headers", []),
                content_type=p.get("content_type", ""),
                category=p.get("category", "read"),
                strategy=Strategy(p.get("strategy", "public")),
            )
        )

    code = generate_spells(site, patterns)
    output_json({"code": code, "pattern_count": len(patterns)}, seq=0)
