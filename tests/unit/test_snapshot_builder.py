"""Tests for the shared snapshot builder, including frame merge and diff logic."""

from __future__ import annotations

from agentcloak.browser._snapshot_builder import (
    FrameData,
    SnapshotResult,
    build_snapshot,
    diff_snapshots,
    render_diff_tree,
)


def _make_node(
    node_id: str,
    role: str,
    name: str = "",
    *,
    child_ids: list[str] | None = None,
    backend_dom_id: int | None = None,
    properties: list[dict] | None = None,
) -> dict:
    """Helper to construct a minimal CDP AX node dict."""
    node: dict = {
        "nodeId": node_id,
        "role": {"value": role},
        "name": {"value": name},
        "childIds": child_ids or [],
    }
    if backend_dom_id is not None:
        node["backendDOMNodeId"] = backend_dom_id
    if properties is not None:
        node["properties"] = properties
    return node


class TestBuildSnapshotBasic:
    """Verify build_snapshot without frames (regression guard)."""

    def test_empty_nodes(self) -> None:
        result = build_snapshot([])
        assert isinstance(result, SnapshotResult)
        assert result.snapshot.tree_text == ""
        assert result.selector_map == {}

    def test_single_interactive(self) -> None:
        nodes = [
            _make_node("1", "WebArea", child_ids=["2"]),
            _make_node("2", "button", "Submit", backend_dom_id=42),
        ]
        result = build_snapshot(nodes, seq=1, url="http://test", title="Test")
        assert "[1] button" in result.snapshot.tree_text
        assert '"Submit"' in result.snapshot.tree_text
        assert 1 in result.selector_map
        assert result.backend_node_map[1] == 42
        assert result.snapshot.total_interactive == 1

    def test_compact_mode_prunes(self) -> None:
        nodes = [
            _make_node("1", "WebArea", child_ids=["2", "3"]),
            _make_node("2", "heading", "Title"),
            _make_node("3", "button", "Click"),
        ]
        result_full = build_snapshot(nodes, mode="accessible")
        result_compact = build_snapshot(nodes, mode="compact")
        # Compact should have fewer lines (heading is CONTEXT_ROLES, kept only
        # if it's an ancestor of interactive; here it's a sibling, so pruned)
        compact_len = len(result_compact.snapshot.tree_text)
        full_len = len(result_full.snapshot.tree_text)
        assert compact_len <= full_len
        # Button must be in both
        assert "[1] button" in result_full.snapshot.tree_text
        assert "[1] button" in result_compact.snapshot.tree_text


class TestBuildSnapshotFrameMerge:
    """Verify frame_trees parameter merges child frame content."""

    def _main_nodes(self) -> list[dict]:
        return [
            _make_node("root", "WebArea", child_ids=["btn1"]),
            _make_node("btn1", "button", "Main Button", backend_dom_id=10),
        ]

    def _iframe_nodes(self) -> list[dict]:
        return [
            _make_node("r", "WebArea", child_ids=["link1"]),
            _make_node("link1", "link", "Iframe Link", backend_dom_id=20),
        ]

    def test_no_frames_param_unchanged(self) -> None:
        """Without frame_trees, output is identical to before."""
        result = build_snapshot(self._main_nodes())
        assert "[frame" not in result.snapshot.tree_text
        assert "[1] button" in result.snapshot.tree_text
        assert result.snapshot.total_interactive == 1

    def test_empty_frame_trees_unchanged(self) -> None:
        """Passing empty frame_trees list has no effect."""
        r1 = build_snapshot(self._main_nodes())
        r2 = build_snapshot(self._main_nodes(), frame_trees=[])
        assert r1.snapshot.tree_text == r2.snapshot.tree_text

    def test_frame_merge_adds_content(self) -> None:
        """Frame content appears under [frame "..."] context node."""
        frame = FrameData(
            frame_id="frame-1",
            name="my-iframe",
            url="http://iframe.test",
            nodes=self._iframe_nodes(),
        )
        result = build_snapshot(self._main_nodes(), frame_trees=[frame])

        tree = result.snapshot.tree_text
        # Main content is present
        assert "[1] button" in tree
        assert '"Main Button"' in tree
        # Frame header is present
        assert '[frame "my-iframe"]' in tree
        # Iframe interactive element gets its own ref number
        assert "[2] link" in tree
        assert '"Iframe Link"' in tree
        # Both elements are in selector_map
        assert 1 in result.selector_map
        assert 2 in result.selector_map
        assert result.snapshot.total_interactive == 2

    def test_frame_merge_backend_node_map(self) -> None:
        """Backend node IDs from frame nodes are correctly mapped."""
        frame = FrameData(
            frame_id="f1",
            name="child",
            url="http://child.test",
            nodes=self._iframe_nodes(),
        )
        result = build_snapshot(self._main_nodes(), frame_trees=[frame])
        # ref 1 = main button (backendDOMNodeId=10)
        # ref 2 = iframe link (backendDOMNodeId=20)
        assert result.backend_node_map.get(1) == 10
        assert result.backend_node_map.get(2) == 20

    def test_frame_node_ids_no_collision(self) -> None:
        """Frame nodes with same nodeId as main frame don't collide."""
        # Both main and iframe have a node with id "root"
        main_nodes = [
            _make_node("root", "WebArea", child_ids=["a"]),
            _make_node("a", "button", "Main"),
        ]
        iframe_nodes = [
            _make_node("root", "WebArea", child_ids=["a"]),
            _make_node("a", "link", "Frame"),
        ]
        frame = FrameData(
            frame_id="f1", name="collision-test", url="", nodes=iframe_nodes
        )
        result = build_snapshot(main_nodes, frame_trees=[frame])
        tree = result.snapshot.tree_text
        assert "[1] button" in tree
        assert "[2] link" in tree
        assert result.snapshot.total_interactive == 2

    def test_frame_uses_url_as_label_fallback(self) -> None:
        """When frame has no name, URL is used as label."""
        frame = FrameData(
            frame_id="f2",
            name="",
            url="http://ads.example.com/widget",
            nodes=self._iframe_nodes(),
        )
        result = build_snapshot(self._main_nodes(), frame_trees=[frame])
        assert '[frame "http://ads.example.com/widget"]' in result.snapshot.tree_text

    def test_frame_uses_frame_id_as_last_fallback(self) -> None:
        """When frame has no name and no URL, frame_id is used."""
        frame = FrameData(
            frame_id="ABC123",
            name="",
            url="",
            nodes=self._iframe_nodes(),
        )
        result = build_snapshot(self._main_nodes(), frame_trees=[frame])
        assert '[frame "ABC123"]' in result.snapshot.tree_text

    def test_multiple_frames(self) -> None:
        """Multiple child frames are all merged."""
        f1_nodes = [_make_node("n1", "button", "Frame1 Btn")]
        f2_nodes = [_make_node("n1", "link", "Frame2 Link")]
        frames = [
            FrameData(frame_id="f1", name="nav", url="", nodes=f1_nodes),
            FrameData(frame_id="f2", name="ads", url="", nodes=f2_nodes),
        ]
        result = build_snapshot(self._main_nodes(), frame_trees=frames)
        tree = result.snapshot.tree_text
        assert '[frame "nav"]' in tree
        assert '[frame "ads"]' in tree
        # Main button + 2 frame interactive elements = 3 total
        assert result.snapshot.total_interactive == 3

    def test_frame_merge_with_compact_mode(self) -> None:
        """Frame content is included in compact mode."""
        frame = FrameData(
            frame_id="f1",
            name="child",
            url="",
            nodes=self._iframe_nodes(),
        )
        result = build_snapshot(
            self._main_nodes(), mode="compact", frame_trees=[frame]
        )
        tree = result.snapshot.tree_text
        # Interactive elements from both main and frame should survive pruning
        assert "[1] button" in tree
        assert "[2] link" in tree

    def test_frame_content_indented(self) -> None:
        """Frame content nodes are indented under the frame header."""
        frame = FrameData(
            frame_id="f1",
            name="child",
            url="",
            nodes=self._iframe_nodes(),
        )
        result = build_snapshot(self._main_nodes(), frame_trees=[frame])
        lines = result.snapshot.tree_text.split("\n")
        # Find the frame header line — should be at depth 0 (no indent)
        frame_line = [ln for ln in lines if '[frame "child"]' in ln]
        assert len(frame_line) == 1
        assert not frame_line[0].startswith("  ")  # depth 0
        # The link inside the frame should be indented (depth 1+)
        link_line = [ln for ln in lines if "[2] link" in ln]
        assert len(link_line) == 1
        assert link_line[0].startswith("  ")  # at least depth 1


class TestDiffSnapshots:
    """Verify diff_snapshots correctly marks added, changed, and removed lines."""

    def test_first_snapshot_all_added(self) -> None:
        """When previous is empty, every line is marked '+'."""
        current = [
            (0, '[1] button "Submit"', 1),
            (0, 'heading "Title"', None),
        ]
        result = diff_snapshots([], current)
        assert len(result) == 2
        assert result[0] == (0, '[1] button "Submit"', 1, "+")
        assert result[1] == (0, 'heading "Title"', None, "+")

    def test_identical_snapshots_no_markers(self) -> None:
        """When nothing changed, all markers are None."""
        lines = [
            (0, '[1] button "Submit"', 1),
            (1, 'heading "Title"', None),
        ]
        result = diff_snapshots(lines, lines)
        assert all(marker is None for _, _, _, marker in result)
        # No removed summary
        assert not any("# removed:" in text for _, text, _, _ in result)

    def test_added_element(self) -> None:
        """New element appears with '+' marker."""
        previous = [
            (0, '[1] button "Submit"', 1),
        ]
        current = [
            (0, '[1] button "Submit"', 1),
            (0, '[2] link "More"', 2),
        ]
        result = diff_snapshots(previous, current)
        assert result[0][3] is None  # button unchanged
        assert result[1][3] == "+"  # link is new

    def test_changed_interactive_element(self) -> None:
        """Interactive element with same ref but different text is marked '~'."""
        previous = [
            (0, '[1] button "Submit"', 1),
        ]
        current = [
            (0, '[1] button "Submit" disabled', 1),
        ]
        result = diff_snapshots(previous, current)
        assert result[0][3] == "~"

    def test_changed_depth(self) -> None:
        """Element at different depth is marked '~'."""
        previous = [
            (0, '[1] button "Submit"', 1),
        ]
        current = [
            (2, '[1] button "Submit"', 1),
        ]
        result = diff_snapshots(previous, current)
        assert result[0][3] == "~"

    def test_removed_refs_summary(self) -> None:
        """Removed interactive elements are listed in a summary line."""
        previous = [
            (0, '[1] button "Submit"', 1),
            (0, '[2] link "More"', 2),
            (0, '[3] checkbox "Agree"', 3),
        ]
        current = [
            (0, '[1] button "Submit"', 1),
        ]
        result = diff_snapshots(previous, current)
        # Last line should be the removed summary
        summary = result[-1]
        assert "# removed:" in summary[1]
        assert "[2]" in summary[1]
        assert "[3]" in summary[1]

    def test_no_removed_summary_when_all_present(self) -> None:
        """No removed summary if all previous refs still exist."""
        lines = [
            (0, '[1] button "A"', 1),
            (0, '[2] button "B"', 2),
        ]
        result = diff_snapshots(lines, lines)
        assert not any("# removed:" in text for _, text, _, _ in result)

    def test_non_interactive_change(self) -> None:
        """Non-interactive lines use text as identity key."""
        previous = [
            (0, 'heading "Welcome"', None),
        ]
        current = [
            (0, 'heading "Goodbye"', None),
        ]
        result = diff_snapshots(previous, current)
        # "Welcome" gone, "Goodbye" new
        assert result[0][3] == "+"

    def test_mixed_scenario(self) -> None:
        """Full mixed scenario: unchanged, added, changed, removed."""
        previous = [
            (0, '[1] button "OK"', 1),
            (0, '[2] textbox "Email" value="old@test.com"', 2),
            (0, '[3] link "Help"', 3),
            (0, 'heading "Form"', None),
        ]
        current = [
            (0, '[1] button "OK"', 1),
            (0, '[2] textbox "Email" value="new@test.com"', 2),
            (0, '[4] checkbox "Remember"', 4),
            (0, 'heading "Form"', None),
        ]
        result = diff_snapshots(previous, current)
        markers = {text: marker for _, text, _, marker in result}

        assert markers['[1] button "OK"'] is None  # unchanged
        assert markers['[2] textbox "Email" value="new@test.com"'] == "~"  # changed
        assert markers['[4] checkbox "Remember"'] == "+"  # added
        assert markers['heading "Form"'] is None  # unchanged

        # ref 3 removed
        summary_lines = [text for _, text, _, _ in result if "# removed:" in text]
        assert len(summary_lines) == 1
        assert "[3]" in summary_lines[0]


class TestRenderDiffTree:
    """Verify render_diff_tree formatting."""

    def test_markers_in_output(self) -> None:
        diff_lines = [
            (0, '[1] button "Submit"', 1, None),
            (0, '[2] link "New"', 2, "+"),
            (1, '[3] textbox "Name" value="changed"', 3, "~"),
        ]
        rendered = render_diff_tree(diff_lines)
        lines = rendered.split("\n")
        assert lines[0] == '[1] button "Submit"'
        assert lines[1] == '[+] [2] link "New"'
        assert lines[2] == '  [~] [3] textbox "Name" value="changed"'

    def test_indentation_preserved(self) -> None:
        diff_lines = [
            (0, 'navigation "Nav"', None, None),
            (1, '[1] link "Home"', 1, "+"),
            (2, 'More text', None, "~"),
        ]
        rendered = render_diff_tree(diff_lines)
        lines = rendered.split("\n")
        assert lines[0] == 'navigation "Nav"'
        assert lines[1] == '  [+] [1] link "Home"'
        assert lines[2] == '    [~] More text'

    def test_empty_input(self) -> None:
        assert render_diff_tree([]) == ""

    def test_removed_summary_line(self) -> None:
        diff_lines = [
            (0, '[1] button "OK"', 1, None),
            (0, "# removed: [2] [3]", None, None),
        ]
        rendered = render_diff_tree(diff_lines)
        assert "# removed: [2] [3]" in rendered
