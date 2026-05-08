"""Pipeline DSL — declarative data-flow adapter execution."""

from browserctl.adapters.pipeline.engine import execute_pipeline
from browserctl.adapters.pipeline.template import render, render_deep

__all__ = ["execute_pipeline", "render", "render_deep"]
