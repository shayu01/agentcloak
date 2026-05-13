"""Bridge lifecycle commands — start, doctor."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import typer

from agentcloak.cli.output import output_json

__all__ = ["app"]

app = typer.Typer()


@app.command("start")
def bridge_start(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host for extension WS."),
    port: int | None = typer.Option(None, "--port", help="Bind port."),
) -> None:
    """Start the bridge process (connects extension to daemon)."""
    from agentcloak.bridge.server import start_bridge

    asyncio.run(start_bridge(host=host, port=port))


@app.command("doctor")
def bridge_doctor() -> None:
    """Check bridge component status."""
    checks: list[dict[str, Any]] = []

    # Check bridge config
    from agentcloak.bridge.config import load_bridge_config

    cfg = load_bridge_config()
    checks.append(
        {
            "name": "bridge_config",
            "ok": True,
            "detail": f"port={cfg.bridge_port}, "
            f"candidates={len(cfg.daemon_candidates)}",
            "hint": "",
        }
    )

    # Check extension directory
    ext_dir = Path(__file__).parent.parent.parent / "bridge" / "extension"
    manifest = ext_dir / "manifest.json"
    checks.append(
        {
            "name": "extension_files",
            "ok": manifest.is_file(),
            "detail": str(ext_dir) if manifest.is_file() else "not found",
            "hint": "" if manifest.is_file() else "extension files missing",
        }
    )

    # Check aiohttp (required for bridge WS)
    try:
        import aiohttp

        checks.append(
            {
                "name": "aiohttp",
                "ok": True,
                "detail": aiohttp.__version__,
                "hint": "",
            }
        )
    except ImportError:
        checks.append(
            {
                "name": "aiohttp",
                "ok": False,
                "detail": "not installed",
                "hint": "pip install aiohttp",
            }
        )

    all_ok = all(c["ok"] for c in checks)
    output_json({"healthy": all_ok, "checks": checks}, seq=0)

    if not all_ok:
        raise typer.Exit(1)


@app.command("extension-path")
def bridge_extension_path() -> None:
    """Print the path to the Chrome extension directory."""
    ext_dir = Path(__file__).parent.parent.parent / "bridge" / "extension"
    output_json({"path": str(ext_dir.resolve())}, seq=0)
