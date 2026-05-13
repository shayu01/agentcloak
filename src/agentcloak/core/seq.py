"""Monotonic sequence counter and event ring buffer."""

from collections import deque
from dataclasses import dataclass, field

__all__ = ["RingBuffer", "SeqCounter", "SeqEvent"]


@dataclass(frozen=True)
class SeqEvent:
    """A recorded action with its sequence number."""

    seq: int
    kind: str
    data: dict[str, object] = field(default_factory=dict[str, object])


class SeqCounter:
    """Global monotonic counter, incremented only by mutating actions."""

    def __init__(self, start: int = 0) -> None:
        self._value = start
        self._last_action_seq = 0

    @property
    def value(self) -> int:
        return self._value

    @property
    def last_action_seq(self) -> int:
        """Seq of the most recent user-initiated mutating action."""
        return self._last_action_seq

    def increment(self) -> int:
        self._value += 1
        return self._value

    def increment_action(self) -> int:
        """Increment seq AND mark this as a user-initiated action."""
        self._value += 1
        self._last_action_seq = self._value
        return self._value


class RingBuffer:
    """Fixed-capacity event buffer supporting `since` queries."""

    def __init__(self, *, capacity: int = 1000) -> None:
        self._capacity = capacity
        self._events: deque[SeqEvent] = deque()

    @property
    def capacity(self) -> int:
        return self._capacity

    def __len__(self) -> int:
        return len(self._events)

    def append(self, event: SeqEvent) -> None:
        if len(self._events) >= self._capacity:
            self._events.popleft()
        self._events.append(event)

    def since(self, seq: int) -> list[SeqEvent]:
        return [e for e in self._events if e.seq > seq]

    def all(self) -> list[SeqEvent]:
        return list(self._events)
