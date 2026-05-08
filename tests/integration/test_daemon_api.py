"""Scenario G: daemon HTTP API — full endpoint chain via aiohttp TestServer."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import orjson
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

from browserctl.daemon.middleware import error_middleware
from browserctl.daemon.routes import setup_routes


@pytest_asyncio.fixture
async def daemon_test_client(
    fresh_context: Any,
) -> AsyncGenerator[TestClient, None]:
    """Create an aiohttp TestClient with real browser context."""
    from browserctl.core.config import load_config
    from browserctl.core.resume import ResumeWriter

    paths, _ = load_config()

    app = web.Application(middlewares=[error_middleware])
    app["browser_ctx"] = fresh_context
    app["local_proxy"] = None
    app["bridge_token"] = "test-token"
    app["last_request_time"] = 0.0

    resume_writer = ResumeWriter(paths)
    app["resume_writer"] = resume_writer

    setup_routes(app)
    client = TestClient(TestServer(app))
    await client.start_server()
    yield client
    await client.close()


async def test_health_endpoint(
    daemon_test_client: TestClient, local_server: str
) -> None:
    """GET /health should return ok."""
    resp = await daemon_test_client.get("/health")
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert "stealth_tier" in data


async def test_navigate_via_http(
    daemon_test_client: TestClient, local_server: str
) -> None:
    """POST /navigate should navigate and return structured response."""
    resp = await daemon_test_client.post(
        "/navigate",
        data=orjson.dumps({"url": f"{local_server}/index.html", "timeout": 10.0}),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert data["data"]["url"].endswith("/index.html")
    assert data["data"]["title"] == "Test Page"
    assert "seq" in data


async def test_snapshot_via_http(
    daemon_test_client: TestClient, local_server: str
) -> None:
    """GET /snapshot should return page tree."""
    # Navigate first
    await daemon_test_client.post(
        "/navigate",
        data=orjson.dumps({"url": f"{local_server}/index.html"}),
        headers={"Content-Type": "application/json"},
    )
    resp = await daemon_test_client.get("/snapshot?mode=accessible")
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert "tree_text" in data["data"]
    assert "selector_map" in data["data"]


async def test_action_via_http(
    daemon_test_client: TestClient, local_server: str
) -> None:
    """POST /action should execute and return result."""
    await daemon_test_client.post(
        "/navigate",
        data=orjson.dumps({"url": f"{local_server}/index.html"}),
        headers={"Content-Type": "application/json"},
    )
    # Scroll action doesn't need a target index
    resp = await daemon_test_client.post(
        "/action",
        data=orjson.dumps({"kind": "scroll", "direction": "down", "amount": 100}),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True


async def test_resume_endpoint(
    daemon_test_client: TestClient, local_server: str
) -> None:
    """GET /resume should return snapshot structure."""
    # Navigate to trigger resume update
    await daemon_test_client.post(
        "/navigate",
        data=orjson.dumps({"url": f"{local_server}/index.html"}),
        headers={"Content-Type": "application/json"},
    )
    resp = await daemon_test_client.get("/resume")
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    snap = data["data"]
    assert "url" in snap
    assert "tabs" in snap
    assert "recent_actions" in snap
    assert "capture_active" in snap
    assert "stealth_tier" in snap


async def test_error_envelope_via_http(daemon_test_client: TestClient) -> None:
    """Invalid request should return proper error envelope."""
    resp = await daemon_test_client.post(
        "/action",
        data=orjson.dumps({"kind": "nonexistent_action"}),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status == 400
    data = await resp.json()
    assert data["ok"] is False
    assert "error" in data
    assert "hint" in data
    assert "action" in data


async def test_tab_endpoints(daemon_test_client: TestClient, local_server: str) -> None:
    """Tab CRUD via HTTP endpoints."""
    # Navigate first
    await daemon_test_client.post(
        "/navigate",
        data=orjson.dumps({"url": f"{local_server}/index.html"}),
        headers={"Content-Type": "application/json"},
    )

    # List tabs
    resp = await daemon_test_client.get("/tabs")
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    initial_count = data["data"]["count"]

    # New tab
    resp = await daemon_test_client.post(
        "/tab/new",
        data=orjson.dumps({}),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status == 200
    new_data = await resp.json()
    assert new_data["ok"] is True
    new_tab_id = new_data["data"]["tab_id"]

    # Verify count increased
    resp = await daemon_test_client.get("/tabs")
    data = await resp.json()
    assert data["data"]["count"] == initial_count + 1

    # Close the new tab
    resp = await daemon_test_client.post(
        "/tab/close",
        data=orjson.dumps({"tab_id": new_tab_id}),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status == 200
    close_data = await resp.json()
    assert close_data["ok"] is True
