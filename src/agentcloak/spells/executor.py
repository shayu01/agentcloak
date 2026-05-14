"""Spell execution — dispatches to function handler or pipeline engine."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from agentcloak.core.errors import AgentBrowserError
from agentcloak.spells.context import SpellContext
from agentcloak.spells.pipeline.engine import execute_pipeline

if TYPE_CHECKING:
    from agentcloak.spells.types import SpellEntry

__all__ = ["execute_spell"]

log = structlog.get_logger()


async def execute_spell(
    entry: SpellEntry,
    *,
    args: dict[str, Any],
    browser: Any | None = None,
) -> list[dict[str, Any]]:
    """Run a spell and return its result rows."""
    meta = entry.meta
    log.info("spell.execute", spell=meta.full_name, strategy=meta.strategy)

    for arg_def in meta.args:
        if arg_def.name not in args and arg_def.default is not None:
            args[arg_def.name] = arg_def.default

    if meta.needs_browser and browser is None:
        raise AgentBrowserError(
            error="spell_no_browser",
            hint=f"Spell '{meta.full_name}' requires a browser context "
            f"(strategy={meta.strategy}).",
            action="start a browser session first",
        )

    if meta.navigate_before and browser is not None:
        log.debug("spell.pre_navigate", url=meta.navigate_before)
        await browser.navigate(meta.navigate_before)

    if entry.is_pipeline:
        if meta.pipeline is None:
            raise RuntimeError(
                f"Spell '{meta.full_name}' marked as pipeline"
                " but has no pipeline definition"
            )
        raw = await execute_pipeline(meta.pipeline, args=args, browser=browser)
        if isinstance(raw, list):
            return raw  # type: ignore[return-value]
        return [raw] if raw is not None else []

    if entry.handler is None:
        raise AgentBrowserError(
            error="spell_no_handler",
            hint=f"Spell '{meta.full_name}' has neither pipeline nor handler.",
            action="add a handler function or pipeline definition",
        )

    ctx = SpellContext(meta=meta, args=args, browser=browser)
    return await entry.handler(ctx)
