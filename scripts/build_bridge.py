#!/usr/bin/env python3
"""PyInstaller build script for agentcloak-bridge.exe.

Run on Windows:
    pip install pyinstaller
    python scripts/build_bridge.py

Produces: dist/agentcloak-bridge.exe
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
BRIDGE_ENTRY = ROOT / "src" / "agentcloak" / "bridge" / "__main__.py"
EXTENSION_DIR = ROOT / "src" / "agentcloak" / "bridge" / "agentcloak-chrome-extension"


def main() -> None:
    if not BRIDGE_ENTRY.is_file():
        print(f"Entry point not found: {BRIDGE_ENTRY}", file=sys.stderr)
        sys.exit(1)

    sep = ";" if sys.platform == "win32" else ":"
    add_data = f"{EXTENSION_DIR}{sep}agentcloak-chrome-extension"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--name",
        "agentcloak-bridge",
        "--add-data",
        add_data,
        "--hidden-import",
        "agentcloak.bridge",
        "--hidden-import",
        "agentcloak.bridge.server",
        "--hidden-import",
        "agentcloak.bridge.config",
        "--hidden-import",
        "starlette",
        "--hidden-import",
        "uvicorn",
        "--hidden-import",
        "websockets",
        "--hidden-import",
        "structlog",
        str(BRIDGE_ENTRY),
    ]

    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    print("\nDone! Output: dist/agentcloak-bridge.exe")


if __name__ == "__main__":
    main()
