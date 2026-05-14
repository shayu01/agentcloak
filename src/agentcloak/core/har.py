"""HAR 1.2 serialization — import/export CaptureEntry as standard HAR."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlparse

if TYPE_CHECKING:
    from agentcloak.core.capture import CaptureEntry

__all__ = ["to_har"]


def to_har(entries: list[CaptureEntry]) -> dict[str, Any]:
    """Serialize CaptureEntry list to HAR 1.2 format."""
    return {
        "log": {
            "version": "1.2",
            "creator": {"name": "agentcloak", "version": "0.1.0"},
            "entries": [_entry_to_har(e) for e in entries],
        }
    }


def _parse_query_string(url: str) -> list[dict[str, str]]:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    result: list[dict[str, str]] = []
    for name, values in qs.items():
        for val in values:
            result.append({"name": name, "value": val})
    return result


def _headers_to_list(headers: dict[str, str]) -> list[dict[str, str]]:
    return [{"name": k, "value": v} for k, v in headers.items()]


def _entry_to_har(entry: CaptureEntry) -> dict[str, Any]:
    request: dict[str, Any] = {
        "method": entry.method,
        "url": entry.url,
        "httpVersion": "HTTP/1.1",
        "cookies": [],
        "headers": _headers_to_list(entry.request_headers),
        "queryString": _parse_query_string(entry.url),
        "headersSize": -1,
        "bodySize": len(entry.request_body) if entry.request_body else 0,
    }
    if entry.request_body:
        ct = entry.request_headers.get(
            "content-type",
            entry.request_headers.get("Content-Type", "application/octet-stream"),
        )
        request["postData"] = {
            "mimeType": ct,
            "text": entry.request_body,
        }

    response_text = entry.response_body or ""
    response: dict[str, Any] = {
        "status": entry.status,
        "statusText": "",
        "httpVersion": "HTTP/1.1",
        "cookies": [],
        "headers": _headers_to_list(entry.response_headers),
        "content": {
            "size": len(response_text),
            "mimeType": entry.content_type or "application/octet-stream",
            "text": response_text,
        },
        "redirectURL": "",
        "headersSize": -1,
        "bodySize": -1,
    }

    return {
        "startedDateTime": entry.timestamp,
        "time": entry.duration_ms,
        "request": request,
        "response": response,
        "cache": {},
        "timings": {
            "send": 0,
            "wait": entry.duration_ms,
            "receive": 0,
        },
    }
