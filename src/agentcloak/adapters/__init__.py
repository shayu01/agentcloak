"""Site adapters — reusable site-specific automation."""

from agentcloak.adapters.context import AdapterContext
from agentcloak.adapters.executor import execute_adapter
from agentcloak.adapters.registry import adapter, get_registry
from agentcloak.adapters.types import AdapterEntry, AdapterMeta, Arg

__all__ = [
    "AdapterContext",
    "AdapterEntry",
    "AdapterMeta",
    "Arg",
    "adapter",
    "execute_adapter",
    "get_registry",
]
