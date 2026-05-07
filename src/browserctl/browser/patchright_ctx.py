"""PatchrightContext — default browser backend using patchright (Playwright fork)."""

from __future__ import annotations

import base64
import shutil
from typing import Any

from browserctl.browser.state import ElementRef, PageSnapshot
from browserctl.core.errors import BackendError, BrowserTimeoutError, NavigationError
from browserctl.core.seq import RingBuffer, SeqCounter, SeqEvent
from browserctl.core.types import StealthTier

__all__ = ["PatchrightContext"]

_INTERACTIVE_ROLES = frozenset(
    {
        "button",
        "checkbox",
        "combobox",
        "link",
        "menuitem",
        "menuitemcheckbox",
        "menuitemradio",
        "option",
        "radio",
        "searchbox",
        "slider",
        "spinbutton",
        "switch",
        "tab",
        "textbox",
        "treeitem",
    }
)


_SNAP_CHROMIUM = "/snap/chromium/current/usr/lib/chromium-browser/chrome"


def _find_chromium() -> str | None:
    from pathlib import Path

    if Path(_SNAP_CHROMIUM).is_file():
        return _SNAP_CHROMIUM
    for name in (
        "chromium-browser",
        "chromium",
        "google-chrome-stable",
        "google-chrome",
    ):
        path = shutil.which(name)
        if path:
            return path
    return None


class PatchrightContext:
    """BrowserContext implementation backed by patchright/playwright."""

    def __init__(
        self,
        *,
        page: Any,
        browser: Any,
        playwright: Any,
        seq_counter: SeqCounter,
        ring_buffer: RingBuffer,
    ) -> None:
        self._page = page
        self._browser = browser
        self._playwright = playwright
        self._seq_counter = seq_counter
        self._ring_buffer = ring_buffer
        self._setup_network_listeners()

    def _setup_network_listeners(self) -> None:
        self._page.on("response", self._on_response)

    def _on_response(self, response: Any) -> None:
        try:
            request = response.request
            self._ring_buffer.append(
                SeqEvent(
                    seq=self._seq_counter.value,
                    kind="network",
                    data={
                        "method": request.method,
                        "url": request.url,
                        "status": response.status,
                        "resource_type": request.resource_type,
                    },
                )
            )
        except Exception:
            pass

    @property
    def seq(self) -> int:
        return self._seq_counter.value

    @property
    def stealth_tier(self) -> StealthTier:
        return StealthTier.PATCHRIGHT

    async def navigate(self, url: str, *, timeout: float = 30.0) -> dict[str, Any]:
        try:
            resp = await self._page.goto(
                url, timeout=timeout * 1000, wait_until="domcontentloaded"
            )
        except Exception as exc:
            if "timeout" in str(exc).lower():
                raise BrowserTimeoutError(
                    error="navigation_timeout",
                    hint=f"Page did not load within {timeout}s",
                    action=f"retry with longer timeout or check URL: {url}",
                ) from exc
            raise NavigationError(
                error="navigation_failed",
                hint=str(exc),
                action="check URL and network connectivity",
            ) from exc

        new_seq = self._seq_counter.increment()
        self._ring_buffer.append(
            SeqEvent(seq=new_seq, kind="navigate", data={"url": url})
        )

        status = resp.status if resp else 0
        return {
            "url": self._page.url,
            "title": await self._page.title(),
            "status": status,
            "seq": new_seq,
        }

    async def snapshot(self, *, mode: str = "accessible") -> PageSnapshot:
        if mode == "accessible":
            return await self._snapshot_accessible()
        if mode == "dom":
            return await self._snapshot_dom()
        if mode == "content":
            return await self._snapshot_content()
        raise BackendError(
            error="invalid_snapshot_mode",
            hint=f"Unknown mode: {mode}",
            action="use one of: accessible, dom, content",
        )

    async def _snapshot_accessible(self) -> PageSnapshot:
        cdp = await self._page.context.new_cdp_session(self._page)
        try:
            tree = await cdp.send("Accessibility.getFullAXTree")
        finally:
            await cdp.detach()

        nodes: list[dict[str, Any]] = tree.get("nodes", [])
        selector_map: dict[int, ElementRef] = {}
        lines: list[str] = []
        counter = 1

        for node in nodes:
            role = node.get("role", {}).get("value", "")
            name = node.get("name", {}).get("value", "")
            if not role or role == "none":
                continue

            if role.lower() in _INTERACTIVE_ROLES:
                selector_map[counter] = ElementRef(
                    index=counter,
                    tag=role,
                    role=role,
                    text=name,
                    attributes=dict[str, str](),
                )
                lines.append(f"[{counter}] <{role}> {name}")
                counter += 1
            elif name:
                lines.append(f"{role}: {name}")

        return PageSnapshot(
            seq=self._seq_counter.value,
            url=self._page.url,
            title=await self._page.title(),
            mode="accessible",
            tree_text="\n".join(lines),
            selector_map=selector_map,
        )

    async def _snapshot_dom(self) -> PageSnapshot:
        html = await self._page.content()
        truncated = html[:100_000]
        if len(html) > 100_000:
            truncated += "\n[...truncated...]"
        return PageSnapshot(
            seq=self._seq_counter.value,
            url=self._page.url,
            title=await self._page.title(),
            mode="dom",
            tree_text=truncated,
        )

    async def _snapshot_content(self) -> PageSnapshot:
        text: str = await self._page.evaluate("document.body?.innerText || ''")
        return PageSnapshot(
            seq=self._seq_counter.value,
            url=self._page.url,
            title=await self._page.title(),
            mode="content",
            tree_text=text,
        )

    async def action(self, kind: str, target: str, **kw: Any) -> dict[str, Any]:
        raise BackendError(
            error="action_not_implemented",
            hint=f"Action '{kind}' is not implemented in Phase 0",
            action="wait for Phase 1 which adds click/fill/type/scroll/hover",
        )

    async def evaluate(self, js: str) -> Any:
        try:
            result = await self._page.evaluate(js)
        except Exception as exc:
            raise BackendError(
                error="evaluate_failed",
                hint=str(exc),
                action="check JS syntax and page context",
            ) from exc

        new_seq = self._seq_counter.increment()
        self._ring_buffer.append(
            SeqEvent(seq=new_seq, kind="evaluate", data={"js": js[:200]})
        )
        return result

    async def network(
        self, *, since: int | str = "last_action"
    ) -> list[dict[str, Any]]:
        if since == "last_action":
            since_seq = max(0, self._seq_counter.value - 1)
        else:
            since_seq = int(since)
        events = self._ring_buffer.since(since_seq)
        return [e.data for e in events if e.kind == "network"]

    async def screenshot(self, *, full_page: bool = False) -> bytes:
        return await self._page.screenshot(full_page=full_page, type="png")

    async def close(self) -> None:
        await self._browser.close()
        await self._playwright.stop()


def screenshot_to_base64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


async def launch_patchright(
    *,
    headless: bool = True,
    viewport_width: int = 1280,
    viewport_height: int = 800,
) -> PatchrightContext:
    """Launch a patchright browser and return a context."""
    try:
        from patchright.async_api import async_playwright
    except ImportError:
        from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    executable = _find_chromium()

    launch_args: dict[str, Any] = {"headless": headless, "args": ["--no-sandbox"]}
    if executable:
        launch_args["executable_path"] = executable

    try:
        browser = await pw.chromium.launch(**launch_args)
    except Exception as exc:
        await pw.stop()
        raise BackendError(
            error="browser_launch_failed",
            hint=str(exc),
            action="run 'patchright install chromium' or install system chromium",
        ) from exc

    ctx = await browser.new_context(
        viewport={"width": viewport_width, "height": viewport_height}
    )
    page = await ctx.new_page()

    seq_counter = SeqCounter()
    ring_buffer = RingBuffer()

    return PatchrightContext(
        page=page,
        browser=browser,
        playwright=pw,
        seq_counter=seq_counter,
        ring_buffer=ring_buffer,
    )
