"""Scenario G: daemon HTTP API — full endpoint chain via FastAPI TestClient.

Migrated to FastAPI/httpx (TestClient is the sync httpx-based client provided
by Starlette) so the test stack matches what the daemon ships in production.
The browser context behind the fixture is real (PlaywrightContext) — only
the HTTP transport is in-process.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

from agentcloak.daemon.app import configure_app_state, create_app


@pytest_asyncio.fixture
async def daemon_test_client(
    fresh_context: Any,
) -> AsyncGenerator[TestClient, None]:
    """Build a FastAPI TestClient backed by a real browser context."""
    from agentcloak.core.config import load_config
    from agentcloak.core.resume import ResumeWriter

    paths, cfg = load_config()
    resume_writer = ResumeWriter(paths)

    app = create_app()
    configure_app_state(
        app,
        browser_ctx=fresh_context,
        local_proxy=None,
        resume_writer=resume_writer,
        bridge_token="test-token",
        config=cfg,
    )
    app.state.shutdown_event = asyncio.Event()

    with TestClient(app) as client:
        yield client


def test_health_endpoint(daemon_test_client: TestClient, local_server: str) -> None:
    """GET /health should return ok."""
    resp = daemon_test_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "stealth_tier" in data


def test_navigate_via_http(daemon_test_client: TestClient, local_server: str) -> None:
    """POST /navigate should navigate and return structured response."""
    resp = daemon_test_client.post(
        "/navigate",
        json={"url": f"{local_server}/index.html", "timeout": 10.0},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["data"]["url"].endswith("/index.html")
    assert data["data"]["title"] == "Test Page"
    assert "seq" in data


def test_snapshot_via_http(daemon_test_client: TestClient, local_server: str) -> None:
    """GET /snapshot should return page tree."""
    # Navigate first
    daemon_test_client.post(
        "/navigate",
        json={"url": f"{local_server}/index.html"},
    )
    # ``include_selector_map`` defaults to ``False`` (token-saving for MCP),
    # so this test asks for it explicitly.
    resp = daemon_test_client.get(
        "/snapshot",
        params={"mode": "accessible", "include_selector_map": "true"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "tree_text" in data["data"]
    assert "selector_map" in data["data"]


def test_action_via_http(daemon_test_client: TestClient, local_server: str) -> None:
    """POST /action should execute and return result."""
    daemon_test_client.post(
        "/navigate",
        json={"url": f"{local_server}/index.html"},
    )
    # Scroll action doesn't need a target index
    resp = daemon_test_client.post(
        "/action",
        json={"kind": "scroll", "direction": "down", "amount": 100},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True


def test_resume_endpoint(daemon_test_client: TestClient, local_server: str) -> None:
    """GET /resume should return snapshot structure."""
    daemon_test_client.post(
        "/navigate",
        json={"url": f"{local_server}/index.html"},
    )
    resp = daemon_test_client.get("/resume")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    snap = data["data"]
    assert "url" in snap
    assert "tabs" in snap
    assert "recent_actions" in snap
    assert "capture_active" in snap
    assert "stealth_tier" in snap


def test_error_envelope_via_http(daemon_test_client: TestClient) -> None:
    """Invalid request should return proper error envelope."""
    resp = daemon_test_client.post(
        "/action",
        json={"kind": "nonexistent_action"},
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["ok"] is False
    assert "error" in data
    assert "hint" in data
    assert "action" in data


def test_tab_endpoints(daemon_test_client: TestClient, local_server: str) -> None:
    """Tab CRUD via HTTP endpoints."""
    daemon_test_client.post(
        "/navigate",
        json={"url": f"{local_server}/index.html"},
    )

    # List tabs
    resp = daemon_test_client.get("/tabs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    initial_count = data["data"]["count"]

    # New tab
    resp = daemon_test_client.post("/tab/new", json={})
    assert resp.status_code == 200
    new_data = resp.json()
    assert new_data["ok"] is True
    new_tab_id = new_data["data"]["tab_id"]

    # Verify count increased
    resp = daemon_test_client.get("/tabs")
    data = resp.json()
    assert data["data"]["count"] == initial_count + 1

    # Close the new tab
    resp = daemon_test_client.post("/tab/close", json={"tab_id": new_tab_id})
    assert resp.status_code == 200
    close_data = resp.json()
    assert close_data["ok"] is True


# Mark the original `pytest` import as used; tests are sync and rely on
# pytest's discovery via name-based collection.
_ = pytest
