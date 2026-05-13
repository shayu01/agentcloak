"""PlaywrightContext — browser backend using standard Playwright."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import shutil
import socket
from datetime import UTC
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog

from agentcloak.browser.state import (
    INTERACTIVE_ROLES,
    ElementRef,
    PageSnapshot,
    TabInfo,
)
from agentcloak.core.capture import CaptureEntry, CaptureStore
from agentcloak.core.errors import (
    BackendError,
    BrowserTimeoutError,
    ElementNotFoundError,
    NavigationError,
)
from agentcloak.core.seq import RingBuffer, SeqCounter, SeqEvent
from agentcloak.core.types import StealthTier

__all__ = ["PlaywrightContext"]

logger = structlog.get_logger()

_INTERACTIVE_ROLES = INTERACTIVE_ROLES


_SKIP_ROLES = frozenset({"none", "InlineTextBox", "LineBreak"})

_HEADING_ROLES = frozenset({"heading", "banner", "navigation", "main", "region"})

_SNAP_CHROMIUM = "/snap/chromium/current/usr/lib/chromium-browser/chrome"


def _find_free_port() -> int:
    """Bind to port 0 and return the OS-assigned free port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


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


class PlaywrightContext:
    """BrowserContext implementation backed by Playwright."""

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
        capture_store: CaptureStore | None = None,
        cdp_port: int | None = None,
    ) -> None:
        # Multi-tab state: map tab_id -> Page, initial page is tab 0
        self._tabs: dict[int, Any] = {0: page}
        self._active_tab: int = 0
        self._next_tab_id: int = 1
        self._browser = browser
        self._playwright = playwright
        self._seq_counter = seq_counter
        self._ring_buffer = ring_buffer
        self._browser_context = browser_context
        self._proxy_url = proxy_url
        self._capture_store = capture_store or CaptureStore()
        self._backend_node_map: dict[int, int] = {}
        self._selector_map: dict[int, ElementRef] = {}
        self._pending_captures: set[asyncio.Task[None]] = set()
        self._cdp_port: int | None = cdp_port
        self._setup_network_listeners(page)

    @property
    def _page(self) -> Any:
        """Return the active tab's Page object."""
        return self._tabs[self._active_tab]

    def _setup_network_listeners(self, page: Any | None = None) -> None:
        target = page if page is not None else self._page
        target.on("response", self._on_response)

    @property
    def capture_store(self) -> CaptureStore:
        return self._capture_store

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
            if self._capture_store.recording:
                task = asyncio.ensure_future(
                    self._record_capture_async(request, response)
                )
                self._pending_captures.add(task)
                task.add_done_callback(self._pending_captures.discard)
        except Exception:
            logger.debug("on_response_error", exc_info=True)

    async def _record_capture_async(self, request: Any, response: Any) -> None:
        try:
            from datetime import datetime

            from agentcloak.core.capture import _is_recordable_content, truncate_body

            req_headers: dict[str, str] = {}
            try:
                for k, v in request.headers.items():
                    req_headers[k] = v
            except Exception:
                pass

            resp_headers: dict[str, str] = {}
            try:
                for k, v in response.headers.items():
                    resp_headers[k] = v
            except Exception:
                pass

            content_type = resp_headers.get(
                "content-type", resp_headers.get("Content-Type", "")
            )

            req_body: str | None = None
            try:
                if request.method in ("POST", "PUT", "PATCH"):
                    req_body = request.post_data
            except Exception:
                pass

            resp_body: str | None = None
            if _is_recordable_content(content_type):
                try:
                    raw = await response.body()
                    resp_body = truncate_body(raw.decode("utf-8", errors="replace"))
                except Exception:
                    pass

            entry = CaptureEntry(
                seq=self._seq_counter.value,
                timestamp=datetime.now(UTC).isoformat(),
                method=request.method,
                url=request.url,
                status=response.status,
                resource_type=request.resource_type,
                request_headers=req_headers,
                response_headers=resp_headers,
                request_body=req_body,
                response_body=resp_body,
                content_type=content_type,
                duration_ms=0.0,
            )
            self._capture_store.add(entry)
        except Exception:
            pass

    @property
    def seq(self) -> int:
        return self._seq_counter.value

    @property
    def stealth_tier(self) -> StealthTier:
        return StealthTier.PLAYWRIGHT

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
        if mode == "compact":
            return await self._snapshot_compact()
        if mode == "dom":
            return await self._snapshot_dom()
        if mode == "content":
            return await self._snapshot_content()
        raise BackendError(
            error="invalid_snapshot_mode",
            hint=f"Unknown mode: {mode}",
            action="use one of: accessible, compact, dom, content",
        )

    async def _get_ax_tree(self) -> list[dict[str, Any]]:
        """Fetch the full accessibility tree via CDP."""
        cdp = await self._page.context.new_cdp_session(self._page)
        try:
            tree = await cdp.send("Accessibility.getFullAXTree")
        finally:
            await cdp.detach()
        return tree.get("nodes", [])

    async def _snapshot_accessible(self) -> PageSnapshot:
        nodes = await self._get_ax_tree()
        selector_map: dict[int, ElementRef] = {}
        backend_node_map: dict[int, int] = {}
        lines: list[str] = []
        counter = 1

        for node in nodes:
            role = node.get("role", {}).get("value", "")
            name = node.get("name", {}).get("value", "")
            if not role or role in _SKIP_ROLES:
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
        self._selector_map = selector_map

        return PageSnapshot(
            seq=self._seq_counter.value,
            url=self._page.url,
            title=await self._page.title(),
            mode="accessible",
            tree_text="\n".join(lines),
            selector_map=selector_map,
        )

    async def _snapshot_compact(self) -> PageSnapshot:
        """Compact snapshot: only interactive [N] elements + headings."""
        nodes = await self._get_ax_tree()
        selector_map: dict[int, ElementRef] = {}
        backend_node_map: dict[int, int] = {}
        lines: list[str] = []
        counter = 1

        for node in nodes:
            role = node.get("role", {}).get("value", "")
            name = node.get("name", {}).get("value", "")
            if not role or role in _SKIP_ROLES:
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
            elif role.lower() in _HEADING_ROLES and name:
                lines.append(f"{role}: {name}")

        self._backend_node_map = backend_node_map
        self._selector_map = selector_map

        return PageSnapshot(
            seq=self._seq_counter.value,
            url=self._page.url,
            title=await self._page.title(),
            mode="compact",
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
        """Resolve a selector_map index to a Playwright ElementHandle.

        Uses backendDOMNodeId from the last snapshot for exact matching.
        Falls back to role+name locator if CDP resolve fails.
        """
        if not self._selector_map:
            raise ElementNotFoundError(
                error="no_snapshot",
                hint="No snapshot taken yet — selector_map is empty",
                action="run 'snapshot' first to populate the selector_map",
            )
        if index not in self._selector_map:
            count = len(self._selector_map)
            raise ElementNotFoundError(
                error="element_not_found",
                hint=f"Index [{index}] not in selector_map ({count} entries)",
                action="run 'snapshot' to refresh the "
                "selector_map, then retry with a valid index",
            )

        backend_node_id = self._backend_node_map.get(index)
        if backend_node_id is not None:
            try:
                return await self._resolve_by_backend_node(backend_node_id, index)
            except Exception as exc:
                logger.debug(
                    "cdp_resolve_fallback",
                    index=index,
                    backend_node_id=backend_node_id,
                    error=str(exc),
                )

        return await self._resolve_by_role(index)

    async def _resolve_by_backend_node(
        self, backend_node_id: int, index: int
    ) -> Any:
        """Resolve via CDP backendDOMNodeId — exact match, no re-snapshot."""
        marker = f"__cloak_{index}"
        cdp = await self._page.context.new_cdp_session(self._page)
        try:
            result = await cdp.send(
                "DOM.resolveNode", {"backendNodeId": backend_node_id}
            )
            object_id = result["object"]["objectId"]
            await cdp.send(
                "Runtime.callFunctionOn",
                {
                    "objectId": object_id,
                    "functionDeclaration": "function() {"
                    f" this.setAttribute('data-cloak-ref','{marker}');"
                    " }",
                },
            )
        finally:
            await cdp.detach()
        locator = self._page.locator(f'[data-cloak-ref="{marker}"]')
        if await locator.count() == 0:
            raise BackendError(
                error="element_resolve_failed",
                hint=f"CDP resolved [{index}] but locator found nothing",
                action="the element may have been removed — run 'snapshot' to refresh",
            )
        return locator.first

    async def _resolve_by_role(self, index: int) -> Any:
        """Fallback: resolve via role + name from cached selector_map."""
        ref = self._selector_map[index]
        role_name = ref.role.lower()

        if ref.text:
            locator = self._page.get_by_role(role_name, name=ref.text, exact=False)
            try:
                count = await locator.count()
                if count > 0:
                    if count > 1:
                        logger.debug(
                            "role_resolve_ambiguous",
                            index=index,
                            role=role_name,
                            name=ref.text,
                            matches=count,
                        )
                    return locator.first
            except Exception as exc:
                logger.debug(
                    "role_name_resolve_failed",
                    index=index,
                    role=role_name,
                    name=ref.text,
                    error=str(exc),
                )

        locator = self._page.get_by_role(role_name)
        try:
            count = await locator.count()
            if count > 0:
                logger.debug(
                    "role_only_resolve",
                    index=index,
                    role=role_name,
                    matches=count,
                )
                return locator.first
        except Exception as exc:
            logger.debug(
                "role_only_resolve_failed",
                index=index,
                role=role_name,
                error=str(exc),
            )

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

        with contextlib.suppress(Exception):
            await self._page.wait_for_load_state("domcontentloaded", timeout=800)
        with contextlib.suppress(Exception):
            await self._page.evaluate(
                "document.querySelectorAll('[data-cloak-ref]')"
                ".forEach(e=>e.removeAttribute('data-cloak-ref'))"
            )

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
                hint="click requires a target element",
                action="provide 'target' as '[N]' ref from snapshot, or use (x, y) coordinates",
            )

        element = await self._resolve_element(index)
        await element.click(button=button, click_count=int(click_count))
        ref = self._get_ref(index)
        return {"clicked": True, "index": index, "element": ref}

    async def _action_fill(self, target: str, **kw: Any) -> dict[str, Any]:
        if not target:
            raise ElementNotFoundError(
                error="element_not_found",
                hint="fill requires a target element",
                action="provide 'target' as '[N]' ref from snapshot",
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
                hint="type requires a target element",
                action="provide 'target' as '[N]' ref from snapshot",
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
                hint="hover requires a target element",
                action="provide 'target' as '[N]' ref from snapshot, or use (x, y) coordinates",
            )

        element = await self._resolve_element(index)
        await element.hover()
        ref = self._get_ref(index)
        return {"hovered": True, "index": index, "element": ref}

    async def _action_select(self, target: str, **kw: Any) -> dict[str, Any]:
        if not target:
            raise ElementNotFoundError(
                error="element_not_found",
                hint="select requires a target element",
                action="provide 'target' as '[N]' ref from snapshot",
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
                hint="select requires 'value' or 'label' parameter",
                action="provide 'value' (option value) or 'label' (visible text)",
            )

        ref = self._get_ref(index)
        return {
            "selected": True,
            "index": index,
            "value": value,
            "label": label,
            "element": ref,
        }

    async def _action_press(self, target: str, **kw: Any) -> dict[str, Any]:
        key = kw.get("key", "")
        if not key:
            raise BackendError(
                error="press_missing_key",
                hint="press requires 'key' parameter",
                action="provide 'key' (e.g. 'Enter', 'Tab', 'Escape', 'ArrowDown')",
            )
        if target:
            index = int(target)
            element = await self._resolve_element(index)
            await element.press(str(key))
            ref = self._get_ref(index)
            return {"pressed": True, "key": key, "index": index, "element": ref}
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

    async def evaluate(self, js: str, *, world: str = "main") -> Any:
        if world == "main":
            result = await self._evaluate_main_world(js)
        else:
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

    async def _evaluate_main_world(self, js: str) -> Any:
        """Evaluate JS in the page's main execution context via CDP.

        The CDP session created by Playwright defaults to Playwright's utility
        world, not the page's main world.  We call Runtime.enable to discover
        execution contexts, pick the one with auxData.isDefault == True (the
        page's main world), and pass its contextId to Runtime.evaluate.
        """
        cdp = await self._page.context.new_cdp_session(self._page)
        try:
            # Collect execution contexts reported by Runtime.enable.
            contexts: list[dict[str, Any]] = []

            def _on_ctx(params: dict[str, Any]) -> None:
                contexts.append(params["context"])

            cdp.on("Runtime.executionContextCreated", _on_ctx)
            await cdp.send("Runtime.enable")

            # Find the page's main world (isDefault == True).
            main_ctx_id: int | None = None
            for ec in contexts:
                aux: dict[str, Any] = ec.get("auxData", {})
                if aux.get("isDefault") is True:
                    main_ctx_id = ec["id"]
                    break

            if main_ctx_id is None:
                raise BackendError(
                    error="evaluate_failed",
                    hint="could not find main world execution context",
                    action="ensure page is loaded before evaluating",
                )

            resp = await cdp.send(
                "Runtime.evaluate",
                {
                    "expression": js,
                    "contextId": main_ctx_id,
                    "returnByValue": True,
                    "awaitPromise": True,
                    "userGesture": True,
                },
            )
        except BackendError:
            raise
        except Exception as exc:
            raise BackendError(
                error="evaluate_failed",
                hint=str(exc),
                action="check JS syntax and page context",
            ) from exc
        finally:
            with contextlib.suppress(Exception):
                await cdp.send("Runtime.disable")
            await cdp.detach()

        if "exceptionDetails" in resp:
            desc = resp["exceptionDetails"].get("text", "JS exception")
            raise BackendError(
                error="evaluate_failed",
                hint=desc,
                action="check JS syntax and page context",
            )

        result_obj = resp.get("result", {})
        if result_obj.get("type") == "undefined":
            return None
        return result_obj.get("value")

    async def network(
        self, *, since: int | str = "last_action"
    ) -> list[dict[str, Any]]:
        if since == "last_action":
            since_seq = self._seq_counter.last_action_seq
        else:
            since_seq = int(since)
        events = self._ring_buffer.since(since_seq)
        return [e.data for e in events if e.kind == "network"]

    async def screenshot(
        self,
        *,
        full_page: bool = False,
        format: str = "jpeg",
        quality: int = 80,
    ) -> bytes:
        kwargs: dict[str, Any] = {"full_page": full_page, "type": format}
        if format == "jpeg":
            kwargs["quality"] = quality
        return await self._page.screenshot(**kwargs)

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
                action="retry with a larger 'timeout' value, or check the URL",
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

        _useful_headers = {
            "content-type", "content-length", "content-encoding",
            "set-cookie", "location", "cache-control",
            "x-ratelimit-remaining", "x-ratelimit-limit",
            "retry-after", "www-authenticate",
        }
        filtered_headers = {
            k: v for k, v in resp.headers.items()
            if k.lower() in _useful_headers
        }

        parsed_body: Any = resp_body
        if body_encoding == "text" and "json" in content_type:
            import contextlib
            import json as _json
            with contextlib.suppress(Exception):
                parsed_body = _json.loads(resp_body if isinstance(resp_body, str) else resp.text)

        return {
            "status": resp.status_code,
            "headers": filtered_headers,
            "body": parsed_body,
            "body_encoding": body_encoding,
            "truncated": truncated,
            "content_type": content_type,
            "cookies_used": cookies_used,
            "url": str(resp.url),
        }

    def _get_browser_context(self) -> Any:
        """Return the Playwright BrowserContext, whether persistent or ephemeral."""
        if self._browser_context is not None:
            return self._browser_context
        # Ephemeral mode: get context from the active page
        return self._page.context

    async def tab_list(self) -> list[TabInfo]:
        """Return metadata for all open tabs."""
        result: list[TabInfo] = []
        for tid, page in self._tabs.items():
            try:
                url = page.url
            except Exception:
                url = ""
            try:
                title = await page.title()
            except Exception:
                title = ""
            result.append(
                TabInfo(
                    tab_id=tid,
                    url=url,
                    title=title,
                    active=(tid == self._active_tab),
                )
            )
        return result

    async def tab_new(self, url: str | None = None) -> dict[str, Any]:
        """Create a new tab, optionally navigating to a URL."""
        pw_ctx = self._get_browser_context()
        new_page = await pw_ctx.new_page()
        new_id = self._next_tab_id
        self._next_tab_id += 1
        self._tabs[new_id] = new_page
        self._active_tab = new_id
        self._setup_network_listeners(new_page)

        result: dict[str, Any] = {"tab_id": new_id}
        if url:
            nav = await self.navigate(url)
            result["url"] = nav.get("url", url)
            result["title"] = nav.get("title", "")
        else:
            result["url"] = new_page.url
            try:
                result["title"] = await new_page.title()
            except Exception:
                result["title"] = ""
        return result

    async def tab_close(self, tab_id: int) -> dict[str, Any]:
        """Close a tab by ID. Auto-creates blank tab if closing the last one."""
        if tab_id not in self._tabs:
            raise ElementNotFoundError(
                error="tab_not_found",
                hint=(
                    f"Tab {tab_id} does not exist"
                    f" (open tabs: {sorted(self._tabs.keys())})"
                ),
                action="use 'tab list' to see available tab IDs",
            )
        page = self._tabs.pop(tab_id)
        # Grab browser context BEFORE closing (ephemeral needs page.context)
        if self._browser_context is not None:
            pw_ctx = self._browser_context
        else:
            pw_ctx = page.context
        await page.close()

        if not self._tabs:
            # Auto-create blank tab so daemon always has an operable page
            new_page = await pw_ctx.new_page()
            new_id = self._next_tab_id
            self._next_tab_id += 1
            self._tabs[new_id] = new_page
            self._active_tab = new_id
            self._setup_network_listeners(new_page)
            return {"closed": tab_id, "auto_created": new_id}

        if self._active_tab == tab_id:
            # Switch to the most recent remaining tab
            self._active_tab = max(self._tabs.keys())

        return {"closed": tab_id}

    async def tab_switch(self, tab_id: int) -> dict[str, Any]:
        """Switch the active tab."""
        if tab_id not in self._tabs:
            raise ElementNotFoundError(
                error="tab_not_found",
                hint=(
                    f"Tab {tab_id} does not exist"
                    f" (open tabs: {sorted(self._tabs.keys())})"
                ),
                action="use 'tab list' to see available tab IDs",
            )
        self._active_tab = tab_id
        page = self._tabs[tab_id]
        try:
            url = page.url
        except Exception:
            url = ""
        try:
            title = await page.title()
        except Exception:
            title = ""
        return {"tab_id": tab_id, "url": url, "title": title}

    async def raw_cdp(
        self, method: str, params: dict[str, Any] | None = None
    ) -> Any:
        cdp = await self._page.context.new_cdp_session(self._page)
        try:
            return await cdp.send(method, params or {})
        except Exception as exc:
            raise BackendError(
                error="cdp_call_failed",
                hint=f"{method}: {exc}",
                action="check CDP method name and parameters",
            ) from exc
        finally:
            await cdp.detach()

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
        elif self._browser_context is not None:
            await self._browser_context.close()
        if self._playwright is not None:
            await self._playwright.stop()


def screenshot_to_base64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


async def launch_playwright(
    *,
    headless: bool = True,
    viewport_width: int = 1280,
    viewport_height: int = 800,
    profile_dir: Path | None = None,
    proxy_url: str | None = None,
) -> PlaywrightContext:
    """Launch a Playwright browser and return a context."""
    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    executable = _find_chromium()

    # Allocate a free port for CDP; Chrome 90+ supports pipe+port coexistence.
    cdp_port = _find_free_port()
    chrome_args = ["--no-sandbox", f"--remote-debugging-port={cdp_port}"]

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
                action="run 'playwright install chromium' or install system chromium",
            ) from exc

        pages = browser_context.pages
        page = pages[0] if pages else await browser_context.new_page()

        seq_counter = SeqCounter()
        ring_buffer = RingBuffer()

        return PlaywrightContext(
            page=page,
            browser=None,
            playwright=pw,
            seq_counter=seq_counter,
            ring_buffer=ring_buffer,
            browser_context=browser_context,
            proxy_url=proxy_url,
            cdp_port=cdp_port,
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
            action="run 'playwright install chromium' or install system chromium",
        ) from exc

    ctx = await browser.new_context(
        viewport={"width": viewport_width, "height": viewport_height}
    )
    page = await ctx.new_page()

    seq_counter = SeqCounter()
    ring_buffer = RingBuffer()

    return PlaywrightContext(
        page=page,
        browser=browser,
        playwright=pw,
        seq_counter=seq_counter,
        ring_buffer=ring_buffer,
        proxy_url=proxy_url,
        cdp_port=cdp_port,
    )
