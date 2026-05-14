"""Pipeline executor — runs a sequence of declarative steps."""

from __future__ import annotations

from typing import Any

import structlog

from agentcloak.core.errors import AgentBrowserError
from agentcloak.spells.pipeline.steps import STEP_REGISTRY, StepContext

__all__ = ["execute_pipeline"]

log = structlog.get_logger()


async def execute_pipeline(
    pipeline: tuple[dict[str, Any], ...],
    *,
    args: dict[str, Any],
    browser: Any | None = None,
) -> Any:
    """Execute a declarative pipeline and return the final data."""
    ctx = StepContext(args=args, browser=browser)
    data: Any = None

    for i, step in enumerate(pipeline):
        for op, params in step.items():
            handler = STEP_REGISTRY.get(op)
            if handler is None:
                raise AgentBrowserError(
                    error="pipeline_unknown_step",
                    hint=f"Unknown pipeline step '{op}' at index {i}.",
                    action="check available steps: " + ", ".join(sorted(STEP_REGISTRY)),
                )
            log.debug("pipeline.step", op=op, index=i)
            data = await handler(params, data, ctx)

    return data
