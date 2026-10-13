"""Event calendar.

SIMAN processes an entity through consecutive blocks until it reaches a block
that consumes time (DELAY, transfer) or holds it (QUEUE before SEIZE, WAIT, ...).
Entities that become ready "now" (for example, a queued entity that obtains a
resource released by another entity) go on the current event chain and run, in
FIFO order, before the clock advances. Future events live in a heap ordered by
(time, priority, insertion sequence).
"""

from __future__ import annotations

import heapq
import itertools
import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(order=True)
class Event:
    time: float
    priority: float
    seq: int
    action: Callable[[], Any] = field(compare=False)
    entity: Any = field(compare=False, default=None)
    cancelled: bool = field(compare=False, default=False)

    def cancel(self) -> None:
        self.cancelled = True


class Calendar:
    def __init__(self) -> None:
        self.now = 0.0
        self._heap: list[Event] = []
        self._current: deque[Event] = deque()
        self._seq = itertools.count()

    def schedule(self, delay: float, action: Callable[[], Any], entity: Any = None,
                 priority: float = 0.0) -> Event:
        if delay < 0 or math.isnan(delay):
            raise ValueError(f"negative or NaN delay {delay!r}")
        ev = Event(self.now + delay, priority, next(self._seq), action, entity)
        if delay == 0:
            self._current.append(ev)
        else:
            heapq.heappush(self._heap, ev)
        return ev

    def schedule_at(self, time: float, action: Callable[[], Any], entity: Any = None,
                    priority: float = 0.0) -> Event:
        return self.schedule(max(0.0, time - self.now), action, entity, priority)

    def cancel_entity(self, entity: Any) -> Event | None:
        """Remove an entity's pending future event (ZAP). Returns it, or None."""
        for ev in itertools.chain(self._current, self._heap):
            if ev.entity is entity and not ev.cancelled:
                ev.cancel()
                return ev
        return None

    def peek_time(self) -> float:
        if self._current:
            return self.now
        while self._heap and self._heap[0].cancelled:
            heapq.heappop(self._heap)
        return self._heap[0].time if self._heap else math.inf

    def pop(self) -> Event | None:
        while self._current:
            ev = self._current.popleft()
            if not ev.cancelled:
                return ev
        while self._heap:
            ev = heapq.heappop(self._heap)
            if ev.cancelled:
                continue
            # Everything due at the same instant is treated as current.
            self.now = ev.time
            return ev
        return None

    def clear(self) -> None:
        self._heap.clear()
        self._current.clear()
        self.now = 0.0

    def __len__(self) -> int:
        return sum(not e.cancelled for e in self._heap) + sum(not e.cancelled for e in self._current)
