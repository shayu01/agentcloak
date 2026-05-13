"""Adapter execution — dispatches to function handler or pipeline engine."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from agentcloak.adapters.context import AdapterContext
from agentcloak.adapters.pipeline.engine import execute_pipeline
from agentcloak.core.errors import AgentBrowserError

if TYPE_CHECKING:
    from agentcloak.adapters.types import AdapterEntry

__all__ = ["execute_adapter"]

log = structlog.get_logger()


async def execute_adapter(
    entry: AdapterEntry,
    *,
    args: dict[str, Any],
    browser: Any | None = None,
) -> list[dict[str, Any]]:
    """Run an adapter and return its result rows."""
    meta = entry.meta
    log.info("adapter.execute", adapter=meta.full_name, strategy=meta.strategy)

    for arg_def in meta.args:
        if arg_def.name not in args and arg_def.default is not None:
            args[arg_def.name] = arg_def.default

    if meta.needs_browser and browser is None:
        raise AgentBrowserError(
            error="adapter_no_browser",
            hint=f"Adapter '{meta.full_name}' requires a browser context "
            f"(strategy={meta.strategy}).",
            action="start a browser session first",
        )

    if meta.navigate_before and browser is not None:
        log.debug("adapter.pre_navigate", url=meta.navigate_before)
        await browser.navigate(meta.navigate_before)

    if entry.is_pipeline:
        if meta.pipeline is None:
            raise RuntimeError(
                f"Adapter '{meta.full_name}' marked as pipeline"
                " but has no pipeline definition"
            )
        raw = await execute_pipeline(meta.pipeline, args=args, browser=browser)
        if isinstance(raw, list):
            return raw  # type: ignore[return-value]
        return [raw] if raw is not None else []

    if entry.handler is None:
        raise AgentBrowserError(
            error="adapter_no_handler",
            hint=f"Adapter '{meta.full_name}' has neither pipeline nor handler.",
            action="add a handler function or pipeline definition",
        )

    ctx = AdapterContext(meta=meta, args=args, browser=browser)
    return await entry.handler(ctx)
