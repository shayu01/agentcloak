"""BrowserContext Protocol — the contract all backends implement."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from browserctl.browser.state import PageSnapshot
    from browserctl.core.types import StealthTier

__all__ = ["ActionResult", "BrowserContext", "NetworkRequest"]


type ActionResult = dict[str, Any]
type NetworkRequest = dict[str, Any]


@runtime_checkable
class BrowserContext(Protocol):
    """Unified interface for all browser backends."""

    async def navigate(self, url: str, *, timeout: float = 30.0) -> ActionResult: ...

    async def snapshot(self, *, mode: str = "accessible") -> PageSnapshot: ...

    async def action(self, kind: str, target: str, **kw: Any) -> ActionResult: ...

    async def evaluate(self, js: str, *, world: str = "main") -> Any: ...

    async def network(
        self, *, since: int | str = "last_action"
    ) -> list[NetworkRequest]: ...

    async def screenshot(
        self,
        *,
        full_page: bool = False,
        format: str = "jpeg",
        quality: int = 80,
    ) -> bytes: ...

    async def close(self) -> None: ...

    @property
    def seq(self) -> int: ...

    @property
    def stealth_tier(self) -> StealthTier: ...
