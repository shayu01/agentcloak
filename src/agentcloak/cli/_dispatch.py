"""CLI dispatch helper — text-mode by default, JSON envelope on opt-in.

CLI commands all want the same shape:

* When ``--json`` (or ``AGENTCLOAK_OUTPUT=json``) is active, call the typed
  ``*_sync`` method on :class:`DaemonClient`, unwrap ``{ok, seq, data}``,
  and emit the full envelope.
* Otherwise issue the same HTTP request with ``Accept: text/plain`` and
  print whatever the daemon returned verbatim.

Centralising the branch in one helper keeps every command file a thin
parameter-binding shell. The alternative — wiring two code paths into 20+
commands — is exactly the kind of duplication v0.3.0 set out to remove.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agentcloak.cli.output import is_json_mode, json_out, value

if TYPE_CHECKING:
    from agentcloak.client import DaemonClient

__all__ = ["dispatch_text_or_json", "emit_envelope"]


def emit_envelope(result: dict[str, Any]) -> None:
    """Emit a daemon envelope as JSON to stdout.

    Helper for commands whose CLI flow doesn't fit the simple ``method+path``
    dispatch (e.g. local-only spell run or commands that combine multiple
    daemon calls). ``data`` and ``seq`` are extracted from the standard
    envelope shape — fall back to the raw dict when the caller already
    unwrapped it.
    """
    data = result.get("data", result)
    seq = int(result.get("seq", 0) or 0)
    json_out(data, seq=seq)


def dispatch_text_or_json(
    client: DaemonClient,
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
    params: dict[str, str] | None = None,
) -> None:
    """Issue a daemon request and emit the result honouring ``--json`` mode.

    Used by commands that don't need to post-process the response. Commands
    that do (e.g. ``screenshot`` writing base64 to a file) should call the
    text/JSON paths individually.
    """
    if is_json_mode():
        # JSON path uses the typed sync API to keep error envelopes uniform.
        result = client._send_sync(  # pyright: ignore[reportPrivateUsage]
            method, path, json_body=json_body, params=params
        )
        emit_envelope(result)
        return
    text = client.request_text_sync(method, path, json_body=json_body, params=params)
    value(text)
