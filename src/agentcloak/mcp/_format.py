"""Shared response formatting for MCP tools.

The shared :class:`~agentcloak.client.DaemonClient` raises
:class:`AgentBrowserError` on any non-2xx response. MCP tools need to return
strings, so this helper centralises the exception-to-string translation: every
tool wraps its daemon call in :func:`format_call` and gets back the same JSON
shape the previous ``DaemonBridge.format_result`` produced (data on success,
three-field envelope on failure).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import orjson

from agentcloak.core.errors import AgentBrowserError

if TYPE_CHECKING:
    from collections.abc import Awaitable

__all__ = ["error_json", "format_call", "format_envelope"]


def format_envelope(envelope: dict[str, Any]) -> str:
    """Render a daemon success envelope as a JSON string.

    The daemon wraps every success in ``{"ok": True, "seq": N, "data": ...}``.
    MCP clients only care about the payload, so we strip the envelope and emit
    the inner ``data`` object directly. ``orjson`` keeps the byte order stable
    so checksum-based caching still works.
    """
    payload = envelope.get("data", envelope)
    return orjson.dumps(payload).decode()


def error_json(exc: AgentBrowserError) -> str:
    """Render an :class:`AgentBrowserError` as the standard three-field envelope."""
    return orjson.dumps(
        {
            "error": exc.error,
            "hint": exc.hint,
            "action": exc.action,
        }
    ).decode()


async def format_call(coro: Awaitable[dict[str, Any]]) -> str:
    """Run a daemon coroutine and JSON-encode the result for an MCP tool.

    Centralising the try/except means every MCP tool gets the same error
    behaviour without copying boilerplate. Any unexpected exception still
    bubbles up so the MCP framework can log it — only errors that carry the
    three-field envelope get translated here.
    """
    try:
        result = await coro
    except AgentBrowserError as exc:
        return error_json(exc)
    return format_envelope(result)
