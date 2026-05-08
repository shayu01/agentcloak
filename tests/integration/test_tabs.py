"""Scenario C: multi-tab workflow — new, switch, close, auto-create."""

from __future__ import annotations

from typing import Any


async def test_tab_new_and_list(browser_context: Any, local_server: str) -> None:
    """Create a new tab and verify it appears in the list."""
    await browser_context.navigate(f"{local_server}/index.html")
    initial_tabs = await browser_context.tab_list()
    initial_count = len(initial_tabs)

    result = await browser_context.tab_new(f"{local_server}/form.html")
    assert "tab_id" in result

    tabs = await browser_context.tab_list()
    assert len(tabs) == initial_count + 1


async def test_tab_switch(browser_context: Any, local_server: str) -> None:
    """Switch between tabs and verify active changes."""
    await browser_context.navigate(f"{local_server}/index.html")
    tabs_before = await browser_context.tab_list()

    new_tab = await browser_context.tab_new(f"{local_server}/form.html")
    new_id = new_tab["tab_id"]

    # Find the original tab
    original_id = None
    for t in tabs_before:
        if t.active:
            original_id = t.tab_id
            break

    if original_id is not None:
        result = await browser_context.tab_switch(original_id)
        assert result["tab_id"] == original_id

    # Switch back to new tab
    result = await browser_context.tab_switch(new_id)
    assert result["tab_id"] == new_id

    # Cleanup: close the new tab
    await browser_context.tab_close(new_id)


async def test_tab_close(browser_context: Any, local_server: str) -> None:
    """Close a tab and verify it's removed from the list."""
    await browser_context.navigate(f"{local_server}/index.html")

    new_tab = await browser_context.tab_new(f"{local_server}/links.html")
    new_id = new_tab["tab_id"]

    tabs_before = await browser_context.tab_list()
    count_before = len(tabs_before)

    result = await browser_context.tab_close(new_id)
    assert result["closed"] == new_id

    tabs_after = await browser_context.tab_list()
    assert len(tabs_after) == count_before - 1


async def test_tab_close_last_auto_creates(
    fresh_context: Any, local_server: str
) -> None:
    """Closing the last tab should auto-create a blank one."""
    await fresh_context.navigate(f"{local_server}/index.html")
    tabs = await fresh_context.tab_list()
    assert len(tabs) == 1

    only_id = tabs[0].tab_id
    result = await fresh_context.tab_close(only_id)
    assert result["closed"] == only_id
    assert "auto_created" in result

    new_tabs = await fresh_context.tab_list()
    assert len(new_tabs) == 1
    assert new_tabs[0].tab_id == result["auto_created"]
