"""PatchrightContext — default browser backend using patchright (Playwright fork)."""

from __future__ import annotations

import asyncio
import base64
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from browserctl.browser.state import ElementRef, PageSnapshot
from browserctl.core.errors import (
    BackendError,
    BrowserTimeoutError,
    ElementNotFoundError,
    NavigationError,
)
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
        browser: Any | None,
        playwright: Any,
        seq_counter: SeqCounter,
        ring_buffer: RingBuffer,
        browser_context: Any | None = None,
        proxy_url: str | None = None,
    ) -> None:
        self._page = page
        self._browser = browser
        self._playwright = playwright
        self._seq_counter = seq_counter
        self._ring_buffer = ring_buffer
        self._browser_context = browser_context
        self._proxy_url = proxy_url
        self._backend_node_map: dict[int, int] = {}
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

        new_seq = self._seq_counter.increment_action()
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
        backend_node_map: dict[int, int] = {}
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
                backend_dom_id = node.get("backendDOMNodeId")
                if backend_dom_id is not None:
                    backend_node_map[counter] = int(backend_dom_id)
                lines.append(f"[{counter}] <{role}> {name}")
                counter += 1
            elif name:
                lines.append(f"{role}: {name}")

        self._backend_node_map = backend_node_map

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

    async def _resolve_element(self, index: int) -> Any:
        """Resolve a selector_map index to a Playwright Locator."""
        snap = await self.snapshot(mode="accessible")
        if index not in snap.selector_map:
            count = len(snap.selector_map)
            raise ElementNotFoundError(
                error="element_not_found",
                hint=f"Index [{index}] not in selector_map ({count} entries)",
                action="run 'snapshot' to refresh the "
                "selector_map, then retry with a valid index",
            )

        ref = snap.selector_map[index]
        role_name = ref.role.lower()

        # Primary: role + name (exact match for the AX tree entry)
        if ref.text:
            locator = self._page.get_by_role(role_name, name=ref.text, exact=False)
            try:
                if await locator.count() > 0:
                    return locator.first
            except Exception:
                pass

        # Fallback: role only (less precise but still valid)
        locator = self._page.get_by_role(role_name)
        try:
            if await locator.count() > 0:
                return locator.first
        except Exception:
            pass

        raise BackendError(
            error="element_resolve_failed",
            hint=f"Could not resolve [{index}] <{ref.role}> '{ref.text}' in the DOM",
            action="the page may have changed — run 'snapshot' to refresh, then retry",
        )

    async def action(self, kind: str, target: str, **kw: Any) -> dict[str, Any]:
        pre_url = self._page.url
        valid_kinds = {"click", "fill", "type", "scroll", "hover", "select", "press"}
        if kind not in valid_kinds:
            raise BackendError(
                error="invalid_action_kind",
                hint=f"Unknown action kind: '{kind}'",
                action=f"use one of: {', '.join(sorted(valid_kinds))}",
            )

        handler = {
            "click": self._action_click,
            "fill": self._action_fill,
            "type": self._action_type,
            "scroll": self._action_scroll,
            "hover": self._action_hover,
            "select": self._action_select,
            "press": self._action_press,
        }[kind]

        result = await handler(target, **kw)

        post_url = self._page.url
        caused_navigation = post_url != pre_url

        new_seq = self._seq_counter.increment_action()
        self._ring_buffer.append(
            SeqEvent(
                seq=new_seq,
                kind="action",
                data={"action": kind, "target": target, **kw},
            )
        )

        result["ok"] = True
        result["seq"] = new_seq
        result["action"] = kind
        result["caused_navigation"] = caused_navigation
        if caused_navigation:
            result["new_url"] = post_url
        return result

    async def _action_click(self, target: str, **kw: Any) -> dict[str, Any]:
        x = kw.get("x")
        y = kw.get("y")
        button = kw.get("button", "left")
        click_count = kw.get("click_count", 1)

        if x is not None and y is not None:
            await self._page.mouse.click(
                float(x), float(y), button=button, click_count=int(click_count)
            )
            return {"clicked": True, "x": x, "y": y}

        index = int(target) if target else None
        if index is None:
            raise ElementNotFoundError(
                error="element_not_found",
                hint="click requires --index N or --x/--y coordinates",
                action="provide an element index or coordinate pair",
            )

        element = await self._resolve_element(index)
        await element.click(button=button, click_count=int(click_count))
        ref = self._get_ref(index)
        return {"clicked": True, "index": index, "element": ref}

    async def _action_fill(self, target: str, **kw: Any) -> dict[str, Any]:
        if not target:
            raise ElementNotFoundError(
                error="element_not_found",
                hint="fill requires --index N",
                action="provide an element index from the selector_map",
            )
        index = int(target)
        text = kw.get("text", "")
        element = await self._resolve_element(index)
        await element.fill(str(text))
        ref = self._get_ref(index)
        return {"filled": True, "index": index, "text": text, "element": ref}

    async def _action_type(self, target: str, **kw: Any) -> dict[str, Any]:
        if not target:
            raise ElementNotFoundError(
                error="element_not_found",
                hint="type requires --index N",
                action="provide an element index from the selector_map",
            )
        index = int(target)
        text = kw.get("text", "")
        delay = kw.get("delay", 0)
        element = await self._resolve_element(index)
        await element.press_sequentially(str(text), delay=float(delay))
        ref = self._get_ref(index)
        return {"typed": True, "index": index, "text": text, "element": ref}

    async def _action_scroll(self, target: str, **kw: Any) -> dict[str, Any]:
        direction = kw.get("direction", "down")
        amount = int(kw.get("amount", 300))

        delta_x, delta_y = 0, 0
        if direction == "down":
            delta_y = amount
        elif direction == "up":
            delta_y = -amount
        elif direction == "right":
            delta_x = amount
        elif direction == "left":
            delta_x = -amount

        if target:
            index = int(target)
            element = await self._resolve_element(index)
            await element.scroll_into_view_if_needed()
            return {"scrolled": True, "index": index, "direction": direction}

        await self._page.mouse.wheel(delta_x, delta_y)
        return {"scrolled": True, "direction": direction, "amount": amount}

    async def _action_hover(self, target: str, **kw: Any) -> dict[str, Any]:
        x = kw.get("x")
        y = kw.get("y")

        if x is not None and y is not None:
            await self._page.mouse.move(float(x), float(y))
            return {"hovered": True, "x": x, "y": y}

        index = int(target) if target else None
        if index is None:
            raise ElementNotFoundError(
                error="element_not_found",
                hint="hover requires --index N or --x/--y coordinates",
                action="provide an element index or coordinate pair",
            )

        element = await self._resolve_element(index)
        await element.hover()
        ref = self._get_ref(index)
        return {"hovered": True, "index": index, "element": ref}

    async def _action_select(self, target: str, **kw: Any) -> dict[str, Any]:
        if not target:
            raise ElementNotFoundError(
                error="element_not_found",
                hint="select requires --index N",
                action="provide an element index from the selector_map",
            )
        index = int(target)
        value = kw.get("value")
        label = kw.get("label")
        element = await self._resolve_element(index)

        if value is not None:
            await element.select_option(value=str(value))
        elif label is not None:
            await element.select_option(label=str(label))
        else:
            raise BackendError(
                error="select_missing_option",
                hint="select requires --value or --label",
                action="provide --value 'option_value' or --label 'Option Text'",
            )

        ref = self._get_ref(index)
        return {
            "selected": True,
            "index": index,
            "value": value,
            "label": label,
            "element": ref,
        }

    async def _action_press(self, _target: str, **kw: Any) -> dict[str, Any]:
        key = kw.get("key", "")
        if not key:
            raise BackendError(
                error="press_missing_key",
                hint="press requires --key argument",
                action="provide --key 'Enter', --key 'Escape', etc.",
            )
        await self._page.keyboard.press(str(key))
        return {"pressed": True, "key": key}

    def _get_ref(self, index: int) -> str:
        """Return a human-readable ref string for an element index."""
        return f"[{index}]"

    async def action_batch(
        self,
        actions: list[dict[str, Any]],
        *,
        sleep: float = 0.0,
    ) -> dict[str, Any]:
        """Execute a batch of actions, aborting on URL change."""
        results: list[dict[str, Any]] = []
        total = len(actions)

        if total == 0:
            return {"results": [], "completed": 0, "total": 0}

        for i, act in enumerate(actions):
            kind = act.get("kind", act.get("action", ""))
            index = act.get("index")
            target = str(index) if index is not None else act.get("target", "")
            extra = {
                k: v
                for k, v in act.items()
                if k not in ("kind", "action", "index", "target")
            }

            result = await self.action(str(kind), str(target), **extra)
            results.append(result)

            if result.get("caused_navigation"):
                return {
                    "results": results,
                    "completed": i + 1,
                    "total": total,
                    "aborted_reason": "url_changed",
                }

            if sleep > 0 and i < total - 1:
                await asyncio.sleep(sleep)

        return {"results": results, "completed": total, "total": total}

    async def evaluate(self, js: str) -> Any:
        try:
            result = await self._page.evaluate(js)
        except Exception as exc:
            raise BackendError(
                error="evaluate_failed",
                hint=str(exc),
                action="check JS syntax and page context",
            ) from exc

        new_seq = self._seq_counter.increment_action()
        self._ring_buffer.append(
            SeqEvent(seq=new_seq, kind="evaluate", data={"js": js[:200]})
        )
        return result

    async def network(
        self, *, since: int | str = "last_action"
    ) -> list[dict[str, Any]]:
        if since == "last_action":
            since_seq = self._seq_counter.last_action_seq
        else:
            since_seq = int(since)
        events = self._ring_buffer.since(since_seq)
        return [e.data for e in events if e.kind == "network"]

    async def screenshot(self, *, full_page: bool = False) -> bytes:
        return await self._page.screenshot(full_page=full_page, type="png")

    async def fetch(
        self,
        url: str,
        *,
        method: str = "GET",
        body: str | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """HTTP fetch using browser cookies and user agent."""
        context = self._page.context

        # Extract cookies from the browser context
        cookies_raw: list[dict[str, Any]] = await context.cookies()
        cookie_jar = httpx.Cookies()
        for c in cookies_raw:
            cookie_jar.set(
                c["name"],
                c["value"],
                domain=c.get("domain", ""),
                path=c.get("path", "/"),
            )

        # Extract user agent from the page
        ua: str = await self._page.evaluate("navigator.userAgent")

        # Build headers: UA first, then any user-provided overrides
        req_headers: dict[str, str] = {"User-Agent": ua}
        if headers:
            req_headers.update(headers)

        # Make the request (route through LocalProxy when available)
        client_kwargs: dict[str, Any] = {
            "cookies": cookie_jar,
            "timeout": httpx.Timeout(timeout),
            "follow_redirects": True,
        }
        if self._proxy_url:
            client_kwargs["proxy"] = self._proxy_url

        try:
            async with httpx.AsyncClient(**client_kwargs) as client:
                resp = await client.request(
                    method.upper(),
                    url,
                    headers=req_headers,
                    content=body.encode("utf-8") if body else None,
                )
        except httpx.TimeoutException as exc:
            raise BrowserTimeoutError(
                error="fetch_timeout",
                hint=f"HTTP request to {url} timed out after {timeout}s",
                action="retry with a longer --timeout or check the URL",
            ) from exc
        except httpx.RequestError as exc:
            raise BackendError(
                error="fetch_request_failed",
                hint=f"Request to {url} failed: {exc}",
                action="check URL and network connectivity",
            ) from exc

        # Determine if response is text or binary
        content_type = resp.headers.get("content-type", "")
        is_binary = not (
            "text/" in content_type
            or "json" in content_type
            or "xml" in content_type
            or "javascript" in content_type
            or "html" in content_type
        )

        max_body = 100_000
        if is_binary:
            raw = resp.content
            if len(raw) > max_body:
                resp_body = base64.b64encode(raw[:max_body]).decode("ascii")
                truncated = True
            else:
                resp_body = base64.b64encode(raw).decode("ascii")
                truncated = False
            body_encoding = "base64"
        else:
            resp_body = resp.text
            truncated = len(resp_body) > max_body
            if truncated:
                resp_body = resp_body[:max_body] + "\n[...truncated...]"
            body_encoding = "text"

        # Count how many cookies were sent
        parsed = urlparse(url)
        cookies_used = [
            c["name"]
            for c in cookies_raw
            if parsed.hostname
            and (
                parsed.hostname == c.get("domain", "")
                or parsed.hostname.endswith(c.get("domain", ""))
            )
        ]

        new_seq = self._seq_counter.increment_action()
        self._ring_buffer.append(
            SeqEvent(
                seq=new_seq,
                kind="fetch",
                data={"method": method.upper(), "url": url, "status": resp.status_code},
            )
        )

        return {
            "status": resp.status_code,
            "headers": dict(resp.headers),
            "body": resp_body,
            "body_encoding": body_encoding,
            "truncated": truncated,
            "content_type": content_type,
            "cookies_used": cookies_used,
            "url": str(resp.url),
        }

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
        elif self._browser_context is not None:
            await self._browser_context.close()
        if self._playwright is not None:
            await self._playwright.stop()


def screenshot_to_base64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


async def launch_patchright(
    *,
    headless: bool = True,
    viewport_width: int = 1280,
    viewport_height: int = 800,
    profile_dir: Path | None = None,
    proxy_url: str | None = None,
) -> PatchrightContext:
    """Launch a patchright browser and return a context."""
    try:
        from patchright.async_api import async_playwright
    except ImportError:
        from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    executable = _find_chromium()

    chrome_args = ["--no-sandbox"]

    if profile_dir is not None:
        # Persistent context: cookies/localStorage/etc. persist to disk
        launch_kwargs: dict[str, Any] = {
            "headless": headless,
            "args": chrome_args,
            "viewport": {"width": viewport_width, "height": viewport_height},
        }
        if executable:
            launch_kwargs["executable_path"] = executable

        try:
            browser_context = await pw.chromium.launch_persistent_context(
                str(profile_dir),
                **launch_kwargs,
            )
        except Exception as exc:
            await pw.stop()
            raise BackendError(
                error="browser_launch_failed",
                hint=str(exc),
                action="run 'patchright install chromium' or install system chromium",
            ) from exc

        pages = browser_context.pages
        page = pages[0] if pages else await browser_context.new_page()

        seq_counter = SeqCounter()
        ring_buffer = RingBuffer()

        return PatchrightContext(
            page=page,
            browser=None,
            playwright=pw,
            seq_counter=seq_counter,
            ring_buffer=ring_buffer,
            browser_context=browser_context,
            proxy_url=proxy_url,
        )

    # Ephemeral context: no persistent state
    launch_args: dict[str, Any] = {"headless": headless, "args": chrome_args}
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
        proxy_url=proxy_url,
    )
