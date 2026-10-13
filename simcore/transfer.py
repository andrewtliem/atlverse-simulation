"""Material handling: free-path transporters and conveyors (SIMAN Advanced Transfer).

Free-path transporters (TRANSPORTERS + DISTANCES elements)
  REQUEST   hold until a unit is allocated, then move it empty to the entity's station
  ALLOCATE  allocate a unit without moving it
  MOVE      move an allocated unit empty to a station
  TRANSPORT move entity and its unit to a destination station
  FREE      release the unit at its current station
  HALT / ACTIVATE  take a unit out of / back into service

Conveyors (CONVEYORS + SEGMENTS elements), cell based
  ACCESS  hold until `cells` consecutive free cells exist at the entity's station
  CONVEY  ride to a destination station; arrival is when the leading cell reaches it
  EXIT    release the cells
  START / STOP  conveyor status
A non-accumulating conveyor stops entirely while any entity sits at its destination
without exiting; an accumulating conveyor only blocks the entities behind it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from . import blocks as B
from .core import HOLD, Entity, Simulation
from .stats import TimePersistent

# --- Free-path transporters --------------------------------------------------------


class TransporterUnit:
    def __init__(self, fleet: "Fleet", index: int, station: str) -> None:
        self.fleet, self.index = fleet, index
        self.station = station
        self.owner: Entity | None = None
        self.active = True
        self.moving = False

    @property
    def idle(self) -> bool:
        return self.active and self.owner is None


class Fleet:
    def __init__(self, sim: Simulation, spec: dict) -> None:
        self.sim = sim
        self.name = spec["name"]
        self.velocity = spec.get("velocity", 1.0)
        self.distances: dict = spec["distances"]
        start = spec.get("initial_station")
        n = int(spec.get("units", 1))
        starts = start if isinstance(start, list) else [start] * n
        self.units = [TransporterUnit(self, i + 1, starts[i]) for i in range(n)]
        self.busy = TimePersistent(f"{self.name}.NumberBusy")
        self.waiters: list = []  # Request/Allocate blocks

    def distance(self, a: str, b: str) -> float:
        if a == b or a is None or b is None:
            return 0.0
        d = self.distances.get((a, b))
        if d is None:
            d = self.distances.get((b, a))  # SIMAN mirrors unspecified reverse distances
        if d is None:
            raise KeyError(f"no distance from {a} to {b} for transporter {self.name}")
        return d

    def travel_time(self, a: str, b: str) -> float:
        return self.distance(a, b) / self.velocity

    def travel(self, u: "TransporterUnit", dest: str, velocity: float | None, done) -> None:
        """Move unit u to dest and call done() on arrival (free path: no interference)."""
        v = velocity or self.velocity
        t = self.distance(u.station, dest) / v
        u.moving = True

        def arrive():
            u.moving = False
            u.station = dest
            done()
        self.sim.cal.schedule(t, arrive)

    def touch(self) -> None:
        self.busy.update(self.sim.now, sum(u.owner is not None for u in self.units))

    def pick(self, rule: str, station: str | None, unit: int | None = None) -> TransporterUnit | None:
        free = [u for u in self.units if u.idle]
        if unit is not None:
            free = [u for u in free if u.index == unit]
        if not free:
            return None
        rule = rule.upper()
        if rule == "SDS":  # smallest distance to station
            return min(free, key=lambda u: self.distance(u.station, station))
        if rule == "LDS":
            return max(free, key=lambda u: self.distance(u.station, station))
        if rule == "RAN":
            return free[int(self.sim.model.streams[10].u() * len(free))]
        if rule == "CYC":
            last = getattr(self, "_cyc", 0)
            for k in range(len(self.units)):
                u = self.units[(last + k) % len(self.units)]
                if u in free:
                    self._cyc = u.index % len(self.units)
                    return u
        return free[0]  # POR (preferred order)

    def freed(self) -> None:
        for w in self.waiters:
            while w.queue_of(self.sim).entities and any(u.idle for u in self.units):
                if not w.serve_head(self.sim):
                    break


def _fleet(sim: Simulation, name: str) -> Fleet:
    return sim._fleets[name]


def _unit_of(sim: Simulation, e: Entity, name: str) -> TransporterUnit:
    u = e.attrs.get(f"__tu_{name}")
    if u is None:
        raise RuntimeError(f"{e} has no {name} transporter allocated")
    return u


@dataclass(repr=False, eq=False)
class Request(B.HoldBlock):
    """REQUEST: Priority, Transporter, selection rule (CYC|RAN|POR|SDS|LDS), unit number,
    velocity override. Moves the allocated unit empty to the entity's station."""

    transporter: str = ""
    rule: str = "SDS"
    unit: Any = None
    priority: Any = 1
    move: bool = True
    label: str | None = None

    def bind(self, model) -> None:
        super().bind(model)
        lst = model.fleet_waiters.setdefault(self.transporter, [])
        if self not in lst:
            lst.append(self)

    def execute(self, sim, e):
        q = self.entry_queue(sim, e)
        if not q.entities and self._try(sim, e):
            self.pass_through(sim, e)
            return HOLD if self.move else None
        return self.park(sim, e)

    def _try(self, sim, e) -> bool:
        f = _fleet(sim, self.transporter)
        unit = None if self.unit is None else int(sim.evaluate(self.unit, e))
        u = f.pick(self.rule, e.station, unit)
        if u is None:
            return False
        u.owner = e
        e.attrs[f"__tu_{self.transporter}"] = u
        f.touch()
        if self.move:
            e.pc = self.index + 1
            f.travel(u, e.station, None, lambda: sim.schedule_move(e, 0.0))
        return True

    def serve_head(self, sim) -> bool:
        q = self.queue_of(sim)
        e = q.entities[0]
        if not self._try(sim, e):
            return False
        q.remove(e)
        if not self.move:
            sim.schedule_move(e, 0.0, self.index + 1)
        return True


class Allocate(Request):
    """ALLOCATE: like REQUEST but the unit stays where it is."""

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.move = False


@dataclass(repr=False, eq=False)
class Move(B.Block):
    """MOVE: move the entity's allocated unit (empty) to a station; entity waits."""

    transporter: str = ""
    destination: Any = ""
    label: str | None = None

    def execute(self, sim, e):
        f = _fleet(sim, self.transporter)
        u = _unit_of(sim, e, self.transporter)
        dest = sim.model.next_destination(sim, e, self.destination)
        e.pc = self.index + 1
        f.travel(u, dest, None, lambda: sim.schedule_move(e, 0.0))
        return HOLD


@dataclass(repr=False, eq=False)
class Transport(B.Block):
    """TRANSPORT: carry the entity to Destination (station or SEQ) with its allocated unit."""

    transporter: str = ""
    destination: Any = "SEQ"
    velocity: Any = None
    label: str | None = None

    def execute(self, sim, e):
        f = _fleet(sim, self.transporter)
        u = _unit_of(sim, e, self.transporter)
        dest = sim.model.next_destination(sim, e, self.destination)
        v = None if self.velocity is None else float(sim.evaluate(self.velocity, e))
        sim.model.station_leave(sim, e.station)
        t0 = sim.now

        def arrive():
            e.accrue("tran", sim.now - t0)
            sim.schedule_move(e, 0.0, sim.model.station_index[dest])
        f.travel(u, dest, v, arrive)
        return HOLD


@dataclass(repr=False, eq=False)
class Free(B.Block):
    transporter: str = ""
    label: str | None = None

    def execute(self, sim, e):
        f = _fleet(sim, self.transporter)
        u = e.attrs.pop(f"__tu_{self.transporter}", None)
        if u is None:
            raise RuntimeError(f"{e} frees {self.transporter} but has none allocated")
        u.owner = None
        f.touch()
        f.freed()
        return None


@dataclass(repr=False, eq=False)
class Halt(B.Block):
    transporter: str = ""
    unit: Any = 1
    label: str | None = None

    def execute(self, sim, e):
        f = _fleet(sim, self.transporter)
        f.units[int(sim.evaluate(self.unit, e)) - 1].active = False
        return None


@dataclass(repr=False, eq=False)
class Activate(B.Block):
    transporter: str = ""
    unit: Any = 1
    label: str | None = None

    def execute(self, sim, e):
        f = _fleet(sim, self.transporter)
        f.units[int(sim.evaluate(self.unit, e)) - 1].active = True
        f.freed()
        return None


# --- Conveyors ---------------------------------------------------------------------


class Conveyor:
    """Cells numbered 0..n-1 along the path; stations sit at cell positions."""

    def __init__(self, sim: Simulation, spec: dict) -> None:
        self.sim = sim
        self.name = spec["name"]
        self.cell_size = float(spec.get("cell_size", 1.0))
        self.velocity = float(spec.get("velocity", 1.0))
        self.accumulating = spec.get("type", "nonaccumulating").lower().startswith("acc")
        self.loop = bool(spec.get("loop", False))
        pos = 0.0
        self.station_cell: dict[str, int] = {spec["segments"][0][0]: 0}
        for a, b, length in spec["segments"]:
            pos += length
            self.station_cell[b] = int(round(pos / self.cell_size))
        self.n = max(self.station_cell.values()) + (0 if self.loop else 1)
        self.cells: list[Entity | None] = [None] * max(1, self.n)
        self.active = True
        self.step_time = self.cell_size / self.velocity
        self.riders: dict[int, dict] = {}   # entity serial -> {e, head, length, dest, moving}
        self.ticking = False
        self.waiters: list = []
        self.util = TimePersistent(f"{self.name}.CellsOccupied")

    def _idx(self, i: int) -> int:
        return i % self.n if self.loop else i

    def free_run(self, start: int, length: int, ignore: Entity | None = None) -> bool:
        for k in range(length):
            i = start - k
            if not self.loop and (i < 0 or i >= self.n):
                return False
            c = self.cells[self._idx(i)]
            if c is not None and c is not ignore:
                return False
        return True

    def place(self, e: Entity, head: int, length: int) -> None:
        for k in range(length):
            self.cells[self._idx(head - k)] = e
        self.riders[e.serial] = dict(e=e, head=head, length=length, dest=None)
        self._touch()

    def remove(self, e: Entity) -> None:
        r = self.riders.pop(e.serial, None)
        if r is None:
            return
        for k in range(r["length"]):
            if self.cells[self._idx(r["head"] - k)] is e:
                self.cells[self._idx(r["head"] - k)] = None
        self._touch()
        self.kick()
        for w in self.waiters:
            w.retry(self.sim)

    def _touch(self) -> None:
        self.util.update(self.sim.now, sum(c is not None for c in self.cells))

    def convey(self, e: Entity, dest: str, on_arrive) -> None:
        r = self.riders[e.serial]
        r["dest"] = self.station_cell[dest]
        r["on_arrive"] = on_arrive
        r["arrived"] = False
        if self._at_dest(r):
            self._arrive(r)
        self.kick()

    def _at_dest(self, r) -> bool:
        return r["dest"] is not None and self._idx(r["head"]) == r["dest"]

    def _arrive(self, r) -> None:
        r["arrived"] = True
        cb = r.pop("on_arrive")
        r["dest"] = None
        cb()

    def _stopped_by_arrival(self) -> bool:
        return not self.accumulating and any(r.get("arrived") for r in self.riders.values())

    def kick(self) -> None:
        if not self.ticking and self.active and any(r["dest"] is not None for r in self.riders.values()):
            self.ticking = True
            self.sim.cal.schedule(self.step_time, self._step)

    def _step(self) -> None:
        self.ticking = False
        if not self.active or self._stopped_by_arrival():
            return
        movers = [r for r in self.riders.values() if r["dest"] is not None]
        # Move riders from the front so space vacated ahead is usable in the same step.
        movers.sort(key=lambda r: -r["head"])
        moved_any = False
        for r in movers:
            nxt = r["head"] + 1
            if not self.loop and nxt >= self.n:
                continue
            ahead = self.cells[self._idx(nxt)]
            if ahead is not None and ahead is not r["e"]:
                if self.accumulating:
                    continue
                # Non-accumulating conveyors move as one; a blocked lead stops everyone.
                return
            e = r["e"]
            self.cells[self._idx(r["head"] - r["length"] + 1)] = None
            self.cells[self._idx(nxt)] = e
            r["head"] = nxt
            moved_any = True
        for r in movers:
            if self._at_dest(r):
                self._arrive(r)
        if moved_any:
            self._touch()
            for w in self.waiters:  # cells at entry points may have opened up
                w.retry(self.sim)
        if moved_any or any(r["dest"] is not None for r in self.riders.values()):
            self.kick()


def _conv(sim: Simulation, name: str) -> Conveyor:
    return sim._conveyors[name]


@dataclass(repr=False, eq=False)
class Access(B.HoldBlock):
    """ACCESS: Conveyor, Number of Cells. Entity must be at a station on the conveyor."""

    conveyor: str = ""
    cells: Any = 1
    priority: Any = 1
    label: str | None = None

    def bind(self, model) -> None:
        super().bind(model)
        lst = model.conveyor_waiters.setdefault(self.conveyor, [])
        if self not in lst:
            lst.append(self)

    def _try(self, sim, e) -> bool:
        c = _conv(sim, self.conveyor)
        n = int(sim.evaluate(self.cells, e))
        head = c.station_cell[e.station]
        if not c.free_run(head, n):
            return False
        c.place(e, head, n)
        return True

    def execute(self, sim, e):
        if not self.entry_queue(sim, e).entities and self._try(sim, e):
            self.pass_through(sim, e)
            return None
        return self.park(sim, e)

    def retry(self, sim) -> None:
        q = self.queue_of(sim)
        if q.entities and self._try(sim, q.entities[0]):
            self.resume(sim, q.entities[0])


@dataclass(repr=False, eq=False)
class Convey(B.Block):
    conveyor: str = ""
    destination: Any = "SEQ"
    label: str | None = None

    def execute(self, sim, e):
        c = _conv(sim, self.conveyor)
        dest = sim.model.next_destination(sim, e, self.destination)
        sim.model.station_leave(sim, e.station)
        t0 = sim.now

        def arrive():
            e.accrue("tran", sim.now - t0)
            sim.schedule_move(e, 0.0, sim.model.station_index[dest])
        c.convey(e, dest, arrive)
        return HOLD


@dataclass(repr=False, eq=False)
class Exit(B.Block):
    conveyor: str = ""
    label: str | None = None

    def execute(self, sim, e):
        _conv(sim, self.conveyor).remove(e)
        return None


@dataclass(repr=False, eq=False)
class Start(B.Block):
    conveyor: str = ""
    label: str | None = None

    def execute(self, sim, e):
        c = _conv(sim, self.conveyor)
        c.active = True
        c.kick()
        return None


@dataclass(repr=False, eq=False)
class Stop(B.Block):
    conveyor: str = ""
    label: str | None = None

    def execute(self, sim, e):
        _conv(sim, self.conveyor).active = False
        return None


# --- model integration ------------------------------------------------------------------

def install(model) -> None:
    """Attach transporter/conveyor support to a Model instance."""
    if getattr(model, "_transfer_installed", False):
        return
    model._transfer_installed = True
    model.transporter_specs = getattr(model, "transporter_specs", {})
    model.conveyor_specs = getattr(model, "conveyor_specs", {})
    model.fleet_waiters = {}
    model.conveyor_waiters = {}
    start = model.start

    def start_with_transfer(sim):
        make = getattr(model, "_fleet_factory", Fleet)
        sim._fleets = {n: make(sim, s) for n, s in model.transporter_specs.items()}
        sim._conveyors = {n: Conveyor(sim, s) for n, s in model.conveyor_specs.items()}
        start(sim)
        for n, f in sim._fleets.items():
            f.waiters = model.fleet_waiters.get(n, [])
        for n, c in sim._conveyors.items():
            c.waiters = model.conveyor_waiters.get(n, [])

    model.start = start_with_transfer


def transporter(model, name: str, units: int = 1, velocity: float = 1.0, distances: dict | None = None,
                initial_station=None) -> None:
    install(model)
    model.transporter_specs[name] = dict(name=name, units=units, velocity=velocity,
                                         distances=distances or {}, initial_station=initial_station)


def conveyor(model, name: str, segments: list, velocity: float = 1.0, cell_size: float = 1.0,
             type: str = "nonaccumulating", loop: bool = False) -> None:
    """segments: [(from_station, to_station, length), ...] in path order."""
    install(model)
    model.conveyor_specs[name] = dict(name=name, segments=segments, velocity=velocity,
                                      cell_size=cell_size, type=type, loop=loop)
