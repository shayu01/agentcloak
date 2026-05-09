"""Scenario A: information gathering — navigate, screenshot, snapshot, evaluate."""

from __future__ import annotations

from typing import Any

import pytest


async def test_navigate_local_page(browser_context: Any, local_server: str) -> None:
    """Navigate to local page and verify URL, title, seq."""
    result = await browser_context.navigate(f"{local_server}/index.html")
    assert "url" in result
    assert result["url"].endswith("/index.html")
    assert result["title"] == "Test Page"
    assert result["seq"] > 0


async def test_screenshot_default_jpeg(browser_context: Any, local_server: str) -> None:
    """Default screenshot format is JPEG."""
    await browser_context.navigate(f"{local_server}/index.html")
    raw = await browser_context.screenshot()
    assert isinstance(raw, bytes)
    assert raw[:2] == b"\xff\xd8"  # JPEG magic bytes


async def test_snapshot_accessible(browser_context: Any, local_server: str) -> None:
    """Accessible snapshot should produce selector_map with entries."""
    await browser_context.navigate(f"{local_server}/index.html")
    snap = await browser_context.snapshot(mode="accessible")
    assert snap.url.endswith("/index.html")
    assert snap.title == "Test Page"
    assert snap.mode == "accessible"
    assert len(snap.selector_map) > 0
    assert snap.tree_text


async def test_snapshot_content(browser_context: Any, local_server: str) -> None:
    """Content snapshot should extract page text."""
    await browser_context.navigate(f"{local_server}/index.html")
    snap = await browser_context.snapshot(mode="content")
    assert snap.mode == "content"
    assert "Integration Test Page" in snap.tree_text


async def test_evaluate_js(browser_context: Any, local_server: str) -> None:
    """Evaluate JS expression and verify return value."""
    await browser_context.navigate(f"{local_server}/index.html")
    result = await browser_context.evaluate("document.title")
    assert result == "Test Page"


async def test_evaluate_js_complex(browser_context: Any, local_server: str) -> None:
    """Evaluate complex JS returning a computed value."""
    await browser_context.navigate(f"{local_server}/index.html")
    result = await browser_context.evaluate("2 + 2")
    assert result == 4


async def test_navigate_invalid_url(fresh_context: Any) -> None:
    """Navigating to invalid URL should raise NavigationError."""
    from browserctl.core.errors import AgentBrowserError

    with pytest.raises(AgentBrowserError):
        await fresh_context.navigate("http://this-domain-does-not-exist-12345.invalid")


@pytest.mark.network
async def test_navigate_real_website(browser_context: Any) -> None:
    """Navigate to a real website and verify basic response."""
    result = await browser_context.navigate("https://example.com")
    assert "example.com" in result["url"]
    assert result["title"]
