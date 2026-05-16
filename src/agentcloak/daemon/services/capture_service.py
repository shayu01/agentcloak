"""CaptureService — request/response recording, export, analyze, replay.

The capture store itself (RingBuffer + HAR conversion) lives in
:mod:`agentcloak.core.capture`. This service adds the route-level orchestration
(toggle recording, format export results, drive ``PatternAnalyzer``, replay a
captured request via the browser's ``fetch``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from agentcloak.core.errors import AgentBrowserError

if TYPE_CHECKING:
    from agentcloak.core.capture import CaptureStore

__all__ = ["CaptureService"]

logger = structlog.get_logger()

# Headers that must not be propagated when replaying a captured request — they
# break the new TLS+HTTP exchange.
_HOP_BY_HOP = frozenset(
    {
        "host",
        "content-length",
        "connection",
        "transfer-encoding",
        "keep-alive",
        "te",
        "trailer",
        "upgrade",
        "proxy-authorization",
        "proxy-authenticate",
    }
)


class CaptureReplayError(AgentBrowserError):
    """Capture replay-specific errors with structured envelope."""


class CaptureService:
    """Wraps a :class:`CaptureStore` with route-friendly helpers."""

    def __init__(self, store: CaptureStore) -> None:
        self._store = store

    @property
    def store(self) -> CaptureStore:
        return self._store

    # ------------------------------------------------------------------
    # Recording control
    # ------------------------------------------------------------------

    def start(self) -> dict[str, Any]:
        self._store.start()
        return {"recording": True}

    def stop(self) -> dict[str, Any]:
        self._store.stop()
        return {"recording": False, "entries": len(self._store)}

    def status(self) -> dict[str, Any]:
        return {"recording": self._store.recording, "entries": len(self._store)}

    def clear(self) -> dict[str, Any]:
        self._store.clear()
        return {"cleared": True}

    # ------------------------------------------------------------------
    # Export — HAR (default) or raw JSON
    # ------------------------------------------------------------------

    def export(self, *, fmt: str = "har") -> dict[str, Any]:
        from agentcloak.core.har import to_har

        entries = self._store.entries()
        if fmt == "json":
            return {
                "entries": self._store.to_dict_list(),
                "count": len(entries),
            }
        return to_har(entries)

    # ------------------------------------------------------------------
    # Analyze — PatternAnalyzer
    # ------------------------------------------------------------------

    def analyze(self, *, domain: str | None = None) -> dict[str, Any]:
        from agentcloak.spells.analyzer import PatternAnalyzer

        if domain:
            entries = self._store.entries_by_domain(domain)
        else:
            entries = self._store.api_entries()

        try:
            analyzer = PatternAnalyzer(entries)
            patterns = analyzer.analyze()
        except Exception as exc:
            logger.exception("capture_analyze_failed")
            raise CaptureReplayError(
                error="analyze_failed",
                hint="PatternAnalyzer raised an exception; check daemon logs",
                action="try capture export --format json to inspect raw entries",
            ) from exc

        patterns_data: list[dict[str, Any]] = []
        for p in patterns:
            status_codes = {str(k): v for k, v in p.status_codes.items()}
            patterns_data.append(
                {
                    "method": p.method,
                    "path": p.path,
                    "domain": p.domain,
                    "call_count": p.call_count,
                    "query_params": p.query_params,
                    "status_codes": status_codes,
                    "auth_headers": p.auth_headers,
                    "content_type": p.content_type,
                    "category": p.category,
                    "strategy": p.strategy.value,
                    "request_schema": p.request_schema,
                    "response_schema": p.response_schema,
                    "example_urls": p.example_urls,
                }
            )

        return {"patterns": patterns_data, "count": len(patterns_data)}

    # ------------------------------------------------------------------
    # Replay — re-issue a captured request via the browser's fetch
    # ------------------------------------------------------------------

    async def replay(
        self,
        ctx: Any,
        *,
        url: str,
        method: str = "GET",
    ) -> dict[str, Any]:
        if not url:
            raise CaptureReplayError(
                error="missing_url",
                hint="url is required",
                action="provide a URL to replay",
            )

        entry = self._store.find_latest(url, method)
        if entry is None:
            raise CaptureReplayError(
                error="capture_entry_not_found",
                hint=f"No captured {method.upper()} {url}",
                action=(
                    "run 'capture start', navigate to trigger the request, then replay"
                ),
            )

        replay_headers = {
            k: v
            for k, v in entry.request_headers.items()
            if k.lower() not in _HOP_BY_HOP
        }

        result = await ctx.fetch(
            url,
            method=entry.method,
            body=entry.request_body,
            headers=replay_headers if replay_headers else None,
        )
        result["replayed_from"] = {
            "url": entry.url,
            "method": entry.method,
            "seq": entry.seq,
        }
        return result
