"""SIMAN blocks.

`execute(sim, entity)` returns:
  None      -> continue with the next block
  "label"   -> continue at a labelled block
  HOLD      -> the entity is parked (queue, delay, ...) and will be resumed later
  DISPOSED  -> the entity left the model
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

from .core import DISPOSED, HOLD, Entity, Queue, Simulation


class Block:
    label: str | None = None
    index: int = -1

    def execute(self, sim: Simulation, e: Entity):  # pragma: no cover - interface
        raise NotImplementedError

    def bind(self, model) -> None:
        """Resolve names after the whole model is known."""

    def __repr__(self) -> str:
        return f"{type(self).__name__}#{self.index}" + (f"[{self.label}]" if self.label else "")


def _ev(sim: Simulation, expr, e: Entity | None = None):
    return sim.evaluate(expr, e)


# --- Arrivals -------------------------------------------------------------------

@dataclass(repr=False, eq=False)
class Create(Block):
    """CREATE: Batch Size, Offset Time, Interval, Maximum Batches, Entity Type."""

    interval: Any = 1.0
    batch_size: Any = 1
    first: Any = 0.0
    max_batches: Any = math.inf
    entity_type: str | None = None
    schedule: str | None = None      # arrival schedule name: rate varies by time
    label: str | None = None

    def start(self, sim: Simulation) -> None:
        state = {"n": 0}
        maxb = _ev(sim, self.max_batches)

        def arrive():
            if state["n"] >= maxb:
                return
            state["n"] += 1
            n = int(_ev(sim, self.batch_size))
            for _ in range(n):
                e = sim.new_entity(self.entity_type, self.index + 1)
                sim.schedule_move(e, 0.0)
            if state["n"] < maxb:
                sim.cal.schedule(self._next_gap(sim), arrive)

        sim.cal.schedule(float(_ev(sim, self.first)), arrive)

    def _next_gap(self, sim: Simulation) -> float:
        if self.schedule:
            return sim.model.schedules[self.schedule].next_arrival_gap(sim)
        return float(_ev(sim, self.interval))

    def execute(self, sim, e):
        return None


# --- Attribute / variable assignment -----------------------------------------------

@dataclass(repr=False, eq=False)
class Assign(Block):
    """ASSIGN: list of (target, expression). Targets: attribute, variable, Var(i,j),
    special attributes (Entity.Type, Entity.Picture, ...), STATE(Resource), MR(Resource)."""

    assignments: list = field(default_factory=list)
    label: str | None = None

    def execute(self, sim, e):
        for target, expr in self.assignments:
            sim.model.assign(sim, e, target, _ev(sim, expr, e))
        return None


# --- Time ---------------------------------------------------------------------------

@dataclass(repr=False, eq=False)
class Delay(Block):
    """DELAY: Duration, Allocation (value_added | non_value_added | wait | transfer | other)."""

    duration: Any = 0.0
    allocation: str = "other"
    label: str | None = None

    def execute(self, sim, e):
        d = float(_ev(sim, self.duration, e))
        if d < 0:
            d = 0.0
        key = {"value_added": "va", "non_value_added": "nva", "wait": "wait",
               "transfer": "tran", "other": "other"}[self.allocation]
        e.accrue(key, d)
        if d == 0:
            return None
        e.in_delay = True
        sim.schedule_move(e, d, e.pc + 1, on_resume=lambda: setattr(e, "in_delay", False))
        return HOLD


@dataclass(repr=False, eq=False)
class Stack(Block):
    """STACK: SAVE pushes Depth copies of the internal cost/time attributes
    (Entity.StartTime, VA/NVA/Wait/Tran/Other time and cost); DESTROY pops Depth levels.
    Diff.* variables return current minus top-of-stack values."""

    depth: Any = 1
    action: str = "save"
    label: str | None = None

    def execute(self, sim, e):
        n = int(_ev(sim, self.depth, e))
        if self.action.lower() == "save":
            for _ in range(n):
                e.stack.append(dict(e.costs, start_time=e.start_time))
        else:
            if n > len(e.stack):
                raise RuntimeError(f"STACK DESTROY {n} but {e} has {len(e.stack)} levels")
            del e.stack[len(e.stack) - n:]
        return None


# --- Queues and holds ---------------------------------------------------------------

@dataclass(repr=False, eq=False)
class QueueBlock(Block):
    """QUEUE: waiting space in front of a hold block. Capacity overflow -> Balk Label.
    With `choices` (queue names) and `select` (expression giving a queue name or a 1-based
    index into choices) each entity picks its queue (Arena Queue Type Set/Attribute/Expression);
    the hold block then serves the choices in listed order."""

    queue: str = ""
    capacity: Any = math.inf
    balk_label: str | None = None
    choices: list | None = None
    select: Any = None
    label: str | None = None

    def execute(self, sim, e):
        if self.choices:
            v = _ev(sim, self.select, e)
            name = self.choices[int(v) - 1] if isinstance(v, (int, float)) else str(v)
            if name not in self.choices:
                raise RuntimeError(f"queue {name!r} chosen by {self.select!r} is not one of {self.choices}")
            q = sim.model.queue(sim, name)
        else:
            q = sim.model.queue(sim, self.queue)
        cap = _ev(sim, self.capacity, e)
        if len(q) >= cap:
            if self.balk_label:
                return self.balk_label
            sim.dispose(e)
            return DISPOSED
        e._pending_queue = q  # the following hold block decides whether to park
        feeds = getattr(self, "feeds", None)
        if feeds is not None:  # detached queue listed on a QPICK: go to its hold block
            return f"__ix{feeds}"
        return None


class HoldBlock(Block):
    """Common behaviour for blocks preceded by a QUEUE (SEIZE, WAIT, SCAN, ...) or by a
    QPICK that serves several detached queues."""

    priority: Any = 1
    qpick = None

    def bind(self, model) -> None:
        prev = model.blocks[self.index - 1] if self.index > 0 else None
        if isinstance(prev, QPick):
            self.qpick = prev
            self.queue_name = None
        elif isinstance(prev, QueueBlock) and prev.choices:
            for n in prev.choices:
                model.ensure_queue(n)
            self.qpick = _QueueChoice(list(prev.choices))
            self.queue_name = None
        elif isinstance(prev, QueueBlock):
            self.queue_name = prev.queue
        else:
            self.queue_name = f"__internal_{self.index}"
            model.ensure_queue(self.queue_name)

    def queue_of(self, sim) -> Queue:
        """The queue to serve next (QPICK: chosen by its queue selection rule)."""
        if self.qpick is not None:
            return self.qpick.choose(sim)
        return sim.model.queue(sim, self.queue_name)

    def all_queues(self, sim) -> list:
        if self.qpick is not None:
            return [sim.model.queue(sim, n) for n in self.qpick._queues]
        return [sim.model.queue(sim, self.queue_name)]

    def entry_queue(self, sim, e) -> Queue:
        """The queue an arriving entity belongs to."""
        if self.qpick is not None and getattr(e, "_pending_queue", None) is not None:
            return e._pending_queue
        return self.queue_of(sim)

    def priority_value(self, sim, e=None) -> float:
        """Priority of the waiting entity `e` (an expression may use its attributes); SIMAN
        treats negative values as 0. Without `e`, the entity at the head of the queue."""
        if e is None:
            q = self.queue_of(sim)
            e = q.entities[0] if q.entities else None
        return max(0.0, float(_ev(sim, self.priority, e)))

    def park(self, sim, e) -> object:
        q = self.entry_queue(sim, e)
        e._pending_queue = None
        q.insert(e)
        e.pc = self.index
        return HOLD

    def pass_through(self, sim, e) -> None:
        """Entity got through without waiting: SIMAN still records a zero wait."""
        q = getattr(e, "_pending_queue", None)
        if q is not None:
            q.wait.record(0.0)
        e._pending_queue = None

    def resume(self, sim, e) -> None:
        """Remove from its queue and continue after this block."""
        (e.queue or self.queue_of(sim)).remove(e)
        sim.schedule_move(e, 0.0, self.index + 1)


class _QueueChoice:
    """Queues a hold block serves when entities choose their queue: listed order."""

    def __init__(self, names: list) -> None:
        self._queues = names

    def choose(self, sim) -> Queue:
        qs = [sim.model.queue(sim, n) for n in self._queues]
        return next((q for q in qs if q.entities), qs[0])


@dataclass(repr=False, eq=False)
class QPick(Block):
    """QPICK: the following hold block serves several detached QUEUE blocks (by label);
    rule chooses which queue's head goes next: POR | CYC | RAN | LNQ | SNQ."""

    queue_labels: list = field(default_factory=list)
    rule: str = "POR"
    label: str | None = None

    def bind(self, model) -> None:
        self._queues = []
        for lab in self.queue_labels:
            qb = model.blocks[model.label_index(lab)]
            if not isinstance(qb, QueueBlock):
                raise ValueError(f"QPICK label {lab} is not a QUEUE block")
            qb.feeds = self.index + 1
            self._queues.append(qb.queue)
            model.ensure_queue(qb.queue)

    def execute(self, sim, e):
        return None

    def choose(self, sim) -> Queue:
        qs = [sim.model.queue(sim, n) for n in self._queues]
        busy = [q for q in qs if q.entities]
        if not busy:
            return qs[0]
        rule = self.rule.upper()
        if rule == "LNQ":
            return max(busy, key=len)
        if rule == "SNQ":
            return min(busy, key=len)
        if rule == "RAN":
            return busy[int(sim.model.streams[10].u() * len(busy))]
        if rule == "CYC":
            start = getattr(self, "_cyc", 0)
            for k in range(len(qs)):
                q = qs[(start + k) % len(qs)]
                if q.entities:
                    self._cyc = (qs.index(q) + 1) % len(qs)
                    return q
        return busy[0]  # POR: first listed non-empty queue


@dataclass(repr=False, eq=False)
class Seize(HoldBlock):
    """SEIZE: Priority, list of (Resource ID, Number of Units). Resource ID may be an
    expression or a set reference ("SetName(i)"). `select` picks a member of a resource set
    by rule (one dict or a list): {"set", "rule": CYC|RAN|POR|LNB|LRC|SNB|SRC|ER, "units",
    "save": attribute receiving the member index, "index": member for ER (specific member)}.
    `state` forces the seized resources into a StateSet state until released."""

    resources: list = field(default_factory=list)  # [(resource_expr, units_expr)]
    priority: Any = 1
    allocation: str = "other"
    select: Any = None
    state: str | None = None
    label: str | None = None

    def bind(self, model) -> None:
        super().bind(model)
        self._selects = [] if not self.select else [self.select] if isinstance(self.select, dict) else list(self.select)
        for rexpr, _ in self.resources:
            if isinstance(rexpr, str) and rexpr in model.resource_specs:
                model.register_waiter(rexpr, self)
            elif isinstance(rexpr, str):
                # "Set(i)" or an expression: wake on any member of a mentioned set, else on all
                m = re.match(r"\s*(\w[\w .]*?)\s*\(", rexpr)
                names = model.sets.get(m.group(1).strip()) if m else None
                for r in names or list(model.resource_specs):
                    model.register_waiter(r, self)
        for sel in self._selects:
            for r in model.sets[sel["set"]]:
                model.register_waiter(r, self)
            sel["_cyc"] = 0

    def _requirements(self, sim, e) -> list | None:
        reqs = []
        for rexpr, uexpr in self.resources:
            name = sim.model.resource_name(sim, rexpr, e)
            reqs.append((sim.model.resource(sim, name), int(_ev(sim, uexpr, e))))
        for sel in self._selects:
            r = sim.model.select_resource(sim, sel, e, exclude={x.name for x, _ in reqs})
            if r is None:
                return None
            reqs.append((r, int(_ev(sim, sel.get("units", 1), e))))
        return reqs

    def _can(self, reqs) -> bool:
        return reqs is not None and all(r.available >= n for r, n in reqs)

    def _take(self, sim, e, reqs) -> None:
        for r, n in reqs:
            r.seize(e, n, self.allocation)
        k = len(self.resources)
        for sel, (r, _) in zip(self._selects, reqs[k:]):
            if sel.get("save"):
                e.attrs[sel["save"]] = sim.model.sets[sel["set"]].index(r.name) + 1  # index into the set
        if self.state:
            for r, _ in reqs:
                r.forced_state = self.state
                r._touch()

    def execute(self, sim, e):
        q = self.entry_queue(sim, e)
        reqs = self._requirements(sim, e)
        blocked = any(set(r.name for r, _ in (self._requirements(sim, w) or [])) &
                      set(r.name for r, _ in (reqs or [])) for w in q.entities)
        if not blocked and self._can(reqs):
            self._take(sim, e, reqs)
            self.pass_through(sim, e)
            return None
        return self.park(sim, e)

    def try_release_waiting(self, sim, res) -> bool:
        """Called when `res` frees units. Applies head-of-line blocking per resource."""
        q = self.queue_of(sim)
        blocked: set[str] = set()
        for e in list(q.entities):
            reqs = self._requirements(sim, e)
            names = {r.name for r, _ in (reqs or [])}
            if reqs is None:
                # set member not available: block every member the entity could take
                names = {n for sel in self._selects for n in sim.model.sets[sel["set"]]}
            if names & blocked:
                continue
            if self._can(reqs):
                self._take(sim, e, reqs)
                self.resume(sim, e)
                return True
            blocked |= names
            if res.name in blocked:
                return False
        return False


@dataclass(repr=False, eq=False)
class Release(Block):
    """RELEASE: list of (Resource ID, Quantity). Quantity defaults to all held when None.
    An item may also be a set release {"set", "rule": last|first|specific, "index", "units"}:
    last/first member of the set seized by this entity, or the member at `index`."""

    resources: list = field(default_factory=list)
    label: str | None = None

    def execute(self, sim, e):
        for item in self.resources:
            if isinstance(item, dict):
                name = self._set_member(sim, e, item)
                qexpr = item.get("units", 1)
            else:
                rexpr, qexpr = item
                name = sim.model.resource_name(sim, rexpr, e)
            held = e.seized.get(name, 0)
            n = held if qexpr is None else int(_ev(sim, qexpr, e))
            r = sim.model.resource(sim, name)
            r.release(e, n)
            if r.forced_state and r.busy == 0:
                r.forced_state = None
                r._touch()
        return None

    @staticmethod
    def _set_member(sim, e, item) -> str:
        members = sim.model.sets[item["set"]]
        rule = str(item.get("rule", "last")).lower()
        if rule.startswith("spec"):
            return members[int(_ev(sim, item.get("index", 1), e)) - 1]
        held = sorted((n for n in e.seized if n in members), key=lambda n: e.seize_seq.get(n, 0))
        if not held:
            raise RuntimeError(f"{e} releases from set {item['set']} but holds none of its members")
        return held[-1] if rule.startswith("last") else held[0]


@dataclass(repr=False, eq=False)
class Alter(Block):
    """ALTER: Resource ID, Capacity Change (positive or negative)."""

    resource: Any = ""
    change: Any = 0
    label: str | None = None

    def execute(self, sim, e):
        r = sim.model.resource(sim, sim.model.resource_name(sim, self.resource, e))
        # MR changes at once (never below 0); busy units above it go when released
        r.set_capacity(max(0, r.capacity + int(_ev(sim, self.change, e))), rule="ignore")
        return None


@dataclass(repr=False, eq=False)
class Preempt(HoldBlock):
    """PREEMPT: take one unit of a resource from its current holder.

    The preempted entity's remaining delay is saved; it resumes when it gets the
    resource back (or is sent to `send_label`, storing the remaining time in `store_attr`).
    """

    resource: Any = ""
    priority: Any = 1
    send_label: str | None = None
    store_attr: str | None = None
    label: str | None = None

    def bind(self, model) -> None:
        super().bind(model)
        if isinstance(self.resource, str) and self.resource in model.resource_specs:
            model.register_waiter(self.resource, self)

    def execute(self, sim, e):
        r = sim.model.resource(sim, sim.model.resource_name(sim, self.resource, e))
        pri = self.priority_value(sim, e)
        if r.available >= 1:
            r.seize(e, 1, preempt_priority=pri)
            self.pass_through(sim, e)
            return None
        victim = sim.model.find_preemptable(sim, r, pri)
        if victim is None:
            return self.park(sim, e)
        sim.model.do_preempt(sim, r, victim, self.send_label, self.store_attr)
        r.seize(e, 1, preempt_priority=pri)
        self.pass_through(sim, e)
        return None

    def try_release_waiting(self, sim, res) -> bool:
        q = self.queue_of(sim)
        if q.entities and res.available >= 1:
            e = q.entities[0]
            res.seize(e, 1, preempt_priority=self.priority_value(sim, e))
            self.resume(sim, e)
            return True
        return False


# --- Flow control ----------------------------------------------------------------------

@dataclass(repr=False, eq=False)
class Branch(Block):
    """BRANCH: Max Number of Branches, branches = [(kind, cond_or_prob, label, primary)].
    kind: IF | ELSE | WITH | ALWAYS. The original entity takes the first selected branch
    (or the one flagged primary); further selected branches receive duplicates."""

    branches: list = field(default_factory=list)
    max_branches: Any = math.inf
    stream: int = 10
    label: str | None = None

    def execute(self, sim, e):
        chosen = []
        limit = _ev(sim, self.max_branches, e)
        u = None
        cum = 0.0
        for kind, arg, lab, *_ in self.branches:
            if len(chosen) >= limit:
                break
            kind = kind.upper()
            if kind == "ALWAYS":
                chosen.append(lab)
            elif kind == "IF":
                if _ev(sim, arg, e):
                    chosen.append(lab)
            elif kind == "WITH":
                if u is None:
                    u = sim.model.streams[self.stream].u()
                lo = cum
                cum += float(_ev(sim, arg, e))
                if lo <= u < cum:
                    chosen.append(lab)
            elif kind == "ELSE":
                if not chosen:
                    chosen.append(lab)
        if not chosen:
            sim.dispose(e)
            return DISPOSED
        for lab in chosen[1:]:
            d = e.clone(sim)
            sim.wip[d.type] = sim.wip.get(d.type, 0) + 1
            sim.schedule_move(d, 0.0, sim.model.label_index(lab))
        return chosen[0]


@dataclass(repr=False, eq=False)
class If(Block):
    """IF / ELSEIF / ELSE / ENDIF. Model.bind() fills `false_target` (index of the next
    ELSEIF/ELSE/ENDIF) and `endif` (index of the matching ENDIF)."""

    condition: Any = True
    label: str | None = None

    def execute(self, sim, e):
        if _ev(sim, self.condition, e):
            return None
        e._jumped_in = True
        return f"__ix{self.false_target}"


@dataclass(repr=False, eq=False)
class ElseIf(If):
    def execute(self, sim, e):
        if not getattr(e, "_jumped_in", False):
            return f"__ix{self.endif}"  # previous branch finished: skip to ENDIF
        e._jumped_in = False
        return super().execute(sim, e)


@dataclass(repr=False, eq=False)
class Else(Block):
    label: str | None = None

    def execute(self, sim, e):
        if not getattr(e, "_jumped_in", False):
            return f"__ix{self.endif}"
        e._jumped_in = False
        return None


@dataclass(repr=False, eq=False)
class EndIf(Block):
    label: str | None = None

    def execute(self, sim, e):
        e._jumped_in = False
        return None


@dataclass(repr=False, eq=False)
class While(Block):
    condition: Any = True
    label: str | None = None

    def execute(self, sim, e):
        if _ev(sim, self.condition, e):
            return None
        return f"__ix{self.end_index + 1}"


@dataclass(repr=False, eq=False)
class EndWhile(Block):
    label: str | None = None

    def execute(self, sim, e):
        return f"__ix{self.while_index}"


# --- Statistics ---------------------------------------------------------------------------

@dataclass(repr=False, eq=False)
class Count(Block):
    """COUNT: Counter ID, Increment. With `set` the counter is member `set_index` of a counter set."""

    counter: str = ""
    increment: Any = 1
    set: str | None = None
    set_index: Any = 1
    label: str | None = None

    def execute(self, sim, e):
        name = sim.model.sets[self.set][int(_ev(sim, self.set_index, e)) - 1] if self.set else self.counter
        sim.model.count(sim, name, float(_ev(sim, self.increment, e)))
        return None


@dataclass(repr=False, eq=False)
class EntityStats(Block):
    """Arena Record module, type Entity Statistics: record the entity's flow-time and
    cost statistics now (as Dispose would) and continue."""

    label: str | None = None

    def execute(self, sim, e):
        sim.model.record_entity_stats(sim, e)
        return None


@dataclass(repr=False, eq=False)
class TallyBlock(Block):
    """TALLY: Tally ID, Value (expression | 'INT(attr)' interval | 'BET' between),
    Number of Observations."""

    tally: str = ""
    value: Any = 0
    observations: Any = 1
    set: str | None = None
    set_index: Any = 1
    label: str | None = None

    def execute(self, sim, e):
        name = sim.model.sets[self.set][int(_ev(sim, self.set_index, e)) - 1] if self.set else self.tally
        t = sim.model.tally(sim, name)
        v = self.value
        if isinstance(v, str) and v.upper().startswith("INT(") and v.endswith(")"):
            val = sim.now - float(sim.model.get_attr(sim, e, v[4:-1].strip()))
        elif isinstance(v, str) and v.upper() == "BET":
            last = sim.model.tally_last.setdefault((sim.rep, name), None)
            sim.model.tally_last[(sim.rep, name)] = sim.now
            if last is None:
                return None
            val = sim.now - last
        else:
            val = float(_ev(sim, v, e))
        for _ in range(int(_ev(sim, self.observations, e))):
            t.record(val)
        return None


@dataclass(repr=False, eq=False)
class Dispose(Block):
    record_stats: bool = True
    label: str | None = None

    def execute(self, sim, e):
        if not self.record_stats:
            e._no_stats = True
        sim.dispose(e)
        return DISPOSED


@dataclass(repr=False, eq=False)
class Duplicate(Block):
    """DUPLICATE: list of (Number of Duplicates, Duplicate Destination label).
    `cost_pct` (Arena Separate: Percent Cost to Duplicates) splits that percentage of the
    original's cost and time attributes evenly over the duplicates; the original keeps the rest.
    None copies them unchanged (SIMAN block behaviour)."""

    copies: list = field(default_factory=list)
    cost_pct: Any = None
    label: str | None = None

    def execute(self, sim, e):
        made = []
        for n_expr, lab in self.copies:
            for _ in range(int(_ev(sim, n_expr, e))):
                d = e.clone(sim)
                sim.wip[d.type] = sim.wip.get(d.type, 0) + 1
                made.append((d, sim.model.label_index(lab) if lab else e.pc + 1))
        if self.cost_pct is not None and made:
            share = min(max(float(_ev(sim, self.cost_pct, e)), 0.0), 100.0) / 100
            base = dict(e.costs)
            for d, _ in made:
                d.costs = {k: v * share / len(made) for k, v in base.items()}
            e.costs = {k: v * (1 - share) for k, v in base.items()}
        for d, pc in made:
            sim.schedule_move(d, 0.0, pc)
        return None


# --- Signals and conditions -----------------------------------------------------------------

@dataclass(repr=False, eq=False)
class Wait(HoldBlock):
    """WAIT: hold the entity until SIGNAL sends `signal_code`; `limit` releases at most N."""

    signal_code: Any = 1
    limit: Any = math.inf
    label: str | None = None

    def bind(self, model) -> None:
        super().bind(model)
        model.wait_blocks.append(self)

    def execute(self, sim, e):
        e.wait_signal = float(_ev(sim, self.signal_code, e))
        return self.park(sim, e)

    def signal(self, sim, code: float, budget: float) -> int:
        budget = min(budget, float(_ev(sim, self.limit)))
        released = 0
        for q in self.all_queues(sim):
            for e in list(q.entities):
                if released >= budget:
                    return released
                if e.wait_signal == code:
                    e.wait_signal = None
                    self.resume(sim, e)
                    released += 1
        return released


@dataclass(repr=False, eq=False)
class Signal(Block):
    """SIGNAL: Signal Code, Release Limit (across all WAIT blocks)."""

    code: Any = 1
    limit: Any = math.inf
    label: str | None = None

    def execute(self, sim, e):
        code = float(_ev(sim, self.code, e))
        budget = _ev(sim, self.limit, e)
        for w in sim.model.wait_blocks:
            per = _ev(sim, w.limit)
            budget -= w.signal(sim, code, min(budget, per))
            if budget <= 0:
                break
        return None


@dataclass(repr=False, eq=False)
class Scan(HoldBlock):
    """SCAN: hold entities until Condition is true. Re-evaluated after every event."""

    condition: Any = True
    label: str | None = None

    def bind(self, model) -> None:
        super().bind(model)
        model.scan_blocks.append(self)

    def execute(self, sim, e):
        q = self.queue_of(sim)
        if not q.entities and _ev(sim, self.condition, e):
            return None
        return self.park(sim, e)

    def poll(self, sim) -> bool:
        for q in self.all_queues(sim):
            if q.entities and _ev(sim, self.condition, q.entities[0]):
                self.resume(sim, q.entities[0])
                return True
        return False


@dataclass(repr=False, eq=False)
class HoldForever(HoldBlock):
    """Arena Hold module, Infinite Hold: the entity waits until a Remove takes it out."""

    label: str | None = None

    def execute(self, sim, e):
        return self.park(sim, e)


# --- Grouping --------------------------------------------------------------------------------

@dataclass(repr=False, eq=False)
class Group(HoldBlock):
    """GROUP: form a representative entity from Quantity entities (temporary or permanent).
    `match_attr` groups only entities with equal attribute values."""

    quantity: Any = 2
    temporary: bool = True
    match_attr: str | None = None
    save_criterion: str = "last"  # first | last | product | sum  (representative attributes)
    rep_type: str | None = None   # entity type of the representative (default: from save criterion)
    label: str | None = None

    def execute(self, sim, e):
        q = self.queue_of(sim)
        self.park(sim, e)
        n = int(_ev(sim, self.quantity, e))
        if self.match_attr:
            key = e.attrs.get(self.match_attr)
            members = [x for x in q.entities if x.attrs.get(self.match_attr) == key]
        else:
            members = list(q.entities)
        if len(members) < n:
            return HOLD
        members = members[:n]
        for m in members:
            q.remove(m)
        rep = self._representative(sim, members)
        rep.pc = self.index + 1
        sim.schedule_move(rep, 0.0)
        return HOLD

    def _representative(self, sim, members):
        return make_representative(sim, members, self.save_criterion, getattr(self, "rep_type", None),
                                   temporary=self.temporary)


def make_representative(sim, members, criterion: str = "last", rep_type=None, temporary=True):
    """Representative entity per the GROUP/COMBINE rules:
    numeric attributes by save criterion (first|last|sum|product); string attributes,
    serial number, station, sequence, jobstep and type from the first member (last if
    criterion is last); CreateTime = min over members; cost/time attributes summed."""
    criterion = criterion.lower()
    src = members[-1] if criterion == "last" else members[0]
    rep = src.clone(sim)
    rep.serial = src.serial
    for k, v in src.attrs.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool) and criterion in ("sum", "product"):
            acc = 0.0 if criterion == "sum" else 1.0
            for m in members:
                acc = acc + m.attrs[k] if criterion == "sum" else acc * m.attrs[k]
            rep.attrs[k] = acc
    rep.create_time = min(m.create_time for m in members)
    rep.costs = {k: sum(m.costs[k] for m in members) for k in src.costs}
    rep.hold_cost_rate = sum(m.hold_cost_rate for m in members)
    if rep_type is not None:
        rep.type = rep_type
        rep.picture = sim.model.entity_types.get(rep_type, {}).get("picture")
    sim.wip[rep.type] = sim.wip.get(rep.type, 0) + 1
    if temporary:
        rep.members = list(members)
        rep.group_temporary = True
        for m in members:  # members leave WIP while grouped; SPLIT brings them back
            sim.wip[m.type] = sim.wip.get(m.type, 0) - 1
            if sim.anim is not None:
                sim.anim_event("dispose", m.serial)  # hidden while inside the group
                m._node = None
    else:
        for m in members:
            m._no_stats = True
            sim.dispose(m)
    return rep


@dataclass(repr=False, eq=False)
class Split(Block):
    """SPLIT: dissolve a temporary group; members continue to the next block.
    member_attrs (Arena Separate): "retain" keeps the members' own values, "all" gives them
    the representative's user attributes and Entity.Type/Picture/Station/Sequence/Jobstep/
    HoldCostRate, or a list of attribute names copies just those from the representative."""

    restore_attrs: bool = True
    member_attrs: Any = None
    label: str | None = None

    _SPECIAL = ("type", "picture", "station", "sequence", "jobstep", "hold_cost_rate")

    def execute(self, sim, e):
        if not e.group_temporary:
            raise RuntimeError(f"SPLIT of {e}, which is not a temporary group")
        mode = self.member_attrs if self.member_attrs is not None else ("retain" if self.restore_attrs else "all")
        for m in e.members:
            if mode == "all":
                m.attrs = {k: (list(v) if isinstance(v, list) else v) for k, v in e.attrs.items()}
                for k in self._SPECIAL:
                    setattr(m, k, getattr(e, k))
            elif isinstance(mode, (list, tuple)):
                for k in mode:
                    if not sim.model.set_special_attr(m, k, sim.model.get_attr(sim, e, k)):
                        m.attrs[k] = e.attrs.get(k, 0.0)
            sim.wip[m.type] = sim.wip.get(m.type, 0) + 1
            sim.schedule_move(m, 0.0, self.index + 1)
        e.members = []
        e._no_stats = True
        sim.dispose(e, counted=False)
        return DISPOSED


@dataclass(repr=False, eq=False)
class Match(Block):
    """MATCH: synchronise entities waiting in several detached queues.
    queues = [(queue name, destination label)]; optional match attribute."""

    queues: list = field(default_factory=list)
    match_attr: str | None = None
    label: str | None = None

    def bind(self, model) -> None:
        for qn, _ in self.queues:
            model.ensure_queue(qn)
            model.match_blocks.setdefault(qn, []).append(self)

    def execute(self, sim, e):
        return None

    def try_match(self, sim) -> None:
        qs = [(sim.model.queue(sim, qn), lab) for qn, lab in self.queues]
        while all(q.entities for q, _ in qs):
            if self.match_attr:
                keys = set.intersection(*[{x.attrs.get(self.match_attr) for x in q.entities} for q, _ in qs])
                if not keys:
                    return
                k = min(keys, key=lambda kk: min(x.queue_enter for x in qs[0][0].entities if x.attrs.get(self.match_attr) == kk))
                picks = [next(x for x in q.entities if x.attrs.get(self.match_attr) == k) for q, _ in qs]
            else:
                picks = [q.entities[0] for q, _ in qs]
            for (q, lab), x in zip(qs, picks):
                q.remove(x)
                if lab:
                    sim.schedule_move(x, 0.0, sim.model.label_index(lab))
                else:
                    x._no_stats = True
                    sim.dispose(x)


@dataclass(repr=False, eq=False)
class Detach(Block):
    """A detached QUEUE (no following hold block): entities wait until removed/matched."""

    queue: str = ""
    label: str | None = None

    def bind(self, model) -> None:
        model.ensure_queue(self.queue)

    def execute(self, sim, e):
        q = sim.model.queue(sim, self.queue)
        q.insert(e)
        e.pc = self.index
        for m in sim.model.match_blocks.get(self.queue, []):
            m.try_match(sim)
        return HOLD


@dataclass(repr=False, eq=False)
class Combine(Group):
    """COMBINE: permanent representative from Quantity entities; optional match expression
    and representative entity type."""

    temporary: bool = False
    match_expr: Any = None
    rep_type: str | None = None

    def execute(self, sim, e):
        q = self.queue_of(sim)
        self.park(sim, e)
        n = int(_ev(sim, self.quantity, e))
        if self.match_expr is not None:
            key = _ev(sim, self.match_expr, e)
            members = [x for x in q.entities if _ev(sim, self.match_expr, x) == key]
        else:
            members = list(q.entities)
        if len(members) < n:
            return HOLD
        members = members[:n]
        for m in members:
            q.remove(m)
        rep = make_representative(sim, members, self.save_criterion, self.rep_type, temporary=False)
        rep.pc = self.index + 1
        sim.schedule_move(rep, 0.0)
        return HOLD


@dataclass(repr=False, eq=False)
class PickQ(Block):
    """PICKQ: choose one of several labelled QUEUE blocks (CYC|RAN|POR|LNQ|SNQ|LRC|SRC)."""

    queue_labels: list = field(default_factory=list)
    rule: str = "POR"
    balk_label: str | None = None
    label: str | None = None

    def execute(self, sim, e):
        m = sim.model
        cands = []
        for lab in self.queue_labels:
            qb = m.blocks[m.label_index(lab)]
            q = m.queue(sim, qb.queue)
            cap = _ev(sim, qb.capacity, e)
            cands.append((lab, q, cap))
        open_ = [c for c in cands if len(c[1]) < c[2]]
        if not open_:
            if self.balk_label:
                return self.balk_label
            sim.dispose(e)
            return DISPOSED
        rule = self.rule.upper()
        if rule == "LNQ":
            pick = max(open_, key=lambda c: len(c[1]))
        elif rule == "SNQ":
            pick = min(open_, key=lambda c: len(c[1]))
        elif rule == "LRC":
            pick = max(open_, key=lambda c: c[2] - len(c[1]))
        elif rule == "SRC":
            pick = min(open_, key=lambda c: c[2] - len(c[1]))
        elif rule == "RAN":
            pick = open_[int(m.streams[10].u() * len(open_))]
        elif rule == "CYC":
            start = getattr(self, "_cyc", 0)
            order = cands[start:] + cands[:start]
            pick = next(c for c in order if c in open_)
            self._cyc = (cands.index(pick) + 1) % len(cands)
        else:
            pick = open_[0]
        return pick[0]


@dataclass(repr=False, eq=False)
class Pickup(Block):
    """PICKUP: move Quantity entities starting at Rank from a queue into this entity's group."""

    queue: str = ""
    rank: Any = 1
    quantity: Any = 1
    label: str | None = None

    def execute(self, sim, e):
        q = sim.model.queue(sim, self.queue)
        r, n = int(_ev(sim, self.rank, e)), int(_ev(sim, self.quantity, e))
        if r + n - 1 > len(q):
            raise RuntimeError(f"PICKUP of {n} from rank {r} but {self.queue} holds {len(q)}")
        picked = q.entities[r - 1:r - 1 + n]
        for x in picked:
            q.remove(x)
            sim.wip[x.type] = sim.wip.get(x.type, 0) - 1
            if sim.anim is not None:
                sim.anim_event("dispose", x.serial)
                x._node = None
        e.members.extend(picked)
        e.group_temporary = True
        return None


@dataclass(repr=False, eq=False)
class Dropoff(Block):
    """DROPOFF: send Quantity group members starting at Rank to a label, optionally copying
    representative attributes ('*', 'A(*)' or a list of names)."""

    rank: Any = 1
    quantity: Any = 1
    destination: str = ""
    attributes: Any = None
    label: str | None = None

    def execute(self, sim, e):
        if e.members and not e.group_temporary:
            raise RuntimeError("members cannot be removed from a permanent group")
        r, n = int(_ev(sim, self.rank, e)), int(_ev(sim, self.quantity, e))
        out = e.members[r - 1:r - 1 + n]
        del e.members[r - 1:r - 1 + n]
        for x in out:
            a = self.attributes
            if a in ("*", "A(*)"):
                x.attrs.update({k: (list(v) if isinstance(v, list) else v) for k, v in e.attrs.items()})
                if a == "*":
                    x.station, x.sequence, x.jobstep, x.type, x.picture = (
                        e.station, e.sequence, e.jobstep, e.type, e.picture)
            elif isinstance(a, (list, tuple)):
                for name in a:
                    sim.model.assign(sim, x, name, sim.model.get_attr(sim, e, name))
            sim.wip[x.type] = sim.wip.get(x.type, 0) + 1
            sim.schedule_move(x, 0.0, sim.model.label_index(self.destination))
        return None


@dataclass(repr=False, eq=False)
class Copy(Block):
    """COPY: duplicate the entity at Rank of a queue (it stays queued) and send the copy on."""

    queue: str = ""
    rank: Any = 1
    destination: str = ""
    label: str | None = None

    def execute(self, sim, e):
        q = sim.model.queue(sim, self.queue)
        r = int(_ev(sim, self.rank, e))
        if 1 <= r <= len(q):
            d = q.entities[r - 1].clone(sim)
            sim.wip[d.type] = sim.wip.get(d.type, 0) + 1
            sim.schedule_move(d, 0.0, sim.model.label_index(self.destination))
        return None


@dataclass(repr=False, eq=False)
class Select(HoldBlock):
    """SELECT: send the entity to one of several labelled SEIZE blocks whose resources are
    available, chosen by rule (POR|CYC|RAN|LNB|SNB|LRC|SRC). Only the queue head is eligible."""

    seize_labels: list = field(default_factory=list)
    rule: str = "POR"
    label: str | None = None

    def bind(self, model) -> None:
        super().bind(model)
        self._targets = [model.blocks[model.label_index(lab)] for lab in self.seize_labels]
        for t in self._targets:
            for rexpr, _ in t.resources:
                if isinstance(rexpr, str) and rexpr in model.resource_specs:
                    model.register_waiter(rexpr, self)

    def _choose(self, sim, e):
        ok = [t for t in self._targets if t._can(t._requirements(sim, e))]
        if not ok:
            return None
        rule = self.rule.upper()
        load = lambda t: sum(r.busy for r, _ in t._requirements(sim, e))
        free = lambda t: sum(r.available for r, _ in t._requirements(sim, e))
        if rule == "LNB":
            return max(ok, key=load)
        if rule == "SNB":
            return min(ok, key=load)
        if rule == "LRC":
            return max(ok, key=free)
        if rule == "SRC":
            return min(ok, key=free)
        if rule == "RAN":
            return ok[int(sim.model.streams[10].u() * len(ok))]
        if rule == "CYC":
            start = getattr(self, "_cyc", 0)
            order = self._targets[start:] + self._targets[:start]
            t = next(x for x in order if x in ok)
            self._cyc = (self._targets.index(t) + 1) % len(self._targets)
            return t
        return ok[0]

    def execute(self, sim, e):
        if not self.entry_queue(sim, e).entities:
            t = self._choose(sim, e)
            if t is not None:
                self.pass_through(sim, e)
                return t.label
        return self.park(sim, e)

    def try_release_waiting(self, sim, res) -> bool:
        q = self.queue_of(sim)
        if not q.entities:
            return False
        e = q.entities[0]
        t = self._choose(sim, e)
        if t is None:
            return False
        q.remove(e)
        t._take(sim, e, t._requirements(sim, e))
        sim.schedule_move(e, 0.0, t.index + 1)
        return True


@dataclass(repr=False, eq=False)
class BlockPoints(Block):
    """BLOCK block: add block points to a blockage (named BlockPoints to avoid clashing with Block)."""

    blockage: str = ""
    points: Any = 1
    label: str | None = None

    def execute(self, sim, e):
        n = int(_ev(sim, self.points, e))
        if n >= 0:
            sim.model.change_blockage(sim, self.blockage, n)
        return None


@dataclass(repr=False, eq=False)
class Unblock(Block):
    blockage: str = ""
    points: Any = 1
    label: str | None = None

    def execute(self, sim, e):
        n = int(_ev(sim, self.points, e))
        if n >= 0:
            sim.model.change_blockage(sim, self.blockage, -n)
        return None


@dataclass(repr=False, eq=False)
class Proceed(HoldBlock):
    """PROCEED: hold until all listed blockages have zero block points."""

    blockages: list = field(default_factory=list)
    priority: Any = 1
    label: str | None = None

    def bind(self, model) -> None:
        super().bind(model)
        for b in self.blockages:
            lst = model.proceed_blocks.setdefault(b, [])
            if self not in lst:
                lst.append(self)

    def _clear(self, sim) -> bool:
        return all(sim._blockages.get(b, 0) <= 0 for b in self.blockages)

    def execute(self, sim, e):
        if not self.queue_of(sim).entities and self._clear(sim):
            self.pass_through(sim, e)
            return None
        return self.park(sim, e)

    def release_one(self, sim) -> bool:
        q = self.queue_of(sim)
        if q.entities and self._clear(sim):
            self.resume(sim, q.entities[0])
            return True
        return False


@dataclass(repr=False, eq=False)
class OnChange(Block):
    """ONCHANGE: source block; creates an entity each time a monitored variable gets a
    new value (one per changed variable) and the optional condition holds."""

    variables: list = field(default_factory=list)
    condition: Any = None
    entity_type: str | None = None
    label: str | None = None

    def bind(self, model) -> None:
        for v in self.variables:
            lst = model.onchange_watchers.setdefault(v, [])
            if self not in lst:
                lst.append(self)

    def changed(self, sim, var: str) -> None:
        if self.condition is not None and not _ev(sim, self.condition):
            return
        e = sim.new_entity(self.entity_type, self.index + 1)
        sim.schedule_move(e, 0.0)

    def execute(self, sim, e):
        return None


@dataclass(repr=False, eq=False)
class Close(Block):
    """CLOSE: close a FILES element file; it reopens from the start on next use."""

    file: str = ""
    label: str | None = None

    def execute(self, sim, e):
        h = sim._files.pop(self.file, None)
        if h is not None:
            h.close()
        return None


# --- Queue manipulation -----------------------------------------------------------------------

@dataclass(repr=False, eq=False)
class Remove(Block):
    """REMOVE: take the entity at Rank from a queue and send it to Removed Entity label."""

    queue: str = ""
    rank: Any = 1
    destination: str = ""
    label: str | None = None

    def execute(self, sim, e):
        q = sim.model.queue(sim, self.queue)
        r = int(_ev(sim, self.rank, e))
        if 1 <= r <= len(q):
            x = q.remove_at(r)
            sim.schedule_move(x, 0.0, sim.model.label_index(self.destination))
        return None


@dataclass(repr=False, eq=False)
class Search(Block):
    """SEARCH: set J to the first rank in [start, end] of `queue` satisfying condition (0 if none).
    Inside the condition, attributes refer to the searched entity."""

    queue: str = ""
    start: Any = 1
    end: Any = "NQ"
    condition: Any = True
    found_label: str | None = None
    label: str | None = None

    def execute(self, sim, e):
        q = sim.model.queue(sim, self.queue)
        lo = int(_ev(sim, self.start, e))
        hi = len(q) if self.end == "NQ" else int(_ev(sim, self.end, e))
        step = 1 if hi >= lo else -1
        sim.j = 0
        for r in range(lo, hi + step, step):
            if 1 <= r <= len(q) and _ev(sim, self.condition, q.entities[r - 1]):
                sim.j = r
                break
        if sim.j == 0 and self.found_label is None:
            return None
        return None if sim.j == 0 else self.found_label


@dataclass(repr=False, eq=False)
class FindJ(Block):
    """FINDJ: J = first index in [start, end] for which condition holds (uses J in the condition)."""

    start: Any = 1
    end: Any = 1
    condition: Any = True
    label: str | None = None

    def execute(self, sim, e):
        lo, hi = int(_ev(sim, self.start, e)), int(_ev(sim, self.end, e))
        step = 1 if hi >= lo else -1
        found = 0
        for j in range(lo, hi + step, step):
            sim.j = j
            if _ev(sim, self.condition, e):
                found = j
                break
        sim.j = found
        return None


@dataclass(repr=False, eq=False)
class Insert(Block):
    """INSERT: place the current entity into a queue at a given rank (default by ranking)."""

    queue: str = ""
    rank: Any = None
    label: str | None = None

    def execute(self, sim, e):
        q = sim.model.queue(sim, self.queue)
        q.insert(e, None if self.rank is None else int(_ev(sim, self.rank, e)))
        e.pc = q.owner.index if q.owner else self.index
        owner = q.owner
        if isinstance(owner, Seize):  # the hold block may be able to serve it now
            for r, _ in owner._requirements(sim, e) or []:
                sim.resource_freed(r)
        elif owner is not None and hasattr(owner, "poll"):
            owner.poll(sim)
        return HOLD


@dataclass(repr=False, eq=False)
class Zap(Block):
    """ZAP: remove the entity with the given serial number from the calendar and send it on."""

    serial: Any = 0
    destination: str = ""
    label: str | None = None

    def execute(self, sim, e):
        target = int(_ev(sim, self.serial, e))
        for ev in list(sim.cal._heap):
            if ev.entity is not None and ev.entity.serial == target and not ev.cancelled:
                ev.cancel()
                sim.schedule_move(ev.entity, 0.0, sim.model.label_index(self.destination))
                break
        return None


# --- Stations and routing ------------------------------------------------------------------------

@dataclass(repr=False, eq=False)
class Station(Block):
    station: str = ""
    label: str | None = None

    def bind(self, model) -> None:
        model.station_index[self.station] = self.index

    def execute(self, sim, e):
        e.station = self.station
        sim.model.station_enter(sim, self.station)
        return None


@dataclass(repr=False, eq=False)
class Route(Block):
    """ROUTE: Route Time, Destination (station name, or 'SEQ' to follow the entity's sequence)."""

    duration: Any = 0.0
    destination: Any = "SEQ"
    label: str | None = None

    def execute(self, sim, e):
        dest = sim.model.next_destination(sim, e, self.destination)
        d = float(_ev(sim, self.duration, e))
        e.accrue("tran", d)
        sim.model.station_leave(sim, e.station)
        sim.schedule_move(e, d, sim.model.station_index[dest])
        return HOLD


# --- Storages and misc --------------------------------------------------------------------------

@dataclass(repr=False, eq=False)
class Store(Block):
    storage: str = ""
    label: str | None = None

    def execute(self, sim, e):
        sim.model.storage(sim, self.storage, +1)
        return None


@dataclass(repr=False, eq=False)
class Unstore(Block):
    storage: str = ""
    label: str | None = None

    def execute(self, sim, e):
        sim.model.storage(sim, self.storage, -1)
        return None


@dataclass(repr=False, eq=False)
class Trace(Block):
    message: str = ""
    args: list = field(default_factory=list)
    label: str | None = None

    def execute(self, sim, e):
        vals = [_ev(sim, a, e) for a in self.args]
        sim.model.output.append(f"{sim.now:.4f} {self.message.format(*vals)}")
        return None


@dataclass(repr=False, eq=False)
class Write(Block):
    """WRITE: append evaluated values to a model file (FILES element) or the output list."""

    file: str | None = None
    values: list = field(default_factory=list)
    fmt: str | None = None
    label: str | None = None

    def execute(self, sim, e):
        vals = [_ev(sim, v, e) for v in self.values]
        line = self.fmt.format(*vals) if self.fmt else " ".join(str(v) for v in vals)
        sim.model.write_line(sim, self.file, line)
        return None


@dataclass(repr=False, eq=False)
class Read(Block):
    """READ: read the next record of a FILES element into attributes/variables."""

    file: str = ""
    targets: list = field(default_factory=list)
    eof_label: str | None = None
    label: str | None = None

    def execute(self, sim, e):
        rec = sim.model.read_record(sim, self.file)
        if rec is None:
            return self.eof_label or None
        for t, v in zip(self.targets, rec):
            sim.model.assign(sim, e, t, v)
        return None


@dataclass(repr=False, eq=False)
class Call(Block):
    """User code hook (replaces SIMAN EVENT / VBA blocks): fn(sim, entity) -> None|label."""

    fn: Any = None
    label: str | None = None

    def execute(self, sim, e):
        return self.fn(sim, e)
