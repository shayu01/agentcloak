"""Example adapters demonstrating pipeline and function modes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agentcloak.adapters.registry import adapter
from agentcloak.adapters.types import Arg
from agentcloak.core.types import Strategy

if TYPE_CHECKING:
    from agentcloak.adapters.context import AdapterContext

# -- Pipeline mode: public API, no browser needed --

@adapter(
    site="httpbin",
    name="headers",
    strategy=Strategy.PUBLIC,
    description="Inspect request headers via httpbin.org",
    access="read",
    args=(Arg("user-agent", default="agentcloak/0.1", help="Custom User-Agent"),),
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
    """Pipeline adapter placeholder."""


# -- Function mode: browser required (UI interaction) --


@adapter(
    site="example",
    name="title",
    strategy=Strategy.COOKIE,
    domain="example.com",
    description="Get the page title of example.com",
    access="read",
)
async def example_title(ctx: AdapterContext) -> list[dict[str, object]]:
    title = await ctx.evaluate("document.title")
    url = await ctx.evaluate("location.href")
    return [{"title": title, "url": url}]
