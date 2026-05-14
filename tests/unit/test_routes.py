"""Tests for daemon/routes.py — route registration and response shapes."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import orjson
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from agentcloak.browser.playwright_ctx import PlaywrightContext
from agentcloak.core.seq import RingBuffer, SeqCounter, SeqEvent
from agentcloak.daemon.middleware import error_middleware
from agentcloak.daemon.routes import (
    _batch_has_refs,
    _resolve_action_refs,
    _traverse,
    setup_routes,
)


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


def _mock_ctx() -> PlaywrightContext:
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

    ctx = PlaywrightContext(
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
            return_value={
                "webSocketDebuggerUrl": "ws://127.0.0.1:19222/devtools/browser/abc"
            }
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
        assert (
            data["data"]["ws_endpoint"] == "ws://127.0.0.1:19222/devtools/browser/abc"
        )
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
    async def test_profile_create_from_current_ok(
        self, tmp_path: Any, client: TestClient
    ) -> None:
        ctx = client.app["browser_ctx"]
        mock_bctx = MagicMock()
        mock_bctx.cookies = AsyncMock(return_value=[{"name": "sid", "value": "abc"}])
        ctx._get_browser_context = MagicMock(return_value=mock_bctx)

        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        mock_paths = MagicMock()
        mock_paths.profiles_dir = tmp_path / "profiles"

        with (
            patch(
                "agentcloak.core.config.load_config",
                return_value=(mock_paths, MagicMock()),
            ),
            patch(
                "asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)
            ),
        ):
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
    async def test_profile_create_from_current_renamed(
        self, tmp_path: Any, client: TestClient
    ) -> None:
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

        with (
            patch(
                "agentcloak.core.config.load_config",
                return_value=(mock_paths, MagicMock()),
            ),
            patch(
                "asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)
            ),
        ):
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
    async def test_profile_create_from_current_writer_error(
        self, tmp_path: Any, client: TestClient
    ) -> None:
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

        with (
            patch(
                "agentcloak.core.config.load_config",
                return_value=(mock_paths, MagicMock()),
            ),
            patch(
                "asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)
            ),
        ):
            resp = await client.post(
                "/profile/create-from-current",
                data=orjson.dumps({"name": "my-profile"}),
                headers={"Content-Type": "application/json"},
            )

        assert resp.status == 500
        data = orjson.loads(await resp.read())
        assert data["ok"] is False
        assert data["error"] == "profile_writer_failed"


class TestBatchRefResolution:
    """Unit tests for $N.path batch reference resolution (R4.4)."""

    def test_traverse_simple(self) -> None:
        obj = {"data": {"url": "https://example.com"}}
        assert _traverse(obj, "data.url") == "https://example.com"

    def test_traverse_single_key(self) -> None:
        obj = {"name": "test"}
        assert _traverse(obj, "name") == "test"

    def test_traverse_deep_path(self) -> None:
        obj = {"a": {"b": {"c": {"d": 42}}}}
        assert _traverse(obj, "a.b.c.d") == 42

    def test_traverse_missing_key_raises(self) -> None:
        obj = {"data": {"url": "test"}}
        with pytest.raises(KeyError):
            _traverse(obj, "data.missing")

    def test_traverse_non_dict_raises(self) -> None:
        obj = {"data": "string_value"}
        with pytest.raises(KeyError, match="Cannot traverse"):
            _traverse(obj, "data.nested")

    def test_batch_has_refs_true(self) -> None:
        actions = [
            {"kind": "click", "target": "5"},
            {"kind": "fill", "text": "$0.data.url"},
        ]
        assert _batch_has_refs(actions) is True

    def test_batch_has_refs_false(self) -> None:
        actions = [
            {"kind": "click", "target": "5"},
            {"kind": "fill", "text": "plain text"},
        ]
        assert _batch_has_refs(actions) is False

    def test_batch_has_refs_empty(self) -> None:
        assert _batch_has_refs([]) is False

    def test_batch_has_refs_non_string_values(self) -> None:
        actions = [{"kind": "click", "index": 5, "click_count": 1}]
        assert _batch_has_refs(actions) is False

    def test_resolve_action_refs_basic(self) -> None:
        params = {"kind": "fill", "text": "$0.data.url"}
        results = [{"data": {"url": "https://example.com"}}]
        resolved = _resolve_action_refs(params, results)
        assert resolved == {"kind": "fill", "text": "https://example.com"}

    def test_resolve_action_refs_no_refs(self) -> None:
        params = {"kind": "click", "target": "5"}
        results = [{"data": {"url": "test"}}]
        resolved = _resolve_action_refs(params, results)
        assert resolved == {"kind": "click", "target": "5"}

    def test_resolve_action_refs_non_string_preserved(self) -> None:
        params = {"kind": "click", "index": 5, "click_count": 1}
        resolved = _resolve_action_refs(params, [])
        assert resolved == {"kind": "click", "index": 5, "click_count": 1}

    def test_resolve_action_refs_out_of_bounds_preserved(self) -> None:
        params = {"text": "$99.data.url"}
        results = [{"data": {"url": "test"}}]
        resolved = _resolve_action_refs(params, results)
        # Out-of-bounds $N is preserved as-is
        assert resolved == {"text": "$99.data.url"}

    def test_resolve_action_refs_multiple(self) -> None:
        params = {"url": "$0.data.url", "title": "$1.data.title", "kind": "fill"}
        results = [
            {"data": {"url": "https://a.com"}},
            {"data": {"title": "Page B"}},
        ]
        resolved = _resolve_action_refs(params, results)
        assert resolved["url"] == "https://a.com"
        assert resolved["title"] == "Page B"
        assert resolved["kind"] == "fill"

    def test_resolve_action_refs_bad_path_raises(self) -> None:
        params = {"text": "$0.missing.key"}
        results = [{"data": {"url": "test"}}]
        with pytest.raises(KeyError):
            _resolve_action_refs(params, results)


class TestIncludeSnapshot:
    """Tests for includeSnapshot action parameter (R4.3)."""

    @pytest.mark.asyncio
    async def test_action_include_snapshot(self, client: TestClient) -> None:
        """Action with include_snapshot=true should attach snapshot data."""
        ctx = client.app["browser_ctx"]
        # Mock action to return a simple click result
        ctx.action = AsyncMock(
            return_value={"ok": True, "clicked": True, "seq": 1, "action": "click"}
        )

        resp = await client.post(
            "/action",
            data=orjson.dumps(
                {
                    "kind": "click",
                    "target": "5",
                    "include_snapshot": True,
                }
            ),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 200
        data = orjson.loads(await resp.read())
        assert data["ok"] is True
        # Snapshot should be included in the action result
        assert "snapshot" in data["data"]
        snap = data["data"]["snapshot"]
        assert "tree_text" in snap
        assert "mode" in snap
        assert "total_nodes" in snap
        assert "total_interactive" in snap

    @pytest.mark.asyncio
    async def test_action_without_include_snapshot(self, client: TestClient) -> None:
        """Action without include_snapshot should NOT attach snapshot."""
        ctx = client.app["browser_ctx"]
        ctx.action = AsyncMock(
            return_value={"ok": True, "clicked": True, "seq": 1, "action": "click"}
        )

        resp = await client.post(
            "/action",
            data=orjson.dumps({"kind": "click", "target": "5"}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 200
        data = orjson.loads(await resp.read())
        assert data["ok"] is True
        assert "snapshot" not in data["data"]


class TestStaleRefRetry:
    """Tests for stale ref auto-retry (R4.5)."""

    @pytest.mark.asyncio
    async def test_stale_ref_retries_on_numeric_target(
        self, client: TestClient
    ) -> None:
        """ElementNotFoundError with numeric target triggers retry."""
        from agentcloak.core.errors import ElementNotFoundError

        ctx = client.app["browser_ctx"]
        call_count = 0

        async def action_side_effect(kind: str, target: str, **kw: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ElementNotFoundError(
                    error="element_not_found",
                    hint="Element [5] not in selector_map",
                    action="take a new snapshot",
                )
            return {"ok": True, "clicked": True, "seq": 2, "action": "click"}

        ctx.action = AsyncMock(side_effect=action_side_effect)

        resp = await client.post(
            "/action",
            data=orjson.dumps({"kind": "click", "target": "5"}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 200
        data = orjson.loads(await resp.read())
        assert data["ok"] is True
        assert data["data"]["retried"] is True
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_stale_ref_no_retry_on_non_numeric(self, client: TestClient) -> None:
        """ElementNotFoundError with non-numeric target propagates (no retry)."""
        from agentcloak.core.errors import ElementNotFoundError

        ctx = client.app["browser_ctx"]
        ctx.action = AsyncMock(
            side_effect=ElementNotFoundError(
                error="element_not_found",
                hint="fill requires a target element",
                action="provide target",
            )
        )

        resp = await client.post(
            "/action",
            data=orjson.dumps({"kind": "fill", "target": ""}),
            headers={"Content-Type": "application/json"},
        )
        # Should return 400 from middleware (ElementNotFoundError is AgentBrowserError)
        assert resp.status == 400
        data = orjson.loads(await resp.read())
        assert data["error"] == "element_not_found"


class TestBatchWithRefs:
    """Integration tests for $N batch references in handle_action_batch (R4.4)."""

    @pytest.mark.asyncio
    async def test_batch_with_refs_resolves(self, client: TestClient) -> None:
        """Batch with $N.path references resolves correctly."""
        ctx = client.app["browser_ctx"]
        call_count = 0

        async def action_side_effect(kind: str, target: str, **kw: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if kind == "click":
                return {
                    "ok": True,
                    "clicked": True,
                    "seq": 1,
                    "action": "click",
                    "result_url": "https://clicked.com",
                }
            if kind == "fill":
                return {
                    "ok": True,
                    "filled": True,
                    "seq": 2,
                    "action": "fill",
                    "text": kw.get("text", ""),
                }
            return {"ok": True}

        ctx.action = AsyncMock(side_effect=action_side_effect)

        actions = [
            {"kind": "click", "target": "5"},
            {"kind": "fill", "target": "3", "text": "$0.result_url"},
        ]
        resp = await client.post(
            "/action/batch",
            data=orjson.dumps({"actions": actions, "sleep": 0}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 200
        data = orjson.loads(await resp.read())
        assert data["ok"] is True
        results = data["data"]["results"]
        assert len(results) == 2
        # Second action should have received the resolved URL as text
        assert results[1]["text"] == "https://clicked.com"

    @pytest.mark.asyncio
    async def test_batch_without_refs_delegates_to_backend(
        self, client: TestClient
    ) -> None:
        """Batch without $N refs uses the backend's action_batch directly."""
        ctx = client.app["browser_ctx"]
        ctx.action_batch = AsyncMock(
            return_value={"results": [], "completed": 0, "total": 0}
        )

        actions = [
            {"kind": "click", "target": "5"},
            {"kind": "fill", "target": "3", "text": "hello"},
        ]
        resp = await client.post(
            "/action/batch",
            data=orjson.dumps({"actions": actions, "sleep": 0}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 200
        # Backend's action_batch should have been called
        ctx.action_batch.assert_called_once()

    @pytest.mark.asyncio
    async def test_batch_ref_resolution_failure(self, client: TestClient) -> None:
        """Invalid $N reference path aborts batch with error."""
        ctx = client.app["browser_ctx"]
        ctx.action = AsyncMock(
            return_value={
                "ok": True,
                "clicked": True,
                "seq": 1,
                "action": "click",
            }
        )

        actions = [
            {"kind": "click", "target": "5"},
            {"kind": "fill", "target": "3", "text": "$0.nonexistent.path"},
        ]
        resp = await client.post(
            "/action/batch",
            data=orjson.dumps({"actions": actions, "sleep": 0}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 200
        data = orjson.loads(await resp.read())
        results = data["data"]["results"]
        # First action succeeded, second failed during ref resolution
        assert results[0]["ok"] is True
        assert results[1]["error"] == "ref_resolution_failed"
        assert data["data"]["aborted_reason"] == "ref_resolution_failed"
