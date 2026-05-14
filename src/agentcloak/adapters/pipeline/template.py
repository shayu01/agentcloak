"""Template engine for pipeline DSL — resolves {path} expressions."""

from __future__ import annotations

import re
from typing import Any, cast

__all__ = ["render", "render_deep"]

_FULL_RE = re.compile(r"^\{([^}]+)\}$")
_PARTIAL_RE = re.compile(r"\{([^}]+)\}")


def _resolve_path(path: str, context: dict[str, Any]) -> Any:
    parts = path.strip().split(".")
    value: Any = context
    for part in parts:
        if isinstance(value, dict):
            value = cast("Any", value[part])
        elif isinstance(value, (list, tuple)) and part.isdigit():
            value = cast("Any", value[int(part)])
        else:
            value = getattr(cast("Any", value), part)
    return value


def render(template: Any, context: dict[str, Any]) -> Any:
    """Render a template string against *context*.

    Full template ``{path}`` returns the resolved value with its native type.
    Mixed templates like ``"prefix {path} suffix"`` return a string.
    Non-string values pass through unchanged.
    """
    if not isinstance(template, str):
        return template

    full = _FULL_RE.match(template)
    if full:
        return _resolve_path(full.group(1), context)

    def _replace(m: re.Match[str]) -> str:
        return str(_resolve_path(m.group(1), context))

    return _PARTIAL_RE.sub(_replace, template)


def render_deep(obj: Any, context: dict[str, Any]) -> Any:
    """Recursively render all template strings in a nested structure."""
    if isinstance(obj, str):
        return render(obj, context)
    if isinstance(obj, dict):
        return {
            k: render_deep(v, context) for k, v in cast("dict[str, Any]", obj).items()
        }
    if isinstance(obj, list):
        return [render_deep(el, context) for el in cast("list[Any]", obj)]
    return obj
