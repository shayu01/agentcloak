"""AdapterContext — unified runtime interface for adapter handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from browserctl.adapters.types import AdapterMeta
    from browserctl.browser.protocol import (
        ActionResult,
        BrowserContext,
        NetworkRequest,
    )
    from browserctl.browser.state import PageSnapshot

__all__ = ["AdapterContext"]


class AdapterContext:
    """Wraps BrowserContext + parsed args for adapter execution."""

    def __init__(
        self,
        *,
        meta: AdapterMeta,
        args: dict[str, Any],
        browser: BrowserContext | None = None,
    ) -> None:
        self._meta = meta
        self._args = args
        self._browser = browser

    @property
    def meta(self) -> AdapterMeta:
        return self._meta

    @property
    def args(self) -> dict[str, Any]:
        return self._args

    @property
    def browser(self) -> BrowserContext:
        if self._browser is None:
            msg = "browser context not available for this adapter"
            raise RuntimeError(msg)
        return self._browser

    @property
    def has_browser(self) -> bool:
        return self._browser is not None

    # -- Convenience proxies to BrowserContext --

    async def navigate(self, url: str, *, timeout: float = 30.0) -> ActionResult:
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
