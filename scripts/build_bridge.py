#!/usr/bin/env python3
"""PyInstaller build script for browserctl-bridge.exe.

Run on Windows:
    pip install pyinstaller
    python scripts/build_bridge.py

Produces: dist/browserctl-bridge.exe
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
BRIDGE_ENTRY = ROOT / "src" / "browserctl" / "bridge" / "__main__.py"
EXTENSION_DIR = ROOT / "src" / "browserctl" / "bridge" / "extension"


def main() -> None:
    if not BRIDGE_ENTRY.is_file():
        print(f"Entry point not found: {BRIDGE_ENTRY}", file=sys.stderr)
        sys.exit(1)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--name",
        "browserctl-bridge",
        "--add-data",
        f"{EXTENSION_DIR}{';' if sys.platform == 'win32' else ':'}extension",
        "--hidden-import",
        "browserctl.bridge",
        "--hidden-import",
        "browserctl.bridge.server",
        "--hidden-import",
        "browserctl.bridge.config",
        "--hidden-import",
        "aiohttp",
        "--hidden-import",
        "structlog",
        str(BRIDGE_ENTRY),
    ]

    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    print("\nDone! Output: dist/browserctl-bridge.exe")


if __name__ == "__main__":
    main()
