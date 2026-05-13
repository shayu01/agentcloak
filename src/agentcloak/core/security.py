"""IDPI (Input Domain Protection and Isolation) — pure security check functions."""

from __future__ import annotations

import html
import re
from fnmatch import fnmatch
from urllib.parse import urlparse

import structlog

from agentcloak.core.errors import SecurityError

logger = structlog.get_logger()

__all__ = [
    "ContentMatch",
    "check_domain_allowed",
    "scan_content",
    "wrap_untrusted",
]

_BLOCKED_SCHEMES = frozenset({"file", "data", "javascript"})


def check_domain_allowed(
    url: str,
    *,
    whitelist: list[str],
    blacklist: list[str],
) -> None:
    """Raise SecurityError if the URL is blocked by IDPI Layer 1.

    Rules:
      - file:// / data:// / javascript: always blocked
      - Both lists empty → allow all
      - Whitelist only → only whitelisted domains pass
      - Blacklist only → blacklisted domains blocked, rest pass
      - Both → whitelist takes priority (whitelisted domains bypass blacklist)
    """
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()

    if scheme in _BLOCKED_SCHEMES:
        raise SecurityError(
            error="blocked_scheme",
            hint=f"The '{scheme}:' scheme is always blocked for security",
            action="use an http:// or https:// URL instead",
        )

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise SecurityError(
            error="invalid_url",
            hint=f"Cannot extract hostname from URL: {url}",
            action="provide a valid URL with a hostname",
        )

    if not whitelist and not blacklist:
        return

    # Whitelist takes priority: whitelisted domains bypass blacklist.
    if whitelist:
        if _matches_any(hostname, whitelist):
            return
        raise SecurityError(
            error="domain_blocked",
            hint=f"Domain '{hostname}' is not in the whitelist",
            action=f"add '{hostname}' to [security] domain_whitelist in config",
        )

    if blacklist and _matches_any(hostname, blacklist):
        raise SecurityError(
            error="domain_blocked",
            hint=f"Domain '{hostname}' is in the blacklist",
            action=(f"remove '{hostname}' from [security] domain_blacklist in config"),
        )


def _matches_any(hostname: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        p = pattern.lower()
        if fnmatch(hostname, p):
            return True
    return False


class ContentMatch:
    """A single content scan match result."""

    __slots__ = ("matched_text", "pattern", "position")

    def __init__(self, pattern: str, matched_text: str, position: int) -> None:
        self.pattern = pattern
        self.matched_text = matched_text
        self.position = position

    def to_dict(self) -> dict[str, str | int]:
        return {
            "pattern": self.pattern,
            "matched_text": self.matched_text,
            "position": self.position,
        }


def scan_content(text: str, patterns: list[str]) -> list[ContentMatch]:
    """Scan text for prompt injection patterns (IDPI Layer 2).

    Returns a list of matches. Empty list means clean.
    Patterns are treated as case-insensitive regular expressions.
    """
    if not patterns or not text:
        return []

    matches: list[ContentMatch] = []
    for pattern in patterns:
        try:
            for m in re.finditer(pattern, text, re.IGNORECASE):
                matches.append(
                    ContentMatch(
                        pattern=pattern,
                        matched_text=m.group(),
                        position=m.start(),
                    )
                )
        except re.error as e:
            logger.warning("invalid_scan_pattern", pattern=pattern, error=str(e))
    return matches


def wrap_untrusted(content: str, source_url: str, *, whitelist: list[str]) -> str:
    """Wrap content from non-whitelisted domains (IDPI Layer 3).

    If whitelist is empty (unconfigured) → no wrapping.
    If source domain is in whitelist → no wrapping.
    Otherwise → wrap with <untrusted_web_content> tags.
    """
    if not whitelist:
        return content

    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()

    if hostname and _matches_any(hostname, whitelist):
        return content

    escaped_url = html.escape(source_url, quote=True)
    return (
        f'<untrusted_web_content source="{escaped_url}">\n'
        f"{content}\n"
        f"</untrusted_web_content>"
    )
