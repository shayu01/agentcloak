"""Self-check and diagnostics command."""

from __future__ import annotations

import platform
import sys
from importlib.metadata import PackageNotFoundError, version
from typing import Any

import typer

from browserctl.cli.output import output_json
from browserctl.core.config import BrowserctlConfig, Paths, load_config

__all__ = ["app"]

app = typer.Typer()

_REQUIRED_PACKAGES = ["typer", "orjson", "structlog", "aiohttp", "patchright"]


def _check_python() -> dict[str, Any]:
    v = sys.version_info
    ok = (v.major, v.minor) >= (3, 12)
    return {
        "name": "python_version",
        "ok": ok,
        "detail": platform.python_version(),
        "hint": "Python >= 3.12 required" if not ok else "",
    }


def _check_package(name: str) -> dict[str, Any]:
    try:
        ver = version(name)
        return {"name": name, "ok": True, "detail": ver, "hint": ""}
    except PackageNotFoundError:
        return {
            "name": name,
            "ok": False,
            "detail": "not installed",
            "hint": f"pip install {name}",
        }


def _check_data_dir(paths: Paths) -> dict[str, Any]:
    exists = paths.root.is_dir()
    return {
        "name": "data_directory",
        "ok": True,
        "detail": str(paths.root),
        "hint": "" if exists else "will be created on first use",
    }


def _check_daemon(cfg: BrowserctlConfig) -> dict[str, Any]:
    return {
        "name": "daemon",
        "ok": False,
        "detail": f"{cfg.daemon_host}:{cfg.daemon_port}",
        "hint": "daemon not running (stub: not implemented yet)",
    }


@app.callback(invoke_without_command=True)
def run_doctor() -> None:
    """Run all diagnostic checks and report status."""
    paths, cfg = load_config()

    checks: list[dict[str, Any]] = []
    checks.append(_check_python())
    for pkg in _REQUIRED_PACKAGES:
        checks.append(_check_package(pkg))
    checks.append(_check_data_dir(paths))
    checks.append(_check_daemon(cfg))

    all_ok = all(c["ok"] for c in checks)
    data: dict[str, Any] = {
        "healthy": all_ok,
        "checks": checks,
    }
    output_json(data, seq=0)
    if not all_ok:
        raise typer.Exit(1)
