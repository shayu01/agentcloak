#!/usr/bin/env python3
"""Check CLI / MCP / daemon interface consistency.

Scans daemon routes, MCP tool definitions, and CLI commands,
then cross-references to find missing coverage.

Exit code 0 = consistent, 1 = gaps found.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "src" / "agentcloak"

# ---------------------------------------------------------------------------
# Scanners
# ---------------------------------------------------------------------------

def scan_daemon_routes() -> set[str]:
    routes_file = ROOT / "daemon" / "routes.py"
    text = routes_file.read_text()
    pattern = re.compile(r'app\.router\.add_(?:get|post)\("(/[^"]+)"')
    routes = set(pattern.findall(text))
    # Exclude internal-only routes
    routes -= {"/health", "/bridge/ws", "/bridge/claim", "/bridge/finalize", "/shutdown", "/ext"}
    return routes


def scan_mcp_tools() -> set[str]:
    tools_dir = ROOT / "mcp" / "tools"
    pattern = re.compile(r"async def (agentcloak_\w+)\(")
    tools: set[str] = set()
    for f in tools_dir.glob("*.py"):
        tools.update(pattern.findall(f.read_text()))
    return tools


def scan_cli_groups() -> set[str]:
    app_file = ROOT / "cli" / "app.py"
    text = app_file.read_text()
    pattern = re.compile(r'add_typer\([^,]+,\s*name="(\w+)"')
    return set(pattern.findall(text))


# ---------------------------------------------------------------------------
# Known mappings (route -> MCP tool prefix)
# ---------------------------------------------------------------------------

ROUTE_TO_MCP_PREFIX: dict[str, str] = {
    "/navigate": "agentcloak_navigate",
    "/screenshot": "agentcloak_screenshot",
    "/snapshot": "agentcloak_snapshot",
    "/evaluate": "agentcloak_evaluate",
    "/network": "agentcloak_network",
    "/action": "agentcloak_action",
    "/action/batch": "agentcloak_action",
    "/fetch": "agentcloak_fetch",
    "/resume": "agentcloak_resume",
    "/cdp/endpoint": "agentcloak_status",
    "/cookies/export": "agentcloak_cookies",
    "/cookies/import": "agentcloak_cookies",
    "/capture/start": "agentcloak_capture_control",
    "/capture/stop": "agentcloak_capture_control",
    "/capture/status": "agentcloak_capture_query",
    "/capture/export": "agentcloak_capture_query",
    "/capture/analyze": "agentcloak_capture_query",
    "/capture/clear": "agentcloak_capture_control",
    "/capture/replay": "agentcloak_capture_control",
    "/tabs": "agentcloak_tab",
    "/tab/new": "agentcloak_tab",
    "/tab/close": "agentcloak_tab",
    "/tab/switch": "agentcloak_tab",
    "/spell/run": "agentcloak_spell_run",
    "/spell/list": "agentcloak_spell_list",
    "/profile/list": "agentcloak_profile",
    "/profile/create": "agentcloak_profile",
    "/profile/delete": "agentcloak_profile",
    "/profile/create-from-current": "agentcloak_profile",
    "/dialog/status": "agentcloak_dialog",
    "/dialog/handle": "agentcloak_dialog",
    "/wait": "agentcloak_wait",
    "/upload": "agentcloak_upload",
    "/frame/list": "agentcloak_frame",
    "/frame/focus": "agentcloak_frame",
}

# ---------------------------------------------------------------------------
# Check
# ---------------------------------------------------------------------------

def main() -> int:
    routes = scan_daemon_routes()
    mcp_tools = scan_mcp_tools()
    cli_groups = scan_cli_groups()

    errors: list[str] = []

    # Check: every daemon route has an MCP mapping
    for route in sorted(routes):
        if route not in ROUTE_TO_MCP_PREFIX:
            errors.append(f"Daemon route {route} has no MCP mapping in check script")
            continue
        expected_tool = ROUTE_TO_MCP_PREFIX[route]
        if expected_tool not in mcp_tools:
            errors.append(f"Daemon route {route} -> MCP tool {expected_tool} not found")

    # Check: every MCP tool has at least one daemon route pointing to it
    mapped_tools = set(ROUTE_TO_MCP_PREFIX.values())
    # Add tools that don't map to routes (doctor, launch, bridge)
    standalone_tools = {"agentcloak_doctor", "agentcloak_launch", "agentcloak_bridge"}
    for tool in sorted(mcp_tools):
        if tool not in mapped_tools and tool not in standalone_tools:
            errors.append(f"MCP tool {tool} has no daemon route mapping")

    if errors:
        print("CLI/MCP/Daemon consistency check FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(f"Consistency check passed: {len(routes)} routes, {len(mcp_tools)} MCP tools, {len(cli_groups)} CLI groups")
    return 0


if __name__ == "__main__":
    sys.exit(main())
