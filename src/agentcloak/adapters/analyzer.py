"""API pattern recognition from captured network traffic."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import parse_qs, urlparse

from agentcloak.core.types import Strategy

if TYPE_CHECKING:
    from agentcloak.core.capture import CaptureEntry

__all__ = ["EndpointPattern", "PatternAnalyzer"]

_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I
)
_LONG_ID_RE = re.compile(r"/\d{4,}\b")
_HEX_HASH_RE = re.compile(r"/[0-9a-f]{24,}", re.I)
_DATE_RE = re.compile(r"/\d{4}-\d{2}-\d{2}")

_AUTH_HEADERS = frozenset(
    {
        "authorization",
        "x-csrf-token",
        "x-api-key",
        "api-key",
        "x-auth-token",
        "x-session-id",
    }
)

_SKIP_DOMAINS = frozenset(
    {
        "fonts.googleapis.com",
        "cdn.jsdelivr.net",
        "www.google-analytics.com",
        "www.googletagmanager.com",
        "connect.facebook.net",
    }
)

_PAGINATION_PARAMS = frozenset(
    {"page", "offset", "limit", "cursor", "after", "before", "per_page", "pagesize"}
)
_FILTER_PARAMS = frozenset(
    {"filter", "q", "query", "search", "status", "type", "category", "keyword"}
)
_SORT_PARAMS = frozenset({"sort", "order", "sort_by", "order_by"})


@dataclass
class EndpointPattern:
    """Recognized API endpoint pattern."""

    method: str
    path: str
    domain: str
    call_count: int = 0
    query_params: list[str] = field(default_factory=list[str])
    status_codes: dict[int, int] = field(default_factory=dict[int, int])
    auth_headers: list[str] = field(default_factory=list[str])
    content_type: str = ""
    category: str = "read"
    request_schema: dict[str, Any] | None = None
    response_schema: dict[str, Any] | None = None
    strategy: Strategy = Strategy.PUBLIC
    example_urls: list[str] = field(default_factory=list[str])


def _normalize_path(path: str) -> str:
    result = _UUID_RE.sub(":uuid", path)
    result = _DATE_RE.sub("/:date", result)
    result = _HEX_HASH_RE.sub("/:hash", result)
    result = _LONG_ID_RE.sub("/:id", result)
    return result


def _extract_schema(obj: Any, max_depth: int = 2) -> Any:
    if max_depth <= 0:
        return type(obj).__name__
    if isinstance(obj, dict):
        return {
            str(k): _extract_schema(v, max_depth - 1)
            for k, v in cast("dict[str, Any]", obj).items()
        }
    if isinstance(obj, list):
        if obj:
            return [_extract_schema(obj[0], max_depth)]
        return []
    if isinstance(obj, bool):
        return "bool"
    if isinstance(obj, int):
        return "int"
    if isinstance(obj, float):
        return "float"
    if isinstance(obj, str):
        return "str"
    if obj is None:
        return "null"
    return type(obj).__name__


def _infer_category(method: str, path: str) -> str:
    p = path.lower()
    if any(kw in p for kw in ("auth", "login", "token", "oauth", "signin", "signup")):
        return "auth"
    if any(kw in p for kw in ("search", "query", "find")):
        return "search"
    telemetry = ("log", "track", "event", "beacon", "metric", "telemetry")
    if any(kw in p for kw in telemetry):
        return "telemetry"
    if method in ("GET", "HEAD", "OPTIONS"):
        return "read"
    return "write"


def _infer_strategy(auth_headers: list[str]) -> Strategy:
    if not auth_headers:
        return Strategy.PUBLIC
    lower = {h.lower() for h in auth_headers}
    if "authorization" in lower:
        return Strategy.HEADER
    return Strategy.COOKIE


class PatternAnalyzer:
    """Analyze captured traffic to extract API endpoint patterns."""

    def __init__(self, entries: list[CaptureEntry]) -> None:
        self._entries = entries

    def analyze(self) -> list[EndpointPattern]:
        groups: dict[str, list[CaptureEntry]] = {}
        for entry in self._entries:
            parsed = urlparse(entry.url)
            if parsed.hostname and parsed.hostname in _SKIP_DOMAINS:
                continue
            ct = entry.content_type.split(";", 1)[0].strip().lower()
            if ct not in ("application/json", "text/json"):
                continue
            if entry.status == 0:
                continue

            normalized = _normalize_path(parsed.path)
            key = f"{entry.method} {parsed.hostname} {normalized}"
            groups.setdefault(key, []).append(entry)

        patterns: list[EndpointPattern] = []
        for key, group_entries in groups.items():
            parts = key.split(" ", 2)
            method = parts[0]
            domain = parts[1]
            path = parts[2]
            pattern = self._build_pattern(method, domain, path, group_entries)
            patterns.append(pattern)

        patterns.sort(key=lambda p: p.call_count, reverse=True)
        return patterns

    def _build_pattern(
        self,
        method: str,
        domain: str,
        path: str,
        entries: list[CaptureEntry],
    ) -> EndpointPattern:
        status_codes: dict[int, int] = {}
        all_query_params: set[str] = set()
        auth_headers_seen: set[str] = set()
        content_types: list[str] = []
        example_urls: list[str] = []
        req_schemas: list[dict[str, Any]] = []
        resp_schemas: list[dict[str, Any]] = []

        for entry in entries:
            status_codes[entry.status] = status_codes.get(entry.status, 0) + 1

            parsed = urlparse(entry.url)
            if parsed.query:
                for part in parsed.query.split("&"):
                    name = part.split("=", 1)[0]
                    if name:
                        all_query_params.add(name)

            for header_name in entry.request_headers:
                h = str(header_name)
                if h.lower() in _AUTH_HEADERS:
                    auth_headers_seen.add(h)

            ct = entry.content_type.split(";", 1)[0].strip()
            if ct:
                content_types.append(ct)

            if len(example_urls) < 3:
                example_urls.append(entry.url)

            if entry.request_body:
                try:
                    req_ct = next(
                        (v for k, v in entry.request_headers.items() if k.lower() == "content-type"),
                        "",
                    ).split(";", 1)[0].strip().lower()
                    if req_ct == "application/x-www-form-urlencoded":
                        parsed_qs = parse_qs(entry.request_body, keep_blank_values=True)
                        body_obj: Any = {
                            k: v[0] if len(v) == 1 else v for k, v in parsed_qs.items()
                        }
                    else:
                        body_obj = json.loads(entry.request_body)
                    schema: Any = _extract_schema(body_obj)
                    if isinstance(schema, dict):
                        req_schemas.append(cast("dict[str, Any]", schema))
                except (json.JSONDecodeError, ValueError):
                    pass

            if entry.response_body:
                try:
                    resp_obj: Any = json.loads(entry.response_body)
                    resp_schema_val: Any = _extract_schema(resp_obj)
                    if isinstance(resp_schema_val, dict):
                        resp_schemas.append(cast("dict[str, Any]", resp_schema_val))
                except (json.JSONDecodeError, ValueError):
                    pass

        auth_list = sorted(auth_headers_seen)
        strategy = _infer_strategy(auth_list)
        category = _infer_category(method, path)

        req_schema = req_schemas[0] if req_schemas else None
        resp_schema = resp_schemas[0] if resp_schemas else None

        primary_ct = content_types[0] if content_types else ""

        return EndpointPattern(
            method=method,
            path=path,
            domain=domain,
            call_count=len(entries),
            query_params=sorted(all_query_params),
            status_codes=status_codes,
            auth_headers=auth_list,
            content_type=primary_ct,
            category=category,
            request_schema=req_schema,
            response_schema=resp_schema,
            strategy=strategy,
            example_urls=example_urls,
        )
