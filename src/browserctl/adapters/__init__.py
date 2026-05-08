"""Site adapters — reusable site-specific automation."""

from browserctl.adapters.context import AdapterContext
from browserctl.adapters.executor import execute_adapter
from browserctl.adapters.registry import adapter, get_registry
from browserctl.adapters.types import AdapterEntry, AdapterMeta, Arg

__all__ = [
    "AdapterContext",
    "AdapterEntry",
    "AdapterMeta",
    "Arg",
    "adapter",
    "execute_adapter",
    "get_registry",
]
