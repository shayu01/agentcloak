"""Shared type definitions."""

from enum import StrEnum

__all__ = ["StealthTier", "Strategy"]


class StealthTier(StrEnum):
    PATCHRIGHT = "patchright"
    CLOAK = "cloak"
    REMOTE_BRIDGE = "remote_bridge"


class Strategy(StrEnum):
    """Adapter interaction mode — encodes transport + auth semantics."""

    PUBLIC = "public"
    COOKIE = "cookie"
    HEADER = "header"
    INTERCEPT = "intercept"
    UI = "ui"
