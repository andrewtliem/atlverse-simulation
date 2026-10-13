"""Runtime objects: entities, queues, resources, variables and the simulation loop."""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .calendar import Calendar
from .expr import evaluate as _evaluate
from .stats import Counter, Frequency, Tally, TimePersistent

if TYPE_CHECKING:
    from .model import Model


# --- Entities -----------------------------------------------------------------

class Entity:
    """A SIMAN entity. User attributes live in `attrs`; special attributes are fields."""

    _ids = itertools.count(1)
    _serials = itertools.count(1)

    def __init__(self, sim: "Simulation", etype: str | None = None, serial_number: int | None = None) -> None:
        self._sim = sim
        self.serial = next(Entity._ids)          # unique id (animation, reports)
        # Entity.SerialNumber: duplicates share the original's number and use none up
        self.serial_number = next(Entity._serials) if serial_number is None else serial_number
        self.type = etype                        # Entity.Type
        self.attrs: dict[str, Any] = {k: ([list(r) if isinstance(r, list) else r for r in v] if isinstance(v, list) else v)
                                      for k, v in sim.model.attribute_defaults.items()}
        self.create_time = sim.now               # Entity.CreateTime
        self.start_time = sim.now                # Entity.StartTime (saved by STACK)
        self.mark_time = sim.now                 # MARK()
        self.station: str | None = None          # Entity.Station / M
        self.sequence: str | None = None         # Entity.Sequence / NS
        self.jobstep = 0                         # Entity.Jobstep / IS
        self.picture: str | None = None          # Entity.Picture
        self.costs = dict(va_time=0.0, nva_time=0.0, wait_time=0.0, tran_time=0.0, other_time=0.0,
                          va_cost=0.0, nva_cost=0.0, wait_cost=0.0, tran_cost=0.0, other_cost=0.0)
        self.hold_cost_rate = 0.0
        self.pc = 0                              # index of the next block to execute
        self.queue: "Queue | None" = None        # queue the entity is waiting in
        self.queue_enter = 0.0
        self.seized: dict[str, int] = {}         # resource name -> units held
        self.members: list[Entity] = []          # GROUP / COMBINE members
        self.group_temporary = False
        self.wait_signal: float | None = None
        self.pending = None                      # pending calendar event (DELAY / transfer)
        self.stack: list[dict] = []              # STACK block
        self.seize_seq: dict[str, int] = {}      # resource -> order of its most recent seize
        self.preempt_pri: dict[str, float] = {}  # resource -> priority it was taken with by PREEMPT
        self.dup_since_seize: set[str] = set()   # resources held when this entity duplicated
        self.in_delay = False
        self.disposed = False

    def get(self, name: str, idx: tuple = ()) -> Any:
        v = self.attrs[name]
        for i in idx:
            v = v[int(i) - 1]
        return v

    def set(self, name: str, value: Any, idx: tuple = ()) -> None:
        if not idx:
            self.attrs[name] = value
            return
        v = self.attrs[name]
        for i in idx[:-1]:
            v = v[int(i) - 1]
        v[int(idx[-1]) - 1] = value

    def cost_rate(self) -> float:
        """Arena: Entity.HoldCostRate plus the busy cost rates of the resources it holds (per hour)."""
        rate = self.hold_cost_rate
        for name, units in self.seized.items():
            r = self._sim._resources.get(name)
            if r is not None:
                rate += r.cost.busy_per_hour * units
        return rate

    def accrue(self, key: str, d: float, rate: float | None = None) -> None:
        """Time `d` in an activity of category key (va|nva|wait|tran|other) and its cost:
        (HoldCostRate + busy rates of held resources) * time, as Arena allocates it."""
        self.costs[f"{key}_time"] += d
        if d > 0:
            self.costs[f"{key}_cost"] += self._sim.model.to_hours(d) * (self.cost_rate() if rate is None else rate)

    def clone(self, sim: "Simulation") -> "Entity":
        self.dup_since_seize |= set(self.seized)  # duplicating blocks later preemption
        e = Entity(sim, self.type, self.serial_number)
        e.attrs = {k: ([list(r) if isinstance(r, list) else r for r in v] if isinstance(v, list) else v)
                   for k, v in self.attrs.items()}
        e.create_time, e.mark_time, e.start_time = self.create_time, self.mark_time, self.start_time
        e.station, e.sequence, e.jobstep, e.picture = self.station, self.sequence, self.jobstep, self.picture
        e.costs = dict(self.costs)
        e.hold_cost_rate = self.hold_cost_rate
        return e

    def __repr__(self) -> str:
        return f"<Entity {self.serial} {self.type or ''}>"


# --- Queues -----------------------------------------------------------------------

RANKINGS = ("FIFO", "LIFO", "LVF", "HVF")


class Queue:
    def __init__(self, sim: "Simulation", name: str, ranking: str = "FIFO",
                 attribute: str | None = None, capacity: float = math.inf) -> None:
        self.sim, self.name = sim, name
        self.ranking = ranking.upper()
        self.attribute = attribute
        self.capacity = capacity
        self.entities: list[Entity] = []
        self.owner = None  # hold block that services this queue
        self.nq = TimePersistent(f"{name}.NumberInQueue")
        self.wait = Tally(f"{name}.WaitingTime")

    def __len__(self) -> int:
        return len(self.entities)

    def _key(self, e: Entity) -> float:
        return float(self.sim.evaluate(self.attribute, e)) if self.attribute else 0.0

    def insert(self, e: Entity, rank: int | None = None) -> None:
        e.queue, e.queue_enter = self, self.sim.now
        e.queue_rate = e.cost_rate()  # what waiting costs: resources seized on leaving don't count
        if rank is not None:
            self.entities.insert(max(0, rank - 1), e)
        elif self.ranking == "FIFO":
            self.entities.append(e)
        elif self.ranking == "LIFO":
            self.entities.insert(0, e)
        else:
            k = self._key(e)
            low_first = self.ranking == "LVF"
            # ties keep FIFO order
            pos = len(self.entities)
            for i, other in enumerate(self.entities):
                ko = self._key(other)
                if (k < ko) if low_first else (k > ko):
                    pos = i
                    break
            self.entities.insert(pos, e)
        self.nq.update(self.sim.now, len(self.entities))
        if self.sim.anim is not None:
            self.sim.anim_event("queue", self.name, len(self.entities))

    def remove(self, e: Entity) -> Entity:
        self.entities.remove(e)
        e.queue = None
        waited = self.sim.now - e.queue_enter
        self.wait.record(waited)
        e.accrue("wait", waited, getattr(e, "queue_rate", None))
        self.nq.update(self.sim.now, len(self.entities))
        if self.sim.anim is not None:
            self.sim.anim_event("queue", self.name, len(self.entities))
        return e

    def remove_at(self, rank: int) -> Entity:
        return self.remove(self.entities[rank - 1])


# --- Resources ------------------------------------------------------------------

IDLE, BUSY, INACTIVE, FAILED = "IDLE", "BUSY", "INACTIVE", "FAILED"


@dataclass
class ResourceCost:
    busy_per_hour: float = 0.0
    idle_per_hour: float = 0.0
    per_use: float = 0.0


class Resource:
    def __init__(self, sim: "Simulation", name: str, capacity: float = 1,
                 cost: ResourceCost | None = None, stateset: dict | None = None) -> None:
        self.sim, self.name = sim, name
        self.capacity = capacity          # MR
        self.busy = 0                     # NR
        self.failed = False
        self.forced_state: str | None = None
        self.cost = cost or ResourceCost()
        self.stateset = stateset or {}
        self.seize_count = 0
        self.seize_counter = 0
        self.pending_decrease = 0         # capacity reduction waiting for units (Wait rule)
        self.waiters: list = []           # hold blocks with entities waiting for this resource
        self.nr = TimePersistent(f"{name}.NumberBusy")
        self.mr = TimePersistent(f"{name}.NumberScheduled", value=capacity)
        self.util = TimePersistent(f"{name}.InstantaneousUtilization")
        self.states = Frequency(f"{name}.States")
        self.states.update(sim.now, self.state)
        self.busy_cost = 0.0
        self.idle_cost = 0.0
        self.usage_cost = 0.0

    @property
    def available(self) -> float:
        if self.failed:
            return 0
        return max(0, self.capacity - self.busy)

    @property
    def autostate(self) -> str:
        if self.failed:
            return FAILED
        if self.busy > 0:
            return BUSY
        if self.capacity <= 0:
            return INACTIVE
        return IDLE

    @property
    def state(self) -> str:
        """Current state name; a STATESETS mapping renames autostates (BUSY -> 'Processing')."""
        if self.forced_state:
            return self.forced_state
        st = self.autostate
        return self.stateset.get(st, st)

    def _accrue_costs(self) -> None:
        """Busy/idle cost since the last change; call before busy or capacity changes."""
        now = self.sim.now
        dt = now - getattr(self, "_cost_last", 0.0)
        self._cost_last = now
        if dt > 0:
            hours = self.sim.model.to_hours(dt)
            self.busy_cost += self.cost.busy_per_hour * hours * self.busy
            self.idle_cost += self.cost.idle_per_hour * hours * max(0, self.capacity - self.busy)

    def _touch(self) -> None:
        now = self.sim.now
        self._accrue_costs()
        self.nr.update(now, self.busy)
        self.mr.update(now, self.capacity)
        # Arena: NR/MR at each instant, at most 100% (busy past a capacity cut counts as 100%)
        self.util.update(now, min(1.0, self.busy / self.capacity) if self.capacity > 0 else (1.0 if self.busy > 0 else 0.0))
        self.states.update(now, self.state)
        for w in getattr(self, "_watchers", ()):
            w()
        if self.sim.anim is not None:
            self.sim.anim_event("resource", self.name, self.state, self.busy, self.capacity)

    def seize(self, entity: Entity, units: int, allocation: str = "other",
              preempt_priority: float | None = None) -> None:
        self._accrue_costs()
        self.busy += units
        self.seize_count += 1
        self.seize_counter += 1
        entity.seize_seq[self.name] = self.seize_counter
        entity.dup_since_seize.discard(self.name)
        if preempt_priority is None:
            entity.preempt_pri.pop(self.name, None)
        else:
            entity.preempt_pri[self.name] = preempt_priority
        entity.seized[self.name] = entity.seized.get(self.name, 0) + units
        if self.cost.per_use:
            self.usage_cost += self.cost.per_use
            key = {"value_added": "va", "non_value_added": "nva", "transfer": "tran"}.get(allocation, allocation)
            entity.costs[f"{key}_cost"] += self.cost.per_use
        self._touch()

    def release(self, entity: Entity | None, units: int) -> None:
        self._accrue_costs()
        if entity is not None:
            held = entity.seized.get(self.name, 0)
            if units > held:
                raise RuntimeError(f"{entity} releases {units} of {self.name} but holds {held}")
            if held == units:
                del entity.seized[self.name]
            else:
                entity.seized[self.name] = held - units
        self.busy -= units
        if self.pending_decrease:
            take = min(self.pending_decrease, self.capacity - self.busy)
            self.capacity -= take
            self.pending_decrease -= take
            if not self.pending_decrease:
                done, self.on_decrease_done = getattr(self, "on_decrease_done", []), []
                for fn in done:
                    fn()
        self._touch()
        self.sim.resource_freed(self)

    def set_capacity(self, cap: float, rule: str = "ignore") -> None:
        """Change capacity (schedules / ALTER). rule: ignore | wait | preempt."""
        self._accrue_costs()
        if cap >= self.capacity:
            self.pending_decrease = 0
            self.capacity = cap
            self._touch()
            self.sim.resource_freed(self)
            return
        excess = self.busy - cap
        if excess <= 0 or rule == "ignore":
            # Ignore: capacity drops at once; busy units finish their work.
            self.capacity = cap
        elif rule == "wait":
            self.capacity = max(cap, self.busy)
            self.pending_decrease = self.capacity - cap
        elif rule == "preempt":
            self.capacity = cap
            self.sim.preempt_units(self, excess)
        self._touch()


# --- Variables ------------------------------------------------------------------

class Variable:
    """Global variable (scalar or 1-2 dimensional array, 1-based) with optional DSTAT."""

    def __init__(self, sim: "Simulation", name: str, init: Any = 0.0, dims: tuple = (),
                 track: bool = False) -> None:
        self.sim, self.name, self.dims = sim, name, dims
        self.init = init
        self.value = _make_array(dims, init)
        self.stat = TimePersistent(name, value=float(init) if track and not dims else 0.0) if track else None

    def get(self, idx: tuple = ()) -> Any:
        v = self.value
        for i in idx:
            v = v[int(i) - 1]
        return v

    def set(self, value: Any, idx: tuple = ()) -> None:
        old = self.get(idx)
        if not idx:
            self.value = value
        else:
            v = self.value
            for i in idx[:-1]:
                v = v[int(i) - 1]
            v[int(idx[-1]) - 1] = value
        if self.stat and not self.dims:
            self.stat.update(self.sim.now, float(value))
        if old != value:
            for w in self.sim.model.onchange_watchers.get(self.name, ()):
                w.changed(self.sim, self.name)

    def reset(self) -> None:
        self.value = _make_array(self.dims, self.init)


def _make_array(dims: tuple, init: Any):
    if not dims:
        return init
    if isinstance(init, list):
        return [list(r) if isinstance(r, list) else r for r in init]
    if len(dims) == 1:
        return [init] * dims[0]
    return [[init] * dims[1] for _ in range(dims[0])]


# --- Simulation -----------------------------------------------------------------

HOLD = object()       # entity is parked; something else resumes it
DISPOSED = object()   # entity left the model


class Simulation:
    """One replication of a model."""

    def __init__(self, model: "Model", rep: int = 1) -> None:
        self.model = model
        self.rep = rep
        self.cal = Calendar()
        self.terminated = False
        self.j = 0                   # global J (SEARCH / FINDJ)
        self.signals: dict[float, list] = {}
        self.trace: list[str] | None = [] if model.trace else None
        self.anim: list | None = [] if (model.animate and rep == 1) else None
        self.wip: dict[str | None, int] = {}
        self.entities_in: dict[str | None, int] = {}
        self.entities_out: dict[str | None, int] = {}

    @property
    def now(self) -> float:
        return self.cal.now

    def evaluate(self, expr, entity: Entity | None = None):
        if expr.__class__ is float or expr.__class__ is int:
            return expr
        r = self.__dict__.get("_resolver")
        if r is None:
            r = self.model.resolver(self)
        if expr.__class__ is str and self.model._aliases:
            expr = self.model.alias_expr(expr)
        return _evaluate(expr, r, entity)

    ANIM_LIMIT = 300_000

    def anim_event(self, *ev) -> None:
        """Animation record: (time, kind, ...). kinds: move, dispose, queue, resource."""
        if self.anim is not None and len(self.anim) < self.ANIM_LIMIT:
            self.anim.append((round(self.now, 6),) + ev)

    def log(self, msg: str) -> None:
        if self.trace is not None:
            self.trace.append(f"{self.now:12.4f}  {msg}")

    # --- entity flow ----------------------------------------------------------
    def new_entity(self, etype: str | None, block_index: int) -> Entity:
        e = Entity(self, etype)
        if etype in self.model.entity_types:
            spec = self.model.entity_types[etype]
            e.picture = spec.get("picture")
            e.hold_cost_rate = spec.get("hold_cost_rate", 0.0)
            for k in ("va_cost", "nva_cost", "wait_cost", "tran_cost", "other_cost"):
                e.costs[k] = spec.get("initial_" + k, 0.0)
        e.pc = block_index
        self.wip[etype] = self.wip.get(etype, 0) + 1
        self.entities_in[etype] = self.entities_in.get(etype, 0) + 1
        return e

    def dispose(self, e: Entity, counted: bool = True) -> None:
        """Entity leaves the model; `counted` False when it only ceases to exist (SPLIT)."""
        if e.seized:
            # SIMAN reports an error when an entity with seized resources is disposed.
            raise RuntimeError(f"{e} disposed while holding resources {e.seized}")
        e.disposed = True
        if self.anim is not None:
            self.anim_event("dispose", e.serial)
        self.wip[e.type] = self.wip.get(e.type, 0) - 1
        if counted:
            self.entities_out[e.type] = self.entities_out.get(e.type, 0) + 1
        self.model.record_entity_stats(self, e)

    def schedule_move(self, e: Entity, delay: float = 0.0, pc: int | None = None,
                      on_resume=None) -> None:
        if pc is not None:
            e.pc = pc

        def go():
            e.pending = None
            if on_resume:
                on_resume()
            self.advance(e)
        e.pending = self.cal.schedule(delay, go, e)

    def advance(self, e: Entity) -> None:
        """Run an entity through blocks until it is held, delayed or disposed."""
        blocks = self.model.blocks
        steps = 0
        while not self.terminated:
            if e.pc >= len(blocks):
                raise RuntimeError(f"{e} fell off the end of the model after block {e.pc}")
            block = blocks[e.pc]
            steps += 1
            if steps > 1_000_000:
                raise RuntimeError(f"{e} is looping without advancing time at {block}")
            if self.trace is not None:
                self.log(f"{e} -> {block}")
            if self.anim is not None:
                node = block.__dict__.get("node")
                if node is not None and node != e.__dict__.get("_node"):
                    e._node = node
                    self.anim_event("move", e.serial, e.type, node, e.picture)
            result = block.execute(self, e)
            if result is HOLD or result is DISPOSED:
                return
            e.pc = e.pc + 1 if result is None else self.model.label_index(result)

    # --- resources ------------------------------------------------------------
    def resource_freed(self, res: Resource) -> None:
        """Offer freed units: preempted entities first (they resume their delay), then
        PREEMPT blocks, then SEIZE blocks by priority (lowest first) and longest wait."""
        pre = self._preempted.get(res.name) if hasattr(self, "_preempted") else None
        while pre and res.available >= 1:
            v = pre.pop(0)
            r, remaining, pc = v._preempted
            v._preempted = None
            r.seize(v, 1)
            v.in_delay = True
            # pc already points past the interrupted DELAY
            self.schedule_move(v, remaining, pc, on_resume=lambda v=v: setattr(v, "in_delay", False))
        while res.available > 0:
            cands = [w for w in res.waiters if w.queue_of(self).entities]
            if not cands:
                return
            cands.sort(key=lambda w: (0 if type(w).__name__ == "Preempt" else 1, w.priority_value(self),
                                      w.queue_of(self).entities[0].queue_enter))
            for w in cands:
                if w.try_release_waiting(self, res):
                    break
            else:
                return

    def preempt_units(self, res: Resource, units: int) -> None:
        self.model.preempt(self, res, units)

    # --- run --------------------------------------------------------------------
    def run(self) -> None:
        m = self.model
        end = m.replication_length
        warmup = m.warmup
        if warmup > 0:
            self.cal.schedule(warmup, self._clear_stats, priority=-1)
        m.start(self)
        n_events = 0
        self.stopped = False
        while not self.terminated:
            t = self.cal.peek_time()
            if t > end or t == math.inf:
                if end != math.inf:
                    self.cal.now = end
                break
            ev = self.cal.pop()
            if ev is None:
                break
            ev.action()
            if m.terminating_condition is not None and self.evaluate(m.terminating_condition):
                break
            n_events += 1
            if m.monitor is not None and n_events % 2000 == 0 and m.monitor(self):
                self.stopped = True  # stopped from outside (the editor's End button)
                break
        m.finish(self)

    def _clear_stats(self) -> None:
        self.model.clear_statistics(self)
