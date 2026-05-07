"""JSON output helpers implementing the CLI output contract."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

import orjson

if TYPE_CHECKING:
    from browserctl.core.errors import AgentBrowserError

__all__ = ["output_error", "output_json", "set_pretty"]

_pretty = False


def set_pretty(*, enabled: bool) -> None:
    global _pretty
    _pretty = enabled


def output_json(data: dict[str, Any], *, seq: int) -> None:
    """Write a success envelope to stdout."""
    envelope: dict[str, Any] = {"ok": True, "seq": seq, "data": data}
    _write_envelope(envelope)


def output_error(exc: AgentBrowserError) -> None:
    """Write an error envelope to stdout."""
    _write_envelope(exc.to_dict())


def _write_envelope(envelope: dict[str, Any]) -> None:
    opts = orjson.OPT_INDENT_2 if _pretty else 0
    sys.stdout.buffer.write(orjson.dumps(envelope, option=opts))
    sys.stdout.buffer.write(b"\n")
    sys.stdout.buffer.flush()
