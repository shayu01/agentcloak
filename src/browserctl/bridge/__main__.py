"""Entry point: python -m browserctl.bridge."""

import argparse
import asyncio
import logging
import sys

import structlog

from browserctl.bridge.server import start_bridge


def main() -> None:
    parser = argparse.ArgumentParser(description="browserctl bridge process")
    parser.add_argument("--host", default=None)
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

    # host precedence: CLI --host > bridge.toml > default 127.0.0.1
    from browserctl.bridge.config import load_bridge_config

    cfg = load_bridge_config()
    host = args.host or cfg.host
    asyncio.run(start_bridge(host=host, port=args.port))


main()
