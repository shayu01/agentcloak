"""Tests for adapters/registry.py — @adapter decorator and AdapterRegistry."""

from __future__ import annotations

from browserctl.adapters.context import AdapterContext
from browserctl.adapters.registry import AdapterRegistry, adapter, get_registry
from browserctl.adapters.types import AdapterEntry, AdapterMeta, Arg
from browserctl.core.types import Strategy


class TestAdapterMeta:
    def test_full_name(self) -> None:
        meta = AdapterMeta(site="github", name="repos", strategy=Strategy.COOKIE)
        assert meta.full_name == "github/repos"

    def test_needs_browser_public(self) -> None:
        meta = AdapterMeta(site="httpbin", name="get", strategy=Strategy.PUBLIC)
        assert meta.needs_browser is False

    def test_needs_browser_cookie(self) -> None:
        meta = AdapterMeta(site="github", name="repos", strategy=Strategy.COOKIE)
        assert meta.needs_browser is True

    def test_needs_browser_ui(self) -> None:
        meta = AdapterMeta(site="grok", name="ask", strategy=Strategy.UI)
        assert meta.needs_browser is True

    def test_navigate_before_cookie_with_domain(self) -> None:
        meta = AdapterMeta(
            site="github", name="repos", strategy=Strategy.COOKIE, domain="github.com"
        )
        assert meta.navigate_before == "https://github.com"

    def test_navigate_before_header_with_domain(self) -> None:
        meta = AdapterMeta(
            site="zhihu", name="feed", strategy=Strategy.HEADER, domain="zhihu.com"
        )
        assert meta.navigate_before == "https://zhihu.com"

    def test_navigate_before_cookie_without_domain(self) -> None:
        meta = AdapterMeta(site="github", name="repos", strategy=Strategy.COOKIE)
        assert meta.navigate_before is None

    def test_navigate_before_public(self) -> None:
        meta = AdapterMeta(
            site="httpbin", name="get", strategy=Strategy.PUBLIC, domain="httpbin.org"
        )
        assert meta.navigate_before is None

    def test_navigate_before_intercept(self) -> None:
        meta = AdapterMeta(
            site="xhs", name="search", strategy=Strategy.INTERCEPT, domain="xiaohongshu.com"
        )
        assert meta.navigate_before is None

    def test_navigate_before_ui(self) -> None:
        meta = AdapterMeta(
            site="grok", name="ask", strategy=Strategy.UI, domain="grok.com"
        )
        assert meta.navigate_before is None


class TestAdapterEntry:
    def test_is_pipeline_true(self) -> None:
        meta = AdapterMeta(
            site="test",
            name="pipe",
            strategy=Strategy.PUBLIC,
            pipeline=({"fetch": "https://example.com"},),
        )
        entry = AdapterEntry(meta=meta)
        assert entry.is_pipeline is True

    def test_is_pipeline_false(self) -> None:
        meta = AdapterMeta(site="test", name="func", strategy=Strategy.PUBLIC)

        async def handler(ctx: AdapterContext) -> list[dict[str, object]]:
            return []

        entry = AdapterEntry(meta=meta, handler=handler)
        assert entry.is_pipeline is False


class TestAdapterRegistry:
    def test_register_and_get(self) -> None:
        reg = AdapterRegistry()
        meta = AdapterMeta(site="test", name="cmd", strategy=Strategy.PUBLIC)
        reg.register(AdapterEntry(meta=meta))
        assert reg.get("test", "cmd") is not None
        assert reg.get("test", "missing") is None

    def test_list_all(self) -> None:
        reg = AdapterRegistry()
        for name in ("a", "b", "c"):
            meta = AdapterMeta(site="s", name=name, strategy=Strategy.PUBLIC)
            reg.register(AdapterEntry(meta=meta))
        assert len(reg.list_all()) == 3

    def test_list_by_site(self) -> None:
        reg = AdapterRegistry()
        for site, name in [("x", "a"), ("x", "b"), ("y", "c")]:
            meta = AdapterMeta(site=site, name=name, strategy=Strategy.PUBLIC)
            reg.register(AdapterEntry(meta=meta))
        assert len(reg.list_by_site("x")) == 2
        assert len(reg.list_by_site("y")) == 1
        assert len(reg.list_by_site("z")) == 0

    def test_override_replaces(self) -> None:
        reg = AdapterRegistry()
        meta1 = AdapterMeta(
            site="s", name="cmd", strategy=Strategy.PUBLIC, description="v1"
        )
        meta2 = AdapterMeta(
            site="s", name="cmd", strategy=Strategy.COOKIE, description="v2"
        )
        reg.register(AdapterEntry(meta=meta1))
        reg.register(AdapterEntry(meta=meta2))
        assert len(reg) == 1
        entry = reg.get("s", "cmd")
        assert entry is not None
        assert entry.meta.description == "v2"

    def test_contains(self) -> None:
        reg = AdapterRegistry()
        meta = AdapterMeta(site="s", name="cmd", strategy=Strategy.PUBLIC)
        reg.register(AdapterEntry(meta=meta))
        assert "s/cmd" in reg
        assert "s/other" not in reg

    def test_clear(self) -> None:
        reg = AdapterRegistry()
        meta = AdapterMeta(site="s", name="cmd", strategy=Strategy.PUBLIC)
        reg.register(AdapterEntry(meta=meta))
        reg.clear()
        assert len(reg) == 0


class TestAdapterDecorator:
    def setup_method(self) -> None:
        get_registry().clear()

    def test_function_mode_registers(self) -> None:
        @adapter(site="test", name="func", strategy=Strategy.PUBLIC)
        async def my_handler(ctx: AdapterContext) -> list[dict[str, object]]:
            return [{"ok": True}]

        reg = get_registry()
        entry = reg.get("test", "func")
        assert entry is not None
        assert entry.handler is my_handler
        assert entry.is_pipeline is False

    def test_pipeline_mode_registers(self) -> None:
        @adapter(
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
        @adapter(site="test", name="deco", strategy=Strategy.PUBLIC)
        async def my_func(ctx: AdapterContext) -> list[dict[str, object]]:
            return []

        assert my_func.__name__ == "my_func"

    def test_args_and_columns(self) -> None:
        @adapter(
            site="test",
            name="with_args",
            strategy=Strategy.COOKIE,
            domain="example.com",
            args=[Arg("limit", type=int, default=10, help="Max results")],
            columns=["id", "title"],
        )
        async def handler(ctx: AdapterContext) -> list[dict[str, object]]:
            return []

        entry = get_registry().get("test", "with_args")
        assert entry is not None
        assert len(entry.meta.args) == 1
        assert entry.meta.args[0].name == "limit"
        assert entry.meta.columns == ("id", "title")
