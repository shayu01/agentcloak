"""Tests for browser/patchright_ctx.py — PatchrightContext with mocked Playwright."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from browserctl.browser.patchright_ctx import PatchrightContext
from browserctl.core.errors import BackendError, BrowserTimeoutError, NavigationError
from browserctl.core.seq import RingBuffer, SeqCounter


def _cdp_node(role: str, name: str) -> dict[str, Any]:
    return {"role": {"value": role}, "name": {"value": name}}


def _mock_cdp_session() -> MagicMock:
    cdp = MagicMock()
    cdp.send = AsyncMock(
        return_value={
            "nodes": [
                _cdp_node("RootWebArea", "Example"),
                _cdp_node("heading", "Main Title"),
                _cdp_node("link", "Click me"),
                _cdp_node("button", "Submit"),
                _cdp_node("textbox", "Search"),
            ]
        }
    )
    cdp.detach = AsyncMock()
    return cdp


def _default_page() -> MagicMock:
    page = MagicMock()
    page.on = MagicMock()
    page.url = "https://example.com"
    page.title = AsyncMock(return_value="Example")
    page.goto = AsyncMock(return_value=MagicMock(status=200))
    page.evaluate = AsyncMock(return_value="result")
    page.screenshot = AsyncMock(return_value=b"\x89PNG\r\n\x1a\nfakedata")
    page.content = AsyncMock(return_value="<html><body>Hello</body></html>")
    page.context = MagicMock()
    page.context.new_cdp_session = AsyncMock(return_value=_mock_cdp_session())
    return page


def _make_ctx(
    *,
    page: Any | None = None,
) -> PatchrightContext:
    mock_page = page if page is not None else _default_page()
    return PatchrightContext(
        page=mock_page,
        browser=MagicMock(),
        playwright=MagicMock(),
        seq_counter=SeqCounter(),
        ring_buffer=RingBuffer(),
    )


class TestNavigate:
    @pytest.mark.asyncio
    async def test_navigate_success(self) -> None:
        ctx = _make_ctx()
        result = await ctx.navigate("https://example.com")
        assert result["url"] == "https://example.com"
        assert result["title"] == "Example"
        assert result["status"] == 200
        assert ctx.seq == 1

    @pytest.mark.asyncio
    async def test_navigate_timeout(self) -> None:
        page = MagicMock()
        page.on = MagicMock()
        page.goto = AsyncMock(side_effect=Exception("Timeout 30000ms exceeded"))
        ctx = _make_ctx(page=page)
        with pytest.raises(BrowserTimeoutError):
            await ctx.navigate("https://slow.example.com")

    @pytest.mark.asyncio
    async def test_navigate_failure(self) -> None:
        page = MagicMock()
        page.on = MagicMock()
        page.goto = AsyncMock(side_effect=Exception("net::ERR_NAME_NOT_RESOLVED"))
        ctx = _make_ctx(page=page)
        with pytest.raises(NavigationError):
            await ctx.navigate("https://bad.example.com")


class TestSnapshot:
    @pytest.mark.asyncio
    async def test_accessible_mode(self) -> None:
        ctx = _make_ctx()
        snap = await ctx.snapshot(mode="accessible")
        assert snap.mode == "accessible"
        assert len(snap.selector_map) == 3
        assert "[1]" in snap.tree_text
        assert "Click me" in snap.tree_text

    @pytest.mark.asyncio
    async def test_dom_mode(self) -> None:
        ctx = _make_ctx()
        snap = await ctx.snapshot(mode="dom")
        assert snap.mode == "dom"
        assert "<html>" in snap.tree_text

    @pytest.mark.asyncio
    async def test_content_mode(self) -> None:
        page = MagicMock()
        page.on = MagicMock()
        page.url = "https://example.com"
        page.title = AsyncMock(return_value="Example")
        page.evaluate = AsyncMock(return_value="Hello World")
        ctx = _make_ctx(page=page)
        snap = await ctx.snapshot(mode="content")
        assert snap.mode == "content"
        assert "Hello World" in snap.tree_text

    @pytest.mark.asyncio
    async def test_invalid_mode(self) -> None:
        ctx = _make_ctx()
        with pytest.raises(BackendError):
            await ctx.snapshot(mode="invalid")


class TestEvaluate:
    @pytest.mark.asyncio
    async def test_evaluate_success(self) -> None:
        ctx = _make_ctx()
        result = await ctx.evaluate("document.title")
        assert result == "result"
        assert ctx.seq == 1

    @pytest.mark.asyncio
    async def test_evaluate_error(self) -> None:
        page = MagicMock()
        page.on = MagicMock()
        page.evaluate = AsyncMock(side_effect=Exception("SyntaxError"))
        ctx = _make_ctx(page=page)
        with pytest.raises(BackendError):
            await ctx.evaluate("bad code{{{")


class TestScreenshot:
    @pytest.mark.asyncio
    async def test_returns_bytes(self) -> None:
        ctx = _make_ctx()
        result = await ctx.screenshot()
        assert isinstance(result, bytes)

    @pytest.mark.asyncio
    async def test_does_not_increment_seq(self) -> None:
        ctx = _make_ctx()
        await ctx.screenshot()
        assert ctx.seq == 0


class TestSeqBehavior:
    @pytest.mark.asyncio
    async def test_navigate_increments(self) -> None:
        ctx = _make_ctx()
        await ctx.navigate("https://a.com")
        await ctx.navigate("https://b.com")
        assert ctx.seq == 2

    @pytest.mark.asyncio
    async def test_snapshot_does_not_increment(self) -> None:
        ctx = _make_ctx()
        await ctx.navigate("https://a.com")
        await ctx.snapshot()
        assert ctx.seq == 1

    @pytest.mark.asyncio
    async def test_evaluate_increments(self) -> None:
        ctx = _make_ctx()
        await ctx.evaluate("1+1")
        assert ctx.seq == 1


class TestProperties:
    def test_stealth_tier(self) -> None:
        ctx = _make_ctx()
        assert ctx.stealth_tier.value == "patchright"
