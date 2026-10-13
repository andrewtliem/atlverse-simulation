"""Guided transporters (AGVs) on a zone-controlled network.

Elements
  INTERSECTIONS  name -> travel length through the intersection (0 = point)
  LINKS          (name, from, to, zones, zone_length, type) with type
                 unidirectional | bidirectional | spur (spur: bidirectional dead end)
  NETWORKS       links included in the system map (default: all)
  stations       station -> intersection (stations sit on intersections)

Movement follows shortest-length paths. A vehicle advances one zone (or intersection)
at a time and must seize the next one before entering it; each zone/intersection holds
one vehicle and serves waiting vehicles FIFO. A vehicle occupies `size` zones; zone
control `start` frees a trailing zone as soon as the vehicle starts into the next one,
`end` keeps it until the vehicle reaches the end of the next one.
Not modelled: acceleration/deceleration, turning-velocity factors, REDIRECTS.
"""

from __future__ import annotations

import heapq
import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from . import blocks as B
from . import transfer as T
from .core import Simulation
from .stats import TimePersistent


class Segment:
    """A zone or an intersection: capacity one vehicle, FIFO waiting list."""

    def __init__(self, key, length: float) -> None:
        self.key = key
        self.length = length
        self.holder = None
        self.waiting: deque = deque()


class Network:
    def __init__(self, spec: dict) -> None:
        self.intersections: dict[str, float] = dict(spec.get("intersections", {}))
        self.station_node: dict[str, str] = dict(spec.get("stations", {}))
        self.segments: dict[Any, Segment] = {}
        self.adj: dict[str, list] = {}  # node -> [(next node, [segment keys], length)]
        allowed = set(spec.get("network") or [])
        for n, length in self.intersections.items():
            self.segments[("I", n)] = Segment(("I", n), float(length))
        for link in spec["links"]:
            name, a, b, zones, zlen = link[:5]
            kind = (link[5] if len(link) > 5 else "unidirectional").lower()
            if allowed and name not in allowed:
                continue
            for n in (a, b):
                if ("I", n) not in self.segments:
                    self.intersections[n] = 0.0
                    self.segments[("I", n)] = Segment(("I", n), 0.0)
            keys = [("Z", name, i) for i in range(int(zones))]
            for k in keys:
                self.segments[k] = Segment(k, float(zlen))
            total = float(zones) * float(zlen)
            self.adj.setdefault(a, []).append((b, keys, total))
            if kind in ("bidirectional", "spur"):
                self.adj.setdefault(b, []).append((a, list(reversed(keys)), total))

    def node(self, place: str) -> str:
        return self.station_node.get(place, place)

    def path(self, a: str, b: str) -> list:
        """Segment keys from intersection a (exclusive) to b (inclusive), shortest length."""
        a, b = self.node(a), self.node(b)
        if a == b:
            return []
        dist = {a: 0.0}
        prev: dict[str, tuple] = {}
        pq = [(0.0, a)]
        while pq:
            d, n = heapq.heappop(pq)
            if n == b:
                break
            if d > dist.get(n, math.inf):
                continue
            for m, keys, length in self.adj.get(n, []):
                nd = d + length + self.intersections.get(m, 0.0)
                if nd < dist.get(m, math.inf):
                    dist[m] = nd
                    prev[m] = (n, keys)
                    heapq.heappush(pq, (nd, m))
        if b not in prev:
            raise RuntimeError(f"no path from {a} to {b} in the guided network")
        out: list = []
        n = b
        while n != a:
            p, keys = prev[n]
            out = keys + [("I", n)] + out
            n = p
        return out

    def distance(self, a: str, b: str) -> float:
        return sum(self.segments[k].length for k in self.path(a, b))


class Vehicle(T.TransporterUnit):
    def __init__(self, fleet, index, station) -> None:
        super().__init__(fleet, index, station)
        self.held: deque = deque()   # segment keys held, oldest first
        self.size = fleet.size


class GuidedFleet(T.Fleet):
    """TRANSPORTERS with System Map Type = Network."""

    def __init__(self, sim: Simulation, spec: dict) -> None:
        self.sim = sim
        self.name = spec["name"]
        self.velocity = spec.get("velocity", 1.0)
        self.net: Network = sim._networks[spec["network"]]
        self.control = spec.get("control", "start").lower()
        self.size = int(spec.get("size", 1))
        start = spec.get("initial_station")
        n = int(spec.get("units", 1))
        starts = start if isinstance(start, list) else [start] * n
        self.units = [Vehicle(self, i + 1, starts[i]) for i in range(n)]
        self.busy = TimePersistent(f"{self.name}.NumberBusy")
        self.waiters: list = []
        for u in self.units:  # vehicles start parked on their intersection
            seg = self.net.segments[("I", self.net.node(u.station))]
            if seg.holder is not None:
                raise RuntimeError(f"two vehicles start on intersection {u.station}")
            seg.holder = u
            u.held.append(seg.key)

    def distance(self, a, b) -> float:
        return self.net.distance(a, b)

    # --- movement ---------------------------------------------------------------------
    def travel(self, u: Vehicle, dest: str, velocity: float | None, done) -> None:
        v = velocity or self.velocity
        route = deque(self.net.path(u.station, dest))
        u.moving = True

        def finish():
            u.moving = False
            u.station = dest
            done()

        def step():
            if not route:
                finish()
                return
            key = route[0]
            seg = self.net.segments[key]
            if seg.holder is not None and seg.holder is not u:
                seg.waiting.append(step)   # retried when the segment is released
                return
            route.popleft()
            seg.holder = u
            u.held.append(key)
            if self.control == "start":
                self._trim(u, keep=u.size)
            self.sim.cal.schedule(seg.length / v, entered)

        def entered():
            if self.control == "end":
                self._trim(u, keep=u.size)
            step()

        step()

    def _trim(self, u: Vehicle, keep: int) -> None:
        while len(u.held) > keep:
            self._release(u, u.held.popleft())

    def _release(self, u: Vehicle, key) -> None:
        seg = self.net.segments[key]
        if seg.holder is u:
            seg.holder = None
            if seg.waiting:
                retry = seg.waiting.popleft()
                self.sim.cal.schedule(0.0, retry)


@dataclass(repr=False, eq=False)
class Capture(B.Block):
    """CAPTURE: the controlling entity's vehicle grows by Quantity zones (it keeps more trailing zones)."""

    transporter: str = ""
    quantity: Any = 1
    label: str | None = None

    def execute(self, sim, e):
        u = T._unit_of(sim, e, self.transporter)
        u.size += int(sim.evaluate(self.quantity, e))
        return None


@dataclass(repr=False, eq=False)
class Relinquish(B.Block):
    """RELINQUISH: the vehicle shrinks by Quantity zones, releasing trailing zones now."""

    transporter: str = ""
    quantity: Any = 1
    label: str | None = None

    def execute(self, sim, e):
        u = T._unit_of(sim, e, self.transporter)
        u.size = max(1, u.size - int(sim.evaluate(self.quantity, e)))
        u.fleet._trim(u, keep=u.size)
        return None


def network(model, name: str, links: list, intersections: dict | None = None,
            stations: dict | None = None, include: list | None = None) -> None:
    """Define a guided network. links: [(name, from, to, zones, zone_length, type), ...]."""
    T.install(model)
    if not hasattr(model, "network_specs"):
        model.network_specs = {}
        start = model.start

        def start_with_networks(sim):
            sim._networks = {n: Network(s) for n, s in model.network_specs.items()}
            start(sim)
        # Networks must exist before fleets are built inside transfer's start hook.
        model.start = start_with_networks
        original_fleet = T.Fleet
        model._fleet_factory = lambda sim, s: GuidedFleet(sim, s) if s.get("network") else original_fleet(sim, s)
    model.network_specs[name] = dict(links=links, intersections=intersections or {},
                                     stations=stations or {}, network=include)


def guided_transporter(model, name: str, network: str, units: int = 1, velocity: float = 1.0,
                       initial_station=None, size: int = 1, control: str = "start") -> None:
    T.install(model)
    model.transporter_specs[name] = dict(name=name, network=network, units=units, velocity=velocity,
                                         initial_station=initial_station, size=size, control=control)
