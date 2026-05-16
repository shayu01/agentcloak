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

    ``None`` values are pruned recursively (R7 from the CLI redesign): the
    daemon ships open-ended Pydantic models that include nullable fields like
    ``current_url`` / ``local_proxy``, but MCP tools pay per-token. Stripping
    nulls shaves ~10% off snapshot/health responses without losing
    information — agents can tell "missing key" from "value=None" through
    the schema.
    """
    payload = envelope.get("data", envelope)
    cleaned = _drop_nulls(payload)
    return orjson.dumps(cleaned).decode()


def _drop_nulls(value: Any) -> Any:
    """Recursively strip ``None`` values from dicts / lists.

    Lists keep ``None`` entries (positional semantics matter for some
    payloads); only dict-level keys with ``None`` value are removed. This
    matches what ``Pydantic.model_dump(exclude_none=True)`` does for nested
    models, but operates on plain dicts so it covers daemon-side payloads
    that don't round-trip through Pydantic.
    """
    if isinstance(value, dict):
        d: dict[str, Any] = value  # type: ignore[assignment]
        return {k: _drop_nulls(v) for k, v in d.items() if v is not None}
    if isinstance(value, list):
        lst: list[Any] = value  # type: ignore[assignment]
        return [_drop_nulls(v) for v in lst]
    return value


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
