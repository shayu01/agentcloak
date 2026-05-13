"""Shared type definitions."""

import re
from enum import StrEnum

__all__ = ["PROFILE_NAME_RE", "StealthTier", "Strategy"]

# Canonical profile name pattern: lowercase alphanumeric segments separated by
# single hyphens.  No leading/trailing hyphen, no consecutive hyphens.
PROFILE_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class StealthTier(StrEnum):
    AUTO = "auto"
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
