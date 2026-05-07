"""Tests for daemon/routes.py — route registration and response shapes."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import orjson
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from browserctl.browser.patchright_ctx import PatchrightContext
from browserctl.core.seq import RingBuffer, SeqCounter, SeqEvent
from browserctl.daemon.middleware import error_middleware
from browserctl.daemon.routes import setup_routes


def _mock_ctx() -> PatchrightContext:
    page = MagicMock()
    page.on = MagicMock()
    page.url = "https://example.com"
    page.title = AsyncMock(return_value="Example")
    page.goto = AsyncMock(return_value=MagicMock(status=200))
    page.evaluate = AsyncMock(return_value="hello")
    page.screenshot = AsyncMock(return_value=b"fakepng")
    page.content = AsyncMock(return_value="<html></html>")
    page.accessibility = MagicMock()
    page.accessibility.snapshot = AsyncMock(
        return_value={
            "role": "WebArea",
            "name": "Test",
            "children": [{"role": "link", "name": "A link"}],
        }
    )

    seq = SeqCounter()
    ring = RingBuffer()
    ring.append(
        SeqEvent(
            seq=0,
            kind="network",
            data={
                "method": "GET",
                "url": "https://example.com",
                "status": 200,
                "resource_type": "document",
            },
        )
    )

    ctx = PatchrightContext(
        page=page,
        browser=MagicMock(),
        playwright=MagicMock(),
        seq_counter=seq,
        ring_buffer=ring,
    )
    return ctx


@pytest.fixture
async def client() -> Any:
    app = web.Application(middlewares=[error_middleware])
    app["browser_ctx"] = _mock_ctx()
    setup_routes(app)
    async with TestClient(TestServer(app)) as c:
        yield c


class TestRoutes:
    @pytest.mark.asyncio
    async def test_health(self, client: TestClient) -> None:
        resp = await client.get("/health")
        assert resp.status == 200
        data = orjson.loads(await resp.read())
        assert data["ok"] is True

    @pytest.mark.asyncio
    async def test_navigate(self, client: TestClient) -> None:
        resp = await client.post(
            "/navigate",
            data=orjson.dumps({"url": "https://test.com"}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 200
        data = orjson.loads(await resp.read())
        assert data["ok"] is True
        assert "data" in data
        assert data["data"]["url"] == "https://example.com"

    @pytest.mark.asyncio
    async def test_screenshot(self, client: TestClient) -> None:
        resp = await client.get("/screenshot")
        assert resp.status == 200
        data = orjson.loads(await resp.read())
        assert data["ok"] is True
        assert "base64" in data["data"]

    @pytest.mark.asyncio
    async def test_snapshot(self, client: TestClient) -> None:
        resp = await client.get("/snapshot?mode=accessible")
        assert resp.status == 200
        data = orjson.loads(await resp.read())
        assert data["ok"] is True
        assert "tree_text" in data["data"]
        assert "selector_map" in data["data"]

    @pytest.mark.asyncio
    async def test_state(self, client: TestClient) -> None:
        resp = await client.get("/state")
        assert resp.status == 200
        data = orjson.loads(await resp.read())
        assert data["ok"] is True
        assert "tree_text" in data["data"]
        assert "screenshot_b64" in data["data"]

    @pytest.mark.asyncio
    async def test_evaluate(self, client: TestClient) -> None:
        resp = await client.post(
            "/evaluate",
            data=orjson.dumps({"js": "1+1"}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 200
        data = orjson.loads(await resp.read())
        assert data["ok"] is True
        assert "result" in data["data"]

    @pytest.mark.asyncio
    async def test_network(self, client: TestClient) -> None:
        resp = await client.get("/network?since=0")
        assert resp.status == 200
        data = orjson.loads(await resp.read())
        assert data["ok"] is True
        assert "requests" in data["data"]
