"""Browser state data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentcloak.core.types import StealthTier

__all__ = [
    "CONTEXT_ROLES",
    "INTERACTIVE_ROLES",
    "BrowserState",
    "ElementRef",
    "PageInfo",
    "PageSnapshot",
    "TabInfo",
]

INTERACTIVE_ROLES = frozenset(
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
        # R3: expanded interactive roles
        "dialog",
        "alertdialog",
        "menu",
        "listbox",
        "tree",
        "grid",
    }
)

CONTEXT_ROLES = frozenset(
    {
        "toolbar",
        "tabpanel",
        "figure",
        "table",
        "form",
        "status",
        "alert",
        # Structural landmark roles (always show in tree for context)
        "heading",
        "banner",
        "navigation",
        "main",
        "region",
        "contentinfo",
        "complementary",
        "search",
    }
)


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
    attributes: dict[str, str] = field(
        default_factory=lambda: dict[str, str]()
    )
    depth: int = 0
    description: str = ""


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
    selector_map: dict[int, ElementRef] = field(
        default_factory=lambda: dict[int, ElementRef]()
    )
    security_warnings: list[dict[str, str | int]] = field(
        default_factory=lambda: list[dict[str, str | int]]()
    )
    total_nodes: int = 0
    total_interactive: int = 0
    truncated_at: int = 0


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
