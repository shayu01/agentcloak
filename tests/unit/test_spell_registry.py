"""Tests for spells/registry.py — @spell decorator and SpellRegistry."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agentcloak.spells.registry import SpellRegistry, get_registry, spell

if TYPE_CHECKING:
    from agentcloak.spells.context import SpellContext
from agentcloak.core.types import Strategy
from agentcloak.spells.types import Arg, SpellEntry, SpellMeta


class TestSpellMeta:
    def test_full_name(self) -> None:
        meta = SpellMeta(site="github", name="repos", strategy=Strategy.COOKIE)
        assert meta.full_name == "github/repos"

    def test_needs_browser_public(self) -> None:
        meta = SpellMeta(site="httpbin", name="get", strategy=Strategy.PUBLIC)
        assert meta.needs_browser is False

    def test_needs_browser_cookie(self) -> None:
        meta = SpellMeta(site="github", name="repos", strategy=Strategy.COOKIE)
        assert meta.needs_browser is True

    def test_needs_browser_ui(self) -> None:
        meta = SpellMeta(site="grok", name="ask", strategy=Strategy.UI)
        assert meta.needs_browser is True

    def test_navigate_before_cookie_with_domain(self) -> None:
        meta = SpellMeta(
            site="github", name="repos", strategy=Strategy.COOKIE, domain="github.com"
        )
        assert meta.navigate_before == "https://github.com"

    def test_navigate_before_header_with_domain(self) -> None:
        meta = SpellMeta(
            site="zhihu", name="feed", strategy=Strategy.HEADER, domain="zhihu.com"
        )
        assert meta.navigate_before == "https://zhihu.com"

    def test_navigate_before_cookie_without_domain(self) -> None:
        meta = SpellMeta(site="github", name="repos", strategy=Strategy.COOKIE)
        assert meta.navigate_before is None

    def test_navigate_before_public(self) -> None:
        meta = SpellMeta(
            site="httpbin", name="get", strategy=Strategy.PUBLIC, domain="httpbin.org"
        )
        assert meta.navigate_before is None

    def test_navigate_before_intercept(self) -> None:
        meta = SpellMeta(
            site="xhs",
            name="search",
            strategy=Strategy.INTERCEPT,
            domain="xiaohongshu.com",
        )
        assert meta.navigate_before is None

    def test_navigate_before_ui(self) -> None:
        meta = SpellMeta(
            site="grok", name="ask", strategy=Strategy.UI, domain="grok.com"
        )
        assert meta.navigate_before is None


class TestSpellEntry:
    def test_is_pipeline_true(self) -> None:
        meta = SpellMeta(
            site="test",
            name="pipe",
            strategy=Strategy.PUBLIC,
            pipeline=({"fetch": "https://example.com"},),
        )
        entry = SpellEntry(meta=meta)
        assert entry.is_pipeline is True

    def test_is_pipeline_false(self) -> None:
        meta = SpellMeta(site="test", name="func", strategy=Strategy.PUBLIC)

        async def handler(ctx: SpellContext) -> list[dict[str, object]]:
            return []

        entry = SpellEntry(meta=meta, handler=handler)
        assert entry.is_pipeline is False


class TestSpellRegistry:
    def test_register_and_get(self) -> None:
        reg = SpellRegistry()
        meta = SpellMeta(site="test", name="cmd", strategy=Strategy.PUBLIC)
        reg.register(SpellEntry(meta=meta))
        assert reg.get("test", "cmd") is not None
        assert reg.get("test", "missing") is None

    def test_list_all(self) -> None:
        reg = SpellRegistry()
        for name in ("a", "b", "c"):
            meta = SpellMeta(site="s", name=name, strategy=Strategy.PUBLIC)
            reg.register(SpellEntry(meta=meta))
        assert len(reg.list_all()) == 3

    def test_list_by_site(self) -> None:
        reg = SpellRegistry()
        for site, name in [("x", "a"), ("x", "b"), ("y", "c")]:
            meta = SpellMeta(site=site, name=name, strategy=Strategy.PUBLIC)
            reg.register(SpellEntry(meta=meta))
        assert len(reg.list_by_site("x")) == 2
        assert len(reg.list_by_site("y")) == 1
        assert len(reg.list_by_site("z")) == 0

    def test_override_replaces(self) -> None:
        reg = SpellRegistry()
        meta1 = SpellMeta(
            site="s", name="cmd", strategy=Strategy.PUBLIC, description="v1"
        )
        meta2 = SpellMeta(
            site="s", name="cmd", strategy=Strategy.COOKIE, description="v2"
        )
        reg.register(SpellEntry(meta=meta1))
        reg.register(SpellEntry(meta=meta2))
        assert len(reg) == 1
        entry = reg.get("s", "cmd")
        assert entry is not None
        assert entry.meta.description == "v2"

    def test_contains(self) -> None:
        reg = SpellRegistry()
        meta = SpellMeta(site="s", name="cmd", strategy=Strategy.PUBLIC)
        reg.register(SpellEntry(meta=meta))
        assert "s/cmd" in reg
        assert "s/other" not in reg

    def test_clear(self) -> None:
        reg = SpellRegistry()
        meta = SpellMeta(site="s", name="cmd", strategy=Strategy.PUBLIC)
        reg.register(SpellEntry(meta=meta))
        reg.clear()
        assert len(reg) == 0


class TestSpellDecorator:
    def setup_method(self) -> None:
        get_registry().clear()

    def test_function_mode_registers(self) -> None:
        @spell(site="test", name="func", strategy=Strategy.PUBLIC)
        async def my_handler(ctx: SpellContext) -> list[dict[str, object]]:
            return [{"ok": True}]

        reg = get_registry()
        entry = reg.get("test", "func")
        assert entry is not None
        assert entry.handler is my_handler
        assert entry.is_pipeline is False

    def test_pipeline_mode_registers(self) -> None:
        @spell(
            site="test",
            name="pipe",
            strategy=Strategy.PUBLIC,
            pipeline=[{"fetch": "https://example.com"}],
        )
        def placeholder() -> None: ...

        reg = get_registry()
        entry = reg.get("test", "pipe")
        assert entry is not None
        assert entry.handler is None
        assert entry.is_pipeline is True
        assert entry.meta.pipeline == ({"fetch": "https://example.com"},)

    def test_decorator_preserves_function(self) -> None:
        @spell(site="test", name="deco", strategy=Strategy.PUBLIC)
        async def my_func(ctx: SpellContext) -> list[dict[str, object]]:
            return []

        assert my_func.__name__ == "my_func"

    def test_args_and_columns(self) -> None:
        @spell(
            site="test",
            name="with_args",
            strategy=Strategy.COOKIE,
            domain="example.com",
            args=[Arg("limit", type=int, default=10, help="Max results")],
            columns=["id", "title"],
        )
        async def handler(ctx: SpellContext) -> list[dict[str, object]]:
            return []

        entry = get_registry().get("test", "with_args")
        assert entry is not None
        assert len(entry.meta.args) == 1
        assert entry.meta.args[0].name == "limit"
        assert entry.meta.columns == ("id", "title")
