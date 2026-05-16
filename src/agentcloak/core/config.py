"""Paths, configuration loading, and defaults."""

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "AgentcloakConfig",
    "ConfigError",
    "Paths",
    "dump_config",
    "load_config",
    "resolve_tier",
]

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
    daemon_port: int = 18765
    default_tier: str = "auto"
    default_profile: str = ""
    viewport_width: int = 1280
    viewport_height: int = 720
    navigation_timeout: int = 30
    idle_timeout_min: int = 30
    stop_on_exit: bool = False
    log_level: str = "warning"
    log_to_file: bool = False
    log_max_bytes: int = 10_000_000  # 10 MB
    log_backup_count: int = 3
    headless: bool = True
    humanize: bool = True
    action_timeout: int = 30000
    batch_settle_timeout: int = 2000
    # HTTP client (CLI/MCP ↔ daemon) request timeout. Browser work can be slow
    # (page load, full-page screenshot) so we lean generous here.
    http_client_timeout: int = 90
    # Maximum bytes of serialized result returned from /evaluate. Larger values
    # are truncated with a marker — prevents MCP token blow-up.
    max_return_size: int = 50_000
    # Default JPEG quality for /screenshot. CLI passes through unchanged.
    screenshot_quality: int = 80
    # Screenshot quality used by MCP tools. Lower than the CLI default (80) so
    # the base64 payload stays within MCP token budgets (B2 from dogfood).
    mcp_screenshot_quality: int = 50
    # Auto-start: total budget for waiting on /health after spawning daemon,
    # and the poll interval between health probes.
    auto_start_timeout: float = 15.0
    auto_start_poll_interval: float = 0.5
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
    stop_on_exit_env = _env("STOP_ON_EXIT")
    if stop_on_exit_env is not None:
        cfg.stop_on_exit = stop_on_exit_env.lower() in ("true", "1", "yes")
    else:
        cfg.stop_on_exit = bool(browser.get("stop_on_exit", cfg.stop_on_exit))
    # Log settings belong in [daemon] (they control daemon process logging).
    # Fall back to [browser] for backward compat with pre-v0.2.0 configs.
    cfg.log_level = (
        _env("LOG_LEVEL")
        or daemon.get("log_level", browser.get("log_level", cfg.log_level))
    )

    log_to_file_env = _env("LOG_TO_FILE")
    if log_to_file_env is not None:
        cfg.log_to_file = log_to_file_env.lower() in ("true", "1", "yes")
    else:
        cfg.log_to_file = bool(
            daemon.get("log_to_file", browser.get("log_to_file", cfg.log_to_file))
        )
    cfg.log_max_bytes = int(
        _env("LOG_MAX_BYTES")
        or daemon.get("log_max_bytes", browser.get("log_max_bytes", cfg.log_max_bytes))
    )
    cfg.log_backup_count = int(
        _env("LOG_BACKUP_COUNT")
        or daemon.get(
            "log_backup_count",
            browser.get("log_backup_count", cfg.log_backup_count),
        )
    )

    headless_env = _env("HEADLESS")
    if headless_env is not None:
        cfg.headless = headless_env.lower() in ("true", "1", "yes")
    else:
        cfg.headless = bool(browser.get("headless", cfg.headless))

    cfg.action_timeout = int(
        _env("ACTION_TIMEOUT") or browser.get("action_timeout", cfg.action_timeout)
    )
    cfg.batch_settle_timeout = int(
        _env("BATCH_SETTLE_TIMEOUT")
        or browser.get("batch_settle_timeout", cfg.batch_settle_timeout)
    )
    cfg.http_client_timeout = int(
        _env("HTTP_CLIENT_TIMEOUT")
        or daemon.get("http_client_timeout", cfg.http_client_timeout)
    )
    cfg.max_return_size = int(
        _env("MAX_RETURN_SIZE") or browser.get("max_return_size", cfg.max_return_size)
    )
    cfg.screenshot_quality = int(
        _env("SCREENSHOT_QUALITY")
        or browser.get("screenshot_quality", cfg.screenshot_quality)
    )
    cfg.mcp_screenshot_quality = int(
        _env("MCP_SCREENSHOT_QUALITY")
        or browser.get("mcp_screenshot_quality", cfg.mcp_screenshot_quality)
    )
    cfg.auto_start_timeout = float(
        _env("AUTO_START_TIMEOUT")
        or daemon.get("auto_start_timeout", cfg.auto_start_timeout)
    )
    cfg.auto_start_poll_interval = float(
        _env("AUTO_START_POLL_INTERVAL")
        or daemon.get("auto_start_poll_interval", cfg.auto_start_poll_interval)
    )

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

    _validate(cfg)
    return paths, cfg


class ConfigError(ValueError):
    """Raised when a config value is invalid."""


_VALID_TIERS = {"auto", "cloak", "playwright", "remote_bridge"}
_VALID_LOG_LEVELS = {"debug", "info", "warning", "error"}


def _validate(cfg: AgentcloakConfig) -> None:
    """Validate config values; raise :class:`ConfigError` on bad input."""
    if not 1 <= cfg.daemon_port <= 65535:
        raise ConfigError(
            f"daemon.port must be 1-65535, got {cfg.daemon_port}"
        )
    if cfg.default_tier not in _VALID_TIERS:
        raise ConfigError(
            f"browser.default_tier must be one of {_VALID_TIERS}, "
            f"got {cfg.default_tier!r}"
        )
    if cfg.log_level not in _VALID_LOG_LEVELS:
        raise ConfigError(
            f"log_level must be one of {_VALID_LOG_LEVELS}, "
            f"got {cfg.log_level!r}"
        )
    if cfg.viewport_width < 1 or cfg.viewport_height < 1:
        raise ConfigError(
            f"viewport dimensions must be positive, "
            f"got {cfg.viewport_width}x{cfg.viewport_height}"
        )
    if cfg.screenshot_quality < 0 or cfg.screenshot_quality > 100:
        raise ConfigError(
            f"screenshot_quality must be 0-100, got {cfg.screenshot_quality}"
        )
    if cfg.mcp_screenshot_quality < 0 or cfg.mcp_screenshot_quality > 100:
        raise ConfigError(
            f"mcp_screenshot_quality must be 0-100, "
            f"got {cfg.mcp_screenshot_quality}"
        )


_ENV_KEYS: dict[str, list[str]] = {
    "daemon_host": ["HOST"],
    "daemon_port": ["PORT"],
    "default_tier": ["DEFAULT_TIER", "TIER"],
    "default_profile": ["DEFAULT_PROFILE", "PROFILE"],
    "viewport_width": ["VIEWPORT_WIDTH"],
    "viewport_height": ["VIEWPORT_HEIGHT"],
    "navigation_timeout": ["NAVIGATION_TIMEOUT_SEC", "NAVIGATION_TIMEOUT"],
    "idle_timeout_min": ["IDLE_TIMEOUT_MIN"],
    "stop_on_exit": ["STOP_ON_EXIT"],
    "log_level": ["LOG_LEVEL"],
    "log_to_file": ["LOG_TO_FILE"],
    "log_max_bytes": ["LOG_MAX_BYTES"],
    "log_backup_count": ["LOG_BACKUP_COUNT"],
    "headless": ["HEADLESS"],
    "humanize": ["HUMANIZE"],
    "action_timeout": ["ACTION_TIMEOUT"],
    "batch_settle_timeout": ["BATCH_SETTLE_TIMEOUT"],
    "http_client_timeout": ["HTTP_CLIENT_TIMEOUT"],
    "max_return_size": ["MAX_RETURN_SIZE"],
    "screenshot_quality": ["SCREENSHOT_QUALITY"],
    "mcp_screenshot_quality": ["MCP_SCREENSHOT_QUALITY"],
    "auto_start_timeout": ["AUTO_START_TIMEOUT"],
    "auto_start_poll_interval": ["AUTO_START_POLL_INTERVAL"],
    "domain_whitelist": ["DOMAIN_WHITELIST"],
    "domain_blacklist": ["DOMAIN_BLACKLIST"],
    "content_scan": ["CONTENT_SCAN"],
    "content_scan_patterns": ["CONTENT_SCAN_PATTERNS"],
}


def dump_config(
    cfg: AgentcloakConfig, paths: Paths,
) -> dict[str, dict[str, object]]:
    """Return each config field with its value and source (env/toml/default)."""
    raw = _read_toml(paths.config_file)
    toml_flat: dict[str, object] = {}
    for _key, section in raw.items():
        if isinstance(section, dict):
            section_typed: dict[str, object] = section  # type: ignore[assignment]
            toml_flat.update(section_typed)

    defaults = AgentcloakConfig()
    result: dict[str, dict[str, object]] = {}

    for field_name in vars(defaults):
        value = getattr(cfg, field_name)
        source = "default"
        env_keys = _ENV_KEYS.get(field_name, [])
        for ek in env_keys:
            if _env(ek) is not None:
                source = f"env:{_ENV_PREFIX}{ek.upper()}"
                break
        if source == "default" and field_name in toml_flat:
            source = "config.toml"
        result[field_name] = {"value": value, "source": source}

    return result


def resolve_tier(tier_value: str) -> str:
    """Resolve 'auto' tier to the best available backend.

    CloakBrowser is the default backend; 'auto' always resolves to 'cloak'.
    """
    if tier_value != "auto":
        return tier_value
    return "cloak"
