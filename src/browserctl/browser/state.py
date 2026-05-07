"""Browser state data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from browserctl.core.types import StealthTier

__all__ = ["BrowserState", "ElementRef", "PageInfo", "PageSnapshot", "TabInfo"]


@dataclass(frozen=True)
class TabInfo:
    """Metadata for an open browser tab."""

    tab_id: int
    url: str
    title: str
    active: bool


@dataclass(frozen=True)
class ElementRef:
    """A reference to an interactive element in the selector_map."""

    index: int
    tag: str
    role: str
    text: str
    attributes: dict[str, str] = field(default_factory=dict[str, str])


@dataclass(frozen=True)
class PageInfo:
    """Metadata about the current page."""

    url: str
    title: str
    load_state: str


@dataclass(frozen=True)
class PageSnapshot:
    """A snapshot of page state in a given mode."""

    seq: int
    url: str
    title: str
    mode: str
    tree_text: str
    selector_map: dict[int, ElementRef] = field(default_factory=dict[int, ElementRef])


@dataclass
class BrowserState:
    """Full observable state of a browser session."""

    seq: int
    url: str
    title: str
    tabs: list[TabInfo]
    selector_map: dict[int, ElementRef]
    tree_text: str
    screenshot_b64: str | None
    screenshot_size: tuple[int, int] | None
    viewport_size: tuple[int, int]
    page_info: PageInfo
    pending_network_requests: list[dict[str, object]]
    recent_events_text: str | None
    stealth_tier: StealthTier
