"""Entry point for background daemon: python -m browserctl.daemon."""

import argparse
import asyncio

from browserctl.daemon.server import start


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--profile", default=None, help="Browser profile name.")
    parser.add_argument(
        "--stealth", action="store_true", help="Enable CloakBrowser stealth mode."
    )
    args = parser.parse_args()
    asyncio.run(
        start(
            host=args.host,
            port=args.port,
            headless=not args.headed,
            profile=args.profile,
            stealth=args.stealth,
        )
    )


main()
