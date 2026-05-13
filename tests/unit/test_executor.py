"""Tests for adapters/executor.py — adapter execution dispatch."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentcloak.adapters.context import AdapterContext
from agentcloak.adapters.executor import execute_adapter
from agentcloak.adapters.types import AdapterEntry, AdapterMeta
from agentcloak.core.errors import AgentBrowserError
from agentcloak.core.types import Strategy


class TestExecuteAdapter:
    async def test_function_mode(self) -> None:
        async def handler(ctx: AdapterContext) -> list[dict[str, object]]:
            return [{"greeting": f"hello {ctx.args['name']}"}]

        meta = AdapterMeta(site="test", name="greet", strategy=Strategy.PUBLIC)
        entry = AdapterEntry(meta=meta, handler=handler)
        result = await execute_adapter(entry, args={"name": "world"})
        assert result == [{"greeting": "hello world"}]

    async def test_browser_required_but_missing(self) -> None:
        async def handler(ctx: AdapterContext) -> list[dict[str, object]]:
            return []

        meta = AdapterMeta(site="test", name="cmd", strategy=Strategy.COOKIE)
        entry = AdapterEntry(meta=meta, handler=handler)

        with pytest.raises(AgentBrowserError) as exc_info:
            await execute_adapter(entry, args={})
        assert exc_info.value.error == "adapter_no_browser"

    async def test_pre_navigate_called(self) -> None:
        async def handler(ctx: AdapterContext) -> list[dict[str, object]]:
            return [{"ok": True}]

        browser = AsyncMock()
        browser.navigate.return_value = {"ok": True}

        meta = AdapterMeta(
            site="test",
            name="cmd",
            strategy=Strategy.COOKIE,
            domain="example.com",
        )
        entry = AdapterEntry(meta=meta, handler=handler)

        await execute_adapter(entry, args={}, browser=browser)
        browser.navigate.assert_called_once_with("https://example.com")

    async def test_no_handler_raises(self) -> None:
        meta = AdapterMeta(site="test", name="broken", strategy=Strategy.PUBLIC)
        entry = AdapterEntry(meta=meta)

        with pytest.raises(AgentBrowserError) as exc_info:
            await execute_adapter(entry, args={})
        assert exc_info.value.error == "adapter_no_handler"

    async def test_pipeline_mode(self) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"value": 42}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.request.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        meta = AdapterMeta(
            site="test",
            name="pipe",
            strategy=Strategy.PUBLIC,
            pipeline=(
                {"fetch": "https://api.example.com/value"},
                {"select": "value"},
            ),
        )
        entry = AdapterEntry(meta=meta)

        with patch("agentcloak.adapters.pipeline.steps.httpx.AsyncClient", return_value=mock_client):
            result = await execute_adapter(entry, args={})

        assert result == [42]

    async def test_public_strategy_no_browser_ok(self) -> None:
        async def handler(ctx: AdapterContext) -> list[dict[str, object]]:
            return [{"ok": True}]

        meta = AdapterMeta(site="test", name="pub", strategy=Strategy.PUBLIC)
        entry = AdapterEntry(meta=meta, handler=handler)
        result = await execute_adapter(entry, args={})
        assert result == [{"ok": True}]
