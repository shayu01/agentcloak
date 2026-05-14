"""Spells — reusable site-specific automation."""

from agentcloak.spells.context import SpellContext
from agentcloak.spells.executor import execute_spell
from agentcloak.spells.registry import get_registry, spell
from agentcloak.spells.types import Arg, SpellEntry, SpellMeta

__all__ = [
    "Arg",
    "SpellContext",
    "SpellEntry",
    "SpellMeta",
    "execute_spell",
    "get_registry",
    "spell",
]
