"""Error handling middleware for the daemon HTTP server."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from aiohttp import web

from browserctl.core.errors import AgentBrowserError

if TYPE_CHECKING:
    from aiohttp.web import Request, StreamResponse

__all__ = ["error_middleware"]

logger = structlog.get_logger()


@web.middleware
async def error_middleware(
    request: Request,
    handler: Any,
) -> StreamResponse:
    """Catch AgentBrowserError and return JSON envelope; log unexpected errors."""
    import time

    request.app["last_request_time"] = time.monotonic()
    try:
        resp: StreamResponse = await handler(request)
        return resp
    except AgentBrowserError as exc:
        logger.warning("agent_error", error=exc.error, hint=exc.hint)
        return web.json_response(exc.to_dict(), status=400)
    except web.HTTPException:
        raise
    except Exception as exc:
        logger.exception("unhandled_error")
        return web.json_response(
            {
                "ok": False,
                "error": "internal_error",
                "hint": str(exc),
                "action": "retry the request, or run 'snapshot' to refresh page state",
            },
            status=500,
        )
