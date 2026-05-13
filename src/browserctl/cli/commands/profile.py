"""Profile management commands — create, list, delete, launch."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import orjson
import typer

from browserctl.cli.output import output_error, output_json
from browserctl.core.config import load_config
from browserctl.core.errors import ProfileError
from browserctl.core.types import PROFILE_NAME_RE as _NAME_RE

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["app"]

app = typer.Typer()


def _validate_name(name: str) -> str:
    """Enforce kebab-case profile naming (alphanumeric + hyphens)."""
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


@app.command("create")
def profile_create(
    name: str = typer.Argument(help="Profile name (kebab-case)."),
    from_current: bool = typer.Option(
        False, "--from-current", help="Copy cookies from current browser session."
    ),
) -> None:
    """Create a new browser profile directory."""
    _validate_name(name)

    if from_current:
        from browserctl.cli.client import DaemonClient

        client = DaemonClient()
        result = asyncio.run(client.profile_create_from_current(name=name))
        output_json(result.get("data", result), seq=result.get("seq", 0))
        return

    paths, _ = load_config()
    pdir = paths.profiles_dir / name

    if pdir.exists():
        output_error(
            ProfileError(
                error="profile_exists",
                hint=f"Profile '{name}' already exists at {pdir}",
                action=(
                    "use a different name or delete with"
                    f" 'browserctl profile delete {name}'"
                ),
            )
        )
        raise typer.Exit(1)

    pdir.mkdir(parents=True, exist_ok=True)
    _write_profile_meta(pdir, name)

    output_json({"name": name, "path": str(pdir), "created": True}, seq=0)


@app.command("list")
def profile_list() -> None:
    """List all browser profiles."""
    paths, _ = load_config()
    profiles_dir = paths.profiles_dir

    profiles: list[dict[str, Any]] = []

    if profiles_dir.is_dir():
        for entry in sorted(profiles_dir.iterdir()):
            if not entry.is_dir():
                continue
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

    output_json({"profiles": profiles, "count": len(profiles)}, seq=0)


@app.command("delete")
def profile_delete(
    name: str = typer.Argument(help="Profile name to delete."),
) -> None:
    """Delete a browser profile and its data."""
    _validate_name(name)
    paths, _ = load_config()
    pdir = paths.profiles_dir / name

    if not pdir.exists():
        output_error(
            ProfileError(
                error="profile_not_found",
                hint=f"Profile '{name}' does not exist",
                action="run 'browserctl profile list' to see available profiles",
            )
        )
        raise typer.Exit(1)

    shutil.rmtree(pdir)
    output_json({"name": name, "deleted": True}, seq=0)


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
    _validate_name(name)
    paths, _ = load_config()
    pdir = paths.profiles_dir / name

    # Auto-create the profile if it doesn't exist
    if not pdir.exists():
        pdir.mkdir(parents=True, exist_ok=True)
        _write_profile_meta(pdir, name)

    if background:
        cmd = [
            sys.executable, "-m", "browserctl.daemon",
            "--profile", name,
        ]
        if host:
            cmd.extend(["--host", host])
        if port:
            cmd.extend(["--port", str(port)])
        if not headless:
            cmd.append("--headed")
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        output_json(
            {"pid": proc.pid, "profile": name, "background": True},
            seq=0,
        )
        return

    # Acceptable exception to layer isolation: CLI starts daemon in-process
    # for foreground mode (no HTTP API to call when daemon isn't running yet).
    from browserctl.daemon.server import start

    asyncio.run(start(host=host, port=port, headless=headless, profile=name))
