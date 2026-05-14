"""Adapter code generation from API endpoint patterns."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from agentcloak.core.types import Strategy

if TYPE_CHECKING:
    from agentcloak.adapters.analyzer import EndpointPattern

__all__ = ["generate_adapter", "generate_adapters"]

_PARAM_RE = re.compile(r":(\w+)")


def _path_params(path: str) -> list[str]:
    return _PARAM_RE.findall(path)


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug or "unnamed"


def _derive_name(pattern: EndpointPattern) -> str:
    parts = [
        p
        for p in pattern.path.strip("/").split("/")
        if not p.startswith(":") and p not in ("api", "v1", "v2", "v3", "v4")
    ]
    if parts:
        return _slugify("_".join(parts[-2:]))
    return _slugify(pattern.path)


def _build_args_code(pattern: EndpointPattern) -> str:
    lines: list[str] = []
    for param in _path_params(pattern.path):
        help_text = f"{param.title()} parameter"
        lines.append(
            f'        Arg("{param}", type=str, required=True, help="{help_text}"),'
        )
    for qp in pattern.query_params:
        lines.append(f'        Arg("{qp}", default=None, help="{qp} query parameter"),')
    if not lines:
        return ""
    inner = "\n".join(lines)
    return f"    args=[\n{inner}\n    ],\n"


def _build_pipeline_code(pattern: EndpointPattern) -> str:
    path = pattern.path
    for param in _path_params(pattern.path):
        path = path.replace(f":{param}", f"{{args.{param}}}")

    url = f"https://{pattern.domain}{path}"

    qp_parts: list[str] = []
    for qp in pattern.query_params:
        qp_parts.append(f"{qp}={{args.{qp}}}")
    if qp_parts:
        url += "?" + "&".join(qp_parts)

    steps: list[str] = []

    if pattern.strategy in (Strategy.COOKIE, Strategy.HEADER):
        steps.append(f'        {{"navigate": "https://{pattern.domain}"}},')

    if pattern.method == "GET":
        steps.append(
            f"        {{\"evaluate\": \"fetch('{url}', {{credentials: 'include'}})"
            f'.then(r => r.json())"}},'
        )
    else:
        body_hint = "{}"
        if pattern.request_schema:
            keys = list(pattern.request_schema.keys())[:5]
            pairs = ", ".join(f'\\"{k}\\": {{args.{k}}}' for k in keys)
            body_hint = f"{{{pairs}}}"
        steps.append(
            f'        {{"evaluate": "fetch(\'{url}\', '
            f"{{method: '{pattern.method}', "
            f"credentials: 'include', "
            f"headers: {{'Content-Type': 'application/json'}}, "
            f"body: JSON.stringify({body_hint})"
            f'}}).then(r => r.json())"}},',
        )

    return "\n".join(steps)


def generate_adapter(
    site: str,
    pattern: EndpointPattern,
    *,
    name: str | None = None,
) -> str:
    """Generate Python adapter source code from an EndpointPattern."""
    adapter_name = name or _derive_name(pattern)
    func_name = f"{_slugify(site)}_{_slugify(adapter_name)}"
    access = "read" if pattern.method in ("GET", "HEAD", "OPTIONS") else "write"

    args_code = _build_args_code(pattern)
    pipeline_code = _build_pipeline_code(pattern)

    lines: list[str] = []
    lines.append("@adapter(")
    lines.append(f'    site="{site}",')
    lines.append(f'    name="{adapter_name}",')
    lines.append(f"    strategy=Strategy.{pattern.strategy.name},")
    if pattern.domain:
        lines.append(f'    domain="{pattern.domain}",')
    lines.append(f'    description="{pattern.method} {pattern.path}",')
    lines.append(f'    access="{access}",')
    if args_code:
        lines.append(args_code.rstrip())
    lines.append("    pipeline=[")
    lines.append(pipeline_code)
    lines.append("    ],")
    lines.append(")")
    lines.append(f"def {func_name}() -> None:")
    lines.append('    """Generated adapter — review before use."""')
    lines.append("")

    return "\n".join(lines)


def generate_adapters(
    site: str,
    patterns: list[EndpointPattern],
) -> str:
    """Generate a complete adapter module from multiple patterns."""
    header_lines = [
        f'"""Auto-generated adapters for {site} — review before use."""',
        "",
        "from __future__ import annotations",
        "",
        "from agentcloak.adapters.registry import adapter",
        "from agentcloak.adapters.types import Arg",
        "from agentcloak.core.types import Strategy",
        "",
    ]
    header = "\n".join(header_lines) + "\n"

    body_parts: list[str] = []
    for pattern in patterns:
        if pattern.category == "telemetry":
            continue
        body_parts.append(generate_adapter(site, pattern))

    return header + "\n\n".join(body_parts)
