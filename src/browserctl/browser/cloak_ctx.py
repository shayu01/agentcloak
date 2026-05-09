"""CloakBrowser stealth backend — high-stealth launch via cloakbrowser package."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from browserctl.browser.patchright_ctx import PatchrightContext, _find_free_port
from browserctl.core.errors import BackendError
from browserctl.core.seq import RingBuffer, SeqCounter
from browserctl.core.types import StealthTier

__all__ = ["launch_cloak"]

_EXTENSIONS_DIR = Path(__file__).parent / "extensions"
TURNSTILE_PATCH_DIR = _EXTENSIONS_DIR / "turnstile_patch"


def _ensure_cloakbrowser() -> Any:
    try:
        import cloakbrowser  # pyright: ignore[reportMissingImports]

        return cloakbrowser
    except ImportError as exc:
        raise BackendError(
            error="stealth_not_installed",
            hint="CloakBrowser package is required for stealth mode",
            action="pip install browserctl[stealth]",
        ) from exc


def _build_extension_args(extensions: list[str] | None) -> list[str]:
    if not extensions:
        return []
    paths = ",".join(extensions)
    return [
        f"--disable-extensions-except={paths}",
        f"--load-extension={paths}",
    ]


class CloakContext(PatchrightContext):
    """PatchrightContext subclass that reports CLOAK stealth tier."""

    @property
    def stealth_tier(self) -> StealthTier:
        return StealthTier.CLOAK


async def launch_cloak(
    *,
    headless: bool = False,
    viewport_width: int = 1280,
    viewport_height: int = 800,
    profile_dir: Path | None = None,
    humanize: bool = True,
    extensions: list[str] | None = None,
    proxy_url: str | None = None,
) -> CloakContext:
    """Launch a CloakBrowser instance and return a CloakContext."""
    cb = _ensure_cloakbrowser()

    ext_args = _build_extension_args(extensions)

    # Allocate a free port for CDP; Chrome 90+ supports pipe+port coexistence.
    cdp_port = _find_free_port()
    all_args = ext_args + [f"--remote-debugging-port={cdp_port}"]

    seq_counter = SeqCounter()
    ring_buffer = RingBuffer()

    if profile_dir is not None:
        profile_dir.mkdir(parents=True, exist_ok=True)
        browser_context = await cb.launch_persistent_context_async(
            user_data_dir=str(profile_dir),
            headless=headless,
            args=all_args,
            humanize=humanize,
            backend="patchright",
            viewport={"width": viewport_width, "height": viewport_height},
        )

        pages = browser_context.pages
        page = pages[0] if pages else await browser_context.new_page()

        return CloakContext(
            page=page,
            browser=None,
            playwright=None,
            seq_counter=seq_counter,
            ring_buffer=ring_buffer,
            browser_context=browser_context,
            proxy_url=proxy_url,
            cdp_port=cdp_port,
        )

    browser = await cb.launch_async(
        headless=headless,
        args=all_args,
        humanize=humanize,
        backend="patchright",
    )

    ctx = await browser.new_context(
        viewport={"width": viewport_width, "height": viewport_height},
    )
    page = await ctx.new_page()

    return CloakContext(
        page=page,
        browser=browser,
        playwright=None,
        seq_counter=seq_counter,
        ring_buffer=ring_buffer,
        proxy_url=proxy_url,
        cdp_port=cdp_port,
    )
