"""Integration test fixtures — browser context (dual-backend) + local HTTP server."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from aiohttp import web

# ---------------------------------------------------------------------------
# Local HTTP server serving test HTML pages
# ---------------------------------------------------------------------------

_PAGES_DIR = Path(__file__).parent / "pages"


async def _create_static_app() -> web.Application:
    """aiohttp app that serves static files from the pages/ directory."""
    app = web.Application()

    async def _serve(request: web.Request) -> web.Response:
        name = request.match_info["name"]
        path = _PAGES_DIR / name
        if not path.is_file():
            return web.Response(text="Not Found", status=404)
        return web.Response(
            body=path.read_bytes(),
            content_type="text/html",
        )

    app.router.add_get("/{name}", _serve)
    # Redirect root to index.html
    app.router.add_get(
        "/",
        lambda _: web.HTTPFound("/index.html"),
    )
    return app


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def local_server() -> AsyncGenerator[str, None]:
    """Session-scoped local HTTP server for test pages."""
    app = await _create_static_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    # Extract the actual port
    assert runner.addresses
    host, port = runner.addresses[0][:2]
    base_url = f"http://{host}:{port}"
    yield base_url
    await runner.cleanup()


# ---------------------------------------------------------------------------
# Browser context fixture — dual-backend parametrization
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(
    params=["patchright", "cloak"],
    scope="session",
    loop_scope="session",
)
async def browser_context(
    request: pytest.FixtureRequest,
) -> AsyncGenerator[Any, None]:
    """Launch a real headless browser context (patchright or cloak)."""
    backend = request.param

    if backend == "cloak":
        pytest.importorskip("cloakbrowser")
        from browserctl.browser.cloak_ctx import launch_cloak

        ctx = await launch_cloak(
            headless=True,
            viewport_width=1280,
            viewport_height=720,
        )
    else:
        from browserctl.browser.patchright_ctx import launch_patchright

        ctx = await launch_patchright(
            headless=True,
            viewport_width=1280,
            viewport_height=720,
        )

    yield ctx
    await ctx.close()


@pytest_asyncio.fixture
async def fresh_context() -> AsyncGenerator[Any, None]:
    """Function-scoped patchright context for tests that need isolation."""
    from browserctl.browser.patchright_ctx import launch_patchright

    ctx = await launch_patchright(
        headless=True,
        viewport_width=1280,
        viewport_height=720,
    )
    yield ctx
    await ctx.close()
