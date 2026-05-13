"""Scenario E: profile / login state persistence via cookies."""

from __future__ import annotations

import tempfile
from pathlib import Path
from urllib.parse import urlparse

import pytest


@pytest.mark.parametrize("backend", ["playwright"])
async def test_profile_cookie_persistence(backend: str, local_server: str) -> None:
    """Set cookie via Playwright API, close context, reopen, verify cookie."""
    from agentcloak.browser.playwright_ctx import launch_playwright

    parsed = urlparse(local_server)

    with tempfile.TemporaryDirectory() as tmpdir:
        profile_dir = Path(tmpdir) / "test-profile"
        profile_dir.mkdir()

        # First session: add a persistent cookie via Playwright API
        ctx1 = await launch_playwright(
            headless=True,
            viewport_width=1280,
            viewport_height=720,
            profile_dir=profile_dir,
        )
        await ctx1.navigate(f"{local_server}/index.html")
        # Use the Playwright context API to set a persistent cookie
        pw_ctx = ctx1._page.context
        await pw_ctx.add_cookies(
            [
                {
                    "name": "test_session",
                    "value": "abc123",
                    "domain": parsed.hostname,
                    "path": "/",
                    # Expire far in the future so it persists across restarts
                    "expires": 2000000000,
                }
            ]
        )
        # Verify it took effect
        cookies = await pw_ctx.cookies()
        names = [c["name"] for c in cookies]
        assert "test_session" in names
        await ctx1.close()

        # Second session: verify cookie persists
        ctx2 = await launch_playwright(
            headless=True,
            viewport_width=1280,
            viewport_height=720,
            profile_dir=profile_dir,
        )
        await ctx2.navigate(f"{local_server}/index.html")
        pw_ctx2 = ctx2._page.context
        cookies2 = await pw_ctx2.cookies()
        cookie_map = {c["name"]: c["value"] for c in cookies2}
        assert cookie_map.get("test_session") == "abc123"
        await ctx2.close()
