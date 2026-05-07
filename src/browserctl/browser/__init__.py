"""Browser backend implementations behind a unified Protocol."""

from browserctl.browser.protocol import BrowserContext
from browserctl.browser.state import BrowserState, ElementRef, PageSnapshot, TabInfo
from browserctl.core.types import StealthTier

__all__ = [
    "BrowserContext",
    "BrowserState",
    "ElementRef",
    "PageSnapshot",
    "StealthTier",
    "TabInfo",
    "create_context",
]


async def create_context(
    *,
    tier: StealthTier = StealthTier.PATCHRIGHT,
    profile: str = "default",
) -> BrowserContext:
    """Factory: create a browser context for the given stealth tier."""
    raise NotImplementedError(f"Backend {tier!r} not yet implemented")
