"""Bundled skill data shipped inside the wheel.

The ``cloak skill install`` command unpacks this tree to the canonical
location at ``~/.agentcloak/skills/agentcloak/`` and symlinks per-platform
skill directories to it.

The mirror under ``skills/agentcloak/`` at the repo root is the editable
source of truth; ``scripts/sync_skill_data.py`` copies it here so the wheel
ships an identical bundle. Preflight verifies the two trees match.
"""
