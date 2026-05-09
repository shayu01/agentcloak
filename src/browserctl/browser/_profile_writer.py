"""Subprocess helper: write cookies into a persistent Chromium profile.

Run as:
    python -m browserctl.browser._profile_writer \
        --profile-dir /path/to/profile \
        --cookies-json '[{"name": "sid", ...}]' \
        [--executable-path /path/to/chrome]
"""

from __future__ import annotations

import argparse
import asyncio
import json


async def _run(
    profile_dir: str, cookies_json: str, executable_path: str | None
) -> None:
    cookies: list[dict] = json.loads(cookies_json)

    try:
        from patchright.async_api import async_playwright
    except ImportError:
        from playwright.async_api import async_playwright  # type: ignore[no-redef]

    pw = await async_playwright().start()
    try:
        exec_path = executable_path or pw.chromium.executable_path
        ctx = await pw.chromium.launch_persistent_context(
            profile_dir,
            headless=True,
            executable_path=exec_path,
        )
        await ctx.add_cookies(cookies)
        await ctx.close()
    finally:
        await pw.stop()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile-dir", required=True, help="Profile directory.")
    parser.add_argument("--cookies-json", required=True, help="JSON cookie list.")
    parser.add_argument("--executable-path", default=None, help="Chrome binary.")
    args = parser.parse_args()

    asyncio.run(_run(args.profile_dir, args.cookies_json, args.executable_path))


if __name__ == "__main__":
    main()
