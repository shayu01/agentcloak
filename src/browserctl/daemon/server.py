"""Daemon lifecycle — start, stop, health. Stub for Phase 0a."""

from __future__ import annotations

__all__ = ["health", "start", "stop"]


async def start(*, host: str = "127.0.0.1", port: int = 9222) -> None:
    """Start the daemon. (stub)"""
    raise NotImplementedError("Daemon not yet implemented")


async def stop() -> None:
    """Stop the running daemon. (stub)"""
    raise NotImplementedError("Daemon not yet implemented")


async def health(*, host: str = "127.0.0.1", port: int = 9222) -> bool:
    """Check if daemon is reachable. (stub)"""
    return False
