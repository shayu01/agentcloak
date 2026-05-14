"""Tests for spells/pipeline/template.py — template engine."""

from agentcloak.spells.pipeline.template import render, render_deep


class TestRender:
    def test_non_string_passthrough(self) -> None:
        assert render(42, {}) == 42
        assert render(None, {}) is None
        assert render([1, 2], {}) == [1, 2]

    def test_no_template_passthrough(self) -> None:
        assert render("plain text", {}) == "plain text"

    def test_full_template_returns_native_type(self) -> None:
        ctx = {"args": {"limit": 20}}
        assert render("{args.limit}", ctx) == 20

    def test_full_template_string_value(self) -> None:
        ctx = {"args": {"query": "python"}}
        assert render("{args.query}", ctx) == "python"

    def test_full_template_list_value(self) -> None:
        ctx = {"data": [1, 2, 3]}
        result = render("{data}", ctx)
        assert result == [1, 2, 3]

    def test_partial_template_interpolation(self) -> None:
        ctx = {"args": {"q": "test", "limit": 5}}
        result = render("search?q={args.q}&limit={args.limit}", ctx)
        assert result == "search?q=test&limit=5"

    def test_nested_path(self) -> None:
        ctx = {"item": {"author": {"name": "Alice"}}}
        assert render("{item.author.name}", ctx) == "Alice"

    def test_list_index_access(self) -> None:
        ctx = {"data": {"items": ["a", "b", "c"]}}
        assert render("{data.items.1}", ctx) == "b"

    def test_missing_key_raises(self) -> None:
        ctx = {"args": {}}
        try:
            render("{args.missing}", ctx)
            raise AssertionError("should have raised")
        except KeyError:
            pass

    def test_index_variable(self) -> None:
        ctx = {"index": 3}
        assert render("{index}", ctx) == 3


class TestRenderDeep:
    def test_string(self) -> None:
        ctx = {"args": {"x": "hello"}}
        assert render_deep("{args.x}", ctx) == "hello"

    def test_dict(self) -> None:
        ctx = {"args": {"title": "Test", "score": 42}}
        result = render_deep({"title": "{args.title}", "score": "{args.score}"}, ctx)
        assert result == {"title": "Test", "score": 42}

    def test_list(self) -> None:
        ctx = {"args": {"a": 1, "b": 2}}
        result = render_deep(["{args.a}", "{args.b}"], ctx)
        assert result == [1, 2]

    def test_nested_structure(self) -> None:
        ctx = {"args": {"url": "https://example.com"}}
        result = render_deep({"fetch": {"url": "{args.url}", "method": "GET"}}, ctx)
        assert result == {"fetch": {"url": "https://example.com", "method": "GET"}}

    def test_non_template_values_preserved(self) -> None:
        ctx = {"args": {"x": 1}}
        result = render_deep({"a": 42, "b": True, "c": None}, ctx)
        assert result == {"a": 42, "b": True, "c": None}
