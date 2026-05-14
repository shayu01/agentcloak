"""Pipeline DSL — declarative data-flow spell execution."""

from agentcloak.spells.pipeline.engine import execute_pipeline
from agentcloak.spells.pipeline.template import render, render_deep

__all__ = ["execute_pipeline", "render", "render_deep"]
