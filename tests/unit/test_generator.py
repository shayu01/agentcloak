"""Tests for spells/generator.py — spell code generation."""

from agentcloak.core.types import Strategy
from agentcloak.spells.analyzer import EndpointPattern
from agentcloak.spells.generator import generate_spell, generate_spells


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


class TestGenerateSpell:
    def test_basic_get(self) -> None:
        code = generate_spell("example", _pattern())
        assert "@spell(" in code
        assert 'site="example"' in code
        assert "Strategy.PUBLIC" in code
        assert "pipeline=" in code

    def test_includes_path_params_as_args(self) -> None:
        code = generate_spell("example", _pattern(path="/api/v1/users/:id"))
        assert 'Arg("id"' in code
        assert "required=True" in code

    def test_includes_query_params_as_args(self) -> None:
        code = generate_spell("example", _pattern(query_params=["page", "limit"]))
        assert 'Arg("page"' in code
        assert 'Arg("limit"' in code

    def test_cookie_strategy_has_navigate(self) -> None:
        code = generate_spell("example", _pattern(strategy=Strategy.COOKIE))
        assert '"navigate"' in code
        assert "Strategy.COOKIE" in code

    def test_post_method_generates_write_access(self) -> None:
        code = generate_spell("example", _pattern(method="POST"))
        assert 'access="write"' in code

    def test_custom_name(self) -> None:
        code = generate_spell("example", _pattern(), name="my_spell")
        assert 'name="my_spell"' in code

    def test_generated_code_compiles(self) -> None:
        code = generate_spell("test", _pattern())
        compile(code, "<test>", "exec")

    def test_header_strategy_code_compiles(self) -> None:
        code = generate_spell(
            "test",
            _pattern(
                strategy=Strategy.HEADER,
                path="/api/users/:id",
                query_params=["fields"],
            ),
        )
        compile(code, "<test>", "exec")


class TestGenerateSpells:
    def test_module_has_imports(self) -> None:
        code = generate_spells("example", [_pattern()])
        assert "from agentcloak.spells.registry import spell" in code
        assert "from agentcloak.core.types import Strategy" in code

    def test_skips_telemetry(self) -> None:
        patterns = [
            _pattern(category="read"),
            _pattern(
                path="/api/track",
                category="telemetry",
            ),
        ]
        code = generate_spells("example", patterns)
        assert "/api/track" not in code

    def test_multiple_spells(self) -> None:
        patterns = [
            _pattern(path="/api/v1/users"),
            _pattern(path="/api/v1/posts", method="POST"),
        ]
        code = generate_spells("example", patterns)
        assert code.count("@spell(") == 2
