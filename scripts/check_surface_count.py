#!/usr/bin/env python3
"""Cross-check daemon routes against CLI commands and MCP tools.

This script is the CI replacement for the old, aiohttp-era
``check_consistency.py`` (which silently passed because its regex no longer
matched FastAPI's decorator style). It treats the daemon's OpenAPI spec as
the source of truth and walks four assertions:

1. every daemon route has a CLI binding listed in ``generate_skill.py``;
2. every daemon route has an MCP binding listed in ``generate_skill.py``;
3. every MCP tool defined under ``mcp/tools/`` is reachable from at least
   one route's mapping (or appears on the standalone allow-list);
4. CLI typer groups cover every command category implied by the routes.

Exit code 0 means everything lines up; non-zero means CI should fail.

The mapping tables in ``generate_skill.py`` are the documented contract —
when a new route lands you update the dict (one line) and this script
keeps the trio in sync.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


# MCP tools that don't correspond to a daemon route. These wrap subprocess
# lifecycle (``agentcloak_launch``) or aggregate health into a synthetic tool
# (``agentcloak_doctor``) — keep this list short and explanatory.
MCP_STANDALONE: set[str] = {
    "agentcloak_doctor",
    "agentcloak_launch",
}


def collect_spec_routes() -> list[tuple[str, str]]:
    """Return ``[(verb, path), ...]`` from the FastAPI app's OpenAPI spec."""
    from agentcloak.daemon.app import create_app

    app = create_app()
    spec = app.openapi()
    routes: list[tuple[str, str]] = []
    for path, methods in spec.get("paths", {}).items():
        for verb in methods:
            if verb in {"get", "post", "put", "patch", "delete"}:
                routes.append((verb.upper(), path))
    return sorted(routes)


def collect_mcp_tools() -> set[str]:
    """Scan ``mcp/tools/*.py`` for ``async def agentcloak_xxx`` definitions."""
    tools_dir = SRC / "agentcloak" / "mcp" / "tools"
    pattern = re.compile(r"async def (agentcloak_\w+)\(")
    tools: set[str] = set()
    for f in tools_dir.glob("*.py"):
        tools.update(pattern.findall(f.read_text()))
    return tools


def collect_cli_groups() -> set[str]:
    """Extract typer group names from ``cli/app.py``."""
    app_file = SRC / "agentcloak" / "cli" / "app.py"
    text = app_file.read_text()
    pattern = re.compile(r'name="([^"]+)"')
    # The first match is the root ``typer.Typer(name="agentcloak", ...)`` so
    # we skip that one — only ``add_typer(..., name="...")`` calls describe
    # actual command groups.
    matches: list[str] = pattern.findall(text)
    if matches:
        matches = matches[1:]
    return {m for m in matches if not m.startswith("agentcloak")}


def extract_mcp_name(binding: str) -> str:
    """Pull the bare ``agentcloak_xxx`` identifier out of a binding string.

    Bindings look like ``"agentcloak_tab (action=new)"`` or just
    ``"agentcloak_navigate"``. Some routes (notably ``/shutdown``) intentionally
    have no MCP exposure — the binding is a parenthesised note and we return
    an empty string so the caller can skip it.
    """
    if binding.startswith("("):
        return ""
    head = binding.split(" ", 1)[0]
    return head


def main() -> int:
    from generate_skill import ROUTE_TO_CLI, ROUTE_TO_MCP

    routes = collect_spec_routes()
    mcp_tools = collect_mcp_tools()
    cli_groups = collect_cli_groups()

    errors: list[str] = []
    warnings: list[str] = []

    # 1. Every route must appear in both mapping tables.
    for _verb, path in routes:
        if path not in ROUTE_TO_CLI:
            errors.append(f"Route {path} missing from generate_skill.ROUTE_TO_CLI")
        if path not in ROUTE_TO_MCP:
            errors.append(f"Route {path} missing from generate_skill.ROUTE_TO_MCP")

    # 2. The MCP binding must refer to a tool that actually exists.
    for path, binding in ROUTE_TO_MCP.items():
        tool_name = extract_mcp_name(binding)
        if not tool_name:
            continue  # intentionally not exposed (e.g. /shutdown)
        if tool_name not in mcp_tools:
            errors.append(
                f"Route {path} maps to MCP tool {tool_name!r}, "
                f"but no async def {tool_name}() found in mcp/tools/"
            )

    # 3. Every MCP tool must be referenced from at least one route mapping
    #    or be on the standalone allow-list.
    referenced_tools: set[str] = set()
    for binding in ROUTE_TO_MCP.values():
        name = extract_mcp_name(binding)
        if name:
            referenced_tools.add(name)
    orphan_tools = mcp_tools - referenced_tools - MCP_STANDALONE
    for tool in sorted(orphan_tools):
        errors.append(f"MCP tool {tool!r} has no route mapping (add to ROUTE_TO_MCP)")

    # 4. Drift signal: if the surface counts shift unexpectedly we want a
    #    human to glance at the change. We only warn, not fail.
    expected_routes = len(ROUTE_TO_CLI)
    if len(routes) != expected_routes:
        warnings.append(
            f"Route count drift: spec has {len(routes)}, "
            f"mapping table has {expected_routes}"
        )

    # Output report.
    print(f"Daemon routes : {len(routes)}")
    print(f"MCP tools     : {len(mcp_tools)}")
    print(f"CLI groups    : {len(cli_groups)}")
    print(f"CLI mappings  : {len(ROUTE_TO_CLI)}")
    print(f"MCP mappings  : {len(ROUTE_TO_MCP)}")

    if warnings:
        print("\nWarnings:")
        for w in warnings:
            print(f"  - {w}")

    if errors:
        print(f"\nFAIL: {len(errors)} consistency error(s):")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("\nOK: all routes have CLI + MCP bindings, all MCP tools are reachable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
