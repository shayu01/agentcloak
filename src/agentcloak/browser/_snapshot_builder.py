"""Shared snapshot builder — builds accessible/compact snapshots from CDP AX tree nodes.

Both PlaywrightContext and RemoteBridgeContext call build_snapshot() with raw CDP nodes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from agentcloak.browser.state import (
    CONTEXT_ROLES as _CONTEXT_ROLES,
)
from agentcloak.browser.state import (
    INTERACTIVE_ROLES as _INTERACTIVE_ROLES,
)
from agentcloak.browser.state import (
    ElementRef,
    PageSnapshot,
)

__all__ = [
    "DiffCounts",
    "FrameData",
    "SnapshotResult",
    "build_snapshot",
    "count_diff",
    "diff_snapshots",
    "render_diff_tree",
    "truncate_diff_lines",
]

# Token-budget hint: tree rendering uses 1 space per depth level rather than
# 2. Combined with compact-mode pruning this drops the byte share spent on
# leading whitespace from ~13% to ~7% on dense pages (HN front page), which
# directly translates into fewer tokens for the consuming agent. The same
# constant feeds ``render_diff_tree`` so accessible / compact / diff renderings
# stay structurally aligned — divergent indent rules would make the diff view
# look misnested next to a plain snapshot.
_INDENT_STEP = " "

_SKIP_ROLES = frozenset({"none", "InlineTextBox", "LineBreak"})

_INVISIBLE_RE = re.compile("[​‌‍⁠﻿]")

_BOOL_PROPS = frozenset(
    {
        "checked",
        "disabled",
        "expanded",
        "selected",
        "pressed",
        "invalid",
        "required",
        "focused",
        "hidden",
    }
)

_VALUE_PROPS = frozenset(
    {
        "valuemin",
        "valuemax",
        "valuenow",
        "valuetext",
        "level",
        "haspopup",
        "autocomplete",
        # link href — CDP exposes it as the "url" AX property on link nodes.
        # Surfacing it lets agents resolve targets without an extra evaluate().
        "url",
    }
)

_FALSE_MEANINGFUL = frozenset({"expanded"})

# CDP AX props with type=tristate carry string values ("true"/"false"/"mixed")
# rather than Python booleans. aria-checked + aria-pressed are spec'd as tristate
# so an indeterminate checkbox or three-state toggle uses "mixed". A naive
# `val is True` check silently drops every tristate property — including the
# common case of a freshly-clicked radio button — so we normalise here.
_TRISTATE_PROPS = frozenset({"checked", "pressed"})


@dataclass
class FrameData:
    """AX tree nodes from a child frame, with metadata for merging."""

    frame_id: str
    name: str
    url: str
    nodes: list[dict[str, Any]]


@dataclass
class SnapshotResult:
    snapshot: PageSnapshot
    selector_map: dict[int, ElementRef]
    backend_node_map: dict[int, int]
    cached_lines: list[tuple[int, str, int | None]]


@dataclass
class DiffCounts:
    """Counts of added/changed/removed lines from a :func:`diff_snapshots` call.

    The header renderer surfaces this as ``| diff: +A ~C -R`` so agents see at
    a glance how much changed without having to scan the tree. Zero counts
    across the board signal "no changes" so the header can collapse to
    ``| (no changes)``.
    """

    added: int = 0
    changed: int = 0
    removed: int = 0

    @property
    def is_empty(self) -> bool:
        return self.added == 0 and self.changed == 0 and self.removed == 0


def _clean_text(text: str) -> str:
    text = _INVISIBLE_RE.sub("", text)
    text = text.replace("\xa0", " ")
    return text.strip()


def _ax_value(obj: dict[str, Any] | None) -> Any:
    if isinstance(obj, dict):
        return obj.get("value")
    return obj


def _extract_props(node: dict[str, Any]) -> dict[str, str]:
    attrs: dict[str, str] = {}
    props: list[dict[str, Any]] = node.get("properties", [])
    is_password = False
    for prop in props:
        pname: str = prop.get("name", "")
        val: object = _ax_value(prop.get("value"))

        if pname == "autocomplete" and isinstance(val, str) and "password" in val:
            is_password = True

        if pname in _BOOL_PROPS:
            # tristate props (checked, pressed) arrive as strings per the
            # CDP/W3C spec ("true"/"false"/"mixed"), while boolean props
            # arrive as real Python bools. Accept either shape so older
            # tooling or mocks that pass True/False through tristate fields
            # still produce the same surface output.
            if pname in _TRISTATE_PROPS:
                normalised = val
                if isinstance(val, bool):
                    normalised = "true" if val else "false"
                if normalised == "true":
                    attrs[pname] = ""
                elif normalised == "mixed":
                    attrs[pname] = "mixed"
                # "false" / anything else → drop (clean default).
            else:
                if val is True:
                    attrs[pname] = ""
                elif val is False and pname in _FALSE_MEANINGFUL:
                    attrs[pname] = "false"
        elif pname in _VALUE_PROPS and val is not None:
            attrs[pname] = str(val)

    val_raw: object = _ax_value(node.get("value"))
    if val_raw is not None and str(val_raw).strip():
        if is_password:
            attrs["value"] = "••••"
        else:
            attrs["value"] = _clean_text(str(val_raw))

    desc_raw: object = _ax_value(node.get("description"))
    if desc_raw is not None and str(desc_raw).strip():
        attrs["description"] = _clean_text(str(desc_raw))

    return attrs


def _format_attrs(attrs: dict[str, str]) -> str:
    parts: list[str] = []
    if "value" in attrs:
        parts.append(f'value="{attrs["value"]}"')
    for key in (
        "checked",
        "disabled",
        "expanded",
        "selected",
        "pressed",
        "invalid",
        "required",
        "focused",
        "hidden",
    ):
        if key in attrs:
            val = attrs[key]
            if val == "":
                parts.append(key)
            else:
                parts.append(f"{key}={val}")
    for key in (
        "level",
        "haspopup",
        "valuemin",
        "valuemax",
        "valuenow",
        "valuetext",
        "description",
    ):
        if key in attrs:
            parts.append(f"{key}={attrs[key]}")
    # Link href — emit last and quoted so the URL stays readable.
    if "url" in attrs:
        parts.append(f'href="{attrs["url"]}"')
    return " ".join(parts)


def _should_fold(node: dict[str, Any], role: str, name: str) -> bool:
    if role in ("generic", "group", "none", ""):
        child_ids = node.get("childIds", [])
        if not name and len(child_ids) <= 1:
            return True
    return False


def _is_static_text_like(node: dict[str, Any]) -> bool:
    role = node.get("role", {}).get("value", "")
    return role == "StaticText"


def _extract_focus_subtree(
    lines: list[tuple[int, str, int | None]],
    target_ref: int,
) -> list[tuple[int, str, int | None]]:
    target_idx = -1
    for i, (_, _, ref) in enumerate(lines):
        if ref == target_ref:
            target_idx = i
            break
    if target_idx < 0:
        return lines

    target_depth = lines[target_idx][0]

    ancestors: list[int] = []
    search_depth = target_depth
    for i in range(target_idx - 1, -1, -1):
        if lines[i][0] < search_depth:
            ancestors.append(i)
            search_depth = lines[i][0]
            if search_depth == 0:
                break
    ancestors.reverse()

    subtree: list[int] = [target_idx]
    for i in range(target_idx + 1, len(lines)):
        if lines[i][0] > target_depth:
            subtree.append(i)
        else:
            break

    result_indices = ancestors + subtree
    return [lines[i] for i in result_indices]


def build_snapshot(
    raw_nodes: list[dict[str, Any]],
    *,
    mode: str = "accessible",
    max_nodes: int = 0,
    max_chars: int = 0,
    focus: int = 0,
    offset: int = 0,
    seq: int = 0,
    url: str = "",
    title: str = "",
    frame_trees: list[FrameData] | None = None,
) -> SnapshotResult:
    # Phase 1: index nodes by nodeId, build child lookup
    node_by_id: dict[str, dict[str, Any]] = {}
    root_ids: list[str] = []
    for raw in raw_nodes:
        nid = raw.get("nodeId", "")
        if nid:
            node_by_id[nid] = raw
    all_child_ids: set[str] = set()
    for raw in raw_nodes:
        for cid in raw.get("childIds", []):
            all_child_ids.add(cid)
    for raw in raw_nodes:
        nid = raw.get("nodeId", "")
        if nid and nid not in all_child_ids:
            root_ids.append(nid)
    if not root_ids and raw_nodes:
        root_ids = [raw_nodes[0].get("nodeId", "")]

    # Phase 2: recursive tree build with ref assignment
    selector_map: dict[int, ElementRef] = {}
    backend_node_map: dict[int, int] = {}
    counter = [1]
    compact = mode == "compact"
    # ``content`` mode walks the same AX tree as compact/accessible but emits
    # plain text only — no ``[N]`` refs, no role labels, no ARIA props. This
    # gives agents a clean "read the page as a human would" view that inherits
    # the StaticText aggregation (so inline-element boundaries get spaces
    # between words instead of running together like ``document.body.innerText``
    # does).
    content_mode = mode == "content"

    all_lines: list[tuple[int, str, int | None]] = []

    def _visit(node_id: str, depth: int) -> None:
        node = node_by_id.get(node_id)
        if node is None:
            return

        ignored = node.get("ignored", False)
        role = node.get("role", {}).get("value", "")
        name_raw = node.get("name", {}).get("value", "")
        name = _clean_text(name_raw)
        child_ids: list[str] = node.get("childIds", [])

        if role in _SKIP_ROLES or ignored:
            for cid in child_ids:
                _visit(cid, depth)
            return

        if _should_fold(node, role, name):
            for cid in child_ids:
                _visit(cid, depth)
            return

        role_lower = role.lower()
        is_interactive = role_lower in _INTERACTIVE_ROLES
        is_context = role_lower in _CONTEXT_ROLES

        if content_mode:
            # Walk the same tree as compact/accessible but record names only.
            # We still allocate refs + populate selector_map so a subsequent
            # ``action`` call against the most recent snapshot can resolve
            # elements — agents may run ``snapshot --mode content`` then
            # ``snapshot`` (compact) to switch view styles without losing the
            # ability to click.
            if is_interactive:
                ref = counter[0]
                attrs = _extract_props(node)
                selector_map[ref] = ElementRef(
                    index=ref,
                    tag=role,
                    role=role,
                    text=name,
                    attributes=attrs,
                    depth=depth,
                    description=attrs.get("description", ""),
                )
                backend_dom_id = node.get("backendDOMNodeId")
                if backend_dom_id is not None:
                    backend_node_map[ref] = int(backend_dom_id)
                if name:
                    all_lines.append((depth, name, ref))
                counter[0] += 1
            elif name:
                # Static text, context roles, anything else with a visible name
                # contributes its bare text — we deliberately drop the role
                # label so the output reads naturally.
                all_lines.append((depth, name, None))
        elif is_interactive:
            ref = counter[0]
            attrs = _extract_props(node)
            selector_map[ref] = ElementRef(
                index=ref,
                tag=role,
                role=role,
                text=name,
                attributes=attrs,
                depth=depth,
                description=attrs.get("description", ""),
            )
            backend_dom_id = node.get("backendDOMNodeId")
            if backend_dom_id is not None:
                backend_node_map[ref] = int(backend_dom_id)

            attr_str = _format_attrs(attrs)
            line = f"[{ref}] {role}"
            if name:
                line += f' "{name}"'
            if attr_str:
                line += f" {attr_str}"
            all_lines.append((depth, line, ref))
            counter[0] += 1
        elif is_context and name:
            attrs = _extract_props(node)
            attr_str = _format_attrs(attrs)
            line = f'{role} "{name}"'
            if attr_str:
                line += f" {attr_str}"
            all_lines.append((depth, line, None))
        elif role == "StaticText" and name:
            all_lines.append((depth, name, None))
        elif not compact and name and role:
            attrs = _extract_props(node)
            attr_str = _format_attrs(attrs)
            line = f'{role} "{name}"'
            if attr_str:
                line += f" {attr_str}"
            all_lines.append((depth, line, None))

        # Recurse children with StaticText aggregation
        i = 0
        while i < len(child_ids):
            cid = child_ids[i]
            cnode = node_by_id.get(cid)
            if cnode and _is_static_text_like(cnode):
                texts: list[str] = []
                while i < len(child_ids):
                    cn = node_by_id.get(child_ids[i])
                    if cn and _is_static_text_like(cn):
                        t = _clean_text(cn.get("name", {}).get("value", ""))
                        if t:
                            texts.append(t)
                        i += 1
                    else:
                        break
                merged = " ".join(texts)
                if merged and merged != name:
                    all_lines.append((depth + 1, merged, None))
            else:
                _visit(cid, depth + 1)
                i += 1

    for rid in root_ids:
        _visit(rid, 0)

    # Phase 2b: merge child frame AX trees (one level of iframes)
    if frame_trees:
        for frame_data in frame_trees:
            # Build a secondary node index for this frame's AX tree.
            # Prefix nodeIds with frameId to avoid collisions with main frame.
            frame_prefix = frame_data.frame_id + ":"
            f_node_by_id: dict[str, dict[str, Any]] = {}
            f_all_child_ids: set[str] = set()
            for raw in frame_data.nodes:
                orig_id = raw.get("nodeId", "")
                if not orig_id:
                    continue
                prefixed_id = frame_prefix + orig_id
                # Rewrite nodeId and childIds with prefix
                patched = dict(raw)
                patched["nodeId"] = prefixed_id
                patched["childIds"] = [
                    frame_prefix + c for c in raw.get("childIds", [])
                ]
                f_node_by_id[prefixed_id] = patched
                for c in patched["childIds"]:
                    f_all_child_ids.add(c)

            f_root_ids: list[str] = []
            for nid in f_node_by_id:
                if nid not in f_all_child_ids:
                    f_root_ids.append(nid)
            if not f_root_ids and f_node_by_id:
                f_root_ids = [next(iter(f_node_by_id))]

            # Temporarily extend node_by_id so _visit can resolve frame nodes
            node_by_id.update(f_node_by_id)

            # Insert a context header line for the frame
            frame_label = frame_data.name or frame_data.url or frame_data.frame_id
            all_lines.append((0, f'[frame "{frame_label}"]', None))

            for frid in f_root_ids:
                _visit(frid, 1)

    # Phase 3: compact mode tree pruning
    total_nodes = len(all_lines)
    total_interactive = len(selector_map)

    if compact:
        keep = [False] * total_nodes
        for idx, (_, _, ref) in enumerate(all_lines):
            if ref is not None:
                keep[idx] = True
                target_depth = all_lines[idx][0]
                for anc in range(idx - 1, -1, -1):
                    if all_lines[anc][0] < target_depth:
                        keep[anc] = True
                        target_depth = all_lines[anc][0]
                        if target_depth == 0:
                            break
        all_lines = [all_lines[i] for i in range(total_nodes) if keep[i]]

    cached_lines = list(all_lines)

    # Phase 4: progressive loading (focus / offset / truncation)
    output_lines = all_lines

    if focus > 0 and focus in selector_map:
        output_lines = _extract_focus_subtree(all_lines, focus)
    elif offset > 0:
        output_lines = all_lines[offset:]

    truncated_at = 0
    if max_nodes and max_nodes > 0 and len(output_lines) > max_nodes:
        visible = output_lines[:max_nodes]
        remaining = output_lines[max_nodes:]
        truncated_at = max_nodes + (offset if offset > 0 else 0)
        output_lines = visible
        remaining_refs = [r for _, _, r in remaining if r is not None]
        if remaining_refs:
            min_ref = min(remaining_refs)
            max_ref = max(remaining_refs)
            summary = (
                f"--- not shown: [{min_ref}]-[{max_ref}]"
                f" {len(remaining)} elements"
                f" (--focus=N to expand subtree,"
                f" --offset={truncated_at} to page) ---"
            )
        else:
            summary = (
                f"--- not shown: {len(remaining)} elements"
                f" (--offset={truncated_at} to page) ---"
            )
        output_lines = [*output_lines, (0, summary, None)]

    # Render lines with ``_INDENT_STEP`` per depth level. Content mode skips
    # the indent because it's optimised for human-readable reading flow, not
    # tree navigation — the structural depth is irrelevant when the agent just
    # wants to know what the page says. Adjacent duplicate lines are then
    # collapsed because a11y parent ``name`` values often repeat their child
    # text verbatim (Wikipedia article text shows up once on the section
    # heading and again on the StaticText child); the dedup is intentionally
    # local to ``content`` so the structured ``[N] role "name"`` lines in
    # accessible/compact still tolerate legitimate repeats.
    rendered: list[str] = []
    if content_mode:
        prev_text: str | None = None
        for _depth, text, _ in output_lines:
            if text == prev_text:
                continue
            rendered.append(text)
            prev_text = text
    else:
        for depth, text, _ in output_lines:
            rendered.append(_INDENT_STEP * depth + text)
    tree_text = "\n".join(rendered)

    if max_chars and max_chars > 0 and len(tree_text) > max_chars:
        tree_text = tree_text[:max_chars] + "\n[...truncated...]"

    snapshot = PageSnapshot(
        seq=seq,
        url=url,
        title=title,
        mode=mode,
        tree_text=tree_text,
        selector_map=selector_map,
        total_nodes=total_nodes,
        total_interactive=total_interactive,
        truncated_at=truncated_at,
    )

    return SnapshotResult(
        snapshot=snapshot,
        selector_map=selector_map,
        backend_node_map=backend_node_map,
        cached_lines=cached_lines,
    )


# ---------------------------------------------------------------------------
# Snapshot diff
# ---------------------------------------------------------------------------

CachedLine = tuple[int, str, int | None]
DiffLine = tuple[int, str, int | None, str | None]


def _line_key(line: CachedLine) -> str:
    """Build a stable identity key for a snapshot line.

    Interactive elements (ref is not None) use the ref number as key so the
    same logical element maps across snapshots even if its text changes.
    Non-interactive lines use a ``role:text`` composite since they have no
    stable ref.
    """
    _depth, text, ref = line
    if ref is not None:
        return f"ref:{ref}"
    # Use the rendered text as a composite key for non-interactive lines.
    # This is intentionally coarse — we care about structural identity,
    # not exact character equality.
    return f"ctx:{text}"


def diff_snapshots(
    previous: list[CachedLine],
    current: list[CachedLine],
) -> list[DiffLine]:
    """Compare two snapshot cached_lines lists and mark changes.

    Returns lines from *current* with a 4th tuple element indicating
    the diff status:

    * ``None``  — unchanged
    * ``"+"``   — added (not present in previous)
    * ``"~"``   — changed (same identity key but different rendered text)

    A trailing summary line lists removed ref numbers (interactive elements
    that were in *previous* but absent from *current*).
    """
    if not previous:
        # First snapshot — everything is new.
        return [(d, t, r, "+") for d, t, r in current]

    # Build lookup from key -> (depth, text) for previous.
    prev_by_key: dict[str, tuple[int, str]] = {}
    prev_refs: set[int] = set()
    for depth, text, ref in previous:
        key = _line_key((depth, text, ref))
        prev_by_key[key] = (depth, text)
        if ref is not None:
            prev_refs.add(ref)

    result: list[DiffLine] = []
    cur_refs: set[int] = set()

    for depth, text, ref in current:
        if ref is not None:
            cur_refs.add(ref)
        key = _line_key((depth, text, ref))
        prev_entry = prev_by_key.get(key)

        if prev_entry is None:
            result.append((depth, text, ref, "+"))
        elif prev_entry != (depth, text):
            result.append((depth, text, ref, "~"))
        else:
            result.append((depth, text, ref, None))

    # Removed interactive elements summary
    removed = sorted(prev_refs - cur_refs)
    if removed:
        refs_str = " ".join(f"[{r}]" for r in removed)
        result.append((0, f"# removed: {refs_str}", None, None))

    return result


def count_diff(diff_lines: list[DiffLine]) -> DiffCounts:
    """Count added (``+``), changed (``~``), and removed lines in a diff.

    The "# removed: [N] [M]" trailing summary line emitted by
    :func:`diff_snapshots` is detected by its prefix so the removed total
    survives a downstream truncation that may have dropped the summary's
    detail tail.
    """
    counts = DiffCounts()
    for _depth, text, _ref, marker in diff_lines:
        if marker == "+":
            counts.added += 1
        elif marker == "~":
            counts.changed += 1
        elif marker is None and text.startswith("# removed:"):
            # Each `[N]` token in the summary corresponds to one removed ref.
            counts.removed += text.count("[")
    return counts


def render_diff_tree(diff_lines: list[DiffLine]) -> str:
    """Render diff lines into indented tree text with ``[+]``/``[~]`` markers."""
    rendered: list[str] = []
    for depth, text, _ref, marker in diff_lines:
        prefix = _INDENT_STEP * depth
        if marker == "+":
            rendered.append(f"{prefix}[+] {text}")
        elif marker == "~":
            rendered.append(f"{prefix}[~] {text}")
        else:
            rendered.append(f"{prefix}{text}")
    return "\n".join(rendered)


def truncate_diff_lines(
    diff_lines: list[DiffLine],
    *,
    max_nodes: int,
    offset: int = 0,
) -> tuple[list[DiffLine], int]:
    """Apply node-level truncation to a diff line list.

    Mirrors ``build_snapshot`` phase 4 so ``--diff`` honours ``--max-nodes``
    in the same shape (ref range, pagination hint) the agent already knows.
    Returns ``(visible_lines_with_summary, truncated_at)`` where
    ``truncated_at == 0`` means no truncation happened.
    """
    if not max_nodes or max_nodes <= 0 or len(diff_lines) <= max_nodes:
        return diff_lines, 0

    visible = diff_lines[:max_nodes]
    remaining = diff_lines[max_nodes:]
    truncated_at = max_nodes + (offset if offset > 0 else 0)

    remaining_refs = [r for _, _, r, _ in remaining if r is not None]
    if remaining_refs:
        min_ref = min(remaining_refs)
        max_ref = max(remaining_refs)
        summary = (
            f"--- not shown: [{min_ref}]-[{max_ref}]"
            f" {len(remaining)} elements"
            f" (--focus=N to expand subtree,"
            f" --offset={truncated_at} to page) ---"
        )
    else:
        summary = (
            f"--- not shown: {len(remaining)} elements"
            f" (--offset={truncated_at} to page) ---"
        )
    visible = [*visible, (0, summary, None, None)]
    return visible, truncated_at
