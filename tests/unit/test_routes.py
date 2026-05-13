"""Tests for daemon/routes.py — route registration and response shapes."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import orjson
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from agentcloak.browser.patchright_ctx import PatchrightContext
from agentcloak.core.seq import RingBuffer, SeqCounter, SeqEvent
from agentcloak.daemon.middleware import error_middleware
from agentcloak.daemon.routes import setup_routes


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
    app["shutdown_event"] = asyncio.Event()
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
    async def test_evaluate_small_result(self, client: TestClient) -> None:
        # Small result should not be truncated
        resp = await client.post(
            "/evaluate",
            data=orjson.dumps({"js": "1+1"}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 200
        data = orjson.loads(await resp.read())
        assert data["ok"] is True
        assert data["data"]["truncated"] is False
        assert "total_size" in data["data"]

    @pytest.mark.asyncio
    async def test_evaluate_truncation(self, client: TestClient) -> None:
        # Artificially low max_return_size triggers truncation
        resp = await client.post(
            "/evaluate",
            data=orjson.dumps({"js": "1+1", "max_return_size": 1}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 200
        data = orjson.loads(await resp.read())
        assert data["ok"] is True
        assert data["data"]["truncated"] is True
        assert "[...truncated...]" in data["data"]["result"]

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

    @pytest.mark.asyncio
    async def test_capture_replay_entry_not_found(self, client: TestClient) -> None:
        resp = await client.post(
            "/capture/replay",
            data=orjson.dumps({"url": "https://example.com/api", "method": "GET"}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 404
        data = orjson.loads(await resp.read())
        assert data["error"] == "capture_entry_not_found"

    @pytest.mark.asyncio
    async def test_capture_replay_ok(self, client: TestClient) -> None:
        from datetime import UTC, datetime

        from agentcloak.core.capture import CaptureEntry

        ctx = client.app["browser_ctx"]
        ctx._capture_store.start()
        entry = CaptureEntry(
            seq=1,
            timestamp=datetime.now(tz=UTC).isoformat(),
            method="GET",
            url="https://example.com/api/data",
            status=200,
            resource_type="xhr",
            request_headers={"authorization": "Bearer tok", "host": "example.com"},
            response_headers={},
            content_type="application/json",
        )
        ctx._capture_store.add(entry)

        fetch_result = {"status": 200, "body": '{"ok":true}', "headers": {}}
        ctx.fetch = AsyncMock(return_value=fetch_result)

        resp = await client.post(
            "/capture/replay",
            data=orjson.dumps({"url": "https://example.com/api/data", "method": "GET"}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 200
        data = orjson.loads(await resp.read())
        assert data["ok"] is True
        assert data["data"]["replayed_from"]["url"] == "https://example.com/api/data"
        assert data["data"]["replayed_from"]["seq"] == 1
        # hop-by-hop header 'host' must be filtered out
        call_kwargs = ctx.fetch.call_args
        passed_headers = call_kwargs.kwargs.get("headers") or {}
        assert "host" not in passed_headers
        assert "authorization" in passed_headers

    @pytest.mark.asyncio
    async def test_profile_create_from_current_ok(self, tmp_path: Any, client: TestClient) -> None:
        ctx = client.app["browser_ctx"]
        mock_bctx = MagicMock()
        mock_bctx.cookies = AsyncMock(return_value=[{"name": "sid", "value": "abc"}])
        ctx._get_browser_context = MagicMock(return_value=mock_bctx)

        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        mock_paths = MagicMock()
        mock_paths.profiles_dir = tmp_path / "profiles"

        with patch("agentcloak.core.config.load_config", return_value=(mock_paths, MagicMock())), \
             patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
            resp = await client.post(
                "/profile/create-from-current",
                data=orjson.dumps({"name": "my-profile"}),
                headers={"Content-Type": "application/json"},
            )

        assert resp.status == 200
        data = orjson.loads(await resp.read())
        assert data["ok"] is True
        assert data["data"]["profile"] == "my-profile"
        assert data["data"]["renamed"] is False
        assert data["data"]["cookie_count"] == 1

    @pytest.mark.asyncio
    async def test_profile_create_from_current_renamed(self, tmp_path: Any, client: TestClient) -> None:
        ctx = client.app["browser_ctx"]
        mock_bctx = MagicMock()
        mock_bctx.cookies = AsyncMock(return_value=[])
        ctx._get_browser_context = MagicMock(return_value=mock_bctx)

        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        (profiles_dir / "my-site").mkdir()  # pre-existing profile

        mock_paths = MagicMock()
        mock_paths.profiles_dir = profiles_dir

        with patch("agentcloak.core.config.load_config", return_value=(mock_paths, MagicMock())), \
             patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
            resp = await client.post(
                "/profile/create-from-current",
                data=orjson.dumps({"name": "my-site"}),
                headers={"Content-Type": "application/json"},
            )

        assert resp.status == 200
        data = orjson.loads(await resp.read())
        assert data["ok"] is True
        assert data["data"]["profile"] == "my-site-2"
        assert data["data"]["renamed"] is True

    @pytest.mark.asyncio
    async def test_shutdown_sets_event(self, client: TestClient) -> None:
        """POST /shutdown must set shutdown_event without raising."""
        event: asyncio.Event = client.app["shutdown_event"]
        assert not event.is_set()
        resp = await client.post("/shutdown")
        assert resp.status == 200
        assert event.is_set()

    @pytest.mark.asyncio
    async def test_profile_create_from_current_writer_error(self, tmp_path: Any, client: TestClient) -> None:
        """Subprocess failure returns 500 with error info."""
        ctx = client.app["browser_ctx"]
        mock_bctx = MagicMock()
        mock_bctx.cookies = AsyncMock(return_value=[])
        ctx._get_browser_context = MagicMock(return_value=mock_bctx)

        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"launch failed"))
        mock_proc.returncode = 1

        mock_paths = MagicMock()
        mock_paths.profiles_dir = tmp_path / "profiles"

        with patch("agentcloak.core.config.load_config", return_value=(mock_paths, MagicMock())), \
             patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
            resp = await client.post(
                "/profile/create-from-current",
                data=orjson.dumps({"name": "my-profile"}),
                headers={"Content-Type": "application/json"},
            )

        assert resp.status == 500
        data = orjson.loads(await resp.read())
        assert data["ok"] is False
        assert data["error"] == "profile_writer_failed"
