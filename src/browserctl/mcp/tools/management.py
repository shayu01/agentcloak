"""Management tools — health, launch, CDP endpoint, cookies, site run."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from browserctl.mcp.client import DaemonBridge

__all__ = ["register"]


def register(mcp: FastMCP, bridge: DaemonBridge) -> None:
    @mcp.tool(annotations={"readOnlyHint": True})
    async def browserctl_status(
        query: Literal[
            "health", "cdp_endpoint", "cookies"
        ] = "health",
        url: str = "",
    ) -> str:
        """Query daemon and browser status.

        Queries:
          health       — daemon status, stealth tier, current URL, capture state
          cdp_endpoint — CDP WebSocket URL (for jshookmcp browser_attach)
          cookies      — export browser cookies (requires remote bridge)

        Args:
            query: What to check — health, cdp_endpoint, or cookies
            url: Filter cookies by URL (only for 'cookies' query)

        Returns:
            health: stealth_tier, current_url, current_title, capture_recording, seq.
            cdp_endpoint: ws_endpoint URL for CDP tools.
            cookies: list of browser cookies.
        """
        if query == "cdp_endpoint":
            result = await bridge.request("GET", "/cdp/endpoint")
        elif query == "cookies":
            json_body: dict[str, str] = {}
            if url:
                json_body["url"] = url
            result = await bridge.request(
                "POST", "/cookies/export", json_body=json_body
            )
        else:
            result = await bridge.request("GET", "/health")
        return bridge._format_result(result)

    @mcp.tool(annotations={"destructiveHint": True, "readOnlyHint": False})
    async def browserctl_launch(
        headless: bool = True,
        stealth: bool = False,
        profile: str = "",
    ) -> str:
        """Start or restart the browser daemon with specific options.

        Use before browserctl_navigate when you need a specific browser mode.
        If the daemon is already running, it will be stopped and restarted.
        If you don't call this, the daemon auto-starts with defaults on first use.

        Args:
            headless: Run browser without visible window (default True)
            stealth: Enable CloakBrowser anti-detection mode
            profile: Named browser profile for persistent cookies/state

        Returns:
            JSON with daemon health status including stealth_tier and profile.
        """
        result = await bridge.launch_daemon(
            headless=headless, stealth=stealth, profile=profile
        )
        return bridge._format_result(result)

    @mcp.tool(annotations={"readOnlyHint": False})
    async def browserctl_site_run(
        name: str,
        args_json: str = "{}",
    ) -> str:
        """Run a registered site adapter by name.

        Adapters are reusable automation commands for specific websites.
        Use browserctl_status(query='health') first to check available adapters,
        or list them via the CLI: browserctl site list.

        Args:
            name: Adapter name as 'site/command' (e.g. 'httpbin/headers')
            args_json: Arguments as JSON object (e.g. '{"limit": 10}')

        Returns:
            JSON with the adapter execution result.
        """
        from browserctl.adapters.discovery import discover_adapters
        from browserctl.adapters.executor import execute_adapter
        from browserctl.adapters.registry import get_registry

        discover_adapters()
        parts = name.split("/", 1)
        if len(parts) != 2:
            return json.dumps({
                "error": "invalid_adapter_name",
                "hint": f"Expected 'site/command', got '{name}'",
                "action": "use format like 'httpbin/headers'",
            })

        registry = get_registry()
        entry = registry.get(parts[0], parts[1])
        if entry is None:
            available = [e.meta.full_name for e in registry.list_all()]
            return json.dumps({
                "error": "adapter_not_found",
                "hint": f"No adapter '{name}'",
                "action": f"available: {', '.join(available[:10])}",
            })

        parsed_args: dict[str, Any] = json.loads(args_json)
        try:
            result = await execute_adapter(entry, args=parsed_args)
            return json.dumps({"result": result})
        except Exception as exc:
            return json.dumps({
                "error": "adapter_execution_failed",
                "hint": str(exc),
                "action": "check adapter args and daemon status",
            })
