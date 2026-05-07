"""Tests for fetch — PatchrightContext.fetch() + daemon route."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import orjson
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from browserctl.browser.patchright_ctx import PatchrightContext
from browserctl.core.errors import BackendError, BrowserTimeoutError
from browserctl.core.seq import RingBuffer, SeqCounter
from browserctl.daemon.middleware import error_middleware
from browserctl.daemon.routes import setup_routes

_HTTPX_CLIENT = (
    "browserctl.browser.patchright_ctx.httpx.AsyncClient"
)


def _mock_cdp() -> MagicMock:
    cdp = MagicMock()
    cdp.send = AsyncMock(
        return_value={
            "nodes": [
                {
                    "role": {"value": "RootWebArea"},
                    "name": {"value": "Test"},
                },
            ]
        }
    )
    cdp.detach = AsyncMock()
    return cdp


def _make_page(
    *,
    cookies: list[dict[str, Any]] | None = None,
    ua: str = "Mozilla/5.0 TestAgent",
) -> MagicMock:
    page = MagicMock()
    page.on = MagicMock()
    page.url = "https://example.com"
    page.title = AsyncMock(return_value="Example")
    page.goto = AsyncMock(return_value=MagicMock(status=200))
    page.screenshot = AsyncMock(return_value=b"fakepng")
    page.content = AsyncMock(return_value="<html></html>")

    page.context = MagicMock()
    page.context.new_cdp_session = AsyncMock(
        return_value=_mock_cdp()
    )
    page.context.cookies = AsyncMock(return_value=cookies or [])
    page.evaluate = AsyncMock(return_value=ua)

    return page


def _make_ctx(
    *, page: MagicMock | None = None
) -> PatchrightContext:
    mock_page = page or _make_page()
    return PatchrightContext(
        page=mock_page,
        browser=MagicMock(),
        playwright=MagicMock(),
        seq_counter=SeqCounter(),
        ring_buffer=RingBuffer(),
    )


def _fake_httpx_response(
    *,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
    text: str = '{"result": "ok"}',
    url: str = "https://api.example.com/data",
) -> httpx.Response:
    resp_headers = {"content-type": "application/json"}
    if headers:
        resp_headers.update(headers)
    return httpx.Response(
        status_code=status_code,
        headers=resp_headers,
        text=text,
        request=httpx.Request("GET", url),
    )


def _mock_httpx(
    resp: httpx.Response,
) -> tuple[MagicMock, AsyncMock]:
    """Return (cls_mock, instance_mock) for patching."""
    inst = AsyncMock()
    inst.request = AsyncMock(return_value=resp)
    inst.__aenter__ = AsyncMock(return_value=inst)
    inst.__aexit__ = AsyncMock(return_value=None)
    cls_mock = MagicMock(return_value=inst)
    return cls_mock, inst


def _cookie(
    name: str, value: str, domain: str
) -> dict[str, str]:
    return {
        "name": name,
        "value": value,
        "domain": domain,
        "path": "/",
    }


class TestPatchrightFetch:
    """Tests for PatchrightContext.fetch() method."""

    @pytest.mark.asyncio
    async def test_fetch_basic_get(self) -> None:
        cookies = [_cookie("session", "abc123", ".example.com")]
        page = _make_page(cookies=cookies)
        ctx = _make_ctx(page=page)
        fake_resp = _fake_httpx_response(
            text='{"hello": "world"}',
        )
        cls_mock, _ = _mock_httpx(fake_resp)

        with patch(_HTTPX_CLIENT, cls_mock):
            result = await ctx.fetch(
                "https://api.example.com/data"
            )

        assert result["status"] == 200
        assert result["body_encoding"] == "text"
        assert result["truncated"] is False
        assert ctx.seq == 1

    @pytest.mark.asyncio
    async def test_fetch_increments_seq(self) -> None:
        ctx = _make_ctx()
        fake_resp = _fake_httpx_response()
        cls_mock, _ = _mock_httpx(fake_resp)

        with patch(_HTTPX_CLIENT, cls_mock):
            await ctx.fetch("https://api.example.com/a")
            await ctx.fetch("https://api.example.com/b")

        assert ctx.seq == 2

    @pytest.mark.asyncio
    async def test_fetch_timeout_raises(self) -> None:
        ctx = _make_ctx()
        cls_mock, inst = _mock_httpx(_fake_httpx_response())
        inst.request = AsyncMock(
            side_effect=httpx.ReadTimeout("timed out")
        )

        with patch(_HTTPX_CLIENT, cls_mock):
            with pytest.raises(BrowserTimeoutError) as exc_info:
                await ctx.fetch("https://slow.example.com")

        assert exc_info.value.error == "fetch_timeout"

    @pytest.mark.asyncio
    async def test_fetch_request_error_raises(self) -> None:
        ctx = _make_ctx()
        cls_mock, inst = _mock_httpx(_fake_httpx_response())
        inst.request = AsyncMock(
            side_effect=httpx.ConnectError("refused")
        )

        with patch(_HTTPX_CLIENT, cls_mock):
            with pytest.raises(BackendError) as exc_info:
                await ctx.fetch("https://bad.example.com")

        assert exc_info.value.error == "fetch_request_failed"

    @pytest.mark.asyncio
    async def test_fetch_truncates_large_text(self) -> None:
        ctx = _make_ctx()
        large_text = "x" * 200_000
        fake_resp = _fake_httpx_response(
            text=large_text,
            headers={"content-type": "text/html"},
        )
        cls_mock, _ = _mock_httpx(fake_resp)

        with patch(_HTTPX_CLIENT, cls_mock):
            result = await ctx.fetch("https://example.com/big")

        assert result["truncated"] is True
        assert result["body"].endswith("[...truncated...]")
        assert len(result["body"]) < 200_000

    @pytest.mark.asyncio
    async def test_fetch_passes_custom_headers(self) -> None:
        ctx = _make_ctx()
        fake_resp = _fake_httpx_response()
        cls_mock, inst = _mock_httpx(fake_resp)

        with patch(_HTTPX_CLIENT, cls_mock):
            await ctx.fetch(
                "https://api.example.com",
                headers={"X-Custom": "value"},
            )

        call_kw = inst.request.call_args.kwargs
        sent_headers = call_kw.get("headers", {})
        assert sent_headers.get("X-Custom") == "value"
        assert "User-Agent" in sent_headers

    @pytest.mark.asyncio
    async def test_fetch_post_with_body(self) -> None:
        ctx = _make_ctx()
        fake_resp = _fake_httpx_response()
        cls_mock, inst = _mock_httpx(fake_resp)

        with patch(_HTTPX_CLIENT, cls_mock):
            await ctx.fetch(
                "https://api.example.com",
                method="POST",
                body='{"key": "val"}',
            )

        call_args = inst.request.call_args
        assert call_args.args[0] == "POST"
        assert call_args.kwargs.get("content") == b'{"key": "val"}'

    @pytest.mark.asyncio
    async def test_fetch_cookies_used_matching(self) -> None:
        cookies = [
            _cookie("sid", "123", ".example.com"),
            _cookie("other", "456", ".other.com"),
        ]
        page = _make_page(cookies=cookies)
        ctx = _make_ctx(page=page)
        fake_resp = _fake_httpx_response(
            url="https://api.example.com/data"
        )
        cls_mock, _ = _mock_httpx(fake_resp)

        with patch(_HTTPX_CLIENT, cls_mock):
            result = await ctx.fetch(
                "https://api.example.com/data"
            )

        assert "sid" in result["cookies_used"]
        assert "other" not in result["cookies_used"]

    @pytest.mark.asyncio
    async def test_fetch_no_cookies_still_works(self) -> None:
        page = _make_page(cookies=[])
        ctx = _make_ctx(page=page)
        fake_resp = _fake_httpx_response()
        cls_mock, _ = _mock_httpx(fake_resp)

        with patch(_HTTPX_CLIENT, cls_mock):
            result = await ctx.fetch("https://api.example.com")

        assert result["status"] == 200
        assert result["cookies_used"] == []


class TestFetchRoute:
    """Tests for the POST /fetch daemon route."""

    @pytest.fixture
    async def client(self) -> Any:
        page = _make_page(
            cookies=[
                _cookie("token", "xyz", ".example.com"),
            ]
        )
        ctx = _make_ctx(page=page)

        app = web.Application(middlewares=[error_middleware])
        app["browser_ctx"] = ctx
        setup_routes(app)
        async with TestClient(TestServer(app)) as c:
            yield c

    @pytest.mark.asyncio
    async def test_fetch_route_success(
        self, client: TestClient
    ) -> None:
        fake_resp = _fake_httpx_response(text='{"d": 1}')
        cls_mock, _ = _mock_httpx(fake_resp)

        with patch(_HTTPX_CLIENT, cls_mock):
            resp = await client.post(
                "/fetch",
                data=orjson.dumps(
                    {"url": "https://api.example.com/data"}
                ),
                headers={"Content-Type": "application/json"},
            )

        assert resp.status == 200
        data = orjson.loads(await resp.read())
        assert data["ok"] is True
        assert data["data"]["status"] == 200
        assert data["seq"] >= 1

    @pytest.mark.asyncio
    async def test_fetch_route_with_method_and_body(
        self, client: TestClient
    ) -> None:
        fake_resp = _fake_httpx_response(status_code=201)
        cls_mock, _ = _mock_httpx(fake_resp)

        with patch(_HTTPX_CLIENT, cls_mock):
            resp = await client.post(
                "/fetch",
                data=orjson.dumps({
                    "url": "https://api.example.com/post",
                    "method": "POST",
                    "body": '{"key": "val"}',
                }),
                headers={"Content-Type": "application/json"},
            )

        assert resp.status == 200
        data = orjson.loads(await resp.read())
        assert data["ok"] is True
        assert data["data"]["status"] == 201

    @pytest.mark.asyncio
    async def test_fetch_route_with_headers(
        self, client: TestClient
    ) -> None:
        fake_resp = _fake_httpx_response()
        cls_mock, _ = _mock_httpx(fake_resp)

        with patch(_HTTPX_CLIENT, cls_mock):
            resp = await client.post(
                "/fetch",
                data=orjson.dumps({
                    "url": "https://api.example.com",
                    "headers": {"Authorization": "Bearer t"},
                }),
                headers={"Content-Type": "application/json"},
            )

        assert resp.status == 200
        data = orjson.loads(await resp.read())
        assert data["ok"] is True
