"""Management tools — launch, status, profile, adapter, doctor, resume."""

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
        query: Literal["health", "cdp_endpoint"] = "health",
    ) -> str:
        """Query daemon and browser status.

        Queries:
          health       — daemon status, stealth tier, current URL, capture state
          cdp_endpoint — CDP WebSocket URL (for jshookmcp browser_attach)

        Args:
            query: What to check — health or cdp_endpoint

        Returns:
            health: stealth_tier, current_url, current_title, seq.
            cdp_endpoint: ws_endpoint URL for CDP tools.
        """
        if query == "cdp_endpoint":
            result = await bridge.request("GET", "/cdp/endpoint")
        else:
            result = await bridge.request("GET", "/health")
        return bridge._format_result(result)

    @mcp.tool(annotations={"readOnlyHint": False})
    async def browserctl_cookies(
        action: Literal["export", "import"] = "export",
        url: str = "",
        cookies_json: str = "",
    ) -> str:
        """Manage browser cookies — export or import.

        Actions:
          export — get all cookies from the browser (local or bridge)
          import — inject cookies into the browser (supports httpOnly)

        Args:
            action: 'export' to get cookies, 'import' to inject cookies
            url: Filter exported cookies by URL (only for export)
            cookies_json: JSON array of cookie objects to import. Each cookie
                needs at least 'name', 'value', 'domain', 'path'. Example:
                '[{"name":"token","value":"abc","domain":".example.com","path":"/"}]'

        Returns:
            export: array of cookies with name, value, domain, path, httpOnly, etc.
            import: count of imported cookies.
        """
        if action == "export":
            json_body: dict[str, str] = {}
            if url:
                json_body["url"] = url
            result = await bridge.request(
                "POST", "/cookies/export", json_body=json_body
            )
            return bridge._format_result(result)

        if action == "import":
            if not cookies_json:
                return json.dumps(
                    {
                        "error": "missing_cookies",
                        "hint": "cookies_json is required for import",
                        "action": "pass cookies as JSON array string",
                    }
                )
            cookies = json.loads(cookies_json) if isinstance(cookies_json, str) else cookies_json
            result = await bridge.request(
                "POST", "/cookies/import", json_body={"cookies": cookies}
            )
            return bridge._format_result(result)

        return json.dumps(
            {"error": "unknown_action", "hint": f"Unknown: {action}"}
        )

    @mcp.tool(annotations={"destructiveHint": True, "readOnlyHint": False})
    async def browserctl_launch(
        tier: str = "",
        profile: str = "",
    ) -> str:
        """Start or restart the browser daemon with specific options.

        If the daemon is already running, it will be stopped and restarted.
        If you don't call this, the daemon auto-starts with env defaults.

        Args:
            tier: Browser tier — 'auto' (detect best), 'patchright', 'cloak',
                  or 'remote_bridge'. Empty = use BROWSERCTL_DEFAULT_TIER env.
            profile: Named browser profile for persistent cookies/state

        Returns:
            JSON with daemon health status.
        """
        from browserctl.core.config import load_config, resolve_tier

        _, cfg = load_config()
        actual_tier = tier or cfg.default_tier
        resolved = resolve_tier(actual_tier)
        stealth = resolved == "cloak"
        result = await bridge.launch_daemon(
            headless=True, stealth=stealth, profile=profile
        )
        return bridge._format_result(result)

    @mcp.tool(annotations={"readOnlyHint": False})
    async def browserctl_adapter_run(
        name: str,
        args_json: str = "{}",
    ) -> str:
        """Run a registered adapter by name.

        Adapters are reusable automation commands for specific websites.
        Use browserctl_adapter_list to see available adapters.

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
            return json.dumps(
                {
                    "error": "invalid_adapter_name",
                    "hint": f"Expected 'site/command', got '{name}'",
                    "action": "use format like 'httpbin/headers'",
                }
            )

        registry = get_registry()
        entry = registry.get(parts[0], parts[1])
        if entry is None:
            available = [e.meta.full_name for e in registry.list_all()]
            return json.dumps(
                {
                    "error": "adapter_not_found",
                    "hint": f"No adapter '{name}'",
                    "action": f"available: {', '.join(available[:10])}",
                }
            )

        parsed_args: dict[str, Any] = json.loads(args_json)
        try:
            result = await execute_adapter(entry, args=parsed_args)
            return json.dumps({"result": result})
        except Exception as exc:
            return json.dumps(
                {
                    "error": "adapter_execution_failed",
                    "hint": str(exc),
                    "action": "check adapter args and daemon status",
                }
            )

    @mcp.tool(annotations={"readOnlyHint": True})
    async def browserctl_adapter_list() -> str:
        """List all registered adapters.

        Returns:
            JSON with adapters array (site, name, strategy, description).
        """
        from browserctl.adapters.discovery import discover_adapters
        from browserctl.adapters.registry import get_registry

        discover_adapters()
        registry = get_registry()
        adapters: list[dict[str, Any]] = []
        for entry in registry.list_all():
            m = entry.meta
            adapters.append(
                {
                    "full_name": m.full_name,
                    "strategy": m.strategy.value,
                    "access": m.access,
                    "description": m.description,
                }
            )
        return json.dumps({"adapters": adapters, "count": len(adapters)})

    @mcp.tool(annotations={"readOnlyHint": False})
    async def browserctl_profile(
        action: Literal["create", "list", "delete"] = "list",
        name: str = "",
    ) -> str:
        """Manage browser profiles for persistent cookies and login state.

        Actions:
          list   — show all available profiles
          create — create a new named profile
          delete — delete an existing profile

        Args:
            action: Profile action — create, list, or delete
            name: Profile name (required for create/delete)

        Returns:
            list: array of profile names.
            create/delete: confirmation.
        """
        from browserctl.core.config import load_config

        paths, _ = load_config()
        profiles_dir = paths.profiles_dir
        profiles_dir.mkdir(parents=True, exist_ok=True)

        if action == "list":
            names = sorted(d.name for d in profiles_dir.iterdir() if d.is_dir())
            return json.dumps({"profiles": names, "count": len(names)})

        if not name:
            return json.dumps(
                {
                    "error": "missing_name",
                    "hint": "Profile name is required for create/delete",
                    "action": "provide a name parameter",
                }
            )

        profile_path = profiles_dir / name
        if action == "create":
            if profile_path.exists():
                return json.dumps(
                    {
                        "error": "profile_exists",
                        "hint": f"Profile '{name}' already exists",
                        "action": "use a different name or delete first",
                    }
                )
            profile_path.mkdir(parents=True)
            return json.dumps({"created": name})

        if action == "delete":
            if not profile_path.exists():
                return json.dumps(
                    {
                        "error": "profile_not_found",
                        "hint": f"Profile '{name}' does not exist",
                        "action": "use browserctl_profile(action='list')",
                    }
                )
            import shutil

            shutil.rmtree(profile_path)
            return json.dumps({"deleted": name})

        return json.dumps({"error": "unknown_action", "hint": f"Unknown: {action}"})

    @mcp.tool(annotations={"readOnlyHint": False})
    async def browserctl_tab(
        action: Literal["list", "new", "close", "switch"] = "list",
        tab_id: int = -1,
        url: str = "",
    ) -> str:
        """Manage browser tabs — list, create, close, switch.

        Actions:
          list   — show all open tabs with id, url, title, active status
          new    — create a new tab (optionally navigate to url)
          close  — close tab by tab_id
          switch — switch active tab to tab_id

        Args:
            action: Tab action — list, new, close, or switch
            tab_id: Tab ID (required for close/switch, ignored for list)
            url: URL to navigate new tab to (only for 'new' action)

        Returns:
            list: array of tabs.
            new: created tab_id and url.
            close: confirmation of closed tab.
            switch: new active tab info.
        """
        if action == "list":
            result = await bridge.request("GET", "/tabs")
            return bridge._format_result(result)

        if action == "new":
            json_body: dict[str, Any] = {}
            if url:
                json_body["url"] = url
            result = await bridge.request("POST", "/tab/new", json_body=json_body)
            return bridge._format_result(result)

        if action == "close":
            if tab_id < 0:
                return json.dumps(
                    {
                        "error": "missing_tab_id",
                        "hint": "tab_id is required for close action",
                        "action": "provide a valid tab_id",
                    }
                )
            result = await bridge.request(
                "POST", "/tab/close", json_body={"tab_id": tab_id}
            )
            return bridge._format_result(result)

        if action == "switch":
            if tab_id < 0:
                return json.dumps(
                    {
                        "error": "missing_tab_id",
                        "hint": "tab_id is required for switch action",
                        "action": "provide a valid tab_id",
                    }
                )
            result = await bridge.request(
                "POST", "/tab/switch", json_body={"tab_id": tab_id}
            )
            return bridge._format_result(result)

        return json.dumps(
            {
                "error": "unknown_action",
                "hint": f"Unknown tab action: {action}",
                "action": "use list, new, close, or switch",
            }
        )

    @mcp.tool(annotations={"readOnlyHint": True})
    async def browserctl_doctor() -> str:
        """Run diagnostic checks on browserctl installation.

        Checks Python version, patchright availability, CloakBrowser status,
        daemon connectivity, and configuration.

        Returns:
            JSON with diagnostic checks array.
        """
        import sys

        from browserctl.core.config import load_config, resolve_tier

        checks: list[dict[str, Any]] = []

        checks.append(
            {
                "name": "python_version",
                "ok": sys.version_info >= (3, 12),
                "value": sys.version,
            }
        )

        try:
            import patchright as _

            checks.append({"name": "patchright", "ok": True})
        except ImportError:
            checks.append({"name": "patchright", "ok": False})

        try:
            import cloakbrowser as _

            checks.append(
                {
                    "name": "cloakbrowser",
                    "ok": True,
                    "hint": "CloakBrowser available — auto tier will use cloak",
                }
            )
        except ImportError:
            checks.append(
                {
                    "name": "cloakbrowser",
                    "ok": False,
                    "hint": "Not installed — pip install browserctl[stealth]",
                }
            )

        _, cfg = load_config()
        resolved = resolve_tier(cfg.default_tier)
        checks.append(
            {
                "name": "default_tier",
                "value": f"{cfg.default_tier} → {resolved}",
            }
        )

        try:
            import httpx

            async with httpx.AsyncClient(timeout=2.0) as client:
                base = f"http://{cfg.daemon_host}:{cfg.daemon_port}"
                resp = await client.get(f"{base}/health")
                checks.append(
                    {
                        "name": "daemon",
                        "ok": resp.status_code == 200,
                        "value": f"{cfg.daemon_host}:{cfg.daemon_port}",
                    }
                )
        except Exception:
            checks.append(
                {
                    "name": "daemon",
                    "ok": False,
                    "value": "not running",
                }
            )

        return json.dumps({"checks": checks})

    @mcp.tool(annotations={"readOnlyHint": True})
    async def browserctl_resume() -> str:
        """Get session resume snapshot for recovering context after restart.

        Returns current URL, open tabs, last 5 actions, capture state,
        and stealth tier. Use this at the start of a new session to
        quickly restore working context.

        Returns:
            JSON with url, title, tabs, recent_actions, capture_active,
            stealth_tier, and timestamp.
        """
        result = await bridge.request("GET", "/resume")
        return bridge._format_result(result)
