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
    headless: bool = True,
    viewport_width: int = 1280,
    viewport_height: int = 800,
) -> BrowserContext:
    """Factory: create a browser context for the given stealth tier."""
    if tier == StealthTier.PATCHRIGHT:
        from browserctl.browser.patchright_ctx import launch_patchright

        return await launch_patchright(
            headless=headless,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
        )

    raise NotImplementedError(f"Backend {tier!r} not yet implemented")
