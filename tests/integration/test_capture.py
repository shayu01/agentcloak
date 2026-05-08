"""Scenario D: network request capture — start, stop, analyze."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest


async def test_capture_start_stop(browser_context: Any, local_server: str) -> None:
    """Start capture, navigate, stop, verify entries recorded."""
    browser_context.capture_store.start()
    assert browser_context.capture_store.recording

    await browser_context.navigate(f"{local_server}/index.html")
    # Small delay to let response handler fire
    await asyncio.sleep(0.5)

    browser_context.capture_store.stop()
    assert not browser_context.capture_store.recording

    entries = browser_context.capture_store.entries()
    assert len(entries) > 0


async def test_capture_records_requests(
    browser_context: Any, local_server: str
) -> None:
    """Verify captured entries have correct structure."""
    browser_context.capture_store.clear()
    browser_context.capture_store.start()

    await browser_context.navigate(f"{local_server}/form.html")
    await asyncio.sleep(0.5)

    browser_context.capture_store.stop()
    entries = browser_context.capture_store.entries()

    if len(entries) > 0:
        entry = entries[0]
        assert hasattr(entry, "method")
        assert hasattr(entry, "url")
        assert hasattr(entry, "status")
        valid = ("GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD")
        assert entry.method in valid

    # Cleanup
    browser_context.capture_store.clear()


@pytest.mark.network
async def test_capture_real_site(browser_context: Any) -> None:
    """Capture requests from a real website."""
    browser_context.capture_store.clear()
    browser_context.capture_store.start()

    await browser_context.navigate("https://httpbin.org/get", timeout=15.0)
    await asyncio.sleep(1)

    browser_context.capture_store.stop()
    entries = browser_context.capture_store.entries()
    assert len(entries) > 0

    browser_context.capture_store.clear()
