"""Unit tests for profile management commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from agentcloak.core.errors import ProfileError


def _make_profiles_dir(tmp_path: Path) -> Path:
    """Create a fake profiles directory."""
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    return profiles


class TestProfileNameValidation:
    def test_valid_simple_name(self) -> None:
        from agentcloak.cli.commands.profile import _validate_name

        assert _validate_name("work") == "work"

    def test_valid_kebab_case(self) -> None:
        from agentcloak.cli.commands.profile import _validate_name

        assert _validate_name("dev-testing") == "dev-testing"

    def test_valid_with_numbers(self) -> None:
        from agentcloak.cli.commands.profile import _validate_name

        assert _validate_name("test-123") == "test-123"

    def test_rejects_uppercase(self) -> None:
        from agentcloak.cli.commands.profile import _validate_name

        with pytest.raises(ProfileError) as exc_info:
            _validate_name("Work")
        assert exc_info.value.error == "invalid_profile_name"

    def test_rejects_spaces(self) -> None:
        from agentcloak.cli.commands.profile import _validate_name

        with pytest.raises(ProfileError) as exc_info:
            _validate_name("my profile")
        assert exc_info.value.error == "invalid_profile_name"

    def test_rejects_underscores(self) -> None:
        from agentcloak.cli.commands.profile import _validate_name

        with pytest.raises(ProfileError) as exc_info:
            _validate_name("my_profile")
        assert exc_info.value.error == "invalid_profile_name"

    def test_rejects_empty(self) -> None:
        from agentcloak.cli.commands.profile import _validate_name

        with pytest.raises(ProfileError) as exc_info:
            _validate_name("")
        assert exc_info.value.error == "invalid_profile_name"

    def test_rejects_leading_hyphen(self) -> None:
        from agentcloak.cli.commands.profile import _validate_name

        with pytest.raises(ProfileError) as exc_info:
            _validate_name("-work")
        assert exc_info.value.error == "invalid_profile_name"

    def test_rejects_trailing_hyphen(self) -> None:
        from agentcloak.cli.commands.profile import _validate_name

        with pytest.raises(ProfileError) as exc_info:
            _validate_name("work-")
        assert exc_info.value.error == "invalid_profile_name"


class TestDirSizeBytes:
    def test_empty_dir(self, tmp_path: Path) -> None:
        from agentcloak.cli.commands.profile import _dir_size_bytes

        assert _dir_size_bytes(tmp_path) == 0

    def test_dir_with_files(self, tmp_path: Path) -> None:
        from agentcloak.cli.commands.profile import _dir_size_bytes

        (tmp_path / "a.txt").write_text("hello")
        (tmp_path / "b.txt").write_text("world!!")
        size = _dir_size_bytes(tmp_path)
        assert size == 5 + 7

    def test_nested_dir(self, tmp_path: Path) -> None:
        from agentcloak.cli.commands.profile import _dir_size_bytes

        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "file.bin").write_bytes(b"\x00" * 100)
        assert _dir_size_bytes(tmp_path) == 100

    def test_nonexistent_dir(self, tmp_path: Path) -> None:
        from agentcloak.cli.commands.profile import _dir_size_bytes

        assert _dir_size_bytes(tmp_path / "nope") == 0


class TestHumanSize:
    def test_bytes(self) -> None:
        from agentcloak.cli.commands.profile import _human_size

        assert _human_size(512) == "512 B"

    def test_kilobytes(self) -> None:
        from agentcloak.cli.commands.profile import _human_size

        assert "KB" in _human_size(2048)

    def test_megabytes(self) -> None:
        from agentcloak.cli.commands.profile import _human_size

        result = _human_size(5 * 1024 * 1024)
        assert "MB" in result

    def test_zero(self) -> None:
        from agentcloak.cli.commands.profile import _human_size

        assert _human_size(0) == "0 B"
