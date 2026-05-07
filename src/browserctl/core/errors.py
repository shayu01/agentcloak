"""Three-field error envelope and exception hierarchy."""

from dataclasses import dataclass
from typing import Any

__all__ = [
    "AgentBrowserError",
    "BackendError",
    "BrowserTimeoutError",
    "DaemonConnectionError",
    "ElementNotFoundError",
    "ErrorEnvelope",
    "NavigationError",
    "ProfileError",
    "SecurityError",
]


@dataclass(frozen=True)
class ErrorEnvelope:
    """Machine-readable error structure: classify, explain, suggest recovery."""

    error: str
    hint: str
    action: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error": self.error,
            "hint": self.hint,
            "action": self.action,
        }


class AgentBrowserError(Exception):
    """Base exception carrying the three-field envelope."""

    def __init__(self, *, error: str, hint: str, action: str) -> None:
        self.error = error
        self.hint = hint
        self.action = action
        super().__init__(hint)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error": self.error,
            "hint": self.hint,
            "action": self.action,
        }

    def to_envelope(self) -> ErrorEnvelope:
        return ErrorEnvelope(error=self.error, hint=self.hint, action=self.action)


class NavigationError(AgentBrowserError):
    """URL navigation failures."""


class ElementNotFoundError(AgentBrowserError):
    """Target element not in selector_map."""


class BrowserTimeoutError(AgentBrowserError):
    """Operation exceeded timeout."""


class DaemonConnectionError(AgentBrowserError):
    """Cannot reach the daemon process."""


class ProfileError(AgentBrowserError):
    """Profile creation, loading, or validation failures."""


class SecurityError(AgentBrowserError):
    """IDPI security layer blocked an operation."""


class BackendError(AgentBrowserError):
    """Browser backend internal failure."""
