"""Subprocess helper: write cookies into a persistent Chromium profile.

Run as:
    python -m agentcloak.browser._profile_writer \
        --profile-dir /path/to/profile \
        --cookies-file /path/to/cookies.json \
        [--executable-path /path/to/chrome]
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any, cast


async def _run(
    profile_dir: str, cookies_json: str, executable_path: str | None
) -> None:
    cookies: list[dict[str, Any]] = json.loads(cookies_json)

    # Playwright types cookies as a TypedDict (``SetCookieParam``) whose import
    # path lives in a private module, so we cast at the boundary instead of
    # depending on Playwright's internal layout.
    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    try:
        exec_path = executable_path or pw.chromium.executable_path
        ctx = await pw.chromium.launch_persistent_context(
            profile_dir,
            headless=True,
            executable_path=exec_path,
        )
        await ctx.add_cookies(cast("Any", cookies))
        await ctx.close()
    finally:
        await pw.stop()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile-dir", required=True, help="Profile directory.")
    parser.add_argument(
        "--cookies-file",
        required=True,
        help="Path to JSON cookie file.",
    )
    parser.add_argument("--executable-path", default=None, help="Chrome binary.")
    args = parser.parse_args()

    cookies_json = Path(args.cookies_file).read_text(encoding="utf-8")

    asyncio.run(_run(args.profile_dir, cookies_json, args.executable_path))


if __name__ == "__main__":
    main()
