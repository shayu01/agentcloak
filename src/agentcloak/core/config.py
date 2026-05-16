"""Paths, configuration loading, and defaults."""

import contextlib
import os
import secrets
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

__all__ = [
    "AgentcloakConfig",
    "ConfigError",
    "Paths",
    "dump_config",
    "ensure_bridge_token",
    "load_config",
    "regenerate_bridge_token",
    "resolve_tier",
    "write_example_config",
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
    # Persistent bridge auth token for Chrome extension <-> daemon. Empty
    # string means "not yet provisioned" — the daemon generates one on
    # first start and writes it back to config.toml via
    # :func:`ensure_bridge_token`.
    bridge_token: str = ""
    # When in remote_bridge mode, close the local browser after it sits
    # idle for this many seconds (0 = keep it warm forever). 30 min
    # default matches the daemon idle timeout.
    local_idle_timeout: int = 1800


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
    bridge = raw.get("bridge", {})

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
    cfg.log_level = _env("LOG_LEVEL") or daemon.get(
        "log_level", browser.get("log_level", cfg.log_level)
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

    cfg.bridge_token = _env("BRIDGE_TOKEN") or bridge.get("token", cfg.bridge_token)
    cfg.local_idle_timeout = int(
        _env("LOCAL_IDLE_TIMEOUT")
        or bridge.get("local_idle_timeout", cfg.local_idle_timeout)
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
        raise ConfigError(f"daemon.port must be 1-65535, got {cfg.daemon_port}")
    if cfg.default_tier not in _VALID_TIERS:
        raise ConfigError(
            f"browser.default_tier must be one of {_VALID_TIERS}, "
            f"got {cfg.default_tier!r}"
        )
    if cfg.log_level not in _VALID_LOG_LEVELS:
        raise ConfigError(
            f"log_level must be one of {_VALID_LOG_LEVELS}, got {cfg.log_level!r}"
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
            f"mcp_screenshot_quality must be 0-100, got {cfg.mcp_screenshot_quality}"
        )
    if cfg.local_idle_timeout < 0:
        raise ConfigError(
            f"bridge.local_idle_timeout must be >= 0, got {cfg.local_idle_timeout}"
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
    "bridge_token": ["BRIDGE_TOKEN"],
    "local_idle_timeout": ["LOCAL_IDLE_TIMEOUT"],
}


def dump_config(
    cfg: AgentcloakConfig,
    paths: Paths,
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


def _generate_bridge_token() -> str:
    """Return a fresh URL-safe bridge token."""
    return secrets.token_urlsafe(32)


def _write_bridge_token(paths: Paths, token: str) -> None:
    """Persist ``token`` under ``[bridge] token`` in ``paths.config_file``.

    Preserves all other sections by reading the existing config, mutating
    just the ``[bridge]`` table, and rewriting the file. We avoid adding
    a ``tomli_w`` dependency by emitting the small set of tables we know
    about ourselves — agentcloak only owns a handful of well-known
    sections so a custom serialiser is simpler than another runtime dep.
    """
    paths.ensure_dirs()
    raw: dict[str, Any] = _read_toml(paths.config_file)
    existing: dict[str, dict[str, Any]] = {}
    # ``_read_toml`` returns the parsed TOML as ``dict[str, Any]``. Only
    # the table-valued entries get round-tripped — agentcloak's schema is
    # flat-tables-only, so scalar top-level keys are dropped on purpose.
    for k, v in raw.items():
        if isinstance(v, dict):
            # ``isinstance(..., dict)`` narrows to ``dict[Unknown, Unknown]``
            # so we cast back to the typed shape we want before round-tripping.
            existing[k] = dict(cast("dict[str, Any]", v))

    bridge_section = existing.setdefault("bridge", {})
    bridge_section["token"] = token

    paths.config_file.write_text(_serialise_toml(existing), encoding="utf-8")
    # Permission flip is best-effort on Windows; the token is also held in
    # active-session.json which already enforces 0o600.
    with contextlib.suppress(OSError):
        os.chmod(str(paths.config_file), 0o600)


def _serialise_toml(sections: dict[str, dict[str, Any]]) -> str:
    """Minimal TOML serialiser for the agentcloak config schema.

    We only deal with flat ``[section]`` tables containing strings, ints,
    bools, and string arrays — the same shapes ``load_config`` accepts.
    Keeping this in-tree avoids pulling in ``tomli_w`` for one writer.
    """
    lines: list[str] = []
    for section_name, table in sections.items():
        if not table:
            continue
        if lines:
            lines.append("")
        lines.append(f"[{section_name}]")
        for key, value in table.items():
            lines.append(f"{key} = {_serialise_toml_value(value)}")
    return "\n".join(lines) + ("\n" if lines else "")


def _serialise_toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, list):
        # ``value`` is typed Any inbound — cast through Any so pyright
        # doesn't infer ``list[Unknown]`` after the isinstance narrow.
        items = cast("list[Any]", value)
        return "[" + ", ".join(_serialise_toml_value(v) for v in items) + "]"
    # Fall back to quoted repr for anything exotic so we never silently
    # corrupt the file (the validator above keeps this branch unreachable
    # for documented config fields).
    return f'"{value!s}"'


def ensure_bridge_token(paths: Paths, cfg: AgentcloakConfig) -> str:
    """Return the persisted bridge token, generating one on first use.

    If ``cfg.bridge_token`` is empty, a fresh URL-safe token is generated
    and written back to ``config.toml`` under ``[bridge] token``. The
    in-memory config object is mutated so callers don't need to reload.
    """
    if cfg.bridge_token:
        return cfg.bridge_token
    token = _generate_bridge_token()
    _write_bridge_token(paths, token)
    cfg.bridge_token = token
    return token


def regenerate_bridge_token(paths: Paths, cfg: AgentcloakConfig) -> str:
    """Generate a new bridge token, persist it, and return it.

    Used by ``agentcloak bridge token --reset``. Any running daemons must
    be restarted to pick the new value up — token rotation is intentionally
    explicit so silent re-pairing is impossible.
    """
    token = _generate_bridge_token()
    _write_bridge_token(paths, token)
    cfg.bridge_token = token
    return token


# Each entry maps to one ``[section]`` in ``config.example.toml`` so a user
# who opens the file can see exactly which keys agentcloak reads, what the
# defaults are, and a one-line description of what the knob does. Keep in
# sync with :class:`AgentcloakConfig` — preflight has a ``config`` check
# that verifies every dataclass field shows up in the docs, and the
# example file is the most discoverable doc surface.
#
# The file is regenerated on every daemon start; it never replaces a
# user's actual ``config.toml``. The whole point is that the example is
# safe to overwrite because it's just documentation.
_EXAMPLE_CONFIG_HEADER = (
    "# agentcloak configuration example\n"
    "#\n"
    "# Auto-generated on every daemon start. Your live settings live in\n"
    "# `config.toml` in the same directory — copy any section from this\n"
    "# file there to customise it. agentcloak NEVER touches your\n"
    "# config.toml; only this example is rewritten.\n"
    "#\n"
    "# Precedence:  env var  >  config.toml  >  the default shown here.\n"
    "# Env vars are AGENTCLOAK_<UPPERCASE_FIELD>, e.g. AGENTCLOAK_HEADLESS.\n"
    "\n"
)


def _example_section(
    title: str,
    description: str,
    entries: list[tuple[str, Any, str]],
) -> str:
    """Render one ``[section]`` block for the example config.

    ``entries`` is ``[(key, default_value, comment), ...]``. The comment
    lines are word-wrapped lightly so each option reads as a short
    sentence rather than a paragraph that scrolls off the right.
    """
    lines: list[str] = [f"# {description}", f"[{title}]"]
    for key, value, comment in entries:
        if comment:
            for ln in comment.splitlines():
                lines.append(f"# {ln}")
        lines.append(f"{key} = {_serialise_toml_value(value)}")
        lines.append("")
    # Trailing blank line trimmed below by ``\n\n`` joiner.
    if lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def write_example_config(paths: Paths) -> Path:
    """Write a freshly-generated ``config.example.toml`` next to ``config.toml``.

    Always overwrites the existing example — that's the contract. The
    user's real ``config.toml`` is left alone. We regenerate on every
    daemon start so adding a new field in :class:`AgentcloakConfig`
    automatically surfaces in the example the next time the daemon comes
    up; no separate "regenerate docs" step to forget.
    """
    paths.ensure_dirs()
    defaults = AgentcloakConfig()

    daemon_section = _example_section(
        "daemon",
        "HTTP server + daemon process settings.",
        [
            (
                "host",
                defaults.daemon_host,
                "Bind address. Use 0.0.0.0 to accept LAN connections.",
            ),
            (
                "port",
                defaults.daemon_port,
                "Base port. If busy, daemon probes port+1, port+2, ...",
            ),
            (
                "log_level",
                defaults.log_level,
                "One of: debug, info, warning, error.",
            ),
            (
                "log_to_file",
                defaults.log_to_file,
                "When true, daemon log goes to ~/.agentcloak/logs/daemon.log\n"
                "(otherwise stderr).",
            ),
            (
                "log_max_bytes",
                defaults.log_max_bytes,
                "Rotation threshold for daemon.log (one-shot at startup).",
            ),
            (
                "log_backup_count",
                defaults.log_backup_count,
                "Number of rotated daemon.log.N files to keep.",
            ),
            (
                "http_client_timeout",
                defaults.http_client_timeout,
                "Seconds CLI/MCP will wait for a daemon HTTP reply.",
            ),
            (
                "auto_start_timeout",
                defaults.auto_start_timeout,
                "Total budget (s) for /health probe when DaemonClient\n"
                "auto-starts the daemon process.",
            ),
            (
                "auto_start_poll_interval",
                defaults.auto_start_poll_interval,
                "Poll interval (s) between /health checks during\n"
                "auto-start.",
            ),
        ],
    )

    browser_section = _example_section(
        "browser",
        "Default browser launch options + interaction defaults.",
        [
            (
                "default_tier",
                defaults.default_tier,
                'Startup backend: "auto" (=cloak), "cloak", "playwright",\n'
                'or "remote_bridge".',
            ),
            (
                "default_profile",
                defaults.default_profile,
                "Profile directory name under ~/.agentcloak/profiles/ that\n"
                "the daemon should attach to (empty = no profile).",
            ),
            (
                "headless",
                defaults.headless,
                "Headless mode is on by default. Set to false to keep the\n"
                "browser window visible (Xvfb is started automatically on\n"
                "servers without a display).",
            ),
            (
                "humanize",
                defaults.humanize,
                "CloakBrowser-only: Bezier mouse, realistic typing cadence.",
            ),
            (
                "viewport_width",
                defaults.viewport_width,
                "Initial viewport width in pixels.",
            ),
            (
                "viewport_height",
                defaults.viewport_height,
                "Initial viewport height in pixels.",
            ),
            (
                "navigation_timeout",
                defaults.navigation_timeout,
                "Default timeout (s) for navigate / wait operations.",
            ),
            (
                "action_timeout",
                defaults.action_timeout,
                "Per-action timeout (ms) for click/fill/etc.",
            ),
            (
                "batch_settle_timeout",
                defaults.batch_settle_timeout,
                "Settle window (ms) after batched mutating actions\n"
                "before the read-after-write snapshot.",
            ),
            (
                "idle_timeout_min",
                defaults.idle_timeout_min,
                "Daemon shuts down after this many minutes of inactivity\n"
                "(0 = never).",
            ),
            (
                "stop_on_exit",
                defaults.stop_on_exit,
                "When true, CLI exit triggers a daemon shutdown.",
            ),
            (
                "max_return_size",
                defaults.max_return_size,
                "Cap (bytes) on serialised /evaluate result; longer values\n"
                "are truncated with a marker.",
            ),
            (
                "screenshot_quality",
                defaults.screenshot_quality,
                "Default JPEG quality (0-100) for /screenshot.",
            ),
            (
                "mcp_screenshot_quality",
                defaults.mcp_screenshot_quality,
                "Lower quality used by MCP tools to stay within token\n"
                "budgets.",
            ),
        ],
    )

    security_section = _example_section(
        "security",
        "IDPI safety layer — domain allow/deny lists + content scan.",
        [
            (
                "domain_whitelist",
                defaults.domain_whitelist,
                "If non-empty, only these glob patterns are reachable;\n"
                'everything else is wrapped in <untrusted_web_content>.\n'
                'Example: ["*.example.com", "api.trusted.io"].',
            ),
            (
                "domain_blacklist",
                defaults.domain_blacklist,
                "Globs that are always blocked even if whitelisted.\n"
                'file://, data:, javascript: are always blocked.',
            ),
            (
                "content_scan",
                defaults.content_scan,
                "Enable regex scan of returned content for sensitive\n"
                "patterns (off by default).",
            ),
            (
                "content_scan_patterns",
                defaults.content_scan_patterns,
                "Regexes used when content_scan is true.",
            ),
        ],
    )

    bridge_section = _example_section(
        "bridge",
        "Remote bridge (Chrome extension) settings.",
        [
            (
                "token",
                "",
                "Auto-generated on first daemon start and persisted here.\n"
                "Run `agentcloak bridge token` to print the live value,\n"
                "`--reset` to rotate.",
            ),
            (
                "local_idle_timeout",
                defaults.local_idle_timeout,
                "Seconds before the warm local browser is closed when\n"
                "the daemon is in remote_bridge mode (0 = keep warm\n"
                "forever).",
            ),
        ],
    )

    body = "\n\n".join(
        [daemon_section, browser_section, security_section, bridge_section]
    )
    text = _EXAMPLE_CONFIG_HEADER + body + "\n"

    example_path = paths.root / "config.example.toml"
    example_path.write_text(text, encoding="utf-8")
    return example_path
