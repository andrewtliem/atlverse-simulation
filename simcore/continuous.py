"""Combined discrete/continuous simulation (LEVELS, RATES, CONTINUOUS, CSTATS, DETECT).

Levels S are continuous state variables. Each level has a rate dS/dt that is either
a plain rate variable (changed by ASSIGN at discrete events) or an expression of
levels/variables (an ODE). Levels are integrated with classical RK4 using steps no
larger than `max_step`; DETECT blocks fire when a crossing expression passes a
threshold in a given direction, located to within `tolerance` by bisection.

Discrete events see levels brought up to the event time before they execute, and
the integrator re-plans its next step after every event, because rates may change.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from . import blocks as B
from .core import Simulation


class CStat:
    """Time-weighted statistic of a continuously varying value (trapezoidal rule)."""

    def __init__(self, name: str, value: float, now: float) -> None:
        self.name = name
        self.start = self.last = now
        self.value = value
        self.area = 0.0
        self.min = self.max = value

    def update(self, now: float, v: float) -> None:
        dt = now - self.last
        if dt > 0:
            self.area += (self.value + v) / 2 * dt
        self.last, self.value = now, v
        self.min, self.max = min(self.min, v), max(self.max, v)

    def average(self, now: float) -> float:
        span = now - self.start
        return self.value if span <= 0 else (self.area + self.value * (now - self.last)) / span

    def clear(self, now: float) -> None:
        self.__init__(self.name, self.value, now)


@dataclass(repr=False, eq=False)
class Detect(B.Block):
    """DETECT: Crossing Variable/expression, Direction (positive|negative|either), Threshold,
    Tolerance. A source block: each crossing creates an entity that continues to the next block."""

    crossing: Any = "S1"
    direction: str = "positive"
    threshold: Any = 0.0
    tolerance: float = 1e-6
    entity_type: str | None = None
    label: str | None = None

    def execute(self, sim, e):
        return None


class Continuous:
    def __init__(self, sim: Simulation, model) -> None:
        self.sim, self.model = sim, model
        sim._cont = self
        spec = model.continuous_spec
        self.max_step = spec["max_step"]
        self.min_step = spec["min_step"]
        self.levels: dict[str, float] = {n: float(s["init"]) for n, s in model.level_specs.items()}
        self.t = sim.now
        self.pending = None
        self.cstats = {n: CStat(n, self._eval(expr), sim.now) for n, expr in model.cstat_specs.items()}
        self.detects = [b for b in model.blocks if isinstance(b, Detect)]
        self._prev = {id(d): self._cross_value(d) for d in self.detects}

    # --- evaluation -----------------------------------------------------------------
    def _eval(self, expr) -> float:
        return float(self.sim.evaluate(expr))

    def _rates(self, levels: dict[str, float]) -> dict[str, float]:
        saved = self.levels
        self.levels = levels
        try:
            out = {}
            for n, s in self.model.level_specs.items():
                r = s["rate"]
                out[n] = 0.0 if r is None else self._eval(r)
            return out
        finally:
            self.levels = saved

    def _rk4(self, y: dict[str, float], h: float) -> dict[str, float]:
        k1 = self._rates(y)
        k2 = self._rates({n: y[n] + h / 2 * k1[n] for n in y})
        k3 = self._rates({n: y[n] + h / 2 * k2[n] for n in y})
        k4 = self._rates({n: y[n] + h * k3[n] for n in y})
        return {n: y[n] + h / 6 * (k1[n] + 2 * k2[n] + 2 * k3[n] + k4[n]) for n in y}

    def _cross_value(self, d: Detect) -> float:
        return self._eval(d.crossing) - self._eval(d.threshold)

    # --- time advance -------------------------------------------------------------------
    def advance_to(self, t: float) -> None:
        """Integrate levels from self.t to t (called before each discrete event)."""
        while self.t < t - 1e-15:
            h = min(self.max_step, t - self.t)
            self.levels = self._rk4(self.levels, h)
            self.t += h
            for c in self.cstats.values():
                c.update(self.t, self._eval(self.model.cstat_specs[c.name]))

    def plan(self) -> None:
        """After an event: schedule the next integration step or detected crossing."""
        if self.pending is not None:
            self.pending.cancel()
            self.pending = None
        for c in self.cstats.values():  # record jumps made by the event (dt = 0)
            c.update(self.sim.now, self._eval(self.model.cstat_specs[c.name]))
        for d in self.detects:
            self._prev[id(d)] = self._cross_value(d)
        if not self.model.level_specs:
            return
        rates = self._rates(self.levels)
        if all(r == 0 for r in rates.values()) and not self.detects_could_fire():
            return  # nothing changes until the next discrete event
        h = self.max_step
        y1 = self._rk4(self.levels, h)
        hit = self._first_crossing(self.levels, y1, h)
        if hit is not None:
            dt, d = hit
            self.pending = self.sim.cal.schedule(max(dt, 0.0), lambda d=d: self._fire(d), priority=-1)
        else:
            self.pending = self.sim.cal.schedule(h, lambda: None, priority=-1)

    def detects_could_fire(self) -> bool:
        return False

    def _crossed(self, d: Detect, before: float, after: float) -> bool:
        dirn = d.direction.lower()
        up = before < 0 <= after
        down = before > 0 >= after
        return up if dirn.startswith("pos") else down if dirn.startswith("neg") else (up or down)

    def _value_with(self, levels, d: Detect) -> float:
        saved = self.levels
        self.levels = levels
        try:
            return self._cross_value(d)
        finally:
            self.levels = saved

    def _first_crossing(self, y0, y1, h):
        best = None
        for d in self.detects:
            a, b = self._value_with(y0, d), self._value_with(y1, d)
            if not self._crossed(d, a, b):
                continue
            lo, hi = 0.0, h
            while hi - lo > max(d.tolerance, 1e-12):
                mid = (lo + hi) / 2
                if self._crossed(d, a, self._value_with(self._rk4(y0, mid), d)):
                    hi = mid
                else:
                    lo = mid
            if best is None or hi < best[0]:
                best = (hi, d)
        return best

    def _fire(self, d: Detect) -> None:
        self.pending = None
        e = self.sim.new_entity(d.entity_type, d.index + 1)
        self.sim.schedule_move(e, 0.0)


# --- model integration -------------------------------------------------------------------

def install(model) -> None:
    if getattr(model, "_continuous_installed", False):
        return
    model._continuous_installed = True
    model.level_specs = getattr(model, "level_specs", {})
    model.cstat_specs = getattr(model, "cstat_specs", {})
    model.continuous_spec = getattr(model, "continuous_spec", dict(max_step=0.1, min_step=1e-6))
    start, finish, collect = model.start, model.finish, model.collect
    resolver_name = None

    def start_cont(sim):
        start(sim)
        sim._cont = Continuous(sim, model)
        cal = sim.cal
        pop = cal.pop

        def pop_with_integration():
            t = cal.peek_time()
            if t != math.inf:
                sim._cont.advance_to(t)
            ev = pop()
            if ev is not None:
                act = ev.action

                def run_then_plan():
                    act()
                    sim._cont.plan()
                ev.action = run_then_plan
            return ev
        cal.pop = pop_with_integration
        sim._cont.plan()

    def finish_cont(sim):
        if sim.now != math.inf:
            sim._cont.advance_to(sim.now)
        finish(sim)

    def collect_cont(sim):
        res = collect(sim)
        res["continuous"] = {n: dict(average=c.average(sim.now), min=c.min, max=c.max, final=c.value)
                             for n, c in sim._cont.cstats.items()}
        res["levels"] = dict(sim._cont.levels)
        return res

    model.start, model.finish, model.collect = start_cont, finish_cont, collect_cont


def level(model, name: str, init: float = 0.0, rate: Any = None) -> None:
    """Define level `name`. rate: rate variable name or expression in levels (ODE)."""
    install(model)
    model.level_specs[name] = dict(init=init, rate=rate)


def cstat(model, name: str, expr: Any) -> None:
    install(model)
    model.cstat_specs[name] = expr


def settings(model, max_step: float = 0.1, min_step: float = 1e-6) -> None:
    install(model)
    model.continuous_spec = dict(max_step=max_step, min_step=min_step)
