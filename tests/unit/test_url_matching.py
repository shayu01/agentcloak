"""Tests for the shared URL matching helpers in ``agentcloak.browser.base``.

The same three-way dispatch (``glob:`` prefix → literal glob → substring)
is used by ``wait --url`` and ``frame focus --url`` on both backends, so
the helpers live in the base module and are unit-tested here.
"""

from __future__ import annotations

import pytest

from agentcloak.browser.base import (
    classify_url_pattern,
    match_url_glob,
    match_url_substring,
)


class TestClassifyUrlPattern:
    def test_plain_text_is_substring(self) -> None:
        assert classify_url_pattern("example") == ("substring", "example")

    def test_question_mark_is_literal_substring(self) -> None:
        # `?` shows up in URL query strings — must not trigger glob mode.
        assert classify_url_pattern("callback?code=") == (
            "substring",
            "callback?code=",
        )

    def test_leading_and_trailing_star_special_case(self) -> None:
        # `*foo*` is the user's way of saying "contains foo" — substring.
        assert classify_url_pattern("*example*") == ("substring", "example")
        assert classify_url_pattern("*example") == ("substring", "example")
        assert classify_url_pattern("example*") == ("substring", "example")

    def test_star_inside_pattern_is_glob(self) -> None:
        assert classify_url_pattern("example.com/*/api") == (
            "glob",
            "example.com/*/api",
        )

    def test_explicit_glob_prefix(self) -> None:
        assert classify_url_pattern("glob:**/dashboard/*") == (
            "glob",
            "**/dashboard/*",
        )

    def test_explicit_glob_prefix_with_only_stars_routes_to_glob(self) -> None:
        # User opted in by writing ``glob:`` — respect it even if the stripped
        # pattern would otherwise look like a substring (e.g. ``glob:*``).
        assert classify_url_pattern("glob:*") == ("glob", "*")


class TestMatchUrlSubstring:
    def test_plain_substring(self) -> None:
        assert match_url_substring("example", "https://example.com/path") is True
        assert match_url_substring("foo", "https://example.com/") is False

    def test_strips_leading_trailing_stars(self) -> None:
        url = "https://example.com/dashboard"
        assert match_url_substring("*example*", url) is True
        assert match_url_substring("*dashboard", url) is True
        assert match_url_substring("https*", url) is True


class TestMatchUrlGlob:
    def test_single_star_does_not_cross_slash(self) -> None:
        # Playwright's documented behaviour: `*` is non-slash matching.
        assert match_url_glob("example.com/*/api", "example.com/v1/api") is True
        assert match_url_glob("example.com/*/api", "example.com/v1/v2/api") is False

    def test_double_star_crosses_slashes(self) -> None:
        url = "https://x.com/a/b/dashboard/home"
        assert match_url_glob("**/dashboard/*", url) is True

    def test_question_mark_is_literal_not_wildcard(self) -> None:
        # Diverges from POSIX glob — `?` is URL syntax, not "one character".
        assert match_url_glob("/callback?code=abc", "/callback?code=abc") is True
        assert match_url_glob("/callback?code=abc", "/callbackXcode=abc") is False

    def test_regex_special_chars_are_escaped(self) -> None:
        # `.` should be literal, not "any character" — `example.com` must not
        # match `exampleXcom`.
        assert match_url_glob("example.com/*", "example.com/foo") is True
        assert match_url_glob("example.com/*", "exampleXcom/foo") is False

    def test_anchored_fullmatch(self) -> None:
        # `"example.com"` must not match `"https://example.com.evil/"`.
        assert match_url_glob("example.com", "example.com") is True
        assert match_url_glob("example.com", "https://example.com/") is False


class TestDispatchEndToEnd:
    """The matrix from the PRD acceptance criteria, exercised through both helpers.

    Mirrors how ``_wait_impl`` / ``_frame_focus_impl`` dispatch on the
    classify result, so a regression in the wiring shows up here too.
    """

    @pytest.mark.parametrize(
        ("pattern", "url", "expected"),
        [
            # Plain substring — current page already at example.com.
            ("example", "https://example.com/", True),
            # `?` is literal substring.
            ("callback?code=", "https://app/callback?code=xyz", True),
            # `*foo*` → substring.
            ("*example*", "https://example.com/foo", True),
            # Star in the middle → glob, anchored & '/'-respecting.
            # (Same semantics as Playwright's wait_for_url glob, which is
            # also anchored — users typically prefix with '**' for protocol.)
            ("**/api/*/users", "https://example.com/api/v1/users", True),
            ("**/api/*/users", "https://example.com/api/v1/v2/users", False),
            # Explicit `glob:` prefix.
            ("glob:**/dashboard/*", "https://x.com/a/dashboard/home", True),
        ],
    )
    def test_acceptance_matrix(self, pattern: str, url: str, expected: bool) -> None:
        kind, processed = classify_url_pattern(pattern)
        if kind == "glob":
            assert match_url_glob(processed, url) is expected
        else:
            assert match_url_substring(pattern, url) is expected
