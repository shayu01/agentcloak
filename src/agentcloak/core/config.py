"""Paths, configuration loading, and defaults."""

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["AgentcloakConfig", "Paths", "load_config", "resolve_tier"]

_ENV_PREFIX = "AGENTCLOAK_"


@dataclass(frozen=True)
class Paths:
    """All filesystem paths derived from a single root."""

    root: Path

    @property
    def config_file(self) -> Path:
        return self.root / "config.toml"

    @property
    def profiles_dir(self) -> Path:
        return self.root / "profiles"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def active_session_file(self) -> Path:
        return self.root / "active-session.json"

    @property
    def resume_file(self) -> Path:
        return self.root / "resume.json"

    def ensure_dirs(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.profiles_dir.mkdir(exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)


def _default_root() -> Path:
    return Path.home() / ".agentcloak"


@dataclass
class AgentcloakConfig:
    """Merged configuration from all sources."""

    daemon_host: str = "127.0.0.1"
    daemon_port: int = 9222
    default_tier: str = "auto"
    default_profile: str = ""
    viewport_width: int = 1280
    viewport_height: int = 720
    navigation_timeout: int = 30
    idle_timeout_min: int = 0
    stop_on_exit: bool = False
    log_level: str = "warning"
    humanize: bool = False
    domain_whitelist: list[str] = field(default_factory=list[str])
    domain_blacklist: list[str] = field(default_factory=list[str])
    content_scan: bool = False
    content_scan_patterns: list[str] = field(default_factory=list[str])


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def _env(key: str) -> str | None:
    return os.environ.get(f"{_ENV_PREFIX}{key.upper()}")


def load_config(*, root: Path | None = None) -> tuple[Paths, AgentcloakConfig]:
    """Load config with precedence: env vars > config.toml > defaults."""
    paths = Paths(root=root or _default_root())
    raw = _read_toml(paths.config_file)

    daemon = raw.get("daemon", {})
    browser = raw.get("browser", {})
    security = raw.get("security", {})

    cfg = AgentcloakConfig()

    cfg.daemon_host = _env("HOST") or daemon.get("host", cfg.daemon_host)
    cfg.daemon_port = int(_env("PORT") or daemon.get("port", cfg.daemon_port))
    cfg.default_tier = (
        _env("DEFAULT_TIER")
        or _env("TIER")
        or browser.get("default_tier", cfg.default_tier)
    )
    cfg.default_profile = (
        _env("DEFAULT_PROFILE")
        or _env("PROFILE")
        or browser.get("default_profile", cfg.default_profile)
    )
    cfg.viewport_width = int(
        _env("VIEWPORT_WIDTH") or browser.get("viewport_width", cfg.viewport_width)
    )
    cfg.viewport_height = int(
        _env("VIEWPORT_HEIGHT") or browser.get("viewport_height", cfg.viewport_height)
    )
    cfg.navigation_timeout = int(
        _env("NAVIGATION_TIMEOUT_SEC")
        or _env("NAVIGATION_TIMEOUT")
        or browser.get("navigation_timeout", cfg.navigation_timeout)
    )
    cfg.idle_timeout_min = int(
        _env("IDLE_TIMEOUT_MIN")
        or browser.get("idle_timeout_min", cfg.idle_timeout_min)
    )
    cfg.stop_on_exit = (_env("STOP_ON_EXIT") or "").lower() in (
        "true",
        "1",
        "yes",
    ) or browser.get("stop_on_exit", cfg.stop_on_exit)
    cfg.log_level = _env("LOG_LEVEL") or browser.get("log_level", cfg.log_level)

    humanize_env = _env("HUMANIZE")
    if humanize_env is not None:
        cfg.humanize = humanize_env.lower() in ("true", "1", "yes")
    else:
        cfg.humanize = bool(browser.get("humanize", cfg.humanize))

    whitelist_env = _env("DOMAIN_WHITELIST")
    if whitelist_env is not None:
        cfg.domain_whitelist = [
            d.strip() for d in whitelist_env.split(",") if d.strip()
        ]
    else:
        cfg.domain_whitelist = security.get("domain_whitelist", cfg.domain_whitelist)

    content_scan_env = _env("CONTENT_SCAN")
    if content_scan_env is not None:
        cfg.content_scan = content_scan_env.lower() in ("true", "1", "yes")
    else:
        cfg.content_scan = bool(security.get("content_scan", cfg.content_scan))

    blacklist_env = _env("DOMAIN_BLACKLIST")
    if blacklist_env is not None:
        cfg.domain_blacklist = [
            d.strip() for d in blacklist_env.split(",") if d.strip()
        ]
    else:
        cfg.domain_blacklist = security.get("domain_blacklist", cfg.domain_blacklist)

    patterns_env = _env("CONTENT_SCAN_PATTERNS")
    if patterns_env is not None:
        cfg.content_scan_patterns = [
            p.strip() for p in patterns_env.split(",") if p.strip()
        ]
    else:
        cfg.content_scan_patterns = security.get(
            "content_scan_patterns", cfg.content_scan_patterns
        )

    return paths, cfg


def resolve_tier(tier_value: str) -> str:
    """Resolve 'auto' tier to the best available backend.

    CloakBrowser is the default backend; 'auto' always resolves to 'cloak'.
    Legacy value 'patchright' is mapped to 'playwright' for backward compat.
    """
    if tier_value == "patchright":
        return "playwright"
    if tier_value != "auto":
        return tier_value
    return "cloak"
