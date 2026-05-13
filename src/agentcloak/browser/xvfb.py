"""Xvfb virtual display manager for headless Linux stealth mode."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from pathlib import Path

import structlog

from agentcloak.core.errors import BackendError

__all__ = ["XvfbManager"]

logger = structlog.get_logger()


class XvfbManager:
    """Auto-manage an Xvfb process when no display is available."""

    def __init__(
        self, *, width: int = 1920, height: int = 1080, depth: int = 24
    ) -> None:
        self._width = width
        self._height = height
        self._depth = depth
        self._process: subprocess.Popen[bytes] | None = None
        self._display: str | None = None
        self._original_display: str | None = None

    def _display_functional(self) -> bool:
        display = os.environ.get("DISPLAY")
        if not display:
            return False
        xdpyinfo = shutil.which("xdpyinfo")
        if not xdpyinfo:
            return False
        try:
            subprocess.run(
                [xdpyinfo, "-display", display],
                capture_output=True,
                timeout=5,
                check=True,
            )
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False

    def _find_free_display(self, start: int = 99) -> int:
        for n in range(start, start + 100):
            lock = Path(f"/tmp/.X{n}-lock")
            socket = Path(f"/tmp/.X11-unix/X{n}")
            if not lock.exists() and not socket.exists():
                return n
        raise BackendError(
            error="xvfb_no_free_display",
            hint="Could not find a free display number (tried :99 to :198)",
            action="free up an X display or set DISPLAY manually",
        )

    async def ensure_display(self) -> str:
        if self._display_functional():
            display = os.environ["DISPLAY"]
            logger.info("xvfb_existing_display", display=display)
            return display

        xvfb_bin = shutil.which("Xvfb")
        if not xvfb_bin:
            raise BackendError(
                error="xvfb_not_found",
                hint="Xvfb is required for stealth mode on headless Linux",
                action="sudo apt-get install -y xvfb",
            )

        display_num = self._find_free_display()
        display = f":{display_num}"
        screen = f"{self._width}x{self._height}x{self._depth}"

        self._original_display = os.environ.get("DISPLAY")
        self._process = subprocess.Popen(
            [xvfb_bin, display, "-screen", "0", screen, "-nolisten", "tcp", "-ac"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        os.environ["DISPLAY"] = display
        self._display = display

        # Give Xvfb time to initialize
        await asyncio.sleep(0.5)

        if self._process.poll() is not None:
            self.cleanup()
            raise BackendError(
                error="xvfb_start_failed",
                hint=f"Xvfb exited immediately (display {display})",
                action="check system logs or try a different display number",
            )

        logger.info("xvfb_started", display=display, pid=self._process.pid)
        return display

    def cleanup(self) -> None:
        if self._process is not None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=2)
            logger.info("xvfb_stopped", pid=self._process.pid)
            self._process = None

        if self._original_display is not None:
            os.environ["DISPLAY"] = self._original_display
        elif self._display and "DISPLAY" in os.environ:
            del os.environ["DISPLAY"]
        self._display = None

    @staticmethod
    def is_available() -> bool:
        return shutil.which("Xvfb") is not None
