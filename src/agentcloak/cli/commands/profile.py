"""Profile management commands — create, list, delete, launch.

Profile CRUD is delegated to :class:`ProfileService` (the same class the
daemon route handlers use) so name validation, path-traversal guards, and the
profile directory layout are defined in exactly one place. The CLI surface
adds optional metadata (``size``, ``last_modified``, ``created_at``) that's
useful when humans are auditing local state but isn't exposed via the daemon
API to keep the wire format minimal.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import orjson
import typer

from agentcloak.cli._dispatch import emit_envelope
from agentcloak.cli.output import error_from_exception, is_json_mode, value
from agentcloak.core.config import load_config
from agentcloak.core.errors import ProfileError
from agentcloak.core.types import PROFILE_NAME_RE as _NAME_RE
from agentcloak.daemon.services import ProfileService

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["app"]

app = typer.Typer()


def _validate_name(name: str) -> str:  # pyright: ignore[reportUnusedFunction]
    """Kebab-case validator kept for backwards compatibility with tests."""
    if not _NAME_RE.match(name):
        raise ProfileError(
            error="invalid_profile_name",
            hint=f"Profile name '{name}' is not valid kebab-case",
            action=(
                "use lowercase alphanumeric and hyphens only,"
                " e.g. 'work' or 'dev-testing'"
            ),
        )
    return name


def _dir_size_bytes(path: Path) -> int:
    if not path.is_dir():
        return 0
    total = 0
    for f in path.rglob("*"):
        if f.is_file():
            total += f.stat().st_size
    return total


def _human_size(nbytes: int) -> str:
    size = float(nbytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} TB"


def _write_profile_meta(pdir: Path, name: str) -> None:
    meta = {
        "name": name,
        "created_at": datetime.now(tz=UTC).isoformat(),
    }
    meta_file = pdir / "profile.json"
    meta_file.write_bytes(orjson.dumps(meta, option=orjson.OPT_INDENT_2))


def _service() -> ProfileService:
    paths, _ = load_config()
    return ProfileService(paths.profiles_dir)


@app.command("create")
def profile_create(
    name: str = typer.Argument(help="Profile name (kebab-case)."),
    from_current: bool = typer.Option(
        False, "--from-current", help="Copy cookies from current browser session."
    ),
) -> None:
    """Create a new browser profile directory."""
    if from_current:
        # Requires a running daemon (cookies live in the browser session).
        from agentcloak.client import DaemonClient

        client = DaemonClient()
        try:
            result = client.profile_create_from_current_sync(name=name)
        except ProfileError as exc:
            error_from_exception(exc)
            return
        if is_json_mode():
            emit_envelope(result)
            return
        data = result.get("data", result)
        value(
            f'created profile "{data.get("profile", name)}" '
            f"({int(data.get('cookie_count', 0) or 0)} cookies)"
        )
        return

    service = _service()
    try:
        service.create(name)
    except ProfileError as exc:
        error_from_exception(exc)
        return

    pdir = service.profiles_dir / name
    _write_profile_meta(pdir, name)
    if is_json_mode():
        emit_envelope(
            {
                "ok": True,
                "seq": 0,
                "data": {"name": name, "path": str(pdir), "created": True},
            }
        )
        return
    value(f'created profile "{name}"')


@app.command("list")
def profile_list() -> None:
    """List all browser profiles."""
    service = _service()
    profiles_dir = service.profiles_dir

    profiles: list[dict[str, Any]] = []
    if profiles_dir.is_dir():
        for entry_name in service.list_profiles():
            entry = profiles_dir / entry_name
            meta_file = entry / "profile.json"
            meta: dict[str, Any] = {}
            if meta_file.is_file():
                meta = orjson.loads(meta_file.read_bytes())

            size_bytes = _dir_size_bytes(entry)
            stat = entry.stat()

            profiles.append(
                {
                    "name": meta.get("name", entry.name),
                    "path": str(entry),
                    "size": _human_size(size_bytes),
                    "size_bytes": size_bytes,
                    "last_modified": datetime.fromtimestamp(
                        stat.st_mtime, tz=UTC
                    ).isoformat(),
                    "created_at": meta.get("created_at"),
                }
            )

    if is_json_mode():
        emit_envelope(
            {
                "ok": True,
                "seq": 0,
                "data": {"profiles": profiles, "count": len(profiles)},
            }
        )
        return
    if not profiles:
        value("no profiles")
        return
    # git-branch style listing — first profile gets the active marker since
    # the local CLI doesn't track which one the daemon is using.
    lines: list[str] = []
    for idx, prof in enumerate(profiles):
        marker = "*" if idx == 0 else " "
        lines.append(f"{marker} {prof['name']} | {prof['path']} | {prof['size']}")
    value("\n".join(lines))


@app.command("delete")
def profile_delete(
    name: str = typer.Argument(help="Profile name to delete."),
) -> None:
    """Delete a browser profile and its data."""
    service = _service()
    try:
        service.delete(name)
    except ProfileError as exc:
        error_from_exception(exc)
        return
    if is_json_mode():
        emit_envelope({"ok": True, "seq": 0, "data": {"name": name, "deleted": True}})
        return
    value(f'deleted profile "{name}"')


@app.command("launch")
def profile_launch(
    name: str = typer.Argument(help="Profile name to launch."),
    background: bool = typer.Option(
        False, "--background", "-b", help="Run daemon in background."
    ),
    headless: bool = typer.Option(
        True, "--headless/--headed", help="Browser headless mode."
    ),
    host: str | None = typer.Option(None, "--host", help="Daemon bind host."),
    port: int | None = typer.Option(None, "--port", help="Daemon bind port."),
) -> None:
    """Launch daemon with a specific profile (persistent context)."""
    service = _service()
    try:
        service.validate_name(name)
    except ProfileError as exc:
        error_from_exception(exc)
        return

    pdir = service.profiles_dir / name
    # Auto-create the profile if it doesn't exist
    if not pdir.exists():
        pdir.mkdir(parents=True, exist_ok=True)
        _write_profile_meta(pdir, name)

    if background:
        from agentcloak.client import DaemonClient

        client = DaemonClient(host=host, port=port, auto_start=False)
        pid = client.spawn_background(
            host=host,
            port=port,
            headless=headless,
            profile=name,
        )
        if is_json_mode():
            emit_envelope(
                {
                    "ok": True,
                    "seq": 0,
                    "data": {"pid": pid, "profile": name, "background": True},
                }
            )
            return
        value(f"started bg | pid {pid} | profile={name}")
        return

    # Acceptable exception to layer isolation: CLI starts daemon in-process
    # for foreground mode (no HTTP API to call when daemon isn't running yet).
    from agentcloak.daemon.server import start

    asyncio.run(start(host=host, port=port, headless=headless, profile=name))
