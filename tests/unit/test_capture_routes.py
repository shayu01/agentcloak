"""Tests for daemon capture routes."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, PropertyMock

import pytest
from fastapi.testclient import TestClient

from agentcloak.core.capture import CaptureStore
from agentcloak.daemon.app import create_app


def _make_client() -> TestClient:
    app = create_app()
    ctx = MagicMock()
    store = CaptureStore()
    type(ctx).capture_store = PropertyMock(return_value=store)
    type(ctx).seq = PropertyMock(return_value=0)
    app.state.browser_ctx = ctx
    return TestClient(app)


class TestCaptureRoutes:
    @pytest.fixture
    def client(self) -> Any:
        with _make_client() as c:
            yield c

    def test_start(self, client: TestClient) -> None:
        resp = client.post("/capture/start")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["recording"] is True

    def test_stop(self, client: TestClient) -> None:
        client.post("/capture/start")
        resp = client.post("/capture/stop")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["recording"] is False

    def test_status(self, client: TestClient) -> None:
        resp = client.get("/capture/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "recording" in data["data"]
        assert "entries" in data["data"]

    def test_clear(self, client: TestClient) -> None:
        resp = client.post("/capture/clear")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["cleared"] is True

    def test_export_har(self, client: TestClient) -> None:
        resp = client.get("/capture/export?format=har")
        assert resp.status_code == 200
        data = resp.json()
        assert "log" in data["data"]

    def test_export_json(self, client: TestClient) -> None:
        resp = client.get("/capture/export?format=json")
        assert resp.status_code == 200
        data = resp.json()
        assert "entries" in data["data"]

    def test_analyze_empty(self, client: TestClient) -> None:
        resp = client.get("/capture/analyze")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["patterns"] == []
        assert data["data"]["count"] == 0
