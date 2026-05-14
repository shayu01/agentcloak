"""Tests for spells/executor.py — spell execution dispatch."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentcloak.spells.executor import execute_spell

if TYPE_CHECKING:
    from agentcloak.spells.context import SpellContext
from agentcloak.core.errors import AgentBrowserError
from agentcloak.core.types import Strategy
from agentcloak.spells.types import SpellEntry, SpellMeta


class TestExecuteSpell:
    async def test_function_mode(self) -> None:
        async def handler(ctx: SpellContext) -> list[dict[str, object]]:
            return [{"greeting": f"hello {ctx.args['name']}"}]

        meta = SpellMeta(site="test", name="greet", strategy=Strategy.PUBLIC)
        entry = SpellEntry(meta=meta, handler=handler)
        result = await execute_spell(entry, args={"name": "world"})
        assert result == [{"greeting": "hello world"}]

    async def test_browser_required_but_missing(self) -> None:
        async def handler(ctx: SpellContext) -> list[dict[str, object]]:
            return []

        meta = SpellMeta(site="test", name="cmd", strategy=Strategy.COOKIE)
        entry = SpellEntry(meta=meta, handler=handler)

        with pytest.raises(AgentBrowserError) as exc_info:
            await execute_spell(entry, args={})
        assert exc_info.value.error == "spell_no_browser"

    async def test_pre_navigate_called(self) -> None:
        async def handler(ctx: SpellContext) -> list[dict[str, object]]:
            return [{"ok": True}]

        browser = AsyncMock()
        browser.navigate.return_value = {"ok": True}

        meta = SpellMeta(
            site="test",
            name="cmd",
            strategy=Strategy.COOKIE,
            domain="example.com",
        )
        entry = SpellEntry(meta=meta, handler=handler)

        await execute_spell(entry, args={}, browser=browser)
        browser.navigate.assert_called_once_with("https://example.com")

    async def test_no_handler_raises(self) -> None:
        meta = SpellMeta(site="test", name="broken", strategy=Strategy.PUBLIC)
        entry = SpellEntry(meta=meta)

        with pytest.raises(AgentBrowserError) as exc_info:
            await execute_spell(entry, args={})
        assert exc_info.value.error == "spell_no_handler"

    async def test_pipeline_mode(self) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"value": 42}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.request.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        meta = SpellMeta(
            site="test",
            name="pipe",
            strategy=Strategy.PUBLIC,
            pipeline=(
                {"fetch": "https://api.example.com/value"},
                {"select": "value"},
            ),
        )
        entry = SpellEntry(meta=meta)

        with patch(
            "agentcloak.spells.pipeline.steps.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await execute_spell(entry, args={})

        assert result == [42]

    async def test_public_strategy_no_browser_ok(self) -> None:
        async def handler(ctx: SpellContext) -> list[dict[str, object]]:
            return [{"ok": True}]

        meta = SpellMeta(site="test", name="pub", strategy=Strategy.PUBLIC)
        entry = SpellEntry(meta=meta, handler=handler)
        result = await execute_spell(entry, args={})
        assert result == [{"ok": True}]
