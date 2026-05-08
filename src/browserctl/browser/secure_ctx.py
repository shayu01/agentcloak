"""SecureBrowserContext — IDPI security wrapper around any BrowserContext."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from browserctl.browser.state import PageSnapshot
    from browserctl.core.config import BrowserctlConfig
    from browserctl.core.types import StealthTier

from browserctl.core.errors import SecurityError
from browserctl.core.security import (
    check_domain_allowed,
    scan_content,
    wrap_untrusted,
)

__all__ = ["SecureBrowserContext"]

logger = logging.getLogger(__name__)


class SecureBrowserContext:
    """Transparent IDPI security layer wrapping any browser context.

    Intercepts navigate/fetch (Layer 1), action/snapshot (Layer 2),
    and snapshot content (Layer 3). All other methods proxy to inner.
    """

    def __init__(self, inner: Any, config: BrowserctlConfig) -> None:
        self._inner = inner
        self._whitelist = config.domain_whitelist
        self._blacklist = config.domain_blacklist
        self._content_scan = config.content_scan
        self._patterns = config.content_scan_patterns

    async def navigate(self, url: str, *, timeout: float = 30.0) -> dict[str, Any]:
        check_domain_allowed(url, whitelist=self._whitelist, blacklist=self._blacklist)
        return await self._inner.navigate(url, timeout=timeout)

    async def snapshot(self, *, mode: str = "accessible") -> PageSnapshot:
        snap: PageSnapshot = await self._inner.snapshot(mode=mode)

        warnings: list[dict[str, str | int]] = []
        if self._content_scan and self._patterns:
            matches = scan_content(snap.tree_text, self._patterns)
            if matches:
                warnings = [m.to_dict() for m in matches]
                logger.warning(
                    "content_scan_warnings",
                    extra={"url": snap.url, "match_count": len(matches)},
                )

        wrapped_text = wrap_untrusted(
            snap.tree_text, snap.url, whitelist=self._whitelist
        )

        return replace(
            snap,
            tree_text=wrapped_text,
            security_warnings=warnings,
        )

    async def action(self, kind: str, target: str, **kw: Any) -> dict[str, Any]:
        if self._content_scan and self._patterns:
            snap: PageSnapshot = await self._inner.snapshot(mode="accessible")
            self._check_action_target(snap, target)
        return await self._inner.action(kind, target, **kw)

    async def action_batch(
        self,
        actions: list[dict[str, Any]],
        *,
        sleep: float = 0.0,
    ) -> dict[str, Any]:
        if not self._content_scan or not self._patterns:
            return await self._inner.action_batch(actions, sleep=sleep)

        results: list[dict[str, Any]] = []
        total = len(actions)

        if total == 0:
            return {"results": [], "completed": 0, "total": 0}

        for i, act in enumerate(actions):
            kind = act.get("kind", act.get("action", ""))
            index = act.get("index")
            target = str(index) if index is not None else act.get("target", "")

            try:
                snap = await self._inner.snapshot(mode="accessible")
                self._check_action_target(snap, target)
            except SecurityError:
                return {
                    "results": results,
                    "completed": i,
                    "total": total,
                    "aborted_reason": "content_scan_blocked",
                    "blocked_action_index": i,
                }

            extra = {
                k: v
                for k, v in act.items()
                if k not in ("kind", "action", "index", "target")
            }
            result = await self._inner.action(str(kind), str(target), **extra)
            results.append(result)

            if result.get("caused_navigation"):
                return {
                    "results": results,
                    "completed": i + 1,
                    "total": total,
                    "aborted_reason": "url_changed",
                }

            if sleep > 0 and i < total - 1:
                import asyncio

                await asyncio.sleep(sleep)

        return {"results": results, "completed": total, "total": total}

    async def tab_new(self, url: str | None = None) -> dict[str, Any]:
        if url:
            check_domain_allowed(
                url, whitelist=self._whitelist, blacklist=self._blacklist
            )
        return await self._inner.tab_new(url)

    async def fetch(
        self,
        url: str,
        *,
        method: str = "GET",
        body: str | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        check_domain_allowed(url, whitelist=self._whitelist, blacklist=self._blacklist)
        return await self._inner.fetch(
            url, method=method, body=body, headers=headers, timeout=timeout
        )

    async def evaluate(self, js: str, *, world: str = "main") -> Any:
        return await self._inner.evaluate(js, world=world)

    async def network(
        self, *, since: int | str = "last_action"
    ) -> list[dict[str, Any]]:
        return await self._inner.network(since=since)

    async def screenshot(
        self,
        *,
        full_page: bool = False,
        format: str = "jpeg",
        quality: int = 80,
    ) -> bytes:
        return await self._inner.screenshot(
            full_page=full_page, format=format, quality=quality
        )

    async def close(self) -> None:
        return await self._inner.close()

    @property
    def seq(self) -> int:
        return self._inner.seq

    @property
    def stealth_tier(self) -> StealthTier:
        return self._inner.stealth_tier

    @property
    def capture_store(self) -> Any:
        return self._inner.capture_store

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def _check_action_target(self, snap: PageSnapshot, target: str) -> None:
        """Check the target element text for injection patterns."""
        try:
            index = int(target)
        except (ValueError, TypeError):
            return

        elem = snap.selector_map.get(index)
        if elem is None:
            return

        text = elem.text or ""
        matches = scan_content(text, self._patterns)
        if matches:
            descriptions = ", ".join(m.pattern for m in matches)
            raise SecurityError(
                error="content_scan_blocked",
                hint=f"Element [{index}] matched injection pattern: {descriptions}",
                action="inspect the element manually or disable content_scan",
            )
