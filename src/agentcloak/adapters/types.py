"""Adapter type definitions — metadata, arguments, and entry records."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from agentcloak.core.types import Strategy

if TYPE_CHECKING:
    from agentcloak.adapters.context import AdapterContext

__all__ = ["AdapterEntry", "AdapterMeta", "Arg"]


@dataclass(frozen=True)
class Arg:
    """Single argument accepted by an adapter command."""

    name: str
    type: type = str
    default: Any = None
    required: bool = False
    help: str = ""
    choices: tuple[str, ...] | None = None
    positional: bool = False


@dataclass(frozen=True)
class AdapterMeta:
    """Declarative metadata for a registered adapter."""

    site: str
    name: str
    strategy: Strategy
    description: str = ""
    domain: str | None = None
    access: Literal["read", "write"] = "read"
    args: tuple[Arg, ...] = ()
    columns: tuple[str, ...] | None = None
    pipeline: tuple[dict[str, Any], ...] | None = None

    @property
    def full_name(self) -> str:
        return f"{self.site}/{self.name}"

    @property
    def needs_browser(self) -> bool:
        return self.strategy is not Strategy.PUBLIC

    @property
    def navigate_before(self) -> str | None:
        if self.strategy in (Strategy.COOKIE, Strategy.HEADER) and self.domain:
            return f"https://{self.domain}"
        return None


AdapterHandler = Callable[["AdapterContext"], Awaitable[list[dict[str, Any]]]]


@dataclass(frozen=True)
class AdapterEntry:
    """A registered adapter: metadata + handler (function or pipeline)."""

    meta: AdapterMeta
    handler: AdapterHandler | None = field(default=None)

    @property
    def is_pipeline(self) -> bool:
        return self.meta.pipeline is not None
