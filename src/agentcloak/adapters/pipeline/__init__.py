"""Pipeline DSL — declarative data-flow adapter execution."""

from agentcloak.adapters.pipeline.engine import execute_pipeline
from agentcloak.adapters.pipeline.template import render, render_deep

__all__ = ["execute_pipeline", "render", "render_deep"]
