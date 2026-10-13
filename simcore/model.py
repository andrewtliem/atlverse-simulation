"""Model: SIMAN experiment elements + block list, and the replication runner."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from . import blocks as B
from . import rng
from .core import (BUSY, FAILED, HOLD, IDLE, INACTIVE, Entity, Queue, Resource,
                   ResourceCost, Simulation, Variable)
from .expr import ExprError, evaluate
from .stats import Counter, Tally, TimePersistent, mean_half_width

TIME_UNITS = {"seconds": 1 / 3600, "minutes": 1 / 60, "hours": 1.0, "days": 24.0}


# --- Schedules and failures -----------------------------------------------------

@dataclass
class Schedule:
    """Piecewise-constant value over time: [(value, duration), ...], repeating.
    Used for resource capacity (Capacity type) or arrival rates (Arrival type)."""

    name: str
    segments: list
    kind: str = "capacity"   # capacity | arrival
    rule: str = "ignore"     # capacity decrease rule: ignore | wait | preempt
    repeat: bool = True
    scale: float = 1.0

    @property
    def cycle(self) -> float:
        return sum(d for _, d in self.segments)

    def value_at(self, t: float) -> float:
        if self.repeat and self.cycle > 0:
            t = t % self.cycle
        acc = 0.0
        for v, d in self.segments:
            if t < acc + d:
                return v * self.scale
            acc += d
        return self.segments[-1][0] * self.scale

    def next_arrival_gap(self, sim: Simulation) -> float:
        """Non-stationary Poisson arrivals by thinning (rate per hour in model time units)."""
        rmax = max(v for v, _ in self.segments) * self.scale
        if rmax <= 0:
            return math.inf
        s = sim.model.streams[rng.DEFAULT_STREAM]
        t = sim.now
        per_unit = 1 / sim.model.to_hours(1.0)
        while True:
            t += -math.log(s.u()) / (rmax / per_unit)
            if s.u() <= self.value_at(t) / rmax:
                return t - sim.now


@dataclass
class Failure:
    """FAILURES element: time-based (up time) or count-based (after N releases)."""

    name: str
    resources: list
    kind: str = "time"        # time | count
    up: Any = 100.0           # up time or count expression
    down: Any = 10.0          # down time expression
    rule: str = "ignore"      # ignore | wait | preempt
    uptime_in_state: str | None = None  # only count up time while resource is in this state


# --- Resolver -------------------------------------------------------------------

class Resolver:
    """Resolves names and function calls inside SIMAN expressions."""

    def __init__(self, sim: Simulation) -> None:
        self.sim = sim
        self.model = sim.model

    def evaluate(self, expr, entity=None):
        return evaluate(expr, self, entity)

    # names without arguments
    def name(self, n: str, e: Entity | None):
        sim, m = self.sim, self.model
        n = m._alias_back.get(n, n)
        u = n.upper()
        if e is not None and n in e.attrs:
            return e.attrs[n]
        if n in sim._vars:
            return sim._vars[n].get()
        cont = getattr(sim, "_cont", None)
        if cont is not None and n in cont.levels:
            return cont.levels[n]
        if n in m.static_specs:
            rec = m.station_recipe.get(e.station) if e is not None else None
            return m.recipe_specs.get(rec, {}).get(n, m.static_specs[n])
        if n in m.expressions:
            return self.evaluate(m.expressions[n], e)
        if u == "TNOW":
            return sim.now
        if u in ("NREP", "REP"):
            return sim.rep
        if u == "MREP":
            return m.replications
        if u == "TFIN":
            return m.replication_length
        if u == "J":
            return sim.j
        if u in ("TRUE", "FALSE"):
            return u == "TRUE"
        if u == "INF" or u == "INFINITE":
            return math.inf
        if e is not None:
            special = m.special_attr(e, n)
            if special is not _MISSING:
                return special
        if (n in m.resource_specs or n in m.queue_specs or n in m.sets or n in m.stations
                or n in m.entity_types or n in m.schedules or n in m.counter_specs or n in m.tally_specs
                or u.startswith("PICTURE.")):
            return n  # symbol name: functions accept it, Entity.Type == Part compares names
        if n in m.symbols:
            return m.symbols[n]
        if n.upper() in (s.upper() for s in ("IDLE", "BUSY", "FAILED", "INACTIVE")):
            return n.upper()
        if u in m.functions:  # zero-argument SIMAN variables such as NG
            return m.functions[u](sim, e)
        raise ExprError(f"unknown name {n!r}")

    # calls: functions, arrays, distributions
    def call(self, n: str, args: tuple, e: Entity | None):
        sim, m = self.sim, self.model
        n = m._alias_back.get(n, n)
        u = n.upper()
        if e is not None and n in e.attrs:
            return e.get(n, args)
        if n in sim._vars:
            return sim._vars[n].get(args)
        if u in rng.NAMES:
            meth = rng.NAMES[u]
            npar = rng.N_PARAMS.get(meth)
            args = list(args)
            stream = rng.DEFAULT_STREAM
            if npar is not None and len(args) > npar:
                stream = int(args.pop())
            elif npar is None and len(args) % 2 == 1:  # DISC/CONT with trailing stream
                stream = int(args.pop())
            return getattr(m.sampler, meth)(*args, m.streams[stream])
        if u in m.functions:
            return m.functions[u](sim, e, *args)
        if n in m.sets:
            return m.sets[n][int(args[0]) - 1]
        if n in m.tables:
            return m.tables[n](args[0])
        raise ExprError(f"unknown function or array {n}({', '.join(map(str, args))})")


_MISSING = object()


def _q(sim, e, q):
    return sim.model.queue(sim, q)


def _r(sim, e, r):
    return sim.model.resource(sim, r)


def _diff(e, key):
    if not e.stack:
        raise RuntimeError(f"Diff.* used but {e} has an empty stack")
    cur = e.start_time if key == "start_time" else e.costs[key]
    return cur - e.stack[-1][key]


BUILTIN_FUNCTIONS: dict[str, Callable] = {
    # queues
    "NQ": lambda sim, e, q: len(_q(sim, e, q)),
    "AQUE": lambda sim, e, q, rank, attr: _q(sim, e, q).entities[int(rank) - 1].attrs[attr],
    "ENTATRANK": lambda sim, e, rank, q: _q(sim, e, q).entities[int(rank) - 1].serial,
    # resources
    "NR": lambda sim, e, r: _r(sim, e, r).busy,
    "MR": lambda sim, e, r: _r(sim, e, r).capacity,
    "IRF": lambda sim, e, r: 1 if _r(sim, e, r).failed else 0,
    "STATE": lambda sim, e, r: _r(sim, e, r).state,
    "RESSEIZES": lambda sim, e, r: _r(sim, e, r).seize_count,
    "RESUTIL": lambda sim, e, r: _r(sim, e, r).util.average(sim.now),
    # counters / tallies / stats
    "NC": lambda sim, e, c: sim.model.counter(sim, c).count,
    "SCHEDVALUE": lambda sim, e, s: sim.model.schedules[s].value_at(sim.now),
    "TAVG": lambda sim, e, t: sim.model.tally(sim, t).average,
    "TNUM": lambda sim, e, t: sim.model.tally(sim, t).n,
    "TMIN": lambda sim, e, t: sim.model.tally(sim, t).min,
    "TMAX": lambda sim, e, t: sim.model.tally(sim, t).max,
    "TSTD": lambda sim, e, t: sim.model.tally(sim, t).std,
    "THALF": lambda sim, e, t: sim.model.tally(sim, t).half_width,
    "DAVG": lambda sim, e, d: sim.model.dstat(sim, d).average(sim.now),
    "DMIN": lambda sim, e, d: sim.model.dstat(sim, d).min,
    "DMAX": lambda sim, e, d: sim.model.dstat(sim, d).max,
    # entities
    "ENTITIESIN": lambda sim, e, t=None: sim.entities_in.get(t, 0) if t else sum(sim.entities_in.values()),
    "ENTITIESOUT": lambda sim, e, t=None: sim.entities_out.get(t, 0) if t else sum(sim.entities_out.values()),
    "ENTITIESWIP": lambda sim, e, t=None: sim.wip.get(t, 0) if t else sum(sim.wip.values()),
    "NSTO": lambda sim, e, s: sim._storages.get(s, 0),
    "NB": lambda sim, e, b: sim._blockages.get(b, 0),
    "NSG": lambda sim, e: len(e.members) if e else 0,
    "NG": lambda sim, e: len(e.members) if e else 0,
    "MEMBER": lambda sim, e, setname, i: sim.model.sets[setname][int(i) - 1],
    "MEMIDX": lambda sim, e, setname, val: sim.model.sets[setname].index(val) + 1,
    "NUMMEM": lambda sim, e, setname: len(sim.model.sets[setname]),
    "NE": lambda sim, e, station: sim._at_station.get(station, 0),
    # STACK differences (current - top of stack)
    **{f"DIFF.{k.upper()}": (lambda key: (lambda sim, e: _diff(e, key)))(v) for k, v in {
        "StartTime": "start_time", "VATime": "va_time", "VACost": "va_cost", "NVATime": "nva_time",
        "NVACost": "nva_cost", "WaitTime": "wait_time", "WaitCost": "wait_cost", "TranTime": "tran_time",
        "TranCost": "tran_cost", "OtherTime": "other_time", "OtherCost": "other_cost"}.items()},
    # math (SIMAN names)
    "ABS": lambda sim, e, x: abs(x),
    "AINT": lambda sim, e, x: float(int(x)),
    "ANINT": lambda sim, e, x: float(round(x)),
    "AMOD": lambda sim, e, a, b: math.fmod(a, b),
    "MOD": lambda sim, e, a, b: int(a) % int(b),
    "INT": lambda sim, e, x: int(x),
    "NINT": lambda sim, e, x: int(round(x)),
    "EP": lambda sim, e, x: math.exp(x),
    "EXP": lambda sim, e, x: math.exp(x),
    "LN": lambda sim, e, x: math.log(x),
    "LOG": lambda sim, e, x: math.log10(x),
    "SQRT": lambda sim, e, x: math.sqrt(x),
    "SIN": lambda sim, e, x: math.sin(x),
    "COS": lambda sim, e, x: math.cos(x),
    "TAN": lambda sim, e, x: math.tan(x),
    "ATAN": lambda sim, e, x: math.atan(x),
    "ACOS": lambda sim, e, x: math.acos(x),
    "ASIN": lambda sim, e, x: math.asin(x),
    "HCOS": lambda sim, e, x: math.cosh(x),
    "HSIN": lambda sim, e, x: math.sinh(x),
    "HTAN": lambda sim, e, x: math.tanh(x),
    "MN": lambda sim, e, *a: min(a),
    "MX": lambda sim, e, *a: max(a),
    "AMIN1": lambda sim, e, *a: min(a),
    "AMAX1": lambda sim, e, *a: max(a),
}


# --- Model ---------------------------------------------------------------------------------

class Model:
    def __init__(self, name: str = "Model", time_units: str = "minutes") -> None:
        self.name = name
        self.time_units = time_units
        self.blocks: list[B.Block] = []
        self.labels: dict[str, int] = {}
        self.anon_labels: dict[int, str] = {}
        self.attribute_defaults: dict[str, Any] = {}
        self.variable_specs: dict[str, dict] = {}
        self.expressions: dict[str, Any] = {}
        self.resource_specs: dict[str, dict] = {}
        self.queue_specs: dict[str, dict] = {}
        self.counter_specs: dict[str, dict] = {}
        self.tally_specs: dict[str, dict] = {}
        self.dstat_specs: dict[str, Any] = {}
        self.outputs: dict[str, Any] = {}
        self.frequency_specs: dict[str, dict] = {}
        self.sets: dict[str, list] = {}
        self.tables: dict[str, Callable] = {}
        self.schedules: dict[str, Schedule] = {}
        self.failures: list[Failure] = []
        self.sequences: dict[str, list] = {}
        self.stations: set[str] = set()
        self.storages: set[str] = set()
        self.entity_types: dict[str, dict] = {}
        self.symbols: dict[str, Any] = {}
        self.files: dict[str, dict] = {}
        self.functions = dict(BUILTIN_FUNCTIONS)
        self.seeds: dict[int, tuple[int, str]] = {}
        self.rng_mode = "arena"            # "arena": reproduce Arena's samplers; "exact": exact ones
        self.disable_randomness = False    # every distribution returns its mean
        # run setup (REPLICATE element)
        self.replications = 1
        self.replication_length = math.inf
        self.warmup = 0.0
        self.terminating_condition = None
        self.monitor = None  # callable(sim) -> True to stop the run; called every 2000 events
        self.initialize_system = True
        self.initialize_stats = True
        self.trace = False
        self.animate = False
        self.record_entity_statistics = True
        self.no_report: set[str] = set()  # names whose statistics are left out of the results
        # wiring filled by bind()
        self.wait_blocks: list[B.Wait] = []
        self.scan_blocks: list[B.Scan] = []
        self.match_blocks: dict[str, list] = {}
        self.station_index: dict[str, int] = {}
        self.blockage_specs: dict[str, Any] = {}
        self.onchange_watchers: dict[str, list] = {}
        self.arrival_specs: list[dict] = []
        self.static_specs: dict[str, Any] = {}
        self.recipe_specs: dict[str, dict] = {}
        self.station_recipe: dict[str, str] = {}
        self.station_area: dict[str, str] = {}
        self.area_parent: dict[str, str | None] = {}
        self.proceed_blocks: dict[str, list] = {}
        self.waiters: dict[str, list] = {}
        self.tally_last: dict = {}
        self.output: list[str] = []
        self._bound = False

    # --- builder API --------------------------------------------------------------
    def add(self, *blocks: B.Block) -> "Model":
        for b in blocks:
            b.index = len(self.blocks)
            if b.label:
                if b.label in self.labels:
                    raise ValueError(f"duplicate label {b.label}")
                self.labels[b.label] = b.index
            self.blocks.append(b)
        self._bound = False
        return self

    def attribute(self, name: str, init: Any = 0.0, dims: tuple = ()) -> "Model":
        self.attribute_defaults[name] = _array(dims, init)
        return self

    def attributes_default(self, name: str, init: Any = 0.0) -> "Model":
        """Declare an attribute unless it already exists."""
        self.attribute_defaults.setdefault(name, init)
        return self

    def variable(self, name: str, init: Any = 0.0, dims: tuple = (), track: bool = False,
                 clear: str = "system") -> "Model":
        """clear: system (reset each replication), statistics (also reset when statistics are
        cleared at the warm-up) or none (keep the value from the previous replication)."""
        self.variable_specs[name] = dict(init=init, dims=dims, track=track, clear=clear.lower())
        return self

    def expression(self, name: str, expr: Any) -> "Model":
        self.expressions[name] = expr
        return self

    def resource(self, name, capacity: Any = 1, schedule: str | None = None,
                 busy_per_hour: float = 0.0, idle_per_hour: float = 0.0, per_use: float = 0.0,
                 stateset: dict | None = None, schedule_rule: str | None = None,
                 initial_state: str | None = None):
        """Model.resource(name, capacity=...) defines; Model.resource(sim, name) looks up."""
        if isinstance(name, Simulation):
            r = name._resources.get(capacity)
            if r is None:
                raise KeyError(f"unknown resource {capacity!r}")
            return r
        self.resource_specs[name] = dict(capacity=capacity, schedule=schedule,
                                         cost=ResourceCost(busy_per_hour, idle_per_hour, per_use),
                                         stateset=stateset or {}, schedule_rule=schedule_rule,
                                         initial_state=initial_state)
        return self

    def queue(self, sim_or_name, name: str | None = None, ranking: str = "FIFO",
              attribute: str | None = None):
        """Model.queue(name, ranking=...) defines; Model.queue(sim, name) looks up."""
        if isinstance(sim_or_name, Simulation):
            q = sim_or_name._queues.get(name)
            if q is None:
                if name not in self.queue_specs:
                    raise KeyError(f"unknown queue {name!r}")
                spec = self.queue_specs[name]
                q = sim_or_name._queues[name] = Queue(sim_or_name, name, spec["ranking"], spec["attribute"])
            return q
        self.queue_specs[sim_or_name] = dict(ranking=ranking, attribute=attribute)
        return self

    def ensure_queue(self, name: str) -> None:
        self.queue_specs.setdefault(name, dict(ranking="FIFO", attribute=None))

    def counter(self, sim_or_name, name: str | None = None, limit: float = math.inf, initial: float = 0):
        if isinstance(sim_or_name, Simulation):
            c = sim_or_name._counters.get(name)
            if c is None:
                spec = self.counter_specs.setdefault(name, dict(limit=math.inf))
                init = spec.get("initial") or 0
                c = sim_or_name._counters[name] = Counter(name, spec["limit"], init, initial=init)
                if spec["limit"] != math.inf:
                    c.on_limit = lambda s=sim_or_name: setattr(s, "terminated", True)
            return c
        self.counter_specs[sim_or_name] = dict(limit=limit, initial=initial or 0)
        return self

    def tally(self, sim_or_name, name: str | None = None):
        if isinstance(sim_or_name, Simulation):
            t = sim_or_name._tallies.get(name)
            if t is None:
                t = sim_or_name._tallies[name] = Tally(name)
            return t
        self.tally_specs[sim_or_name] = {}
        return self

    def dstat(self, sim_or_name, name_or_expr=None, name: str | None = None):
        if isinstance(sim_or_name, Simulation):
            return sim_or_name._dstats[name_or_expr]
        self.dstat_specs[sim_or_name] = name_or_expr
        return self

    def frequency(self, name: str, expr: Any, categories: list | None = None,
                  excluded: tuple = ()) -> "Model":
        """FREQUENCIES element: time spent per value of `expr`, or per category
        [(label, low, high), ...] where low < value <= high."""
        self.frequency_specs[name] = dict(expr=expr, categories=categories, excluded=tuple(excluded))
        return self

    def _frequency_category(self, spec, v):
        """A category is a constant (low == high: the value itself) or a range low < value <= high."""
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        if spec["categories"] is None:
            return v
        for lab, lo, hi in spec["categories"]:
            if lo == hi:
                if v == lo:
                    return lab
            elif isinstance(v, (int, float)) and isinstance(lo, (int, float)) and lo < v <= hi:
                return lab
        return "OUT OF RANGE"

    def output_stat(self, name: str, expr: Any) -> "Model":
        """OUTPUTS element: expression evaluated at the end of each replication."""
        self.outputs[name] = expr
        return self

    def arrival(self, at: str, kind: str = "time", time: Any = 0.0, batch: Any = 1,
                every: Any = None, entity_type: str | None = None) -> "Model":
        """ARRIVALS element. at: block label or station name. kind: time | first | last | every."""
        self.arrival_specs.append(dict(at=at, kind=kind.lower(), time=time, batch=batch, every=every,
                                       entity_type=entity_type))
        return self

    def static(self, name: str, default: Any = 0.0) -> "Model":
        """STATICS element: location-dependent value, resolved via the entity's station recipe."""
        self.static_specs[name] = default
        return self

    def recipe(self, name: str, values: dict, stations: list | None = None) -> "Model":
        """RECIPES element; `stations` assigns the recipe to stations (STATIONS element)."""
        self.recipe_specs[name] = dict(values)
        for st in stations or []:
            self.station_recipe[st] = name
        return self

    def activity_area(self, name: str, stations: list | None = None, parent: str | None = None) -> "Model":
        """ActivityAreas element: stations belong to an area; statistics roll up to parents."""
        self.area_parent[name] = parent
        for st in stations or []:
            self.station_area[st] = name
        return self

    def _areas_of(self, station: str | None) -> list[str]:
        out, a = [], self.station_area.get(station) if station else None
        while a is not None:
            out.append(a)
            a = self.area_parent.get(a)
        return out

    def blockage(self, name: str, initial: Any = 0) -> "Model":
        """BLOCKAGES element."""
        self.blockage_specs[name] = initial
        return self

    def change_blockage(self, sim: Simulation, name: str, delta: int) -> None:
        sim._blockages[name] = max(0, sim._blockages.get(name, 0) + delta)
        if sim._blockages[name] == 0:
            # Release waiting entities one at a time, lowest PROCEED priority first,
            # then longest waiting (QTIME global priority).
            while True:
                cands = [p for p in self.proceed_blocks.get(name, []) if p.queue_of(sim).entities and p._clear(sim)]
                if not cands:
                    break
                cands.sort(key=lambda p: (p.priority_value(sim), p.queue_of(sim).entities[0].queue_enter))
                cands[0].release_one(sim)

    def set(self, name: str, members: list) -> "Model":
        self.sets[name] = list(members)
        return self

    def table(self, name: str, low: float, step: float, values: list) -> "Model":
        def f(x, low=low, step=step, values=values):
            p = (x - low) / step
            if p <= 0:
                return values[0]
            if p >= len(values) - 1:
                return values[-1]
            i = int(p)
            return values[i] + (p - i) * (values[i + 1] - values[i])
        self.tables[name] = f
        return self

    def schedule(self, name: str, segments: list, kind: str = "capacity", rule: str = "ignore",
                 repeat: bool = True, scale: float = 1.0) -> "Model":
        self.schedules[name] = Schedule(name, segments, kind, rule, repeat, scale)
        return self

    def failure(self, name: str, resources: list, kind: str = "time", up: Any = 100.0,
                down: Any = 10.0, rule: str = "ignore", uptime_in_state: str | None = None) -> "Model":
        self.failures.append(Failure(name, resources, kind, up, down, rule, uptime_in_state or None))
        return self

    def sequence(self, name: str, steps: list) -> "Model":
        """steps: [station or (station, {attr: expr, ...}), ...]"""
        self.sequences[name] = [s if isinstance(s, tuple) else (s, {}) for s in steps]
        return self

    def entity_type(self, name: str, **spec) -> "Model":
        self.entity_types[name] = spec
        return self

    def seed(self, stream: int, seed: int, reinit: str = "no") -> "Model":
        self.seeds[stream] = (seed, reinit)
        return self

    def file(self, name: str, path: str, mode: str = "r", sep: str | None = None) -> "Model":
        self.files[name] = dict(path=path, mode=mode, sep=sep)
        return self

    def function(self, name: str, fn: Callable) -> "Model":
        """User function callable from expressions: fn(sim, entity, *args)."""
        self.functions[name.upper()] = fn
        return self

    def replicate(self, replications: int = 1, length: float = math.inf, warmup: float = 0.0,
                  terminating_condition: Any = None, initialize_system: bool = True,
                  initialize_stats: bool = True) -> "Model":
        self.replications = replications
        self.replication_length = length
        self.warmup = warmup
        self.terminating_condition = terminating_condition
        self.initialize_system = initialize_system
        self.initialize_stats = initialize_stats
        return self

    # --- binding ------------------------------------------------------------------------
    def bind(self) -> None:
        if self._bound:
            return
        self._build_aliases()
        self.wait_blocks.clear()
        self.scan_blocks.clear()
        self.onchange_watchers.clear()
        self.match_blocks.clear()
        self.waiters.clear()
        self.station_index.clear()
        for b in self.blocks:
            if isinstance(b, B.Station):
                self.stations.add(b.station)
            if isinstance(b, (B.Store, B.Unstore)):
                self.storages.add(b.storage)
            if isinstance(b, B.QueueBlock):
                self.ensure_queue(b.queue)
            if isinstance(b, (B.Count,)):
                self.counter_specs.setdefault(b.counter, dict(limit=math.inf))
            if isinstance(b, B.TallyBlock):
                self.tally_specs.setdefault(b.tally, {})
        for b in self.blocks:
            b.bind(self)
        self._bind_structured()
        self._bound = True

    def _bind_structured(self) -> None:
        if_stack: list[list[int]] = []
        while_stack: list[int] = []
        for b in self.blocks:
            if isinstance(b, B.ElseIf) or isinstance(b, B.Else):
                if not if_stack:
                    raise ValueError(f"{b} without IF")
                prev = self.blocks[if_stack[-1][-1]]
                prev.false_target = b.index
                if_stack[-1].append(b.index)
            elif isinstance(b, B.If):
                if_stack.append([b.index])
            elif isinstance(b, B.EndIf):
                if not if_stack:
                    raise ValueError(f"{b} without IF")
                chain = if_stack.pop()
                last = self.blocks[chain[-1]]
                if isinstance(last, B.If):
                    last.false_target = b.index
                for ix in chain:
                    self.blocks[ix].endif = b.index
            elif isinstance(b, B.While):
                while_stack.append(b.index)
            elif isinstance(b, B.EndWhile):
                w = self.blocks[while_stack.pop()]
                w.end_index = b.index
                b.while_index = w.index
        if if_stack or while_stack:
            raise ValueError("unterminated IF or WHILE")

    # --- symbol names with spaces (Arena allows "Teller Service.Queue" in expressions) ---
    _aliases: list = []
    _alias_back: dict = {}

    def _symbol_names(self) -> set[str]:
        names = set(self.resource_specs) | set(self.queue_specs) | set(self.variable_specs) | \
            set(self.attribute_defaults) | set(self.sets) | set(self.counter_specs) | set(self.tally_specs) | \
            set(self.expressions) | set(self.stations) | set(self.storages) | set(self.dstat_specs) | \
            set(self.entity_types) | set(self.blockage_specs) | set(self.tables)
        for b in self.blocks:
            if isinstance(b, B.Station):
                names.add(b.station)
            if isinstance(b, B.QueueBlock):
                names.add(b.queue)
        return names

    def _build_aliases(self) -> None:
        import re as _re
        odd = sorted((n for n in self._symbol_names() if isinstance(n, str) and _re.search(r"[^\w.]", n)),
                     key=len, reverse=True)
        self._aliases = [(_re.compile(r"(?<![\w.])" + _re.escape(n) + r"(?![\w])"), f"__sym{i}__", n)
                         for i, n in enumerate(odd)]
        self._alias_back = {mangled: n for _, mangled, n in self._aliases}
        self._alias_cache: dict[str, str] = {}

    def alias_expr(self, src: str) -> str:
        out = self._alias_cache.get(src)
        if out is None:
            parts = re.split(r'("[^"]*")', src)  # quoted text is a string, not a symbol
            for i in range(0, len(parts), 2):
                for rx, mangled, _ in self._aliases:
                    parts[i] = rx.sub(mangled, parts[i])
            out = "".join(parts)
            self._alias_cache[src] = out
        return out

    def label_index(self, label: str) -> int:
        if label.startswith("__ix"):
            return int(label[4:])
        try:
            return self.labels[label]
        except KeyError:
            raise KeyError(f"unknown block label {label!r}") from None

    def register_waiter(self, resource: str, block) -> None:
        lst = self.waiters.setdefault(resource, [])
        if block not in lst:
            lst.append(block)

    # --- runtime helpers -------------------------------------------------------------
    def resolver(self, sim: Simulation) -> Resolver:
        r = getattr(sim, "_resolver", None)
        if r is None:
            r = sim._resolver = Resolver(sim)
        return r

    def to_hours(self, t: float) -> float:
        return t * TIME_UNITS[self.time_units]

    def resource_name(self, sim: Simulation, rexpr: Any, e: Entity | None) -> str:
        if isinstance(rexpr, str) and rexpr in self.resource_specs:
            return rexpr
        v = sim.evaluate(rexpr, e)
        if isinstance(v, str) and v in self.resource_specs:
            return v
        if isinstance(v, (int, float)) and v == int(v) and 1 <= v <= len(self.resource_specs):
            return list(self.resource_specs)[int(v) - 1]  # Arena: a resource's number
        raise KeyError(f"{rexpr!r} does not name a resource (got {v!r})")

    def select_resource(self, sim: Simulation, sel: dict, e: Entity, exclude=()) -> Resource | None:
        """Resource Selection Rules: CYC, RAN, POR, LNB, SNB, LRC, SRC, ER (specific member)."""
        if not isinstance(sel, dict):  # older callers pass the block
            sel = sel.select
        members = [self.resource(sim, n) for n in self.sets[sel["set"]]]
        units = int(sim.evaluate(sel.get("units", 1), e))
        rule = str(sel.get("rule", "CYC")).upper()
        if rule == "ER":
            r = members[int(sim.evaluate(sel.get("index", 1), e)) - 1]
            return r if r.available >= units else None
        free = [r for r in members if r.available >= units and r.name not in exclude]
        if not free:
            return None
        if rule == "POR":
            return free[0]
        if rule == "RAN":
            return free[int(self.streams[rng.DEFAULT_STREAM].u() * len(free))]
        if rule == "LNB":
            return max(free, key=lambda r: r.busy)
        if rule == "SNB":
            return min(free, key=lambda r: r.busy)
        if rule == "LRC":
            return max(free, key=lambda r: r.available)
        if rule == "SRC":
            return min(free, key=lambda r: r.available)
        # CYC: first available member after the previously selected one
        start = sel.get("_cyc", 0)
        for k in range(len(members)):
            r = members[(start + k) % len(members)]
            if r in free:
                sel["_cyc"] = (members.index(r) + 1) % len(members)
                return r
        return None

    def assign(self, sim: Simulation, e: Entity | None, target: str, value: Any) -> None:
        # names may contain spaces in Arena ("Total Reworks"): they are aliased like in expressions
        m = re.fullmatch(r"\s*([A-Za-z_][\w.]*)\s*(?:\((.*)\))?\s*", self.alias_expr(target))
        if not m:
            raise ValueError(f"bad assignment target {target!r}")
        name, idx_src = self._alias_back.get(m.group(1), m.group(1)), m.group(2)
        idx = tuple(sim.evaluate(a.strip(), e) for a in idx_src.split(",")) if idx_src else ()
        u = name.upper()
        if u in ("MR",):
            # like ALTER: MR changes at once; busy units above it are taken away when released
            r = self.resource(sim, self.resource_name(sim, idx[0], e))
            r.set_capacity(max(0.0, float(value)), rule="ignore")
            return
        if u == "STATE":
            r = self.resource(sim, self.resource_name(sim, idx[0], e))
            r.forced_state = None if value in (None, "", "AUTO") else str(value)
            r._touch()
            return
        if e is not None and name in e.attrs:
            e.set(name, value, idx)
            return
        if name in sim._vars:
            sim._vars[name].set(value, idx)
            return
        cont = getattr(sim, "_cont", None)
        if cont is not None and name in cont.levels:
            cont.levels[name] = float(value)
            return
        if e is not None and self.set_special_attr(e, name, value):
            return
        if e is not None:
            # SIMAN lets ASSIGN create attributes implicitly.
            e.attrs[name] = value
            return
        raise KeyError(f"cannot assign {target!r}")

    _SPECIAL = {
        "ENTITY.TYPE": "type", "ENTITY.PICTURE": "picture", "ENTITY.STATION": "station",
        "M": "station", "ENTITY.SEQUENCE": "sequence", "NS": "sequence",
        "ENTITY.JOBSTEP": "jobstep", "IS": "jobstep", "ENTITY.SERIALNUMBER": "serial_number",
        "ENTITY.CREATETIME": "create_time", "ENTITY.HOLDCOSTRATE": "hold_cost_rate",
        "ENTITY.STARTTIME": "start_time",
    }
    _COSTS = {
        "ENTITY.VATIME": "va_time", "ENTITY.NVATIME": "nva_time", "ENTITY.WAITTIME": "wait_time",
        "ENTITY.TRANTIME": "tran_time", "ENTITY.OTHERTIME": "other_time",
        "ENTITY.VACOST": "va_cost", "ENTITY.NVACOST": "nva_cost", "ENTITY.WAITCOST": "wait_cost",
        "ENTITY.TRANCOST": "tran_cost", "ENTITY.OTHERCOST": "other_cost",
    }

    def special_attr(self, e: Entity, name: str):
        u = name.upper()
        if u in self._SPECIAL:
            return getattr(e, self._SPECIAL[u])
        if u in self._COSTS:
            return e.costs[self._COSTS[u]]
        return _MISSING

    def set_special_attr(self, e: Entity, name: str, value: Any) -> bool:
        u = name.upper()
        if u == "ENTITY.TYPE" and value != e.type:
            # WIP and the entity statistics follow the new type
            sim = getattr(e, "_sim", None)
            if sim is not None:
                sim.wip[e.type] = sim.wip.get(e.type, 0) - 1
                sim.wip[value] = sim.wip.get(value, 0) + 1
        if u in self._SPECIAL:
            setattr(e, self._SPECIAL[u], value)
            return True
        if u in self._COSTS:
            e.costs[self._COSTS[u]] = value
            return True
        return False

    def get_attr(self, sim: Simulation, e: Entity, name: str):
        if name in e.attrs:
            return e.attrs[name]
        v = self.special_attr(e, name)
        if v is _MISSING:
            raise KeyError(f"{e} has no attribute {name!r}")
        return v

    def count(self, sim: Simulation, name: str, inc: float) -> None:
        self.counter(sim, name).increment(inc)

    def station_enter(self, sim: Simulation, station: str) -> None:
        sim._at_station[station] = sim._at_station.get(station, 0) + 1
        for a in self._areas_of(station):
            st = sim._area_stats[a]
            st["entered"] += 1
            st["wip"].update(sim.now, st["wip"].value + 1)

    def station_leave(self, sim: Simulation, station: str | None) -> None:
        if station:
            sim._at_station[station] = sim._at_station.get(station, 0) - 1
            for a in self._areas_of(station):
                st = sim._area_stats[a]
                st["wip"].update(sim.now, st["wip"].value - 1)

    def next_destination(self, sim: Simulation, e: Entity, dest: Any) -> str:
        if isinstance(dest, str) and dest.upper() == "SEQ":
            if not e.sequence:
                raise RuntimeError(f"{e} routes by sequence but has no Entity.Sequence")
            steps = self.sequences[e.sequence]
            e.jobstep += 1
            if e.jobstep > len(steps):
                raise RuntimeError(f"{e} ran past the end of sequence {e.sequence}")
            station, assigns = steps[e.jobstep - 1]
            for t, x in assigns.items():
                self.assign(sim, e, t, sim.evaluate(x, e))
            return station
        if isinstance(dest, str) and dest in self.station_index:
            return dest
        v = sim.evaluate(dest, e)
        if v not in self.station_index:
            raise KeyError(f"unknown station {v!r}")
        return v

    def storage(self, sim: Simulation, name: str, delta: int) -> None:
        sim._storages[name] = sim._storages.get(name, 0) + delta
        sim._storage_stats[name].update(sim.now, sim._storages[name])

    def write_line(self, sim: Simulation, file: str | None, line: str) -> None:
        if file is None:
            self.output.append(line)
            return
        h = sim._files.get(file)
        if h is None:
            spec = self.files[file]
            h = sim._files[file] = open(spec["path"], "a" if spec["mode"] == "a" else "w", encoding="utf-8")
        h.write(line + "\n")

    def read_record(self, sim: Simulation, file: str):
        h = sim._files.get(file)
        if h is None:
            spec = self.files[file]
            h = sim._files[file] = open(spec["path"], encoding="utf-8")
        line = h.readline()
        if not line:
            return None
        sep = self.files[file]["sep"]
        out = []
        for tok in (line.split(sep) if sep else line.split()):
            tok = tok.strip()
            try:
                out.append(float(tok))
            except ValueError:
                out.append(tok)
        return out

    # --- preemption ------------------------------------------------------------------------
    def find_preemptable(self, sim: Simulation, res: Resource, priority: float):
        """PREEMPT rules: only the most recently seized unit; its holder must be in a DELAY
        (not transferring or grouped) and must not have duplicated since seizing; a unit
        already taken by PREEMPT yields only to a strictly lower priority value."""
        holders = [e for e in sim._delayed if res.name in e.seized]
        if not holders:
            return None
        victim = max(holders, key=lambda e: e.seize_seq.get(res.name, 0))
        if not victim.in_delay or res.name in victim.dup_since_seize:
            return None
        held_with = victim.preempt_pri.get(res.name)
        if held_with is not None and not priority < held_with:
            return None
        return victim

    def do_preempt(self, sim: Simulation, res: Resource, victim: Entity, send_label, store_attr) -> None:
        remaining = 0.0
        if victim.pending is not None:
            remaining = max(0.0, victim.pending.time - sim.now)
            victim.pending.cancel()
            victim.pending = None
        victim.seized[res.name] -= 1
        if victim.seized[res.name] == 0:
            del victim.seized[res.name]
        res.busy -= 1
        res._touch()
        victim.in_delay = False
        victim.preempt_pri.pop(res.name, None)
        if send_label:
            if store_attr:
                victim.attrs[store_attr] = remaining
            sim.schedule_move(victim, 0.0, self.label_index(send_label))
        else:
            # Resume the same delay when the unit comes back.
            victim._preempted = (res, remaining, victim.pc)
            sim._preempted.setdefault(res.name, []).append(victim)

    def preempt(self, sim: Simulation, res: Resource, units: int) -> None:
        for _ in range(units):
            victim = self.find_preemptable(sim, res, -math.inf)
            if victim is None:
                res.pending_decrease += 1
                continue
            self.do_preempt(sim, res, victim, None, None)

    # --- replication lifecycle -----------------------------------------------------------------
    def start(self, sim: Simulation) -> None:
        self.bind()
        sim._resolver = Resolver(sim)
        sim._vars = {n: Variable(sim, n, s["init"], s["dims"], s["track"]) for n, s in self.variable_specs.items()}
        for n, val in getattr(self, "_carry_vars", {}).items():
            if n in sim._vars:
                sim._vars[n].value = val
        sim._queues = {}
        sim._counters = {}
        sim._tallies = {}
        sim._storages = {}
        sim._storage_stats = {s: TimePersistent(f"{s}.NSTO") for s in self.storages}
        sim._at_station = {}
        sim._files = {}
        sim._delayed = _DelayedView(sim)
        sim._preempted = {}
        sim._last_arrivals = []
        sim._blockages = {n: int(sim.evaluate(v)) for n, v in self.blockage_specs.items()}
        sim._area_stats = {a: dict(entered=0, wip=TimePersistent(f"{a}.WIP")) for a in self.area_parent}
        sim._resources = {}
        for n, spec in self.resource_specs.items():
            cap = spec["capacity"]
            if spec["schedule"]:
                cap = self.schedules[spec["schedule"]].value_at(0)
            r = Resource(sim, n, cap if isinstance(cap, (int, float)) else sim.evaluate(cap), spec["cost"],
                         spec.get("stateset"))
            r.waiters = self.waiters.get(n, [])
            if spec.get("initial_state"):
                r.forced_state = spec["initial_state"]
            sim._resources[n] = r
        for q in self.queue_specs:
            self.queue(sim, q)
        for b in self.blocks:
            if isinstance(b, B.HoldBlock) and b.queue_name is not None:
                self.queue(sim, b.queue_name).owner = b
        sim._dstats = {n: TimePersistent(n) for n in self.dstat_specs}
        from .stats import Frequency
        sim._freqs = {n: Frequency(n, start=sim.now, since=sim.now) for n in self.frequency_specs}
        for t in self.tally_specs:
            self.tally(sim, t)
        for c in self.counter_specs:
            self.counter(sim, c)
        self._start_schedules(sim)
        self._start_failures(sim)
        failing = {r for f in self.failures for r in f.resources}
        sim._failing_resources = [sim._resources[r] for r in failing]
        sim._after_needed = bool(self.frequency_specs or self.dstat_specs or self.scan_blocks or failing)
        self._start_polling(sim)
        for b in self.blocks:
            if isinstance(b, B.Create):
                b.start(sim)
        self._start_arrivals(sim)
        for n, spec in self.frequency_specs.items():   # the value at the start counts from time 0
            sim._freqs[n].update(sim.now, self._frequency_category(spec, sim.evaluate(spec["expr"])))

    def _start_arrivals(self, sim: Simulation) -> None:
        def target(at):
            return self.station_index[at] if at in self.station_index else self.label_index(at)

        def release(spec):
            for _ in range(int(sim.evaluate(spec["batch"]))):
                e = sim.new_entity(spec["entity_type"], target(spec["at"]))
                sim.schedule_move(e, 0.0)

        for spec in self.arrival_specs:
            k = spec["kind"]
            if k == "first":
                sim.cal.schedule(0.0, lambda spec=spec: release(spec), priority=-2)
            elif k == "last":
                sim._last_arrivals.append(spec)
            elif k == "every":
                def tick(spec=spec):
                    release(spec)
                    sim.cal.schedule(float(sim.evaluate(spec["every"])), tick)
                sim.cal.schedule(float(sim.evaluate(spec["time"])), tick)
            else:
                sim.cal.schedule(float(sim.evaluate(spec["time"])), lambda spec=spec: release(spec))

    def _start_schedules(self, sim: Simulation) -> None:
        for rname, spec in self.resource_specs.items():
            if not spec["schedule"]:
                continue
            sch = self.schedules[spec["schedule"]]
            res = sim._resources[rname]

            rule = spec.get("schedule_rule") or sch.rule

            def change(i=0, sch=sch, res=res, rule=rule):
                v, d = sch.segments[i % len(sch.segments)]
                res.set_capacity(v * sch.scale, rule)
                if sch.repeat or i + 1 < len(sch.segments):
                    nxt = lambda: sim.cal.schedule(d, lambda: change(i + 1), priority=-0.5)
                    if rule == "wait" and res.pending_decrease:
                        # Arena's Wait: the lower capacity starts when the busy units are
                        # released and still lasts its full duration (the schedule shifts)
                        res.on_decrease_done = [*getattr(res, "on_decrease_done", []), nxt]
                    else:
                        nxt()
            change()

    def _start_failures(self, sim: Simulation) -> None:
        for f in self.failures:
            for rname in f.resources:
                res = sim._resources[rname]
                if f.kind == "time":
                    self._schedule_failure(sim, f, res)
                else:
                    res._count_failure = (f, int(sim.evaluate(f.up)), 0)

    def _schedule_failure(self, sim: Simulation, f: Failure, res: Resource) -> None:
        def fail():
            self._fail(sim, f, res)
        if f.uptime_in_state:
            self._state_uptime(sim, f, res, float(sim.evaluate(f.up)), fail)
            return
        sim.cal.schedule(float(sim.evaluate(f.up)), fail, priority=-0.5)

    @staticmethod
    def _state_uptime(sim: Simulation, f: Failure, res: Resource, need: float, fail) -> None:
        """Up time counts only while the resource is in state `f.uptime_in_state`."""
        want = f.uptime_in_state.upper()
        w = {"left": need, "since": None, "ev": None}

        def watch():
            inside = str(res.state).upper() == want and not res.failed
            if inside and w["since"] is None:
                w["since"] = sim.now
                w["ev"] = sim.cal.schedule(max(0.0, w["left"]), done, priority=-0.5)
            elif not inside and w["since"] is not None:
                w["left"] -= sim.now - w["since"]
                w["since"] = None
                if w["ev"] is not None:
                    w["ev"].cancel()
                    w["ev"] = None

        def done():
            res._watchers.remove(watch)
            fail()
        if not hasattr(res, "_watchers"):
            res._watchers = []
        res._watchers.append(watch)
        watch()

    def _fail(self, sim: Simulation, f: Failure, res: Resource) -> None:
        if res.busy > 0 and f.rule == "wait":
            # Start the failure when the resource becomes idle.
            res._fail_when_idle = f
            return
        if res.busy > 0 and f.rule == "preempt":
            self.preempt(sim, res, res.busy)
        res.failed = True
        res._touch()

        def repair():
            res.failed = False
            res._touch()
            sim.resource_freed(res)
            if f.kind == "time":
                self._schedule_failure(sim, f, res)
        sim.cal.schedule(float(sim.evaluate(f.down)), repair, priority=-0.5)

    def _start_polling(self, sim: Simulation) -> None:
        """SCAN conditions and resource side effects are checked after every event."""
        original = sim.cal.pop

        def pop():
            ev = original()
            if ev is not None:
                act = ev.action

                def wrapped():
                    act()
                    self._after_event(sim)
                ev.action = wrapped
            return ev
        sim.cal.pop = pop

    def _after_event(self, sim: Simulation) -> None:
        if not sim._after_needed:
            return
        for n, spec in self.frequency_specs.items():
            sim._freqs[n].update(sim.now, self._frequency_category(spec, sim.evaluate(spec["expr"])))
        for n, expr in self.dstat_specs.items():
            sim._dstats[n].update(sim.now, float(sim.evaluate(expr)))
        moved = True
        while moved:
            moved = False
            for s in self.scan_blocks:
                if s.poll(sim):
                    moved = True
        for res in sim._failing_resources:
            f = getattr(res, "_fail_when_idle", None)
            if f is not None and res.busy == 0:
                res._fail_when_idle = None
                self._fail(sim, f, res)
            cf = getattr(res, "_count_failure", None)
            if cf is not None:
                f, limit, seen = cf
                if res.seize_count - seen >= limit:
                    res._count_failure = (f, int(sim.evaluate(f.up)), res.seize_count)
                    self._fail(sim, f, res)

    def record_entity_stats(self, sim: Simulation, e: Entity) -> None:
        if not self.record_entity_statistics or getattr(e, "_no_stats", False):
            return
        t = e.type or "Entity"
        self.tally(sim, f"{t}.TotalTime").record(sim.now - e.create_time)
        for k in ("va_time", "nva_time", "wait_time", "tran_time", "other_time",
                  "va_cost", "nva_cost", "wait_cost", "tran_cost", "other_cost"):
            self.tally(sim, f"{t}.{k}").record(e.costs[k])
        self.tally(sim, f"{t}.TotalCost").record(sum(v for k, v in e.costs.items() if k.endswith("_cost")))
        # Arena clears the time and cost attributes once recorded, so nothing is counted twice
        for k in e.costs:
            e.costs[k] = 0.0

    def clear_statistics(self, sim: Simulation) -> None:
        now = sim.now
        for q in sim._queues.values():
            q.nq.clear(now)
            q.wait.clear()
        for r in sim._resources.values():
            r._touch()
            r.nr.clear(now)
            r.mr.clear(now)
            r.util.clear(now)
            r.states.clear(now)
            r.seize_count = 0
            r.busy_cost = r.idle_cost = r.usage_cost = 0.0
        for t in sim._tallies.values():
            t.clear()
        for c in sim._counters.values():
            c.clear()
        for d in sim._dstats.values():
            d.clear(now)
        for f in sim._freqs.values():
            f.clear(now)
        for v in sim._vars.values():
            if self.variable_specs.get(v.name, {}).get("clear") == "statistics":
                v.reset()
            if v.stat:
                v.stat.clear(now)

    def finish(self, sim: Simulation) -> None:
        if sim._last_arrivals:
            for spec in sim._last_arrivals:
                at = spec["at"]
                ix = self.station_index[at] if at in self.station_index else self.label_index(at)
                for _ in range(int(sim.evaluate(spec["batch"]))):
                    e = sim.new_entity(spec["entity_type"], ix)
                    sim.advance(e)
            sim._last_arrivals = []
        now = sim.now
        for n, expr in self.dstat_specs.items():
            sim._dstats[n].update(now, float(sim.evaluate(expr)))
        for r in sim._resources.values():
            r._touch()
        for h in sim._files.values():
            h.close()
        self._carry_vars = {n: v.value for n, v in sim._vars.items()
                            if self.variable_specs.get(n, {}).get("clear") == "none"}
        sim.results = self.collect(sim)

    def collect(self, sim: Simulation) -> dict:
        now = sim.now
        res: dict[str, dict] = {"time": now, "tallies": {}, "dstats": {}, "counters": {},
                                "outputs": {}, "resources": {}, "queues": {}, "frequencies": {}}
        hide = self.no_report
        for n, t in sim._tallies.items():
            if n in hide or n.split(".")[0] in hide:
                continue
            res["tallies"][n] = dict(average=t.average, half_width=t.half_width, min=t.min, max=t.max,
                                     observations=t.n, std=t.std)
        for q in sim._queues.values():
            if q.name.startswith("__internal_") and not len(q.wait.__dict__) or q.name in hide:
                continue
            res["queues"][q.name] = dict(
                number_waiting=dict(average=q.nq.average(now), half_width=q.nq.half_width,
                                    min=q.nq.min, max=q.nq.max, final=q.nq.value),
                waiting_time=dict(average=q.wait.average, half_width=q.wait.half_width,
                                  min=q.wait.min, max=q.wait.max, observations=q.wait.n))
        for r in sim._resources.values():
            r._accrue_costs()
            if r.name in hide:
                continue
            avg_nr, avg_mr = r.nr.average(now), r.mr.average(now)
            res["resources"][r.name] = dict(
                number_busy=avg_nr, number_scheduled=avg_mr,
                instantaneous_utilization=r.util.average(now),
                scheduled_utilization=avg_nr / avg_mr if avg_mr > 0 else 0.0,
                times_used=r.seize_count, busy_cost=r.busy_cost, idle_cost=r.idle_cost,
                usage_cost=r.usage_cost, states=r.states.report(now))
        for n, d in sim._dstats.items():
            res["dstats"][n] = dict(average=d.average(now), half_width=d.half_width, min=d.min,
                                    max=d.max, final=d.value)
        for v in sim._vars.values():
            if v.stat and v.name not in hide:
                res["dstats"][v.name] = dict(average=v.stat.average(now), half_width=v.stat.half_width,
                                             min=v.stat.min, max=v.stat.max, final=v.stat.value)
        for n, s in sim._storage_stats.items():
            res["dstats"][f"{n}.NSTO"] = dict(average=s.average(now), min=s.min, max=s.max, final=s.value)
        for n, c in sim._counters.items():
            if n not in hide:
                res["counters"][n] = c.count
        for n, f in sim._freqs.items():
            res["frequencies"][n] = f.report(now, self.frequency_specs[n]["excluded"])
        for n, expr in self.outputs.items():
            res["outputs"][n] = float(sim.evaluate(expr))
        res["entities"] = dict(in_=dict(sim.entities_in), out=dict(sim.entities_out), wip=dict(sim.wip))
        res["activity_areas"] = {a: dict(entered=st["entered"], wip_average=st["wip"].average(now),
                                         wip_max=st["wip"].max) for a, st in sim._area_stats.items()}
        return res

    # --- running ------------------------------------------------------------------------------
    def run(self, replications: int | None = None, trace: bool = False, animate: bool = False) -> "RunResult":
        self.bind()
        self.trace = trace
        self.animate = animate
        n = replications or self.replications
        self.streams = rng.Streams(self.seeds, disabled=self.disable_randomness)
        self.sampler = rng.Sampler(self.rng_mode, disabled=self.disable_randomness)
        self.tally_last = {}
        self.output = []
        self._carry_vars = {}
        reps = []
        for rep in range(1, n + 1):
            Entity._ids = __import__("itertools").count(1)
            Entity._serials = __import__("itertools").count(1)
            self.streams.begin_replication(rep)
            sim = Simulation(self, rep)
            sim.run()
            reps.append(sim)
            if getattr(sim, "stopped", False) or (self.monitor is not None and self.monitor(sim)):
                break  # stopped: keep the replications done so far
        return RunResult(self, reps)


class _DelayedView:
    """Entities currently in a timed delay that hold resources (preemption candidates)."""

    def __init__(self, sim: Simulation) -> None:
        self.sim = sim

    def __iter__(self):
        seen = set()
        for ev in list(self.sim.cal._heap):
            e = ev.entity
            if e is not None and not ev.cancelled and e.seized and id(e) not in seen:
                seen.add(id(e))
                yield e


def _array(dims: tuple, init: Any):
    if not dims:
        return init
    if isinstance(init, list):
        return [list(r) if isinstance(r, list) else r for r in init]
    if len(dims) == 1:
        return [init] * dims[0]
    return [[init] * dims[1] for _ in range(dims[0])]


@dataclass
class RunResult:
    model: Model
    sims: list

    @property
    def replications(self) -> list[dict]:
        return [s.results for s in self.sims]

    def across(self, path: str) -> dict:
        """Across-replication summary of one statistic, e.g. 'tallies.Part.TotalTime.average'."""
        vals = []
        for r in self.replications:
            v: Any = r
            parts = path.split(".")
            # keys may contain dots: greedily match the longest key at each level
            i = 0
            while i < len(parts):
                for j in range(len(parts), i, -1):
                    k = ".".join(parts[i:j])
                    if isinstance(v, dict) and k in v:
                        v = v[k]
                        i = j
                        break
                else:
                    raise KeyError(path)
            vals.append(float(v))
        finite = [x for x in vals if not math.isnan(x)]
        avg = sum(finite) / len(finite) if finite else math.nan
        return dict(average=avg, half_width=mean_half_width(finite), min=min(finite, default=math.nan),
                    max=max(finite, default=math.nan), values=vals)

    def report(self) -> str:
        from .report import summary_report
        return summary_report(self)
