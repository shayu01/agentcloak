"""Upload tool — file upload to input elements."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from agentcloak.mcp.client import DaemonBridge

__all__ = ["register"]


def register(mcp: FastMCP, bridge: DaemonBridge) -> None:
    @mcp.tool(annotations={"readOnlyHint": False})
    async def agentcloak_upload(
        index: int,
        files: list[str],
    ) -> str:
        """Upload file(s) to a file input element.

        Use agentcloak_snapshot to find the file input element's [N] ref.

        Args:
            index: Element [N] reference of the file input
            files: List of absolute file paths to upload

        Returns:
            JSON with upload confirmation and file names.
        """
        body = {"index": index, "files": files}
        result = await bridge.request("POST", "/upload", json_body=body)
        return bridge.format_result(result)
