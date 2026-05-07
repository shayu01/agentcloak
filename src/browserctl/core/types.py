"""Shared type definitions."""

from enum import StrEnum

__all__ = ["StealthTier"]


class StealthTier(StrEnum):
    PATCHRIGHT = "patchright"
    CLOAK = "cloak"
    REMOTE_BRIDGE = "remote_bridge"
