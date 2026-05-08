"""Tests for remote bridge — config, CLI, RemoteBridgeContext."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from browserctl.bridge.config import BridgeConfig, load_bridge_config
from browserctl.browser.remote_ctx import RemoteBridgeContext
from browserctl.cli.app import app
from browserctl.core.types import StealthTier

runner = CliRunner()


class TestBridgeConfig:
    def test_default_config(self) -> None:
        cfg = BridgeConfig()
        assert cfg.bridge_port == 18765
        assert len(cfg.daemon_candidates) >= 1
        assert cfg.token is None

    def test_load_missing_file(self) -> None:
        with patch(
            "browserctl.bridge.config._config_path",
            return_value=Path("/nonexistent/bridge.toml"),
        ):
            cfg = load_bridge_config()
            assert cfg.bridge_port == 18765


class TestRemoteBridgeContext:
    def test_stealth_tier(self) -> None:
        ws = MagicMock()
        ws.closed = False
        ctx = RemoteBridgeContext(bridge_ws=ws)
        assert ctx.stealth_tier == StealthTier.REMOTE_BRIDGE

    def test_seq_starts_at_zero(self) -> None:
        ws = MagicMock()
        ws.closed = False
        ctx = RemoteBridgeContext(bridge_ws=ws)
        assert ctx.seq == 0

    def test_feed_message_resolves_pending(self) -> None:
        import asyncio

        ws = MagicMock()
        ws.closed = False
        ctx = RemoteBridgeContext(bridge_ws=ws)

        loop = asyncio.new_event_loop()
        fut: asyncio.Future[dict[str, Any]] = loop.create_future()
        ctx._pending["test-id"] = fut

        ctx.feed_message(json.dumps({"id": "test-id", "ok": True, "data": {}}))
        assert fut.done()
        result = fut.result()
        assert result["ok"] is True
        loop.close()

    def test_feed_message_ignores_invalid_json(self) -> None:
        ws = MagicMock()
        ctx = RemoteBridgeContext(bridge_ws=ws)
        ctx.feed_message("not json")

    def test_feed_message_ignores_unknown_id(self) -> None:
        ws = MagicMock()
        ctx = RemoteBridgeContext(bridge_ws=ws)
        ctx.feed_message(json.dumps({"id": "unknown", "ok": True}))

    @pytest.mark.asyncio
    async def test_send_raises_when_disconnected(self) -> None:
        from browserctl.core.errors import BackendError

        ws = MagicMock()
        ws.closed = True
        ctx = RemoteBridgeContext(bridge_ws=ws)

        with pytest.raises(BackendError, match="Bridge WebSocket"):
            await ctx._send("navigate", {"url": "http://example.com"})


class TestBridgeCLI:
    def test_bridge_start_in_help(self) -> None:
        result = runner.invoke(app, ["bridge", "--help"])
        assert "start" in result.stdout
        assert "doctor" in result.stdout

    def test_bridge_doctor_runs(self) -> None:
        result = runner.invoke(app, ["bridge", "doctor"])
        data = json.loads(result.stdout)
        assert "ok" in data
        checks = data["data"]["checks"]
        names = [c["name"] for c in checks]
        assert "bridge_config" in names
        assert "extension_files" in names

    def test_bridge_extension_path(self) -> None:
        result = runner.invoke(app, ["bridge", "extension-path"])
        data = json.loads(result.stdout)
        path = data["data"]["path"]
        assert "extension" in path


class TestExtensionFiles:
    def test_manifest_exists(self) -> None:
        ext_dir = (
            Path(__file__).parent.parent.parent
            / "src"
            / "browserctl"
            / "bridge"
            / "extension"
        )
        assert (ext_dir / "manifest.json").is_file()
        assert (ext_dir / "background.js").is_file()

    def test_manifest_valid(self) -> None:
        ext_dir = (
            Path(__file__).parent.parent.parent
            / "src"
            / "browserctl"
            / "bridge"
            / "extension"
        )
        data = json.loads((ext_dir / "manifest.json").read_text())
        assert data["manifest_version"] == 3
        assert "debugger" in data["permissions"]
        assert "cookies" in data["permissions"]
        assert "tabs" in data["permissions"]
        assert "<all_urls>" in data["host_permissions"]
