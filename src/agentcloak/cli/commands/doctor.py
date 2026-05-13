"""Self-check and diagnostics command."""

from __future__ import annotations

import asyncio
import platform
import shutil
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import typer

from agentcloak.cli.output import output_json
from agentcloak.core.config import AgentcloakConfig, Paths, load_config

__all__ = ["app"]

app = typer.Typer()

_REQUIRED_PACKAGES = ["typer", "orjson", "structlog", "aiohttp", "cloakbrowser"]

_STEALTH_PACKAGES = ["httpcloak"]

_CHROMIUM_BINARIES = [
    "chromium-browser",
    "chromium",
    "google-chrome-stable",
    "google-chrome",
]


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


def _check_chromium() -> dict[str, Any]:
    for name in _CHROMIUM_BINARIES:
        path = shutil.which(name)
        if path:
            return {"name": "chromium", "ok": True, "detail": path, "hint": ""}
    return {
        "name": "chromium",
        "ok": False,
        "detail": "not found",
        "hint": "install chromium or run 'playwright install chromium'",
    }


def _check_data_dir(paths: Paths) -> dict[str, Any]:
    exists = paths.root.is_dir()
    return {
        "name": "data_directory",
        "ok": True,
        "detail": str(paths.root),
        "hint": "" if exists else "will be created on first use",
    }


def _check_daemon(cfg: AgentcloakConfig) -> dict[str, Any]:
    from agentcloak.cli.client import DaemonClient

    client = DaemonClient(host=cfg.daemon_host, port=cfg.daemon_port, auto_start=False)
    try:
        result = asyncio.run(client.health())
        if result.get("ok"):
            return {
                "name": "daemon",
                "ok": True,
                "detail": f"{cfg.daemon_host}:{cfg.daemon_port}",
                "hint": "",
            }
    except Exception:
        pass
    return {
        "name": "daemon",
        "ok": False,
        "detail": f"{cfg.daemon_host}:{cfg.daemon_port}",
        "hint": "run 'agentcloak daemon start' to launch",
    }


def _check_xvfb() -> dict[str, Any]:
    path = shutil.which("Xvfb")
    if path:
        return {"name": "xvfb", "ok": True, "detail": path, "hint": ""}
    return {
        "name": "xvfb",
        "ok": False,
        "detail": "not found",
        "hint": "sudo apt-get install -y xvfb "
        "(required for headed mode on headless Linux)",
    }


def _check_cloakbrowser_binary() -> dict[str, Any]:
    try:
        import cloakbrowser.download  # pyright: ignore[reportMissingImports]

        binary = str(cloakbrowser.download.ensure_binary())  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
        if Path(binary).is_file():
            return {
                "name": "cloakbrowser_binary",
                "ok": True,
                "detail": binary,
                "hint": "",
            }
        return {
            "name": "cloakbrowser_binary",
            "ok": False,
            "detail": "not downloaded",
            "hint": "run 'cloakbrowser install' to download",
        }
    except ImportError:
        return {
            "name": "cloakbrowser_binary",
            "ok": False,
            "detail": "cloakbrowser not installed",
            "hint": "pip install agentcloak",
        }
    except Exception:
        return {
            "name": "cloakbrowser_binary",
            "ok": False,
            "detail": "binary check failed",
            "hint": "run 'cloakbrowser install' to download",
        }


@app.callback(invoke_without_command=True)
def run_doctor() -> None:
    """Run all diagnostic checks and report status."""
    paths, cfg = load_config()

    checks: list[dict[str, Any]] = []
    checks.append(_check_python())
    for pkg in _REQUIRED_PACKAGES:
        checks.append(_check_package(pkg))
    checks.append(_check_chromium())
    checks.append(_check_cloakbrowser_binary())
    checks.append(_check_data_dir(paths))
    checks.append(_check_daemon(cfg))

    # Optional extras (informational — not required for basic operation)
    stealth_checks: list[dict[str, Any]] = []
    for pkg in _STEALTH_PACKAGES:
        stealth_checks.append(_check_package(pkg))
    stealth_checks.append(_check_xvfb())

    all_ok = all(c["ok"] for c in checks)
    data: dict[str, Any] = {
        "healthy": all_ok,
        "checks": checks,
        "extras": {
            "available": all(c["ok"] for c in stealth_checks),
            "checks": stealth_checks,
        },
    }
    output_json(data, seq=0)
    if not all_ok:
        raise typer.Exit(1)
