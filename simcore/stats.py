"""Statistics collectors matching SIMAN's report categories.

* Tally         - observation-based (TALLIES / TALLY block): avg, min, max, n, half width
* TimePersistent - time-weighted (DSTATS / CSTATS): avg, min, max, final value, half width
* Counter       - COUNTERS: integer count with optional limit
* Frequency     - FREQUENCIES: time spent per category/value range

Half width is the 95% confidence half width from batch means with a von Neumann test
for correlated batches (see `batch_means_half_width`; Law & Kelton, Simulation Modeling
and Analysis, ch. 9).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Hashable

# Student t quantiles: index = number of batches k, value = t(0.975, k - 1), as printed
# in Arena reports; then fixed steps for larger k.
_ARENA_T = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776, 6: 2.571, 7: 2.447, 8: 2.365, 9: 2.306,
            10: 2.262, 11: 2.228, 12: 2.201, 13: 2.179, 14: 2.16, 15: 2.145, 16: 2.131, 17: 2.12,
            18: 2.11, 19: 2.101, 20: 2.093, 21: 2.086, 22: 2.08, 23: 2.074, 24: 2.069, 25: 2.064,
            26: 2.06, 27: 2.056, 28: 2.052, 29: 2.048, 30: 2.045}


def arena_t(k: int) -> float:
    """t multiplier for k batches (or k replications)."""
    if k < 2:
        return math.inf
    if k < 31:
        return _ARENA_T[k]
    for limit, t in ((41, 2.04), (51, 2.02), (101, 2.01), (201, 1.98), (500, 1.97)):
        if k < limit:
            return t
    return 1.96


def t975(df: int) -> float:
    return arena_t(df + 1) if df > 0 else math.nan


def mean_half_width(values: list[float]) -> float:
    """95% half width of the mean of independent values (e.g. replication results)."""
    n = len(values)
    if n < 2:
        return math.nan
    m = sum(values) / n
    var = sum((v - m) ** 2 for v in values) / (n - 1)
    return arena_t(n) * math.sqrt(var / n)


# Batch-means settings: at least 20 batches (else "Insufficient"), batches of 16
# observations to start, merged in pairs when there are 40, and the von Neumann test
# for correlation (else "Correlated"), as the SIMAN manuals describe the half width.
MIN_BATCHES = 20
MAX_BATCHES = 40
INITIAL_BATCH = 16
INSUFFICIENT = math.nan   # reported as "(Insufficient)"
CORRELATED = math.inf     # reported as "(Correlated)"


def batch_means_half_width(batch_means: list[float]) -> float:
    """Half width from batch means with a von Neumann correlation test.

    NaN = "(Insufficient)": fewer than 20 batches.  +inf = "(Correlated)".
    """
    k = len(batch_means)
    if k < MIN_BATCHES:
        return INSUFFICIENT
    m = sum(batch_means) / k
    ss = sum((b - m) ** 2 for b in batch_means)
    sd = sum((batch_means[i] - batch_means[i + 1]) ** 2 for i in range(k - 1))
    c = 1.0 - sd / (2.0 * ss) if ss > 0 else 0.0
    sigma = math.sqrt((k - 2) / (k * k - 1.0))
    if not (-1.96 <= c / sigma <= 1.96):
        return CORRELATED
    return arena_t(k) * math.sqrt(ss / (k - 1)) / math.sqrt(k)


class _Batcher:
    """Batches of INITIAL_BATCH observations (or time units); pairs merge at MAX_BATCHES."""

    def __init__(self, initial: float = INITIAL_BATCH) -> None:
        self.size = float(initial)
        self.means: list[float] = []
        self._acc = 0.0
        self._w = 0.0

    def add(self, value: float, weight: float = 1.0) -> None:
        if self._w + weight < self.size:  # common case: batch not yet full
            self._acc += value * weight
            self._w += weight
            return
        while weight > 0:
            take = min(weight, self.size - self._w)
            self._acc += value * take
            self._w += take
            weight -= take
            if self._w >= self.size - 1e-12:
                self.means.append(self._acc / self._w)
                self._acc = self._w = 0.0
                if len(self.means) >= MAX_BATCHES:
                    self.means = [(a + b) / 2 for a, b in zip(self.means[::2], self.means[1::2])]
                    self.size *= 2

    def half_width(self) -> float:
        return batch_means_half_width(self.means)


@dataclass
class Tally:
    name: str
    n: int = 0
    total: float = 0.0
    sumsq: float = 0.0
    min: float = math.inf
    max: float = -math.inf
    _batch: _Batcher = field(default_factory=_Batcher, repr=False)

    def record(self, value: float) -> None:
        self.n += 1
        self.total += value
        self.sumsq += value * value
        if value < self.min:
            self.min = value
        if value > self.max:
            self.max = value
        self._batch.add(value)

    @property
    def average(self) -> float:
        return self.total / self.n if self.n else math.nan

    @property
    def std(self) -> float:
        if self.n < 2:
            return math.nan
        return math.sqrt(max(0.0, (self.sumsq - self.total ** 2 / self.n) / (self.n - 1)))

    @property
    def half_width(self) -> float:
        return self._batch.half_width()

    def clear(self) -> None:
        self.__init__(self.name)  # type: ignore[misc]


@dataclass
class TimePersistent:
    """Time-weighted statistic of a piecewise-constant value.

    Half width needs at least 320 value changes and 20 time batches."""

    name: str
    value: float = 0.0
    start: float = 0.0
    last: float = 0.0
    area: float = 0.0
    min: float = math.inf
    max: float = -math.inf
    changes: int = 0
    _batch: _Batcher = field(default_factory=lambda: _Batcher(1.0), repr=False)

    def __post_init__(self) -> None:
        self.min = self.max = self.value

    def update(self, now: float, new_value: float) -> None:
        dt = now - self.last
        if dt > 0:
            self.area += self.value * dt
            self._batch.add(self.value, dt)
        self.last = now
        if new_value != self.value:
            self.changes += 1
        self.value = new_value
        if new_value < self.min:
            self.min = new_value
        if new_value > self.max:
            self.max = new_value

    def average(self, now: float) -> float:
        span = now - self.start
        if span <= 0:
            return self.value
        return (self.area + self.value * (now - self.last)) / span

    def finalize(self, now: float) -> None:
        self.update(now, self.value)

    @property
    def half_width(self) -> float:
        if self.changes < 320:
            return INSUFFICIENT
        return self._batch.half_width()

    def clear(self, now: float) -> None:
        v = self.value
        self.__init__(self.name, value=v, start=now, last=now)  # type: ignore[misc]


@dataclass
class Counter:
    name: str
    limit: float = math.inf
    count: float = 0
    on_limit: object = None  # callable invoked when the limit is reached
    initial: float = 0       # Statistic module Initial Value, restored when statistics are cleared

    def increment(self, amount: float = 1) -> bool:
        self.count += amount
        if self.count >= self.limit:
            if callable(self.on_limit):
                self.on_limit()
            return True
        return False

    def clear(self) -> None:
        self.count = self.initial


@dataclass
class Frequency:
    """Time spent in each category (value or state name)."""

    name: str
    current: Hashable = None
    since: float = 0.0
    start: float = 0.0
    time_in: dict = field(default_factory=dict)
    entries: dict = field(default_factory=dict)

    def update(self, now: float, category: Hashable) -> None:
        if category == self.current:
            return
        self._close(now)
        self.current = category
        self.entries[category] = self.entries.get(category, 0) + 1

    def _close(self, now: float) -> None:
        if self.current is not None:
            self.time_in[self.current] = self.time_in.get(self.current, 0.0) + now - self.since
        self.since = now

    def report(self, now: float, excluded: tuple = ()) -> dict:
        self._close(now)
        total = sum(self.time_in.values()) or 1.0
        restricted = sum(t for c, t in self.time_in.items() if c not in excluded) or 1.0
        return {
            c: {
                "number": self.entries.get(c, 0),
                "avg_time": t / max(1, self.entries.get(c, 0)),
                "standard_percent": 100 * t / total,
                "restricted_percent": None if c in excluded else 100 * t / restricted,
            }
            for c, t in self.time_in.items()
        }

    def clear(self, now: float) -> None:
        cur = self.current
        self.__init__(self.name, start=now, since=now)  # type: ignore[misc]
        if cur is not None:
            self.update(now, cur)
