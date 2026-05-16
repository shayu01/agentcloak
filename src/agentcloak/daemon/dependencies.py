"""FastAPI dependency providers for the daemon.

Centralizes access to the browser context, configuration, and other app-scoped
resources. Route handlers depend on these via `Annotated[T, Depends(...)]` so
that wiring stays explicit and easy to override during testing.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request

from agentcloak.core.config import AgentcloakConfig, load_config

__all__ = [
    "BrowserCtxDep",
    "ConfigDep",
    "ContextManagerDep",
    "OptionalBrowserCtxDep",
    "RemoteCtxDep",
    "RequiredRemoteCtxDep",
    "get_browser_ctx",
    "get_config",
    "get_context_manager",
    "get_optional_browser_ctx",
    "get_remote_ctx",
    "require_remote_ctx",
]


def get_browser_ctx(request: Request) -> Any:
    """Get the live SecureBrowserContext (wraps the active backend)."""
    ctx = request.app.state.browser_ctx
    if ctx is None:
        # Tailor the hint based on whether the daemon is in
        # remote_bridge mode (extension not paired) or just hasn't
        # finished startup yet. The hint tells the agent which knob to
        # turn — paying the cost of one ``getattr`` keeps the error
        # actionable instead of "wait and retry".
        active_tier = getattr(request.app.state, "active_tier", None)
        tier_value = getattr(active_tier, "value", active_tier)
        if tier_value == "remote_bridge":
            raise HTTPException(
                status_code=503,
                detail={
                    "ok": False,
                    "error": "browser_not_ready",
                    "hint": "remote_bridge tier active but no extension connected",
                    "action": (
                        "install and connect the agentcloak Chrome extension, "
                        "or call /launch with tier=cloak to use a local browser"
                    ),
                },
            )
        raise HTTPException(
            status_code=503,
            detail={
                "ok": False,
                "error": "browser_not_ready",
                "hint": "Browser context is not initialized",
                "action": "wait a moment for daemon startup, then retry",
            },
        )
    return ctx


def get_optional_browser_ctx(request: Request) -> Any:
    """Get the active context if one exists, else ``None``.

    Used by routes that should answer even when no browser is up — most
    notably ``/health`` so an agent can introspect the daemon's tier
    while waiting for the extension to connect.
    """
    return getattr(request.app.state, "browser_ctx", None)


def get_context_manager(request: Request) -> Any:
    """Return the daemon's :class:`ContextManager`.

    Routes that mutate the active tier (``/launch``) depend on this. The
    manager is created during ``server.start()`` and lives for the
    lifetime of the daemon, so the only failure mode is "daemon still
    bootstrapping" — surfaced as 503 so callers can retry.
    """
    mgr = getattr(request.app.state, "context_manager", None)
    if mgr is None:
        raise HTTPException(
            status_code=503,
            detail={
                "ok": False,
                "error": "context_manager_not_ready",
                "hint": "Daemon is still initialising",
                "action": "retry after a brief delay",
            },
        )
    return mgr


def get_remote_ctx(request: Request) -> Any:
    """Get the bridge/extension remote context if connected, else None."""
    return getattr(request.app.state, "remote_ctx", None)


def require_remote_ctx(request: Request) -> Any:
    """Get the remote ctx, raising a 400 envelope if no bridge is connected."""
    remote = getattr(request.app.state, "remote_ctx", None)
    if remote is None:
        raise HTTPException(
            status_code=400,
            detail={
                "ok": False,
                "error": "no_bridge_connected",
                "hint": "No Chrome Extension connected via bridge or /ext",
                "action": "ensure the Chrome Extension is connected",
            },
        )
    return remote


def get_config(request: Request) -> AgentcloakConfig:
    """Get the AgentcloakConfig snapshot stored on app state.

    Falls back to a fresh `load_config()` so tests that construct the app
    without setting `app.state.config` still work.
    """
    cfg: AgentcloakConfig | None = getattr(request.app.state, "config", None)
    if cfg is not None:
        return cfg
    _, cfg = load_config()
    return cfg


BrowserCtxDep = Annotated[Any, Depends(get_browser_ctx)]
OptionalBrowserCtxDep = Annotated[Any, Depends(get_optional_browser_ctx)]
RemoteCtxDep = Annotated[Any, Depends(get_remote_ctx)]
RequiredRemoteCtxDep = Annotated[Any, Depends(require_remote_ctx)]
ConfigDep = Annotated[AgentcloakConfig, Depends(get_config)]
ContextManagerDep = Annotated[Any, Depends(get_context_manager)]
