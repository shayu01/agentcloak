"""Pydantic request/response models for daemon HTTP API.

The single source of truth for daemon API schemas. Pydantic models drive:
- request body parsing and validation
- response serialization
- OpenAPI spec generation (for Phase 6 auto-generation of CLI/MCP/Skill)

Keep models close to the route handlers they serve. Don't add internal-only
fields here — those live on browser/state.py data classes.

Default values for request fields are sourced from :mod:`agentcloak.core.config`
at import time. The module-level snapshot lets ``Field(default=...)`` emit
concrete numbers into the OpenAPI schema (which Pydantic generates without
running ``default_factory``). Changing config.toml therefore requires a daemon
restart — that's the same lifecycle as every other config-driven default.
"""

from __future__ import annotations

from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from agentcloak.core.config import load_config

_, _CFG = load_config()

_DEFAULT_NAVIGATE_TIMEOUT: float = float(_CFG.navigation_timeout)
_DEFAULT_ACTION_TIMEOUT: int = _CFG.action_timeout
_DEFAULT_BATCH_SETTLE_TIMEOUT: int = _CFG.batch_settle_timeout
_DEFAULT_MAX_RETURN_SIZE: int = _CFG.max_return_size

__all__ = [
    "ActionRequest",
    "ActionResponse",
    "BatchActionRequest",
    "BatchActionResponse",
    "BridgeClaimRequest",
    "BridgeFinalizeRequest",
    "BridgeOpResponse",
    "CDPEndpointResponse",
    "CaptureAnalyzeResponse",
    "CaptureClearResponse",
    "CaptureExportResponse",
    "CaptureReplayRequest",
    "CaptureReplayResponse",
    "CaptureStatusResponse",
    "CookiesExportRequest",
    "CookiesExportResponse",
    "CookiesImportRequest",
    "CookiesImportResponse",
    "DialogHandleRequest",
    "DialogHandleResponse",
    "DialogStatusResponse",
    "ErrorResponse",
    "EvaluateRequest",
    "EvaluateResponse",
    "FetchRequest",
    "FetchResponse",
    "FrameFocusRequest",
    "FrameFocusResponse",
    "FrameListResponse",
    "HealthResponse",
    "NavigateRequest",
    "NavigateResponse",
    "NetworkResponse",
    "OkEnvelope",
    "ProfileCreateFromCurrentRequest",
    "ProfileCreateFromCurrentResponse",
    "ProfileCreateRequest",
    "ProfileCreateResponse",
    "ProfileDeleteRequest",
    "ProfileListResponse",
    "ResumeResponse",
    "ScreenshotResponse",
    "ShutdownResponse",
    "SnapshotResponse",
    "SpellListResponse",
    "SpellRunRequest",
    "SpellRunResponse",
    "TabCloseRequest",
    "TabListResponse",
    "TabNewRequest",
    "TabOpResponse",
    "TabSwitchRequest",
    "UploadRequest",
    "UploadResponse",
    "WaitRequest",
    "WaitResponse",
]


T = TypeVar("T")


class OkEnvelope(BaseModel, Generic[T]):  # noqa: UP046
    """Success envelope `{ok: true, seq: N, data: T}`.

    We keep ``Generic[T]`` (instead of the PEP 695 ``class Foo[T]`` form)
    because Pydantic v2 still wires its generic plumbing through the legacy
    ``typing.Generic`` mechanism — switching to PEP 695 silently breaks
    Pydantic's model validation for parameterised envelopes.
    """

    ok: Literal[True] = True
    seq: int = 0
    data: T


class ErrorResponse(BaseModel):
    """Three-field error envelope. Status code carries the HTTP semantics."""

    ok: Literal[False] = False
    error: str
    hint: str = ""
    action: str = ""


# --- Navigate ---


class NavigateRequest(BaseModel):
    url: str
    timeout: float = _DEFAULT_NAVIGATE_TIMEOUT
    include_snapshot: bool = False
    snapshot_mode: Literal["compact", "accessible"] = "compact"


class _SnapshotAttachment(BaseModel):
    """Lightweight snapshot payload attached to action/navigate responses."""

    tree_text: str
    mode: str
    total_nodes: int
    total_interactive: int


class NavigateResponse(BaseModel):
    """Navigation result — kept open-ended to allow backend-specific fields."""

    model_config = ConfigDict(extra="allow")

    url: str = ""
    title: str = ""
    status: int | None = None
    snapshot: _SnapshotAttachment | None = None


# --- Screenshot ---


class ScreenshotResponse(BaseModel):
    base64: str
    size: int
    format: str


# --- Snapshot ---


class SnapshotResponse(BaseModel):
    """Snapshot tree + optional metadata."""

    model_config = ConfigDict(extra="allow")

    url: str
    title: str
    mode: str
    tree_text: str
    tree_size: int
    truncated: bool
    total_nodes: int
    total_interactive: int
    truncated_at: int | None = None
    diff: bool | None = None
    selector_map: dict[str, dict[str, Any]] | None = None
    security_warnings: list[dict[str, Any]] | None = None


# --- Evaluate ---


class EvaluateRequest(BaseModel):
    js: str
    world: Literal["main", "isolated"] = "main"
    max_return_size: int = _DEFAULT_MAX_RETURN_SIZE


class EvaluateResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    result: Any = None
    truncated: bool = False
    total_size: int = 0


# --- Network ---


class NetworkResponse(BaseModel):
    requests: list[dict[str, Any]]
    count: int


# --- Action ---


class ActionRequest(BaseModel):
    """One action invocation. Extra params (text, key, value, etc.) pass through."""

    model_config = ConfigDict(extra="allow")

    kind: str
    index: int | None = None
    target: str = ""
    include_snapshot: bool = False
    snapshot_mode: Literal["compact", "accessible"] = "compact"


class ActionResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    ok: bool = True
    action: str = ""
    seq: int = 0


class BatchActionRequest(BaseModel):
    actions: list[dict[str, Any]] = Field(default_factory=lambda: [])
    sleep: float = 0.0
    settle_timeout: int = _DEFAULT_BATCH_SETTLE_TIMEOUT


class BatchActionResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    results: list[dict[str, Any]]
    completed: int
    total: int


# --- Fetch ---


class FetchRequest(BaseModel):
    url: str
    method: str = "GET"
    body: str | None = None
    headers: dict[str, str] | None = None
    timeout: float = _DEFAULT_NAVIGATE_TIMEOUT


class FetchResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: int = 0


# --- Cookies ---


class CookiesExportRequest(BaseModel):
    url: str | None = None


class CookiesExportResponse(BaseModel):
    cookies: list[dict[str, Any]]
    count: int = 0


class CookiesImportRequest(BaseModel):
    cookies: list[dict[str, Any]]


class CookiesImportResponse(BaseModel):
    imported: int


# --- Capture ---


class CaptureStatusResponse(BaseModel):
    recording: bool
    entries: int = 0


class CaptureClearResponse(BaseModel):
    """Result of clearing the capture buffer.

    Distinct from :class:`CaptureStatusResponse` because ``status``/``start``/
    ``stop`` advertise the recording state, while ``clear`` reports whether
    the buffer was emptied. Conflating them led to FastAPI's response-model
    validator rejecting ``/capture/clear`` payloads that omit ``recording``.
    """

    cleared: bool


class CaptureExportResponse(BaseModel):
    """HAR or JSON — open-ended, since HAR has its own deep schema."""

    model_config = ConfigDict(extra="allow")


class CaptureAnalyzeResponse(BaseModel):
    patterns: list[dict[str, Any]]
    count: int


class CaptureReplayRequest(BaseModel):
    url: str
    method: str = "GET"


class CaptureReplayResponse(BaseModel):
    """Replay result — proxies an HTTP response payload."""

    model_config = ConfigDict(extra="allow")

    status: int | None = None


# --- CDP ---


class CDPEndpointResponse(BaseModel):
    ws_endpoint: str
    http_url: str
    port: int


# --- Tabs ---


class TabListResponse(BaseModel):
    tabs: list[dict[str, Any]]
    count: int


class TabNewRequest(BaseModel):
    url: str | None = None


class TabCloseRequest(BaseModel):
    tab_id: int


class TabSwitchRequest(BaseModel):
    tab_id: int


class TabOpResponse(BaseModel):
    """Generic tab-operation response (new/close/switch).

    The backend returns a small payload like ``{tab_id, url, title}`` that
    differs slightly per operation, so we keep this open-ended rather than
    fanning out one model per route — agents read whichever fields they
    care about and ignore the rest.
    """

    model_config = ConfigDict(extra="allow")


# --- Resume ---


class ResumeResponse(BaseModel):
    """Session resume snapshot — open-ended to match the writer's payload."""

    model_config = ConfigDict(extra="allow")


# --- Shutdown ---


class ShutdownResponse(BaseModel):
    """Empty payload — the shutdown route signals success via the envelope only."""

    model_config = ConfigDict(extra="allow")


# --- Spells ---


class SpellRunRequest(BaseModel):
    name: str
    args: dict[str, Any] = Field(default_factory=lambda: {})


class SpellRunResponse(BaseModel):
    result: Any


class SpellListResponse(BaseModel):
    spells: list[dict[str, Any]]
    count: int


# --- Profile ---


class ProfileCreateRequest(BaseModel):
    name: str


class ProfileCreateResponse(BaseModel):
    """Profile create response.

    Profile routes historically did not use the OkEnvelope wrapper — they
    returned `{ok: true, created: name}` directly. v0.2.0 normalizes them to
    OkEnvelope[ProfileCreateResponse]; the typed fields below are what lives
    in the `data` payload.
    """

    model_config = ConfigDict(extra="allow")

    created: str | None = None
    deleted: str | None = None


class ProfileDeleteRequest(BaseModel):
    name: str


class ProfileListResponse(BaseModel):
    profiles: list[str]
    count: int


class ProfileCreateFromCurrentRequest(BaseModel):
    name: str


class ProfileCreateFromCurrentResponse(BaseModel):
    profile: str
    renamed: bool
    cookie_count: int


# --- Bridge ---


class BridgeClaimRequest(BaseModel):
    tab_id: int | None = None
    url_pattern: str | None = None


class BridgeFinalizeRequest(BaseModel):
    mode: str = "close"


# --- Dialog ---


class DialogStatusResponse(BaseModel):
    pending: bool
    dialog: dict[str, Any] | None = None


class DialogHandleRequest(BaseModel):
    action: str = "accept"
    text: str | None = None


class DialogHandleResponse(BaseModel):
    """Dialog-handle result — varies per dialog kind (alert/confirm/prompt)."""

    model_config = ConfigDict(extra="allow")


# --- Wait ---


class WaitRequest(BaseModel):
    condition: str = "ms"
    value: str = "1000"
    timeout: int = _DEFAULT_ACTION_TIMEOUT
    state: str = "visible"


class WaitResponse(BaseModel):
    """Wait result — open-ended (depends on the wait condition)."""

    model_config = ConfigDict(extra="allow")


# --- Upload ---


class UploadRequest(BaseModel):
    index: int
    files: list[str]


class UploadResponse(BaseModel):
    """Upload result — typically `{uploaded: N}` plus action feedback."""

    model_config = ConfigDict(extra="allow")


# --- Frame ---


class FrameListResponse(BaseModel):
    frames: list[dict[str, Any]]
    count: int


class FrameFocusRequest(BaseModel):
    name: str | None = None
    url: str | None = None
    main: bool = False


class FrameFocusResponse(BaseModel):
    """Frame-focus result — surfaces the active frame's identifiers."""

    model_config = ConfigDict(extra="allow")


# --- Bridge ---


class BridgeOpResponse(BaseModel):
    """Bridge claim/finalize result — payload comes from the extension verbatim."""

    model_config = ConfigDict(extra="allow")


# --- Health ---


class HealthResponse(BaseModel):
    """Daemon liveness + rich state introspection."""

    model_config = ConfigDict(extra="allow")

    ok: Literal[True] = True
    service: str = "agentcloak-daemon"
    stealth_tier: str | None = None
    seq: int | None = None
    capture_recording: bool | None = None
    capture_entries: int | None = None
    current_url: str | None = None
    current_title: str | None = None
    local_proxy: dict[str, Any] | None = None
