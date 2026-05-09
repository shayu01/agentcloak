"""Entry point: python -m browserctl.bridge."""

import argparse
import asyncio
import logging
import os
import sys

import structlog

from browserctl.bridge.server import start_bridge

# Force unbuffered I/O so stderr output is visible immediately in background
# processes (e.g. `python -m browserctl.bridge &`).
os.environ.setdefault("PYTHONUNBUFFERED", "1")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)  # type: ignore[union-attr]


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
