"""Scenario F: error recovery — structured errors, auto-start detection."""

from __future__ import annotations

import pytest

from browserctl.core.errors import DaemonConnectionError


async def test_connection_error_structured() -> None:
    """DaemonConnectionError should carry proper three-field envelope."""
    err = DaemonConnectionError(
        error="daemon_unreachable",
        hint="Cannot connect to daemon at 127.0.0.1:9222",
        action="run 'browserctl daemon start' first",
    )
    d = err.to_dict()
    assert d["ok"] is False
    assert d["error"] == "daemon_unreachable"
    assert d["hint"]
    assert d["action"]


async def test_client_auto_start_flag() -> None:
    """DaemonClient should have auto_start capability."""
    from browserctl.cli.client import DaemonClient

    # With auto_start disabled, should raise immediately on connect failure
    client = DaemonClient(port=19999, auto_start=False)
    with pytest.raises(DaemonConnectionError) as exc_info:
        await client.health()
    assert exc_info.value.error == "daemon_unreachable"


async def test_client_auto_started_flag_prevents_loop() -> None:
    """After one auto-start attempt, should not retry indefinitely."""
    from browserctl.cli.client import DaemonClient

    client = DaemonClient(port=19998, auto_start=True)
    # Simulate that auto-start already happened
    client._auto_started = True
    with pytest.raises(DaemonConnectionError):
        await client.health()
