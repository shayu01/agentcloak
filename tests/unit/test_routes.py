"""Tests for daemon/routes.py — route registration and response shapes."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import orjson
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from browserctl.browser.patchright_ctx import PatchrightContext
from browserctl.core.seq import RingBuffer, SeqCounter, SeqEvent
from browserctl.daemon.middleware import error_middleware
from browserctl.daemon.routes import setup_routes


def _mock_cdp() -> MagicMock:
    cdp = MagicMock()
    _listeners: dict[str, list] = {}

    def _on(event: str, callback: Any) -> None:
        _listeners.setdefault(event, []).append(callback)

    async def _send(method: str, params: Any = None) -> Any:
        if method == "Accessibility.getFullAXTree":
            return {
                "nodes": [
                    {"role": {"value": "RootWebArea"}, "name": {"value": "Test"}},
                    {"role": {"value": "link"}, "name": {"value": "A link"}},
                ]
            }
        if method == "Runtime.enable":
            main_ctx = {
                "context": {
                    "id": 1,
                    "origin": "https://example.com",
                    "name": "",
                    "auxData": {"isDefault": True, "type": "default", "frameId": "F1"},
                }
            }
            for cb in _listeners.get("Runtime.executionContextCreated", []):
                cb(main_ctx)
            return {}
        if method == "Runtime.disable":
            return {}
        if method == "Runtime.evaluate":
            return {"result": {"type": "string", "value": "hello"}}
        return {}

    cdp.on = MagicMock(side_effect=_on)
    cdp.send = AsyncMock(side_effect=_send)
    cdp.detach = AsyncMock()
    return cdp


def _mock_ctx() -> PatchrightContext:
    page = MagicMock()
    page.on = MagicMock()
    page.url = "https://example.com"
    page.title = AsyncMock(return_value="Example")
    page.goto = AsyncMock(return_value=MagicMock(status=200))
    page.evaluate = AsyncMock(return_value="hello")
    page.screenshot = AsyncMock(return_value=b"fakepng")
    page.content = AsyncMock(return_value="<html></html>")
    page.context = MagicMock()
    page.context.new_cdp_session = AsyncMock(return_value=_mock_cdp())

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

    @pytest.mark.asyncio
    async def test_cdp_endpoint_no_port(self, client: TestClient) -> None:
        # default _mock_ctx has no _cdp_port → 503
        resp = await client.get("/cdp/endpoint")
        assert resp.status == 503
        data = orjson.loads(await resp.read())
        assert data["error"] == "no_cdp_port"

    @pytest.mark.asyncio
    async def test_cdp_endpoint_ok(self) -> None:
        # Build a ctx with a cdp_port set
        ctx = _mock_ctx()
        ctx._cdp_port = 19222

        app = web.Application(middlewares=[error_middleware])
        app["browser_ctx"] = ctx
        setup_routes(app)

        # Mock the aiohttp GET to /json/version
        mock_get_resp = MagicMock()
        mock_get_resp.__aenter__ = AsyncMock(return_value=mock_get_resp)
        mock_get_resp.__aexit__ = AsyncMock(return_value=None)
        mock_get_resp.json = AsyncMock(
            return_value={"webSocketDebuggerUrl": "ws://127.0.0.1:19222/devtools/browser/abc"}
        )

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=mock_get_resp)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            async with TestClient(TestServer(app)) as c:
                resp = await c.get("/cdp/endpoint")
                assert resp.status == 200
                data = orjson.loads(await resp.read())

        assert data["ok"] is True
        assert data["data"]["ws_endpoint"] == "ws://127.0.0.1:19222/devtools/browser/abc"
        assert data["data"]["port"] == 19222
        assert data["data"]["http_url"] == "http://127.0.0.1:19222"
