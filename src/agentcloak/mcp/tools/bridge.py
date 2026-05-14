"""Bridge UX tools -- tab claiming and session lifecycle."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from agentcloak.mcp.client import DaemonBridge

__all__ = ["register"]


def register(mcp: FastMCP, bridge: DaemonBridge) -> None:
    @mcp.tool(annotations={"readOnlyHint": False})
    async def agentcloak_bridge(
        action: Literal["claim", "finalize"] = "claim",
        tab_id: int = -1,
        url_pattern: str = "",
        mode: str = "close",
    ) -> str:
        """Manage remote browser tabs via the Chrome Extension bridge.

        Actions:
          claim    -- take control of a user-opened tab (attach debugger,
                      add to agentcloak tab group). Provide tab_id or url_pattern.
          finalize -- end the agent session. Modes:
                        close       -- close all agent-managed tabs (default)
                        handoff     -- ungroup tabs, leave open for user
                        deliverable -- rename group to 'agentcloak results' (green)

        Requires: Chrome Extension connected via bridge or daemon /ext.

        Args:
            action: 'claim' to take over a tab, 'finalize' to end session
            tab_id: Chrome tab ID to claim (only for claim action)
            url_pattern: URL substring to match for claiming (only for claim)
            mode: Finalize mode -- close, handoff, or deliverable (only for finalize)

        Returns:
            claim: {tabId, url, title, claimed}.
            finalize: {mode, tabsAffected}.
        """
        if action == "claim":
            json_body: dict[str, Any] = {}
            if tab_id >= 0:
                json_body["tab_id"] = tab_id
            if url_pattern:
                json_body["url_pattern"] = url_pattern
            if not json_body:
                return json.dumps(
                    {
                        "error": "missing_target",
                        "hint": "Provide tab_id or url_pattern to claim a tab",
                        "action": "set tab_id or url_pattern parameter",
                    }
                )
            result = await bridge.request("POST", "/bridge/claim", json_body=json_body)
            return bridge.format_result(result)

        if action == "finalize":
            valid_modes = ("close", "handoff", "deliverable")
            if mode not in valid_modes:
                return json.dumps(
                    {
                        "error": "invalid_mode",
                        "hint": f"Mode must be one of: {', '.join(valid_modes)}",
                        "action": "use close, handoff, or deliverable",
                    }
                )
            result = await bridge.request(
                "POST", "/bridge/finalize", json_body={"mode": mode}
            )
            return bridge.format_result(result)

        return json.dumps(
            {
                "error": "unknown_action",
                "hint": f"Unknown bridge action: {action}",
                "action": "use claim or finalize",
            }
        )
