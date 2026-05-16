"""Browser backend implementations behind a unified ABC base class."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agentcloak.browser.base import BrowserContextBase
from agentcloak.browser.state import BrowserState, ElementRef, PageSnapshot, TabInfo
from agentcloak.core.types import StealthTier

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "BrowserContextBase",
    "BrowserState",
    "ElementRef",
    "PageSnapshot",
    "StealthTier",
    "TabInfo",
    "create_context",
]


async def create_context(
    *,
    tier: StealthTier = StealthTier.CLOAK,
    headless: bool = True,
    viewport_width: int = 1280,
    viewport_height: int = 800,
    profile_dir: Path | None = None,
    humanize: bool = False,
    extensions: list[str] | None = None,
    proxy_url: str | None = None,
) -> BrowserContextBase:
    """Factory: create a browser context for the given stealth tier."""
    if tier == StealthTier.PLAYWRIGHT:
        from agentcloak.browser.playwright_ctx import launch_playwright

        return await launch_playwright(
            headless=headless,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
            profile_dir=profile_dir,
            proxy_url=proxy_url,
        )

    if tier == StealthTier.CLOAK:
        from agentcloak.browser.cloak_ctx import launch_cloak

        return await launch_cloak(
            headless=headless,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
            profile_dir=profile_dir,
            humanize=humanize,
            extensions=extensions,
            proxy_url=proxy_url,
        )

    raise NotImplementedError(f"Backend {tier!r} not yet implemented")
