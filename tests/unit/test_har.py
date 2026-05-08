"""Tests for core/har.py — HAR serialization."""

from browserctl.core.capture import CaptureEntry
from browserctl.core.har import from_har, to_har


def _make_entry(**kw: object) -> CaptureEntry:
    defaults = {
        "seq": 1,
        "timestamp": "2026-05-07T12:00:00Z",
        "method": "GET",
        "url": "https://api.example.com/v1/users?page=1",
        "status": 200,
        "resource_type": "xhr",
        "request_headers": {"Authorization": "Bearer xxx"},
        "response_headers": {"Content-Type": "application/json"},
        "request_body": None,
        "response_body": '{"users": []}',
        "content_type": "application/json",
        "duration_ms": 150.0,
    }
    defaults.update(kw)  # type: ignore[arg-type]
    return CaptureEntry(**defaults)  # type: ignore[arg-type]


class TestToHar:
    def test_basic_structure(self) -> None:
        har = to_har([_make_entry()])
        assert har["log"]["version"] == "1.2"
        assert har["log"]["creator"]["name"] == "browserctl"
        assert len(har["log"]["entries"]) == 1

    def test_entry_fields(self) -> None:
        har = to_har([_make_entry()])
        entry = har["log"]["entries"][0]
        assert entry["request"]["method"] == "GET"
        assert entry["request"]["url"] == "https://api.example.com/v1/users?page=1"
        assert entry["response"]["status"] == 200
        assert entry["time"] == 150.0

    def test_query_string_parsed(self) -> None:
        har = to_har([_make_entry()])
        qs = har["log"]["entries"][0]["request"]["queryString"]
        assert len(qs) == 1
        assert qs[0]["name"] == "page"
        assert qs[0]["value"] == "1"

    def test_request_headers(self) -> None:
        har = to_har([_make_entry()])
        headers = har["log"]["entries"][0]["request"]["headers"]
        assert any(h["name"] == "Authorization" for h in headers)

    def test_response_body(self) -> None:
        har = to_har([_make_entry()])
        content = har["log"]["entries"][0]["response"]["content"]
        assert content["text"] == '{"users": []}'
        assert content["mimeType"] == "application/json"

    def test_post_data(self) -> None:
        entry = _make_entry(
            method="POST",
            request_body='{"name": "test"}',
            request_headers={"Content-Type": "application/json"},
        )
        har = to_har([entry])
        post_data = har["log"]["entries"][0]["request"]["postData"]
        assert post_data["text"] == '{"name": "test"}'

    def test_empty_entries(self) -> None:
        har = to_har([])
        assert har["log"]["entries"] == []


class TestFromHar:
    def test_roundtrip(self) -> None:
        original = [_make_entry()]
        har = to_har(original)
        parsed = from_har(har)
        assert len(parsed) == 1
        assert parsed[0].method == "GET"
        assert parsed[0].url == "https://api.example.com/v1/users?page=1"
        assert parsed[0].status == 200

    def test_preserves_headers(self) -> None:
        original = [_make_entry()]
        har = to_har(original)
        parsed = from_har(har)
        assert "Authorization" in parsed[0].request_headers

    def test_preserves_body(self) -> None:
        original = [_make_entry(response_body='{"ok": true}')]
        har = to_har(original)
        parsed = from_har(har)
        assert parsed[0].response_body == '{"ok": true}'

    def test_multiple_entries(self) -> None:
        entries = [_make_entry(seq=i) for i in range(5)]
        har = to_har(entries)
        parsed = from_har(har)
        assert len(parsed) == 5

    def test_accepts_nested_log(self) -> None:
        har = {"log": {"version": "1.2", "entries": []}}
        parsed = from_har(har)
        assert parsed == []
