"""BrowserContext Protocol — kept as a thin alias for backwards compatibility.

The real contract now lives in :mod:`agentcloak.browser.base` as
``BrowserContextBase`` (an ABC). External code that referenced
``BrowserContext`` as a typing target keeps working — we re-export the base
class under the same name so ``isinstance(ctx, BrowserContext)`` still gives a
useful answer.
"""

from __future__ import annotations

from typing import Any

from agentcloak.browser.base import BrowserContextBase

__all__ = ["ActionResult", "BrowserContext", "NetworkRequest"]


type ActionResult = dict[str, Any]
type NetworkRequest = dict[str, Any]

# Alias kept so callers can still write ``from agentcloak.browser.protocol import
# BrowserContext`` for typing purposes.
BrowserContext = BrowserContextBase
