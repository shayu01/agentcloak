"""Example spells demonstrating pipeline and function modes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agentcloak.core.types import Strategy
from agentcloak.spells.registry import spell
from agentcloak.spells.types import Arg

if TYPE_CHECKING:
    from agentcloak.spells.context import SpellContext

# -- Pipeline mode: public API, no browser needed --


@spell(
    site="httpbin",
    name="headers",
    strategy=Strategy.PUBLIC,
    description="Inspect request headers via httpbin.org",
    access="read",
    args=(Arg("user-agent", default="agentcloak/0.2", help="Custom User-Agent"),),
    pipeline=[
        {
            "fetch": {
                "url": "https://httpbin.org/headers",
                "headers": {"User-Agent": "{args.user-agent}"},
            }
        },
        {"select": "headers"},
    ],
)
def httpbin_headers() -> None:
    """Pipeline spell placeholder."""


# -- Function mode: browser required (UI interaction) --


@spell(
    site="example",
    name="title",
    strategy=Strategy.COOKIE,
    domain="example.com",
    description="Get the page title of example.com",
    access="read",
)
async def example_title(ctx: SpellContext) -> list[dict[str, object]]:
    title = await ctx.evaluate("document.title")
    url = await ctx.evaluate("location.href")
    return [{"title": title, "url": url}]
