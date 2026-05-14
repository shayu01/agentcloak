"""BrowserContext Protocol — the contract all backends implement."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from agentcloak.browser.state import FrameInfo, PageSnapshot, PendingDialog
    from agentcloak.core.types import StealthTier

__all__ = ["ActionResult", "BrowserContext", "NetworkRequest"]


type ActionResult = dict[str, Any]
type NetworkRequest = dict[str, Any]


@runtime_checkable
class BrowserContext(Protocol):
    """Unified interface for all browser backends."""

    async def navigate(self, url: str, *, timeout: float = 30.0) -> ActionResult: ...

    async def snapshot(
        self,
        *,
        mode: str = "accessible",
        max_nodes: int = 0,
        max_chars: int = 0,
        focus: int = 0,
        offset: int = 0,
    ) -> PageSnapshot: ...

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

    async def raw_cdp(
        self, method: str, params: dict[str, Any] | None = None
    ) -> Any: ...

    async def dialog_status(self) -> PendingDialog | None: ...

    async def dialog_handle(
        self, action: str, *, text: str | None = None
    ) -> ActionResult: ...

    async def wait(
        self,
        *,
        condition: str,
        value: str = "",
        timeout: int = 30000,
        state: str = "visible",
    ) -> ActionResult: ...

    async def upload(
        self, index: int, files: list[str]
    ) -> ActionResult: ...

    async def frame_list(self) -> list[FrameInfo]: ...

    async def frame_focus(
        self,
        *,
        name: str | None = None,
        url: str | None = None,
        main: bool = False,
    ) -> ActionResult: ...

    async def close(self) -> None: ...

    @property
    def seq(self) -> int: ...

    @property
    def stealth_tier(self) -> StealthTier: ...
