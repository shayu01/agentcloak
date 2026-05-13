"""Bridge configuration — daemon candidates, port, auth."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["BridgeConfig", "load_bridge_config"]

_DEFAULT_BRIDGE_PORT = 18765
_DEFAULT_CANDIDATES = [
    "ws://localhost:9222/bridge/ws",
]


@dataclass
class BridgeConfig:
    host: str = "127.0.0.1"
    bridge_port: int = _DEFAULT_BRIDGE_PORT
    daemon_candidates: list[str] = field(
        default_factory=lambda: list(_DEFAULT_CANDIDATES)
    )
    token: str | None = None


def _config_path() -> Path:
    return Path.home() / ".agentcloak" / "bridge.toml"


def load_bridge_config() -> BridgeConfig:
    cfg = BridgeConfig()
    path = _config_path()
    if not path.is_file():
        return cfg

    with path.open("rb") as f:
        raw = tomllib.load(f)

    bridge = raw.get("bridge", {})
    daemon = raw.get("daemon", {})

    cfg.host = bridge.get("host", cfg.host)
    cfg.bridge_port = bridge.get("port", cfg.bridge_port)
    cfg.token = bridge.get("token")

    candidates: list[str] | None = daemon.get("candidates")
    if candidates:
        cfg.daemon_candidates = candidates

    return cfg
