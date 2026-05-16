"""SpellContext — unified runtime interface for spell handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agentcloak.browser.protocol import (
        ActionResult,
        BrowserContext,
        NetworkRequest,
    )
    from agentcloak.browser.state import PageSnapshot
    from agentcloak.spells.types import SpellMeta

__all__ = ["SpellContext"]


class SpellContext:
    """Wraps BrowserContext + parsed args for spell execution."""

    def __init__(
        self,
        *,
        meta: SpellMeta,
        args: dict[str, Any],
        browser: BrowserContext | None = None,
    ) -> None:
        self._meta = meta
        self._args = args
        self._browser = browser

    @property
    def meta(self) -> SpellMeta:
        return self._meta

    @property
    def args(self) -> dict[str, Any]:
        return self._args

    @property
    def browser(self) -> BrowserContext:
        if self._browser is None:
            msg = "browser context not available for this spell"
            raise RuntimeError(msg)
        return self._browser

    @property
    def has_browser(self) -> bool:
        return self._browser is not None

    # -- Convenience proxies to BrowserContext --

    async def navigate(self, url: str, *, timeout: float | None = None) -> ActionResult:
        # ``timeout=None`` lets the BrowserContext fall back to its configured
        # navigation_timeout — keeps the spell DSL free of hard-coded numbers.
        return await self.browser.navigate(url, timeout=timeout)

    async def snapshot(self, *, mode: str = "accessible") -> PageSnapshot:
        return await self.browser.snapshot(mode=mode)

    async def action(self, kind: str, target: str, **kw: Any) -> ActionResult:
        return await self.browser.action(kind, target, **kw)

    async def evaluate(self, js: str) -> Any:
        return await self.browser.evaluate(js)

    async def network(
        self, *, since: int | str = "last_action"
    ) -> list[NetworkRequest]:
        return await self.browser.network(since=since)

    async def screenshot(self, *, full_page: bool = False) -> bytes:
        return await self.browser.screenshot(full_page=full_page)

    @property
    def seq(self) -> int:
        return self.browser.seq
