"""Tests for cli/client.py — DaemonClient with mocked HTTP."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from browserctl.cli.client import DaemonClient
from browserctl.core.errors import AgentBrowserError, DaemonConnectionError


class TestDaemonClient:
    @pytest.mark.asyncio
    async def test_connection_error_raises(self) -> None:
        import aiohttp

        client = DaemonClient(host="127.0.0.1", port=19999)
        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_session = MagicMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.request = MagicMock(
                side_effect=aiohttp.ClientConnectorError(
                    connection_key=MagicMock(),
                    os_error=OSError("Connection refused"),
                )
            )
            mock_session_cls.return_value = mock_session

            with pytest.raises(DaemonConnectionError):
                await client.health()

    @pytest.mark.asyncio
    async def test_error_response_raises(self) -> None:
        import orjson

        client = DaemonClient(host="127.0.0.1", port=19999)
        error_body = orjson.dumps(
            {
                "ok": False,
                "error": "test_error",
                "hint": "test hint",
                "action": "test action",
            }
        )

        mock_resp = MagicMock()
        mock_resp.read = AsyncMock(return_value=error_body)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.request = MagicMock(return_value=mock_resp)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            with pytest.raises(AgentBrowserError) as exc_info:
                await client.health()
            assert exc_info.value.error == "test_error"
