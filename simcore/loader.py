"""YAML model format.

    name: Bank
    time_units: minutes
    replicate: {replications: 10, length: 480, warmup: 0}
    resources:   {Teller: {capacity: 2}}
    queues:      {Teller.Queue: {ranking: FIFO}}
    attributes:  {priority: 0}
    variables:   {open: 1}
    sets:        {Tellers: [T1, T2]}
    schedules:   {Shift: {segments: [[2, 240], [1, 240]], rule: wait}}
    failures:    [{name: Jam, resources: [Teller], up: EXPO(120), down: 10}]
    seeds:       {10: {seed: 12345, reinit: common}}
    flow:
      - create:  {interval: EXPO(5), entity_type: Customer}
      - process: {name: Service, action: seize_delay_release,
                  resources: [[Teller, 1]], delay: TRIA(3, 5, 8)}
      - decide:  {if: "priority > 1", then: Express}     # 2-way by condition
      - dispose: {}
      - {label: Express, count: {counter: Express}}

Every step is `{<block or module>: {...operands}, label: optional}`.
Block names are the SIMAN names (create, assign, delay, queue, seize, release, branch,
if, elseif, else, endif, while, endwhile, count, tally, dispose, duplicate, wait, signal,
scan, group, split, match, detach, remove, search, findj, insert, zap, station, route,
store, unstore, trace, write, read, alter, preempt).
Advanced Transfer: request, allocate, move, transport, free, halt, activate, access,
convey, exit, start, stop, capture, relinquish.  Continuous: detect.
Modules (Arena Basic Process style): process, decide, batch, separate, record.

Advanced elements:
    transporters: {Fork: {units: 2, velocity: 60, initial_station: Dock,
                          distances: [[Dock, Cell1, 120], [Cell1, Cell2, 40]]}}
    conveyors:    {Belt: {segments: [[In, Mid, 20], [Mid, Out, 30]], velocity: 10,
                          cell_size: 1, type: accumulating}}
    networks:     {Plant: {links: [[L1, A, B, 4, 5, bidirectional]],
                           stations: {Dock: A, Cell: B}}}
    transporters: {AGV: {network: Plant, units: 2, velocity: 1, initial_station: [Dock, Cell],
                         control: start, size: 1}}      # guided
    levels:       {Tank: {init: 0, rate: "inflow - outflow"}}
    cstats:       {TankLevel: Tank}
    continuous:   {max_step: 0.1}
"""

from __future__ import annotations

import math
import re
from typing import Any

from . import blocks as B
from . import continuous as C
from . import guided as G
from . import transfer as T
from .model import Model

BLOCKS = {
    "create": B.Create, "assign": B.Assign, "delay": B.Delay, "queue": B.QueueBlock,
    "seize": B.Seize, "release": B.Release, "branch": B.Branch, "if": B.If, "elseif": B.ElseIf,
    "else": B.Else, "endif": B.EndIf, "while": B.While, "endwhile": B.EndWhile, "count": B.Count,
    "tally": B.TallyBlock, "dispose": B.Dispose, "duplicate": B.Duplicate, "wait": B.Wait,
    "signal": B.Signal, "scan": B.Scan, "group": B.Group, "split": B.Split, "match": B.Match,
    "detach": B.Detach, "remove": B.Remove, "search": B.Search, "findj": B.FindJ, "insert": B.Insert,
    "zap": B.Zap, "station": B.Station, "route": B.Route, "store": B.Store, "unstore": B.Unstore,
    "trace": B.Trace, "write": B.Write, "read": B.Read, "alter": B.Alter, "preempt": B.Preempt,
    "combine": B.Combine, "pickq": B.PickQ, "qpick": B.QPick, "onchange": B.OnChange, "close": B.Close, "stack": B.Stack, "pickup": B.Pickup, "dropoff": B.Dropoff, "copy": B.Copy,
    "select": B.Select, "hold": B.HoldForever, "entity_stats": B.EntityStats, "block": B.BlockPoints, "unblock": B.Unblock, "proceed": B.Proceed,
    # Advanced Transfer
    "request": T.Request, "allocate": T.Allocate, "move": T.Move, "transport": T.Transport,
    "free": T.Free, "halt": T.Halt, "activate": T.Activate, "access": T.Access,
    "convey": T.Convey, "exit": T.Exit, "start": T.Start, "stop": T.Stop,
    "capture": G.Capture, "relinquish": G.Relinquish,
    # continuous
    "detect": C.Detect,
}


def _num(v: Any) -> Any:
    if isinstance(v, str) and v.strip().upper() in ("INF", "INFINITE", "INFINITY"):
        return math.inf
    return v


def _pairs(v):
    """[[a, b], ...] or {a: b} -> [(a, b), ...]"""
    if isinstance(v, dict):
        return list(v.items())
    return [x if isinstance(x, dict) else tuple(x) if isinstance(x, (list, tuple)) else (x, 1) for x in v]


def load(path_or_text: str) -> Model:
    import yaml  # only needed for YAML files; the in-browser build runs without it

    if "\n" in path_or_text or path_or_text.lstrip().startswith("{"):
        data = yaml.safe_load(path_or_text)
    else:
        with open(path_or_text, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    return from_dict(data)


def from_dict(d: dict) -> Model:
    m = Model(d.get("name", "Model"), d.get("time_units", "minutes"))
    for n, init in (d.get("attributes") or {}).items():
        if isinstance(init, dict):
            m.attribute(n, init.get("init", 0.0), tuple(init.get("dims", ())))
        else:
            m.attribute(n, init)
    for n, spec in (d.get("variables") or {}).items():
        if isinstance(spec, dict):
            m.variable(n, spec.get("init", 0.0), tuple(spec.get("dims", ())), spec.get("track", False),
                       spec.get("clear", "system"))
        else:
            m.variable(n, spec)
    for n, e in (d.get("expressions") or {}).items():
        m.expression(n, e)
    for n, spec in (d.get("resources") or {}).items():
        spec = spec or {}
        m.resource(n, _num(spec.get("capacity", 1)), spec.get("schedule"), spec.get("busy_per_hour", 0.0),
                   spec.get("idle_per_hour", 0.0), spec.get("per_use", 0.0), spec.get("stateset"),
                   spec.get("schedule_rule"), spec.get("initial_state"))
    for n, spec in (d.get("queues") or {}).items():
        spec = spec or {}
        m.queue(n, ranking=spec.get("ranking", "FIFO"), attribute=spec.get("attribute"))
    for a in d.get("arrivals") or []:
        m.arrival(a["at"], a.get("kind", "time"), a.get("time", 0.0), a.get("batch", 1), a.get("every"),
                  a.get("entity_type"))
    for n, default in (d.get("statics") or {}).items():
        m.static(n, default)
    for n, spec in (d.get("recipes") or {}).items():
        m.recipe(n, spec.get("values", {}), spec.get("stations"))
    for n, spec in (d.get("activity_areas") or {}).items():
        m.activity_area(n, spec.get("stations"), spec.get("parent"))
    for n, init in (d.get("blockages") or {}).items():
        m.blockage(n, init)
    for n, members in (d.get("sets") or {}).items():
        m.set(n, members)
    for n, spec in (d.get("schedules") or {}).items():
        m.schedule(n, [tuple(s) for s in spec["segments"]], spec.get("kind", "capacity"),
                   spec.get("rule", "ignore"), spec.get("repeat", True), spec.get("scale", 1.0))
    for f in d.get("failures") or []:
        m.failure(f["name"], f["resources"], f.get("kind", "time"), f.get("up", 100), f.get("down", 10),
                  f.get("rule", "ignore"), f.get("uptime_in_state"))
    for n, steps in (d.get("sequences") or {}).items():
        m.sequence(n, [s if isinstance(s, str) else (s["station"], s.get("assign", {})) for s in steps])
    for n, spec in (d.get("tables") or {}).items():
        m.table(n, spec["low"], spec["step"], spec["values"])
    for n, spec in (d.get("entity_types") or {}).items():
        m.entity_type(n, **(spec or {}))
    for n, spec in (d.get("counters") or {}).items():
        m.counter(n, limit=_num((spec or {}).get("limit", math.inf)), initial=_num((spec or {}).get("initial", 0)))
    for n in d.get("tallies") or []:
        m.tally(n)
    for n, expr in (d.get("dstats") or {}).items():
        m.dstat(n, expr)
    for n, spec in (d.get("frequencies") or {}).items():
        m.frequency(n, spec["expr"], [tuple(c) for c in spec["categories"]] if spec.get("categories") else None,
                    tuple(spec.get("excluded", ())))
    for n, expr in (d.get("outputs") or {}).items():
        m.output_stat(n, expr)
    for k, spec in (d.get("seeds") or {}).items():
        m.seed(int(k), spec["seed"], spec.get("reinit", "no"))
    for n, spec in (d.get("files") or {}).items():
        m.file(n, spec["path"], spec.get("mode", "r"), spec.get("sep"))
    for n, spec in (d.get("networks") or {}).items():
        G.network(m, n, [tuple(x) for x in spec["links"]], spec.get("intersections"),
                  spec.get("stations"), spec.get("include"))
    for n, spec in (d.get("transporters") or {}).items():
        if spec.get("network"):
            G.guided_transporter(m, n, spec["network"], spec.get("units", 1), spec.get("velocity", 1.0),
                                 spec.get("initial_station"), spec.get("size", 1), spec.get("control", "start"))
            continue
        dist = {(a, b): float(x) for a, b, x in spec.get("distances", [])}
        T.transporter(m, n, spec.get("units", 1), spec.get("velocity", 1.0), dist, spec.get("initial_station"))
    for n, spec in (d.get("conveyors") or {}).items():
        T.conveyor(m, n, [tuple(x) for x in spec["segments"]], spec.get("velocity", 1.0),
                   spec.get("cell_size", 1.0), spec.get("type", "nonaccumulating"), spec.get("loop", False))
    for n, spec in (d.get("levels") or {}).items():
        spec = spec if isinstance(spec, dict) else {"init": spec}
        C.level(m, n, spec.get("init", 0.0), spec.get("rate"))
    for n, expr in (d.get("cstats") or {}).items():
        C.cstat(m, n, expr)
    if d.get("continuous"):
        C.settings(m, **d["continuous"])
    m.no_report |= set(d.get("no_report") or ())
    m.rng_mode = d.get("rng_mode", "arena")
    m.disable_randomness = bool(d.get("disable_randomness", False))
    rep = d.get("replicate") or {}
    m.replicate(rep.get("replications", 1), _num(rep.get("length", math.inf)), rep.get("warmup", 0.0),
                rep.get("terminating_condition"), rep.get("initialize_system", True),
                rep.get("initialize_stats", True))
    for step in d.get("flow") or []:
        for b in _step(m, step):
            m.add(b)
    return m


def _step(m: Model, step: dict) -> list[B.Block]:
    step = dict(step)
    label = step.pop("label", None)
    node = step.pop("node", None)
    if len(step) != 1:
        raise ValueError(f"each flow step needs exactly one block or module: {step}")
    (kind, ops), = step.items()
    kind = kind.lower()
    ops = {} if ops is None else ops
    out = MODULES[kind](m, ops) if kind in MODULES else [_block(kind, ops)]
    if label:
        out[0].label = label
    if node is not None:
        for b in out:
            b.node = node
    return out


def _block(kind: str, ops: Any) -> B.Block:
    if kind not in BLOCKS:
        raise ValueError(f"unknown block or module {kind!r}")
    cls = BLOCKS[kind]
    if not isinstance(ops, dict):
        # shorthand: `queue: Name`, `delay: EXPO(3)`, `count: Done`, `station: S1`
        first = {B.QueueBlock: "queue", B.Delay: "duration", B.Count: "counter", B.Station: "station",
                 B.If: "condition", B.ElseIf: "condition", B.While: "condition", B.Signal: "code",
                 B.Wait: "signal_code", B.Scan: "condition", B.Detach: "queue"}.get(cls)
        if first is None:
            raise ValueError(f"{kind} needs a mapping of operands")
        ops = {first: ops}
    ops = {k: _num(v) for k, v in ops.items()}
    for key in ("resources", "assignments", "copies", "branches", "queues"):
        if key in ops and key != "branches":
            ops[key] = _pairs(ops[key]) if key != "queues" else [tuple(x) for x in ops[key]]
    if "branches" in ops:
        ops["branches"] = [tuple(x) for x in ops["branches"]]
    if cls is B.Release and "resources" in ops:
        ops["resources"] = [x if isinstance(x, dict) else (x[0], None if x[1] in ("all", None) else x[1])
                            for x in ops["resources"]]
    return cls(**ops)


# --- Arena Basic Process style modules -------------------------------------------------------

RULES = {"cyclical": "CYC", "random": "RAN", "preferred order": "POR", "specific member": "ER",
         "largest remaining capacity": "LRC", "smallest number busy": "SNB"}


def resource_items(m: Model, items) -> tuple[list, list, list]:
    """Arena resource rows -> (seize pairs, set selections, release items).

    A row is [name, qty] or a dict: {resource|attribute|expression: ..., units} or
    {set, units, rule (Arena name or SIMAN code), save: attribute, index: specific member}.
    Release of a set member: the member at `index` (specific), the one whose index was saved,
    else the last member of the set this entity seized."""
    seize, select, release = [], [], []
    for it in _pairs(items or []):
        if not isinstance(it, dict):
            n, q = it
            if isinstance(n, str) and n not in m.resource_specs and n not in m.sets and "(" not in n:
                m.resource(n, 1)
            seize.append((n, q))
            release.append((n, q))
            continue
        q = it.get("units", 1)
        if it.get("set"):
            rule = RULES.get(str(it.get("rule", "CYC")).lower(), str(it.get("rule", "CYC")).upper())
            sel = {"set": it["set"], "rule": rule, "units": q}
            if rule == "ER":
                sel["index"] = it.get("index", 1)
                release.append({"set": it["set"], "rule": "specific", "index": it.get("index", 1), "units": q})
            elif it.get("save"):
                sel["save"] = it["save"]
                m.attributes_default(it["save"])
                release.append({"set": it["set"], "rule": "specific", "index": it["save"], "units": q})
            else:
                release.append({"set": it["set"], "rule": it.get("release_rule", "last"), "units": q})
            select.append(sel)
        else:
            n = it.get("resource") or it.get("attribute") or it.get("expression")
            if it.get("resource") and n not in m.resource_specs:
                m.resource(n, 1)
            seize.append((n, q))
            release.append((n, q))
    return seize, select, release


def _process(m: Model, o: dict) -> list[B.Block]:
    """PROCESS: action delay | seize_delay | seize_delay_release | delay_release."""
    name = o.get("name", "Process")
    action = o.get("action", "seize_delay_release").lower()
    seize, select, release = resource_items(m, o.get("resources", []))
    qname = o.get("queue", f"{name}.Queue")
    alloc = o.get("allocation", "value_added")
    out: list[B.Block] = []
    if "seize" in action:
        m.ensure_queue(qname)
        out += [B.QueueBlock(queue=qname),
                B.Seize(resources=seize, select=select or None, priority=o.get("priority", 1), allocation=alloc)]
    out.append(B.Delay(duration=o.get("delay", 0), allocation=alloc))
    if "release" in action:
        out.append(B.Release(resources=release))
    if o.get("report", True):
        t0 = "__t0_" + re.sub(r"\W", "_", name)
        m.attribute(t0, 0.0)
        out.insert(0, B.Assign(assignments=[(t0, "TNOW")]))
        out.append(B.TallyBlock(tally=f"{name}.TotalTime", value=f"INT({t0})"))
    else:
        m.no_report.add(qname)
    return out


def _decide(m: Model, o: dict) -> list[B.Block]:
    """DECIDE: 2-way/N-way by chance or condition. Falls through on the else branch.

    {if: cond, then: Label}                       2-way by condition
    {chance: 30, then: Label}                     2-way by chance (percent true)
    {conditions: [[cond, Label], ...]}            N-way by condition
    {chances: [[pct, Label], ...]}                N-way by chance
    """
    nxt = f"__decide_else_{len(m.blocks)}_{id(o)}"
    if "if" in o:
        br = [("IF", o["if"], o["then"]), ("ELSE", None, o.get("else", nxt))]
    elif "chance" in o:
        p = float(o["chance"]) / 100
        br = [("WITH", p, o["then"]), ("WITH", 1 - p, o.get("else", nxt))]
    elif "conditions" in o:
        br = [("IF", c, lab) for c, lab in o["conditions"]] + [("ELSE", None, o.get("else", nxt))]
    else:
        br = [("WITH", float(p) / 100, lab) for p, lab in o["chances"]]
        rest = 1 - sum(float(p) for p, _ in o["chances"]) / 100
        br.append(("WITH", rest, o.get("else", nxt)))
    out: list[B.Block] = [B.Branch(branches=br, max_branches=1)]
    if "else" not in o:
        anchor = B.Assign(assignments=[], label=nxt)  # no-op landing point for "else"
        out.append(anchor)
    return out


def _batch(m: Model, o: dict) -> list[B.Block]:
    """BATCH: temporary or permanent, optionally by attribute."""
    name = o.get("name", "Batch")
    q = o.get("queue", f"{name}.Queue")
    m.ensure_queue(q)
    return [B.QueueBlock(queue=q),
            B.Group(quantity=o.get("size", 2), temporary=o.get("type", "temporary") == "temporary",
                    match_attr=o.get("by_attribute"), save_criterion=o.get("save", "last"),
                    rep_type=o.get("representative_type") or None)]


def _separate(m: Model, o: dict) -> list[B.Block]:
    """SEPARATE: split existing batch (member_attributes: retain | all | [attribute, ...]),
    or duplicate original (copies, to: label, cost_percent to the duplicates)."""
    if o.get("type", "split") == "split":
        return [B.Split(member_attrs=o.get("member_attributes", "retain"))]
    return [B.Duplicate(copies=[(o.get("copies", 1), o.get("to"))], cost_pct=o.get("cost_percent"))]


def _record(m: Model, o: dict) -> list[B.Block]:
    """RECORD: count | entity_statistics | time_interval | time_between | expression."""
    t = o.get("type", "count").lower()
    name = o.get("name", "Record")
    st = {"set": o["set"], "set_index": o.get("index", 1)} if o.get("set") else {}
    if t == "count":
        return [B.Count(counter=o.get("counter", name), increment=o.get("value", 1), **st)]
    if t == "entity_statistics":
        return [B.EntityStats()]
    tally = o.get("tally", name)
    if t == "time_interval":
        return [B.TallyBlock(tally=tally, value=f"INT({o['attribute']})", **st)]
    if t == "time_between":
        return [B.TallyBlock(tally=tally, value="BET", **st)]
    if t == "expression":
        return [B.TallyBlock(tally=tally, value=o["value"], **st)]
    raise ValueError(f"unknown record type {t}")


MODULES = {"process": _process, "decide": _decide, "batch": _batch, "separate": _separate,
           "record": _record}
