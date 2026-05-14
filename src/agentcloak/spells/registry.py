"""Spell registry and @spell decorator."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any, Literal, TypeVar, overload

import structlog

from agentcloak.spells.types import Arg, SpellEntry, SpellHandler, SpellMeta

if TYPE_CHECKING:
    from agentcloak.core.types import Strategy

__all__ = ["SpellRegistry", "get_registry", "spell"]

log = structlog.get_logger()
F = TypeVar("F", bound=Callable[..., Any])


class SpellRegistry:
    """Global spell registry — maps ``site/name`` to SpellEntry."""

    def __init__(self) -> None:
        self._entries: dict[str, SpellEntry] = {}

    def register(self, entry: SpellEntry) -> None:
        key = entry.meta.full_name
        if key in self._entries:
            log.info("spell.override", key=key)
        self._entries[key] = entry
        log.debug("spell.registered", key=key, strategy=entry.meta.strategy)

    def get(self, site: str, name: str) -> SpellEntry | None:
        return self._entries.get(f"{site}/{name}")

    def list_all(self) -> list[SpellEntry]:
        return list(self._entries.values())

    def list_by_site(self, site: str) -> list[SpellEntry]:
        prefix = f"{site}/"
        return [
            e for e in self._entries.values() if e.meta.full_name.startswith(prefix)
        ]

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, key: str) -> bool:
        return key in self._entries

    def clear(self) -> None:
        self._entries.clear()


_global_registry = SpellRegistry()


def get_registry() -> SpellRegistry:
    """Return the global spell registry singleton."""
    return _global_registry


@overload
def spell(
    *,
    site: str,
    name: str,
    strategy: Strategy,
    description: str = ...,
    domain: str | None = ...,
    access: Literal["read", "write"] = ...,
    args: Sequence[Arg] = ...,
    columns: Sequence[str] | None = ...,
    pipeline: Sequence[dict[str, Any]] | None = ...,
) -> Callable[[F], F]: ...


@overload
def spell(
    *,
    site: str,
    name: str,
    strategy: Strategy,
    description: str = ...,
    domain: str | None = ...,
    access: Literal["read", "write"] = ...,
    args: Sequence[Arg] = ...,
    columns: Sequence[str] | None = ...,
) -> Callable[[F], F]: ...


def spell(
    *,
    site: str,
    name: str,
    strategy: Strategy,
    description: str = "",
    domain: str | None = None,
    access: Literal["read", "write"] = "read",
    args: Sequence[Arg] = (),
    columns: Sequence[str] | None = None,
    pipeline: Sequence[dict[str, Any]] | None = None,
) -> Callable[[F], F]:
    """Decorator that registers a spell with the global registry.

    Function mode: decorate an ``async def`` handler.
    Pipeline mode: pass ``pipeline=[...]`` and decorate a placeholder.
    """

    def decorator(func: F) -> F:
        meta = SpellMeta(
            site=site,
            name=name,
            strategy=strategy,
            description=description,
            domain=domain,
            access=access,
            args=tuple(args),
            columns=tuple(columns) if columns else None,
            pipeline=tuple(pipeline) if pipeline else None,
        )
        handler: SpellHandler | None = None
        if pipeline is None:
            handler = func  # type: ignore[assignment]

        entry = SpellEntry(meta=meta, handler=handler)
        _global_registry.register(entry)
        return func

    return decorator
