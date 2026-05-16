"""DiagnosticService — unified doctor checks + rich health + resume snapshot.

Today there are three separate places that run "is this thing healthy?"
checks: CLI ``doctor`` command, MCP ``doctor`` tool, and various ad-hoc
``/health`` calls. This service collects all of them so each surface can call
the same code and produce consistent output.
"""

from __future__ import annotations

import platform
import shutil
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

__all__ = ["DiagnosticService"]


_REQUIRED_PACKAGES = (
    "typer",
    "orjson",
    "structlog",
    "fastapi",
    "uvicorn",
    "httpx",
    "cloakbrowser",
    "playwright",
    "httpcloak",
    "mcp",
)


_CHROMIUM_BINARIES = (
    "chromium-browser",
    "chromium",
    "google-chrome-stable",
    "google-chrome",
)


class DiagnosticService:
    """Diagnostics shared by CLI / MCP / daemon."""

    # ------------------------------------------------------------------
    # Doctor — environment checks
    # ------------------------------------------------------------------

    def doctor(self, *, data_dir: Path) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        checks.append(self._check_python())
        for pkg in _REQUIRED_PACKAGES:
            checks.append(self._check_package(pkg))
        checks.append(self._check_chromium())
        checks.append(self._check_cloakbrowser_binary())
        checks.append(self._check_data_dir(data_dir))

        extras: list[dict[str, Any]] = [self._check_xvfb()]

        all_ok = all(c["ok"] for c in checks)
        return {
            "healthy": all_ok,
            "checks": checks,
            "extras": {
                "available": all(c["ok"] for c in extras),
                "checks": extras,
            },
        }

    @staticmethod
    def _check_python() -> dict[str, Any]:
        v = sys.version_info
        ok = (v.major, v.minor) >= (3, 12)
        return {
            "name": "python_version",
            "ok": ok,
            "detail": platform.python_version(),
            "hint": "Python >= 3.12 required" if not ok else "",
        }

    @staticmethod
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

    @staticmethod
    def _check_chromium() -> dict[str, Any]:
        for name in _CHROMIUM_BINARIES:
            path = shutil.which(name)
            if path:
                return {
                    "name": "chromium",
                    "ok": True,
                    "detail": path,
                    "hint": "",
                }
        return {
            "name": "chromium",
            "ok": False,
            "detail": "not found",
            "hint": "install chromium or run 'playwright install chromium'",
        }

    @staticmethod
    def _check_data_dir(data_dir: Path) -> dict[str, Any]:
        exists = data_dir.is_dir()
        return {
            "name": "data_directory",
            "ok": True,
            "detail": str(data_dir),
            "hint": "" if exists else "will be created on first use",
        }

    @staticmethod
    def _check_xvfb() -> dict[str, Any]:
        path = shutil.which("Xvfb")
        if path:
            return {"name": "xvfb", "ok": True, "detail": path, "hint": ""}
        return {
            "name": "xvfb",
            "ok": False,
            "detail": "not found",
            "hint": (
                "sudo apt-get install -y xvfb"
                " (required for headed mode on headless Linux)"
            ),
        }

    @staticmethod
    def _check_cloakbrowser_binary() -> dict[str, Any]:
        try:
            import cloakbrowser.download  # pyright: ignore[reportMissingImports,reportMissingTypeStubs]

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

    # ------------------------------------------------------------------
    # Health — runtime liveness with browser introspection
    # ------------------------------------------------------------------

    async def health(self, ctx: Any, *, local_proxy: Any = None) -> dict[str, Any]:
        data: dict[str, Any] = {
            "ok": True,
            "service": "agentcloak-daemon",
            "stealth_tier": ctx.stealth_tier.value,
            "seq": ctx.seq,
            "capture_recording": ctx.capture_store.recording,
            "capture_entries": len(ctx.capture_store),
        }

        # Pull the current URL/title best-effort; failures are non-fatal.
        try:
            snap = await ctx.snapshot(mode="accessible")
            data["current_url"] = snap.url
            data["current_title"] = snap.title
        except Exception:
            data["current_url"] = None
            data["current_title"] = None

        if local_proxy is not None:
            try:
                data["local_proxy"] = {
                    "running": local_proxy.is_running,
                    "url": local_proxy.proxy_url,
                }
            except Exception:
                data["local_proxy"] = {"running": False}
        return data
