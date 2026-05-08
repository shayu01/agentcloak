"""Tests for core/config.py — paths, config loading, env override."""

from pathlib import Path

import pytest

from browserctl.core.config import BrowserctlConfig, Paths, load_config


class TestPaths:
    def test_derived_paths(self, tmp_path: Path) -> None:
        p = Paths(root=tmp_path)
        assert p.config_file == tmp_path / "config.toml"
        assert p.profiles_dir == tmp_path / "profiles"
        assert p.logs_dir == tmp_path / "logs"
        assert p.active_session_file == tmp_path / "active-session.json"

    def test_ensure_dirs_creates_structure(self, tmp_path: Path) -> None:
        root = tmp_path / "browserctl_test"
        p = Paths(root=root)
        p.ensure_dirs()
        assert root.is_dir()
        assert p.profiles_dir.is_dir()
        assert p.logs_dir.is_dir()


class TestDefaults:
    def test_default_config_values(self) -> None:
        cfg = BrowserctlConfig()
        assert cfg.daemon_host == "127.0.0.1"
        assert cfg.daemon_port == 9222
        assert cfg.default_tier == "auto"
        assert cfg.default_profile == ""
        assert cfg.viewport_width == 1280
        assert cfg.viewport_height == 720
        assert cfg.navigation_timeout == 30
        assert cfg.domain_whitelist == []
        assert cfg.content_scan is False


class TestLoadConfig:
    def test_loads_defaults_when_no_file(self, tmp_path: Path) -> None:
        paths, cfg = load_config(root=tmp_path)
        assert paths.root == tmp_path
        assert cfg.daemon_port == 9222

    def test_reads_toml_file(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[daemon]\nport = 8888\n[browser]\ndefault_tier = "cloak"\n'
        )
        _, cfg = load_config(root=tmp_path)
        assert cfg.daemon_port == 8888
        assert cfg.default_tier == "cloak"

    def test_env_overrides_toml(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text("[daemon]\nport = 8888\n")
        monkeypatch.setenv("BROWSERCTL_PORT", "7777")
        _, cfg = load_config(root=tmp_path)
        assert cfg.daemon_port == 7777

    def test_env_domain_whitelist(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BROWSERCTL_DOMAIN_WHITELIST", "example.com, test.org")
        _, cfg = load_config(root=tmp_path)
        assert cfg.domain_whitelist == ["example.com", "test.org"]
