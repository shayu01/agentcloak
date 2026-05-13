"""Tests for core/errors.py — three-field envelope and exception hierarchy."""

from browserctl.core.errors import (
    AgentBrowserError,
    BackendError,
    BrowserTimeoutError,
    DaemonConnectionError,
    ElementNotFoundError,
    NavigationError,
    ProfileError,
    SecurityError,
)


class TestAgentBrowserError:
    def test_to_dict_matches_envelope_format(self) -> None:
        exc = AgentBrowserError(error="nav_fail", hint="bad url", action="check url")
        d = exc.to_dict()
        assert d["ok"] is False
        assert d["error"] == "nav_fail"
        assert d["hint"] == "bad url"
        assert d["action"] == "check url"

    def test_str_is_hint(self) -> None:
        exc = AgentBrowserError(error="e", hint="human readable", action="a")
        assert str(exc) == "human readable"

    def test_keyword_only_args(self) -> None:
        try:
            AgentBrowserError("e", "h", "a")  # type: ignore[misc]
            raise AssertionError("Should require keyword args")
        except TypeError:
            pass


class TestSubclasses:
    def test_all_subclasses_inherit_base(self) -> None:
        subclasses = [
            NavigationError,
            ElementNotFoundError,
            BrowserTimeoutError,
            DaemonConnectionError,
            ProfileError,
            SecurityError,
            BackendError,
        ]
        for cls in subclasses:
            exc = cls(error="test", hint="test hint", action="test action")
            assert isinstance(exc, AgentBrowserError)
            assert exc.to_dict()["ok"] is False

    def test_catch_by_base_class(self) -> None:
        try:
            raise NavigationError(
                error="timeout",
                hint="page slow",
                action="retry with longer timeout",
            )
        except AgentBrowserError as e:
            assert e.error == "timeout"
