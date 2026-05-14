"""Tests for adapters/analyzer.py — API pattern recognition."""

from agentcloak.adapters.analyzer import (
    PatternAnalyzer,
    _extract_schema,
    _normalize_path,
)
from agentcloak.core.capture import CaptureEntry
from agentcloak.core.types import Strategy


def _api_entry(
    *,
    url: str = "https://api.example.com/v1/users",
    method: str = "GET",
    status: int = 200,
    content_type: str = "application/json",
    request_headers: dict[str, str] | None = None,
    response_body: str | None = None,
    request_body: str | None = None,
) -> CaptureEntry:
    return CaptureEntry(
        seq=1,
        timestamp="2026-05-07T12:00:00Z",
        method=method,
        url=url,
        status=status,
        resource_type="xhr",
        request_headers=request_headers or {},
        response_headers={"Content-Type": content_type},
        request_body=request_body,
        response_body=response_body,
        content_type=content_type,
    )


class TestNormalizePath:
    def test_uuid(self) -> None:
        result = _normalize_path("/api/users/550e8400-e29b-41d4-a716-446655440000")
        assert ":uuid" in result

    def test_numeric_id(self) -> None:
        result = _normalize_path("/api/users/12345/posts")
        assert "/:id/" in result

    def test_hex_hash(self) -> None:
        result = _normalize_path("/api/objects/aabbccddeeff00112233445566")
        assert ":hash" in result

    def test_date(self) -> None:
        result = _normalize_path("/api/events/2026-05-07")
        assert ":date" in result

    def test_no_params(self) -> None:
        result = _normalize_path("/api/v1/users")
        assert result == "/api/v1/users"


class TestExtractSchema:
    def test_dict(self) -> None:
        schema = _extract_schema({"name": "Alice", "age": 25})
        assert schema == {"name": "str", "age": "int"}

    def test_nested_dict(self) -> None:
        schema = _extract_schema({"user": {"name": "Alice"}})
        assert schema == {"user": {"name": "str"}}

    def test_list(self) -> None:
        schema = _extract_schema({"items": [{"id": 1}]})
        assert schema == {"items": [{"id": "int"}]}

    def test_empty_list(self) -> None:
        schema = _extract_schema({"items": []})
        assert schema == {"items": []}

    def test_primitives(self) -> None:
        assert _extract_schema(42) == "int"
        assert _extract_schema(3.14) == "float"
        assert _extract_schema("hello") == "str"
        assert _extract_schema(True) == "bool"
        assert _extract_schema(None) == "null"


class TestPatternAnalyzer:
    def test_groups_by_method_and_path(self) -> None:
        entries = [
            _api_entry(url="https://api.example.com/v1/users/12345"),
            _api_entry(url="https://api.example.com/v1/users/67890"),
        ]
        patterns = PatternAnalyzer(entries).analyze()
        assert len(patterns) == 1
        assert patterns[0].path == "/v1/users/:id"
        assert patterns[0].call_count == 2

    def test_separates_methods(self) -> None:
        entries = [
            _api_entry(url="https://api.example.com/v1/users", method="GET"),
            _api_entry(url="https://api.example.com/v1/users", method="POST"),
        ]
        patterns = PatternAnalyzer(entries).analyze()
        assert len(patterns) == 2

    def test_detects_auth_headers(self) -> None:
        entries = [
            _api_entry(
                request_headers={"Authorization": "Bearer xxx"},
            ),
        ]
        patterns = PatternAnalyzer(entries).analyze()
        assert "Authorization" in patterns[0].auth_headers
        assert patterns[0].strategy == Strategy.HEADER

    def test_public_strategy_when_no_auth(self) -> None:
        entries = [_api_entry()]
        patterns = PatternAnalyzer(entries).analyze()
        assert patterns[0].strategy == Strategy.PUBLIC

    def test_collects_query_params(self) -> None:
        entries = [
            _api_entry(url="https://api.example.com/v1/users?page=1&limit=10"),
            _api_entry(url="https://api.example.com/v1/users?page=2&limit=10"),
        ]
        patterns = PatternAnalyzer(entries).analyze()
        assert "page" in patterns[0].query_params
        assert "limit" in patterns[0].query_params

    def test_status_code_histogram(self) -> None:
        entries = [
            _api_entry(status=200),
            _api_entry(status=200),
            _api_entry(status=404),
        ]
        patterns = PatternAnalyzer(entries).analyze()
        assert patterns[0].status_codes[200] == 2
        assert patterns[0].status_codes[404] == 1

    def test_filters_non_json(self) -> None:
        entries = [
            _api_entry(content_type="application/json"),
            _api_entry(content_type="text/html"),
        ]
        patterns = PatternAnalyzer(entries).analyze()
        assert len(patterns) == 1

    def test_filters_skip_domains(self) -> None:
        entries = [
            _api_entry(url="https://www.google-analytics.com/collect"),
        ]
        patterns = PatternAnalyzer(entries).analyze()
        assert len(patterns) == 0

    def test_category_inference(self) -> None:
        entries = [
            _api_entry(url="https://api.example.com/auth/login", method="POST"),
        ]
        patterns = PatternAnalyzer(entries).analyze()
        assert patterns[0].category == "auth"

    def test_response_schema_extraction(self) -> None:
        entries = [
            _api_entry(response_body='{"id": 1, "name": "Alice"}'),
        ]
        patterns = PatternAnalyzer(entries).analyze()
        assert patterns[0].response_schema is not None
        assert "id" in patterns[0].response_schema
        assert "name" in patterns[0].response_schema

    def test_sorted_by_call_count(self) -> None:
        entries = [
            _api_entry(url="https://api.example.com/v1/rare"),
            _api_entry(url="https://api.example.com/v1/popular"),
            _api_entry(url="https://api.example.com/v1/popular"),
            _api_entry(url="https://api.example.com/v1/popular"),
        ]
        patterns = PatternAnalyzer(entries).analyze()
        assert patterns[0].call_count > patterns[1].call_count

    def test_request_schema_json_body(self) -> None:
        entries = [
            _api_entry(
                method="POST",
                request_headers={"content-type": "application/json"},
                request_body='{"post_id": 123, "page": 1}',
            ),
        ]
        patterns = PatternAnalyzer(entries).analyze()
        assert patterns[0].request_schema is not None
        assert "post_id" in patterns[0].request_schema

    def test_request_schema_url_encoded(self) -> None:
        entries = [
            _api_entry(
                method="POST",
                request_headers={"content-type": "application/x-www-form-urlencoded"},
                request_body="post_id=78327&index=0&i=0",
            ),
        ]
        patterns = PatternAnalyzer(entries).analyze()
        assert patterns[0].request_schema is not None
        assert "post_id" in patterns[0].request_schema
        assert "index" in patterns[0].request_schema

    def test_request_schema_url_encoded_with_charset(self) -> None:
        entries = [
            _api_entry(
                method="POST",
                request_headers={
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
                },
                request_body="action=get&id=42",
            ),
        ]
        patterns = PatternAnalyzer(entries).analyze()
        assert patterns[0].request_schema is not None
        assert "action" in patterns[0].request_schema
