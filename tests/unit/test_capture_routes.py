"""Tests for daemon capture routes."""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock

import pytest
from aiohttp import web

from browserctl.core.capture import CaptureStore
from browserctl.daemon.routes import setup_routes


def _make_app() -> web.Application:
    app = web.Application()
    ctx = MagicMock()
    store = CaptureStore()
    type(ctx).capture_store = PropertyMock(return_value=store)
    type(ctx).seq = PropertyMock(return_value=0)
    app["browser_ctx"] = ctx
    setup_routes(app)
    return app


class TestCaptureRoutes:
    @pytest.fixture
    def client(self, aiohttp_client: any) -> any:
        return aiohttp_client(_make_app())

    async def test_start(self, client: any) -> None:
        c = await client
        resp = await c.post("/capture/start")
        assert resp.status == 200
        data = await resp.json()
        assert data["data"]["recording"] is True

    async def test_stop(self, client: any) -> None:
        c = await client
        await c.post("/capture/start")
        resp = await c.post("/capture/stop")
        assert resp.status == 200
        data = await resp.json()
        assert data["data"]["recording"] is False

    async def test_status(self, client: any) -> None:
        c = await client
        resp = await c.get("/capture/status")
        assert resp.status == 200
        data = await resp.json()
        assert "recording" in data["data"]
        assert "entries" in data["data"]

    async def test_clear(self, client: any) -> None:
        c = await client
        resp = await c.post("/capture/clear")
        assert resp.status == 200
        data = await resp.json()
        assert data["data"]["cleared"] is True

    async def test_export_har(self, client: any) -> None:
        c = await client
        resp = await c.get("/capture/export?format=har")
        assert resp.status == 200
        data = await resp.json()
        assert "log" in data["data"]

    async def test_export_json(self, client: any) -> None:
        c = await client
        resp = await c.get("/capture/export?format=json")
        assert resp.status == 200
        data = await resp.json()
        assert "entries" in data["data"]

    async def test_analyze_empty(self, client: any) -> None:
        c = await client
        resp = await c.get("/capture/analyze")
        assert resp.status == 200
        data = await resp.json()
        assert data["data"]["patterns"] == []
        assert data["data"]["count"] == 0
