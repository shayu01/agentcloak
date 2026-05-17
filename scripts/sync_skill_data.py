#!/usr/bin/env python3
"""Mirror ``skills/agentcloak/`` into ``src/agentcloak/_skill_data/agentcloak/``.

The editable source of truth for the skill bundle is ``skills/agentcloak/``
at the repo root — that's where authors edit ``SKILL.md`` and the
``references/`` md files. The wheel needs a copy under
``src/agentcloak/_skill_data/`` so :mod:`importlib.resources` can serve it
to ``cloak skill install`` after installation.

This script copies tracked files from the source tree to the mirror,
removing stale files in the mirror that no longer exist upstream.
Preflight verifies the two trees match byte-for-byte; CI fails if they
drift, which happens when someone edits ``skills/agentcloak/`` without
rerunning this script.

Usage::

    uv run python scripts/sync_skill_data.py            # mirror in-place
    uv run python scripts/sync_skill_data.py --check    # CI mode: exit 1 on drift
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "skills" / "agentcloak"
MIRROR = ROOT / "src" / "agentcloak" / "_skill_data" / "agentcloak"

# Files we deliberately leave out of the wheel mirror. ``evals/`` is for
# Anthropic's skill evaluator harness; runtime users have no use for it
# and shipping it would bloat the wheel.
EXCLUDE_DIRS: set[str] = {"evals"}


def _iter_tracked_files(source: Path) -> list[Path]:
    """Return every file under ``source`` that should land in the mirror."""
    files: list[Path] = []
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(source)
        # Skip files in any excluded top-level directory.
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        files.append(path)
    return sorted(files)


def _diff(source: Path, mirror: Path) -> tuple[list[Path], list[Path], list[Path]]:
    """Return ``(missing, stale, changed)`` paths relative to ``source``.

    * ``missing`` exist in source but not in mirror.
    * ``stale`` exist in mirror but not in source.
    * ``changed`` exist in both but with different contents.
    """
    source_files = {p.relative_to(source) for p in _iter_tracked_files(source)}
    mirror_files: set[Path] = set()
    if mirror.is_dir():
        for path in mirror.rglob("*"):
            if path.is_file():
                mirror_files.add(path.relative_to(mirror))

    missing = sorted(source_files - mirror_files)
    stale = sorted(mirror_files - source_files)
    changed: list[Path] = []
    for rel in sorted(source_files & mirror_files):
        if (source / rel).read_bytes() != (mirror / rel).read_bytes():
            changed.append(rel)
    return missing, stale, changed


def _sync(source: Path, mirror: Path) -> None:
    """Copy every tracked file from ``source`` to ``mirror``, removing stale."""
    mirror.mkdir(parents=True, exist_ok=True)
    for src_path in _iter_tracked_files(source):
        rel = src_path.relative_to(source)
        dst_path = mirror / rel
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src_path, dst_path)

    # Drop stale files left over from previous syncs.
    if mirror.is_dir():
        keep = {p.relative_to(source) for p in _iter_tracked_files(source)}
        for path in sorted(mirror.rglob("*"), reverse=True):
            if path.is_file():
                rel = path.relative_to(mirror)
                if rel not in keep:
                    path.unlink()
            elif path.is_dir() and not any(path.iterdir()):
                # Empty directories left after stale file removal.
                path.rmdir()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if mirror differs from source (CI mode, no writes).",
    )
    args = parser.parse_args()

    if not SOURCE.is_dir():
        print(f"FAIL: source directory missing: {SOURCE}")
        return 1

    missing, stale, changed = _diff(SOURCE, MIRROR)

    if args.check:
        if missing or stale or changed:
            print(f"FAIL: {MIRROR.relative_to(ROOT)} out of sync with source.")
            for p in missing:
                print(f"  missing: {p}")
            for p in stale:
                print(f"  stale:   {p}")
            for p in changed:
                print(f"  changed: {p}")
            print("Run `python scripts/sync_skill_data.py` to refresh.")
            return 1
        total = len(_iter_tracked_files(SOURCE))
        print(f"OK: {MIRROR.relative_to(ROOT)} matches source ({total} files).")
        return 0

    _sync(SOURCE, MIRROR)
    total = len(_iter_tracked_files(SOURCE))
    print(
        f"OK: synced {total} files from {SOURCE.relative_to(ROOT)} "
        f"to {MIRROR.relative_to(ROOT)}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
