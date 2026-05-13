"""Tests for browser/playwright_ctx.py — PlaywrightContext with mocked Playwright."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from agentcloak.browser.playwright_ctx import PlaywrightContext
from agentcloak.core.errors import BackendError, BrowserTimeoutError, NavigationError
from agentcloak.core.seq import RingBuffer, SeqCounter


def _cdp_node(role: str, name: str) -> dict[str, Any]:
    return {"role": {"value": role}, "name": {"value": name}}


def _ax_tree_response() -> dict[str, Any]:
    return {
        "nodes": [
            _cdp_node("RootWebArea", "Example"),
            _cdp_node("heading", "Main Title"),
            _cdp_node("link", "Click me"),
            _cdp_node("button", "Submit"),
            _cdp_node("textbox", "Search"),
        ]
    }


def _mock_cdp_session() -> MagicMock:
    cdp = MagicMock()
    # Track event listeners so Runtime.enable can replay contexts.
    _listeners: dict[str, list] = {}

    def _on(event: str, callback: Any) -> None:
        _listeners.setdefault(event, []).append(callback)

    async def _send(method: str, params: Any = None) -> Any:
        if method == "Accessibility.getFullAXTree":
            return _ax_tree_response()
        if method == "Runtime.enable":
            # Replay existing execution contexts — simulates CDP behavior.
            main_ctx = {
                "context": {
                    "id": 1,
                    "origin": "https://example.com",
                    "name": "",
                    "auxData": {
                        "isDefault": True, "type": "default", "frameId": "F1",
                    },
                }
            }
            for cb in _listeners.get("Runtime.executionContextCreated", []):
                cb(main_ctx)
            return {}
        if method == "Runtime.disable":
            return {}
        if method == "Runtime.evaluate":
            return {"result": {"type": "string", "value": "result"}}
        return {}

    cdp.on = MagicMock(side_effect=_on)
    cdp.send = AsyncMock(side_effect=_send)
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
) -> PlaywrightContext:
    mock_page = page if page is not None else _default_page()
    return PlaywrightContext(
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
    async def test_accessible_filters_inline_text_box(self) -> None:
        """InlineTextBox and LineBreak roles are filtered from accessible output."""
        cdp = MagicMock()

        async def _send(method: str, params: Any = None) -> Any:
            if method == "Accessibility.getFullAXTree":
                return {
                    "nodes": [
                        _cdp_node("RootWebArea", "Page"),
                        _cdp_node("button", "OK"),
                        _cdp_node("InlineTextBox", "some inline text"),
                        _cdp_node("LineBreak", ""),
                        _cdp_node("StaticText", "visible"),
                    ]
                }
            return {}

        cdp.send = AsyncMock(side_effect=_send)
        cdp.detach = AsyncMock()
        page = _default_page()
        page.context.new_cdp_session = AsyncMock(return_value=cdp)
        ctx = _make_ctx(page=page)
        snap = await ctx.snapshot(mode="accessible")
        assert "InlineTextBox" not in snap.tree_text
        assert "LineBreak" not in snap.tree_text
        assert "OK" in snap.tree_text
        assert "visible" in snap.tree_text

    @pytest.mark.asyncio
    async def test_compact_mode(self) -> None:
        """Compact mode outputs only interactive elements and heading-type roles."""
        ctx = _make_ctx()
        snap = await ctx.snapshot(mode="compact")
        assert snap.mode == "compact"
        assert len(snap.selector_map) == 3
        assert "[1]" in snap.tree_text
        # heading is in _HEADING_ROLES, so it appears as structural context
        assert "heading: Main Title" in snap.tree_text
        # RootWebArea is not interactive and not in _HEADING_ROLES, so excluded
        assert "RootWebArea" not in snap.tree_text

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
        err_cdp = MagicMock()
        err_cdp.send = AsyncMock(side_effect=Exception("SyntaxError"))
        err_cdp.detach = AsyncMock()
        page = _default_page()
        page.context.new_cdp_session = AsyncMock(return_value=err_cdp)
        ctx = _make_ctx(page=page)
        with pytest.raises(BackendError):
            await ctx.evaluate("bad code{{{")

    @pytest.mark.asyncio
    async def test_evaluate_utility_world(self) -> None:
        ctx = _make_ctx()
        result = await ctx.evaluate("document.title", world="utility")
        assert result == "result"
        assert ctx.seq == 1

    @pytest.mark.asyncio
    async def test_evaluate_cdp_exception_details(self) -> None:
        """CDP exceptionDetails in response raises BackendError."""
        cdp = MagicMock()
        _listeners: dict[str, list] = {}

        def _on(event: str, callback: Any) -> None:
            _listeners.setdefault(event, []).append(callback)

        async def _send(method: str, params: Any = None) -> Any:
            if method == "Runtime.enable":
                main_ctx = {
                    "context": {
                        "id": 1,
                        "origin": "",
                        "name": "",
                        "auxData": {
                        "isDefault": True, "type": "default", "frameId": "F1",
                    },
                    }
                }
                for cb in _listeners.get("Runtime.executionContextCreated", []):
                    cb(main_ctx)
                return {}
            if method == "Runtime.disable":
                return {}
            if method == "Runtime.evaluate":
                return {
                    "result": {"type": "object"},
                    "exceptionDetails": {"text": "ReferenceError: x is not defined"},
                }
            return {}

        cdp.on = MagicMock(side_effect=_on)
        cdp.send = AsyncMock(side_effect=_send)
        cdp.detach = AsyncMock()
        page = _default_page()
        page.context.new_cdp_session = AsyncMock(return_value=cdp)
        ctx = _make_ctx(page=page)
        with pytest.raises(BackendError) as exc_info:
            await ctx.evaluate("x")
        assert "ReferenceError" in exc_info.value.hint

    @pytest.mark.asyncio
    async def test_evaluate_undefined_returns_none(self) -> None:
        """CDP result type 'undefined' returns Python None."""
        cdp = MagicMock()
        _listeners: dict[str, list] = {}

        def _on(event: str, callback: Any) -> None:
            _listeners.setdefault(event, []).append(callback)

        async def _send(method: str, params: Any = None) -> Any:
            if method == "Runtime.enable":
                main_ctx = {
                    "context": {
                        "id": 1,
                        "origin": "",
                        "name": "",
                        "auxData": {
                        "isDefault": True, "type": "default", "frameId": "F1",
                    },
                    }
                }
                for cb in _listeners.get("Runtime.executionContextCreated", []):
                    cb(main_ctx)
                return {}
            if method == "Runtime.disable":
                return {}
            if method == "Runtime.evaluate":
                return {"result": {"type": "undefined"}}
            return {}

        cdp.on = MagicMock(side_effect=_on)
        cdp.send = AsyncMock(side_effect=_send)
        cdp.detach = AsyncMock()
        page = _default_page()
        page.context.new_cdp_session = AsyncMock(return_value=cdp)
        ctx = _make_ctx(page=page)
        result = await ctx.evaluate("void 0")
        assert result is None

    @pytest.mark.asyncio
    async def test_evaluate_main_world_passes_context_id(self) -> None:
        """Main world evaluate passes contextId from Runtime.enable discovery."""
        cdp = MagicMock()
        _listeners: dict[str, list] = {}
        captured_params: dict[str, Any] = {}

        def _on(event: str, callback: Any) -> None:
            _listeners.setdefault(event, []).append(callback)

        async def _send(method: str, params: Any = None) -> Any:
            if method == "Runtime.enable":
                main_ctx = {
                    "context": {
                        "id": 42,
                        "origin": "https://example.com",
                        "name": "",
                        "auxData": {
                        "isDefault": True, "type": "default", "frameId": "F1",
                    },
                    }
                }
                for cb in _listeners.get("Runtime.executionContextCreated", []):
                    cb(main_ctx)
                return {}
            if method == "Runtime.disable":
                return {}
            if method == "Runtime.evaluate":
                captured_params.update(params or {})
                return {"result": {"type": "string", "value": "ok"}}
            return {}

        cdp.on = MagicMock(side_effect=_on)
        cdp.send = AsyncMock(side_effect=_send)
        cdp.detach = AsyncMock()
        page = _default_page()
        page.context.new_cdp_session = AsyncMock(return_value=cdp)
        ctx = _make_ctx(page=page)
        result = await ctx.evaluate("window.jQuery")
        assert result == "ok"
        assert captured_params["contextId"] == 42

    @pytest.mark.asyncio
    async def test_evaluate_main_world_no_context_raises(self) -> None:
        """Raises BackendError when no main world context is found."""
        cdp = MagicMock()

        def _on(event: str, callback: Any) -> None:
            pass  # never fires any context events

        async def _send(method: str, params: Any = None) -> Any:
            if method in ("Runtime.enable", "Runtime.disable"):
                return {}
            return {}

        cdp.on = MagicMock(side_effect=_on)
        cdp.send = AsyncMock(side_effect=_send)
        cdp.detach = AsyncMock()
        page = _default_page()
        page.context.new_cdp_session = AsyncMock(return_value=cdp)
        ctx = _make_ctx(page=page)
        with pytest.raises(BackendError) as exc_info:
            await ctx.evaluate("1+1")
        assert "main world" in exc_info.value.hint


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

    @pytest.mark.asyncio
    async def test_default_format_jpeg(self) -> None:
        """Default screenshot format is JPEG with quality 80."""
        page = _default_page()
        ctx = _make_ctx(page=page)
        await ctx.screenshot()
        page.screenshot.assert_called_once_with(
            full_page=False, type="jpeg", quality=80
        )

    @pytest.mark.asyncio
    async def test_png_format_no_quality(self) -> None:
        """PNG format omits quality parameter."""
        page = _default_page()
        ctx = _make_ctx(page=page)
        await ctx.screenshot(format="png")
        page.screenshot.assert_called_once_with(full_page=False, type="png")


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
        assert ctx.stealth_tier.value == "playwright"
