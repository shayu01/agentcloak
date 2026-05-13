"""Tests for adapters/generator.py — adapter code generation."""

from agentcloak.adapters.analyzer import EndpointPattern
from agentcloak.adapters.generator import generate_adapter, generate_adapters
from agentcloak.core.types import Strategy


def _pattern(
    *,
    method: str = "GET",
    path: str = "/api/v1/users",
    domain: str = "api.example.com",
    strategy: Strategy = Strategy.PUBLIC,
    query_params: list[str] | None = None,
    auth_headers: list[str] | None = None,
    category: str = "read",
    request_schema: dict[str, str] | None = None,
) -> EndpointPattern:
    return EndpointPattern(
        method=method,
        path=path,
        domain=domain,
        call_count=10,
        query_params=query_params or [],
        status_codes={200: 10},
        auth_headers=auth_headers or [],
        content_type="application/json",
        category=category,
        strategy=strategy,
        request_schema=request_schema,
    )


class TestGenerateAdapter:
    def test_basic_get(self) -> None:
        code = generate_adapter("example", _pattern())
        assert '@adapter(' in code
        assert 'site="example"' in code
        assert 'Strategy.PUBLIC' in code
        assert "pipeline=" in code

    def test_includes_path_params_as_args(self) -> None:
        code = generate_adapter("example", _pattern(path="/api/v1/users/:id"))
        assert 'Arg("id"' in code
        assert "required=True" in code

    def test_includes_query_params_as_args(self) -> None:
        code = generate_adapter(
            "example", _pattern(query_params=["page", "limit"])
        )
        assert 'Arg("page"' in code
        assert 'Arg("limit"' in code

    def test_cookie_strategy_has_navigate(self) -> None:
        code = generate_adapter(
            "example", _pattern(strategy=Strategy.COOKIE)
        )
        assert '"navigate"' in code
        assert "Strategy.COOKIE" in code

    def test_post_method_generates_write_access(self) -> None:
        code = generate_adapter(
            "example", _pattern(method="POST")
        )
        assert 'access="write"' in code

    def test_custom_name(self) -> None:
        code = generate_adapter("example", _pattern(), name="my_adapter")
        assert 'name="my_adapter"' in code

    def test_generated_code_compiles(self) -> None:
        code = generate_adapter("test", _pattern())
        compile(code, "<test>", "exec")

    def test_header_strategy_code_compiles(self) -> None:
        code = generate_adapter(
            "test",
            _pattern(
                strategy=Strategy.HEADER,
                path="/api/users/:id",
                query_params=["fields"],
            ),
        )
        compile(code, "<test>", "exec")


class TestGenerateAdapters:
    def test_module_has_imports(self) -> None:
        code = generate_adapters("example", [_pattern()])
        assert "from agentcloak.adapters.registry import adapter" in code
        assert "from agentcloak.core.types import Strategy" in code

    def test_skips_telemetry(self) -> None:
        patterns = [
            _pattern(category="read"),
            _pattern(
                path="/api/track",
                category="telemetry",
            ),
        ]
        code = generate_adapters("example", patterns)
        assert "/api/track" not in code

    def test_multiple_adapters(self) -> None:
        patterns = [
            _pattern(path="/api/v1/users"),
            _pattern(path="/api/v1/posts", method="POST"),
        ]
        code = generate_adapters("example", patterns)
        assert code.count("@adapter(") == 2
