"""Tests for stealth layer — cloak_ctx, xvfb, extensions, proxy, doctor integration."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from agentcloak.browser.cloak_ctx import (
    TURNSTILE_PATCH_DIR,
    CloakContext,
    _build_extension_args,
)
from agentcloak.browser.xvfb import XvfbManager
from agentcloak.cli.app import app
from agentcloak.core.errors import BackendError
from agentcloak.core.types import StealthTier

runner = CliRunner()


class TestTurnstilePatchExtension:
    def test_manifest_exists(self) -> None:
        manifest = TURNSTILE_PATCH_DIR / "manifest.json"
        assert manifest.is_file()

    def test_script_exists(self) -> None:
        script = TURNSTILE_PATCH_DIR / "script.js"
        assert script.is_file()

    def test_manifest_is_valid_json(self) -> None:
        manifest = TURNSTILE_PATCH_DIR / "manifest.json"
        data = json.loads(manifest.read_text())
        assert data["manifest_version"] == 3
        assert data["content_scripts"][0]["world"] == "MAIN"
        assert data["content_scripts"][0]["run_at"] == "document_start"
        assert data["content_scripts"][0]["all_frames"] is True

    def test_script_patches_screenx(self) -> None:
        script = TURNSTILE_PATCH_DIR / "script.js"
        content = script.read_text()
        assert "screenX" in content
        assert "screenY" in content
        assert "MouseEvent.prototype" in content


class TestBuildExtensionArgs:
    def test_empty_extensions(self) -> None:
        assert _build_extension_args(None) == []
        assert _build_extension_args([]) == []

    def test_single_extension(self) -> None:
        args = _build_extension_args(["/tmp/ext1"])
        assert args == [
            "--disable-extensions-except=/tmp/ext1",
            "--load-extension=/tmp/ext1",
        ]

    def test_multiple_extensions(self) -> None:
        args = _build_extension_args(["/tmp/ext1", "/tmp/ext2"])
        assert "--disable-extensions-except=/tmp/ext1,/tmp/ext2" in args
        assert "--load-extension=/tmp/ext1,/tmp/ext2" in args


class TestCloakContext:
    def test_stealth_tier_is_cloak(self) -> None:
        ctx = CloakContext.__new__(CloakContext)
        assert ctx.stealth_tier == StealthTier.CLOAK


class TestEnsureCloakbrowser:
    def test_import_error_raises_backend_error(self) -> None:
        from agentcloak.browser.cloak_ctx import _ensure_cloakbrowser

        with patch.dict("sys.modules", {"cloakbrowser": None}):
            with pytest.raises(BackendError, match="CloakBrowser"):
                _ensure_cloakbrowser()


class TestXvfbManager:
    def test_is_available_with_xvfb(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/Xvfb"):
            assert XvfbManager.is_available() is True

    def test_is_available_without_xvfb(self) -> None:
        with patch("shutil.which", return_value=None):
            assert XvfbManager.is_available() is False

    def test_find_free_display(self) -> None:
        mgr = XvfbManager()
        with patch.object(Path, "exists", return_value=False):
            display = mgr._find_free_display(start=99)
            assert display == 99

    def test_find_free_display_skips_occupied(self) -> None:
        mgr = XvfbManager()
        call_count = 0

        original_exists = Path.exists

        def mock_exists(self: Path) -> bool:
            nonlocal call_count
            name = self.name
            if name == ".X99-lock" or name == "X99":
                return True
            return False

        with patch.object(Path, "exists", mock_exists):
            display = mgr._find_free_display(start=99)
            assert display == 100

    def test_cleanup_without_process(self) -> None:
        mgr = XvfbManager()
        mgr.cleanup()

    def test_cleanup_terminates_process(self) -> None:
        mgr = XvfbManager()
        mock_proc = MagicMock()
        mock_proc.wait.return_value = None
        mgr._process = mock_proc
        mgr._display = ":99"
        mgr.cleanup()
        mock_proc.terminate.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_display_uses_existing(self) -> None:
        mgr = XvfbManager()
        with (
            patch.dict(os.environ, {"DISPLAY": ":0"}),
            patch.object(mgr, "_display_functional", return_value=True),
        ):
            display = await mgr.ensure_display()
            assert display == ":0"

    @pytest.mark.asyncio
    async def test_ensure_display_raises_without_xvfb(self) -> None:
        mgr = XvfbManager()
        with (
            patch.object(mgr, "_display_functional", return_value=False),
            patch("shutil.which", return_value=None),
        ):
            with pytest.raises(BackendError, match="Xvfb is required"):
                await mgr.ensure_display()


class TestDoctorStealth:
    def test_doctor_includes_stealth_section(self) -> None:
        result = runner.invoke(app, ["doctor"])
        data = json.loads(result.stdout)
        assert "stealth" in data["data"]
        stealth = data["data"]["stealth"]
        assert "available" in stealth
        assert "checks" in stealth

    def test_stealth_checks_have_required_fields(self) -> None:
        result = runner.invoke(app, ["doctor"])
        data = json.loads(result.stdout)
        for check in data["data"]["stealth"]["checks"]:
            assert "name" in check
            assert "ok" in check
            assert "detail" in check
            assert "hint" in check


class TestDaemonStealthFlag:
    def test_daemon_start_help_shows_stealth(self) -> None:
        result = runner.invoke(app, ["daemon", "start", "--help"])
        assert "--stealth" in result.stdout


class TestCreateContextFactory:
    @pytest.mark.asyncio
    async def test_cloak_tier_without_package_raises(self) -> None:
        from agentcloak.browser import create_context

        with patch.dict("sys.modules", {"cloakbrowser": None}):
            with pytest.raises(BackendError, match="CloakBrowser"):
                await create_context(tier=StealthTier.CLOAK)


class TestProxyUrlIntegration:
    def test_patchright_context_stores_proxy_url(self) -> None:
        from agentcloak.browser.patchright_ctx import PatchrightContext
        from agentcloak.core.seq import RingBuffer, SeqCounter

        page = MagicMock()
        page.on = MagicMock()
        ctx = PatchrightContext(
            page=page,
            browser=None,
            playwright=None,
            seq_counter=SeqCounter(),
            ring_buffer=RingBuffer(),
            proxy_url="http://127.0.0.1:12345",
        )
        assert ctx._proxy_url == "http://127.0.0.1:12345"

    def test_cloak_context_stores_proxy_url(self) -> None:
        page = MagicMock()
        page.on = MagicMock()
        ctx = CloakContext(
            page=page,
            browser=None,
            playwright=None,
            seq_counter=MagicMock(),
            ring_buffer=MagicMock(),
            proxy_url="http://127.0.0.1:9999",
        )
        assert ctx._proxy_url == "http://127.0.0.1:9999"

    def test_doctor_stealth_checks_include_httpcloak(self) -> None:
        result = runner.invoke(app, ["doctor"])
        data = json.loads(result.stdout)
        stealth_names = [c["name"] for c in data["data"]["stealth"]["checks"]]
        assert "httpcloak" in stealth_names
