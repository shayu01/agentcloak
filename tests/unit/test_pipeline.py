"""Tests for spells/pipeline — engine and built-in steps."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentcloak.core.errors import AgentBrowserError
from agentcloak.spells.pipeline.engine import execute_pipeline


class TestPipelineSelect:
    async def test_select_dict_key(self) -> None:
        from agentcloak.spells.pipeline.steps import StepContext, _step_select

        ctx = StepContext(args={})
        data = {"items": [1, 2, 3], "total": 3}
        result = await _step_select("items", data, ctx)
        assert result == [1, 2, 3]

    async def test_select_nested_path(self) -> None:
        from agentcloak.spells.pipeline.steps import StepContext, _step_select

        ctx = StepContext(args={})
        data = {"response": {"data": {"users": ["a", "b"]}}}
        result = await _step_select("response.data.users", data, ctx)
        assert result == ["a", "b"]


class TestPipelineMap:
    async def test_map_transforms_items(self) -> None:
        from agentcloak.spells.pipeline.steps import StepContext, _step_map

        ctx = StepContext(args={})
        data = [
            {"name": "Alice", "score": 100},
            {"name": "Bob", "score": 85},
        ]
        params = {"user": "{item.name}", "points": "{item.score}"}
        result = await _step_map(params, data, ctx)
        assert result == [
            {"user": "Alice", "points": 100},
            {"user": "Bob", "points": 85},
        ]

    async def test_map_with_index(self) -> None:
        from agentcloak.spells.pipeline.steps import StepContext, _step_map

        ctx = StepContext(args={})
        data = [{"title": "A"}, {"title": "B"}]
        params = {"rank": "{index}", "title": "{item.title}"}
        result = await _step_map(params, data, ctx)
        assert result[0]["rank"] == 0
        assert result[1]["rank"] == 1

    async def test_map_non_list_raises(self) -> None:
        from agentcloak.spells.pipeline.steps import StepContext, _step_map

        ctx = StepContext(args={})
        with pytest.raises(AgentBrowserError) as exc_info:
            await _step_map({"x": "{item.x}"}, "not a list", ctx)
        assert exc_info.value.error == "pipeline_type_error"


class TestPipelineFilter:
    async def test_filter_truthy(self) -> None:
        from agentcloak.spells.pipeline.steps import StepContext, _step_filter

        ctx = StepContext(args={})
        data = [
            {"name": "Alice", "active": True},
            {"name": "Bob", "active": False},
            {"name": "Carol", "active": True},
        ]
        result = await _step_filter("{item.active}", data, ctx)
        assert len(result) == 2
        assert result[0]["name"] == "Alice"
        assert result[1]["name"] == "Carol"

    async def test_filter_non_list_raises(self) -> None:
        from agentcloak.spells.pipeline.steps import StepContext, _step_filter

        ctx = StepContext(args={})
        with pytest.raises(AgentBrowserError) as exc_info:
            await _step_filter("{item.x}", {"not": "list"}, ctx)
        assert exc_info.value.error == "pipeline_type_error"


class TestPipelineLimit:
    async def test_limit_truncates(self) -> None:
        from agentcloak.spells.pipeline.steps import StepContext, _step_limit

        ctx = StepContext(args={"n": 2})
        data = [1, 2, 3, 4, 5]
        result = await _step_limit("{args.n}", data, ctx)
        assert result == [1, 2]

    async def test_limit_larger_than_data(self) -> None:
        from agentcloak.spells.pipeline.steps import StepContext, _step_limit

        ctx = StepContext(args={})
        data = [1, 2]
        result = await _step_limit("100", data, ctx)
        assert result == [1, 2]


def _make_httpx_mocks(json_data: object) -> tuple[MagicMock, MagicMock]:
    """Create mock httpx client + response (json() is sync in httpx)."""
    mock_response = MagicMock()
    mock_response.json.return_value = json_data
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.request.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client, mock_response


class TestPipelineEngine:
    async def test_unknown_step_raises(self) -> None:
        pipeline = ({"nonexistent": "params"},)
        with pytest.raises(AgentBrowserError) as exc_info:
            await execute_pipeline(pipeline, args={})
        assert exc_info.value.error == "pipeline_unknown_step"

    async def test_select_then_map(self) -> None:
        mock_client, _ = _make_httpx_mocks(
            {
                "items": [
                    {"id": 1, "title": "First"},
                    {"id": 2, "title": "Second"},
                ]
            }
        )

        pipeline = (
            {"fetch": {"url": "https://api.example.com/items"}},
            {"select": "items"},
            {"map": {"id": "{item.id}", "name": "{item.title}"}},
            {"limit": "1"},
        )

        with patch(
            "agentcloak.spells.pipeline.steps.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await execute_pipeline(pipeline, args={})

        assert result == [{"id": 1, "name": "First"}]

    async def test_navigate_without_browser_raises(self) -> None:
        pipeline = ({"navigate": "https://example.com"},)
        with pytest.raises(AgentBrowserError) as exc_info:
            await execute_pipeline(pipeline, args={})
        assert exc_info.value.error == "pipeline_no_browser"

    async def test_evaluate_without_browser_raises(self) -> None:
        pipeline = ({"evaluate": "document.title"},)
        with pytest.raises(AgentBrowserError) as exc_info:
            await execute_pipeline(pipeline, args={})
        assert exc_info.value.error == "pipeline_no_browser"

    async def test_navigate_with_mock_browser(self) -> None:
        browser = AsyncMock()
        browser.navigate.return_value = {"ok": True}

        pipeline = ({"navigate": "https://example.com"},)
        await execute_pipeline(pipeline, args={}, browser=browser)

        browser.navigate.assert_called_once_with("https://example.com")

    async def test_evaluate_with_mock_browser(self) -> None:
        browser = AsyncMock()
        browser.evaluate.return_value = "Example Domain"

        pipeline = ({"evaluate": "document.title"},)
        result = await execute_pipeline(pipeline, args={}, browser=browser)

        assert result == "Example Domain"
