"""Entry point: python -m browserctl.bridge."""

import argparse
import asyncio
import logging
import sys

import structlog

from browserctl.bridge.server import start_bridge


def main() -> None:
    parser = argparse.ArgumentParser(description="browserctl bridge process")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.dev.ConsoleRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )

    asyncio.run(start_bridge(host=args.host, port=args.port))


main()
