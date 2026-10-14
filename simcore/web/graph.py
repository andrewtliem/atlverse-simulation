"""Editor graph -> simcore model dict, with validation.

Graph JSON saved by the web editor (version 2; module and data fields follow Arena's dialogs):

    {"version": 2, "name": "Bank", "time_units": "minutes",
     "run": {"replications": 1, "length": 480, "warmup": 0, "rng_mode": "arena",
             "disable_randomness": false},
     "data": {"entities": {...}, "queues": {...}, "resources": {...}, "schedules": {...},
              "variables": {...}, "attributes": {...}, "sets": {...}, "failures": {...},
              "expressions": {...}, "statesets": {...}, "transporters": {...}, "conveyors": {...}},
     "nodes": [{"id": "n1", "type": "create", "x": 80, "y": 120, "props": {...}}, ...],
     "links": [{"from": "n1", "to": "n2", "port": "out"}, ...]}

Select-type fields hold Arena's wording ("Seize Delay Release", "Variable Array (1D)", ...).
Repeat groups (Assign assignments, Process resources, Decide conditions, ...) are lists of
objects. Files from the first editor version are converted by `upgrade()`.
"""

from __future__ import annotations

import contextvars
import re
from typing import Any

VERSION = 2


class GraphError(ValueError):
    """Validation problems; `problems` is a list of {"node": id or None, "message": str}."""

    def __init__(self, problems: list[dict]) -> None:
        self.problems = problems
        super().__init__("; ".join((f"[{p['node']}] " if p.get("node") else "") + p["message"] for p in problems))


# --- ports ------------------------------------------------------------------------------------

TERMINAL = {"dispose", "route", "transport", "convey"}


def ports_of(node: dict) -> list[str]:
    t = node["type"]
    p = node.get("props") or {}
    if t == "decide":
        kind = str(p.get("type", "2-way by Chance"))
        if kind.startswith("N-way"):
            rows = p.get("conditions") if "Condition" in kind else p.get("percentages")
            return [str(i + 1) for i in range(len(rows or []))] + ["else"]
        return ["true", "false"]
    if t == "separate":
        return ["original", "duplicate"] if str(p.get("type", "Duplicate")).startswith("Duplicate") else ["original"]
    if t == "remove":
        return ["original", "removed"]
    if t in TERMINAL or t == "sub_out":
        return []
    return ["out"]


def is_submodel(node: dict) -> bool:
    return node["type"] == "process" and (node.get("props") or {}).get("type") == "Submodel"


def flatten(g: dict) -> tuple[list, list, list]:
    """Inline Process submodels: inner modules get ids "<process id>/<id>"; links into the
    process go to what its Entry point connects to, and its Exit points continue at the
    process's own exit. Returns (nodes, links, problems)."""
    nodes: dict[str, dict] = {}
    links: list[dict] = []
    problems: list[dict] = []

    def walk(level: dict, pre: str) -> None:
        for n in level.get("nodes", []):
            fid = pre + str(n["id"])
            nodes[fid] = {**n, "id": fid}
            if is_submodel(n):
                walk(n.get("sub") or {}, fid + "/")
        for lk in level.get("links", []):
            links.append({**lk, "from": pre + str(lk["from"]), "to": pre + str(lk["to"])})

    walk(g, "")
    out = {(lk["from"], lk.get("port", "out")): lk["to"] for lk in links if lk["from"] in nodes and lk["to"] in nodes}
    parent = lambda fid: fid.rsplit("/", 1)[0] if "/" in fid else None

    def entry_of(sid):
        for fid, n in nodes.items():
            if n["type"] == "sub_in" and parent(fid) == sid:
                return out.get((fid, "out"))
        return None

    def resolve(t):
        for _ in range(len(nodes) + 1):
            if t is None or t not in nodes:
                return None
            n = nodes[t]
            if is_submodel(n):
                t = entry_of(t)
            elif n["type"] == "sub_out":
                t = out.get((parent(t), "out"))
            elif n["type"] == "sub_in":
                return None
            else:
                return t
        return None

    special = {fid for fid, n in nodes.items() if is_submodel(n) or n["type"] in ("sub_in", "sub_out")}
    for fid in special:
        n = nodes[fid]
        if is_submodel(n):
            if not any(m["type"] == "sub_in" and parent(k) == fid for k, m in nodes.items()):
                problems.append({"node": fid, "message": "the submodel has no Entry point"})
            elif entry_of(fid) is None:
                problems.append({"node": fid, "message": "the submodel's Entry point is not connected"})
        elif n["type"] in ("sub_in", "sub_out") and parent(fid) is None:
            problems.append({"node": fid, "message": "Entry and Exit points belong inside a submodel"})
    flat_links = []
    for lk in links:
        if lk["from"] in special or lk["from"] not in nodes:
            continue
        t = resolve(lk["to"])
        if t is not None:
            flat_links.append({**lk, "to": t})
    return [n for fid, n in nodes.items() if fid not in special], flat_links, problems


# --- helpers ----------------------------------------------------------------------------------

UNIT_MIN = {"seconds": 1 / 60, "minutes": 1.0, "quarterhours": 15.0, "halfhours": 30.0,
            "hours": 60.0, "days": 1440.0}
PRIORITY = {"High (1)": 1, "Medium (2)": 2, "Low (3)": 3}
ALLOC = {"Value Added": "value_added", "Non-Value Added": "non_value_added", "Transfer": "transfer",
         "Wait": "wait", "Other": "other"}
COST_ATTR = {"VA": "Entity.VACost", "NVA": "Entity.NVACost", "Wait": "Entity.WaitCost", "Transfer": "Entity.TranCost",
             "Other": "Entity.OtherCost"}
ALLOC_STAT = {"value_added": "VA", "non_value_added": "NVA", "transfer": "Transfer", "wait": "Wait", "other": "Other"}
RANKING = {"First In First Out": "FIFO", "Last In First Out": "LIFO",
           "Lowest Attribute Value": "LVF", "Highest Attribute Value": "HVF"}
SELECT_RULE = {"Cyclical": "CYC", "Random": "RAN", "Preferred Order": "POR", "Specific Member": "ER",
               "Largest Remaining Capacity": "LRC", "Smallest Number Busy": "SNB"}


def _lab(node_id: str) -> str:
    return "node_" + str(node_id).replace("/", "__")


def _num(v: Any) -> Any:
    """Numbers stay numbers; anything else is an expression string (None when blank)."""
    if isinstance(v, (bool, int, float)):
        return v
    t = str(v if v is not None else "").strip()
    if t == "":
        return None
    try:
        return int(t)
    except ValueError:
        pass
    try:
        return float(t)
    except ValueError:
        return t


def _or(v: Any, default: Any) -> Any:
    x = _num(v)
    return default if x is None else x


def _truthy(v: Any, default: bool = False) -> bool:
    if v is None or v == "":
        return default
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "on", "checked")


def _infinite(v: Any) -> Any:
    x = _num(v)
    if x is None or (isinstance(x, str) and x.lower() in ("infinite", "inf", "infinity")):
        return "INF"
    return x


# Run Setup "Hours Per Day" sets the length of a day for every time in the model
_HOURS_PER_DAY: contextvars.ContextVar[float] = contextvars.ContextVar("hours_per_day", default=24.0)


def _unit_min(units: Any) -> float:
    u = str(units).lower()
    return _HOURS_PER_DAY.get() * 60 if u == "days" else UNIT_MIN.get(u, 1.0)


def _time(v: Any, units: Any, base: str) -> Any:
    """Expression in `units` converted to the model's base time units."""
    x = _num(v)
    if x is None:
        return None
    k = _unit_min(units or base) / _unit_min(base)
    if abs(k - 1) < 1e-12:
        return x
    if isinstance(x, (int, float)):
        return x * k
    return f"({x}) * {k!r}"


def _values(text: Any) -> list:
    """'1, 2, 3' or one per line -> [1, 2, 3]; quoted text stays a string."""
    out = []
    for part in re.split(r"[,\n;]", str(text if text is not None else "")):
        part = part.strip()
        if part:
            out.append(part[1:-1] if len(part) > 1 and part[0] == part[-1] == '"' else _num(part))
    return out


def _names(text: Any) -> list[str]:
    return [x.strip() for x in re.split(r"[,\n]", str(text or "")) if x.strip()]


def _pairs(text: Any) -> list[tuple]:
    """'A-B: 100' lines -> [('A', 'B', 100.0)]"""
    out = []
    for line in str(text or "").splitlines():
        m = re.match(r"\s*(.+?)\s*-\s*(.+?)\s*:\s*([\d.eE+-]+)\s*$", line)
        if m:
            out.append((m.group(1), m.group(2), float(m.group(3))))
    return out


def _quote(s: Any) -> str:
    return '"' + str(s).replace('"', "") + '"'


def _priority(p: dict) -> Any:
    v = p.get("priority", "Medium (2)")
    if v in PRIORITY:
        return PRIORITY[v]
    return _or(p.get("priority_expr"), 2) if v == "Other" else _or(v, 2)


def _array_ref(name: str, kind: str, row: Any, col: Any) -> str:
    if kind.endswith("(1D)"):
        return f"{name}({_or(row, 1)})"
    if kind.endswith("(2D)"):
        return f"{name}({_or(row, 1)}, {_or(col, 1)})"
    return name


def _condition(c: dict) -> str | None:
    """Decide condition (If / Named / Row / Column / Is / Value) -> expression."""
    kind = c.get("if_type", "Expression")
    if kind == "Expression":
        return str(c.get("value", "")).strip() or None
    named = str(c.get("named", "")).strip()
    if not named:
        return None
    if kind == "Entity Type":
        return f"Entity.Type == {_quote(named)}"
    op = c.get("is", ">=")
    return f"{_array_ref(named, kind, c.get('row'), c.get('column'))} {op} {_or(c.get('value'), 1)}"


# --- upgrade from the first editor format -----------------------------------------------------

_OLD_ACTION = {"delay": "Delay", "seize_delay": "Seize Delay", "seize_delay_release": "Seize Delay Release",
               "delay_release": "Delay Release"}
_OLD_ALLOC = {v: k for k, v in ALLOC.items()}


def _old_res(text: Any) -> list[dict]:
    rows = []
    for part in str(text or "").split(","):
        if part.strip():
            n, _, q = part.partition(":")
            rows.append({"type": "Resource", "resource": n.strip(), "quantity": q.strip() or "1"})
    return rows


def _old_props(t: str, p: dict, units: str, variables: dict) -> dict:
    q: dict[str, Any] = {"name": p.get("name", "")}
    alloc = _OLD_ALLOC.get(p.get("allocation", "value_added"), "Value Added")
    if t == "create":
        at = p.get("arrival_type", "random")
        q.update(entity_type=p.get("entity_type", "Entity 1"),
                 type={"random": "Random (Expo)", "schedule": "Schedule"}.get(at, "Expression"),
                 value=str(p.get("mean", "1")), schedule=p.get("schedule", ""), expression=str(p.get("interval", "1")),
                 units=units, entities_per_arrival=str(p.get("batch", "1")),
                 max_arrivals=str(p.get("max", "")) or "Infinite", first_creation=str(p.get("first", "0")))
    elif t == "process":
        q.update(action=_OLD_ACTION.get(p.get("action", "seize_delay_release"), "Seize Delay Release"),
                 priority="Other", priority_expr=str(p.get("priority", "1")),
                 resources=_old_res(p.get("resources", p.get("resource", ""))), delay_type="Expression",
                 expression=str(p.get("delay", "1")), units=units, allocation=alloc, report=True)
    elif t == "decide":
        mode = {"chance": "2-way chance", "condition": "2-way condition"}.get(p.get("mode"), p.get("mode", "2-way chance"))
        lines = [x.strip() for x in str(p.get("branches", "")).splitlines() if x.strip()]
        q.update(type={"2-way chance": "2-way by Chance", "2-way condition": "2-way by Condition",
                       "n-way chance": "N-way by Chance", "n-way condition": "N-way by Condition"}[mode],
                 percent_true=str(p.get("chance", "50")), if_type="Expression", value=str(p.get("condition", "")),
                 percentages=[{"percent": x} for x in lines] if mode == "n-way chance" else [],
                 conditions=[{"if_type": "Expression", "value": x} for x in lines] if mode == "n-way condition" else [])
    elif t == "assign":
        rows = []
        for line in str(p.get("assignments", "")).splitlines():
            if "=" in line:
                tgt, val = (x.strip() for x in line.split("=", 1))
                if tgt in variables:
                    rows.append({"type": "Variable", "variable": tgt, "value": val})
                elif "(" in tgt or "." in tgt:
                    rows.append({"type": "Other", "other": tgt, "value": val})
                else:
                    rows.append({"type": "Attribute", "attribute": tgt, "value": val})
        q.update(assignments=rows)
    elif t == "batch":
        q.update(type=str(p.get("type", "temporary")).capitalize(), batch_size=str(p.get("size", "2")),
                 save_criterion="Last", rule="By Attribute" if p.get("by_attribute") else "Any Entity",
                 attribute=p.get("by_attribute", ""), rep_type="")
    elif t == "separate":
        q.update(type="Duplicate Original" if p.get("type", "split") == "duplicate" else "Split Existing Batch",
                 percent_cost="50", duplicates=str(p.get("copies", "1")),
                 member_attrs="Retain Original Entity Values", attributes=[])
    elif t == "record":
        stat = p.get("stat", p.get("name", ""))
        q.update(type={"time_interval": "Time Interval", "time_between": "Time Between",
                       "expression": "Expression"}.get(p.get("type"), "Count"),
                 attribute=p.get("attribute", "Entity.CreateTime"), value=str(p.get("value", "1")),
                 tally_name=stat, counter_name=stat, record_into_set=False)
    elif t == "dispose":
        q.update(record_stats=True)
    elif t == "seize":
        q.update(allocation=alloc, priority="Other", priority_expr=str(p.get("priority", "1")),
                 resources=_old_res(p.get("resources", "")), queue_type="Queue", queue_name="")
    elif t == "release":
        q.update(resources=_old_res(p.get("resources", "")))
    elif t == "delay":
        q.update(allocation=alloc, delay_time=str(p.get("delay", "1")), units=units)
    elif t == "hold":
        q.update(type="Scan for Condition" if p.get("mode") == "scan for condition" else "Wait for Signal",
                 wait_value=str(p.get("signal", "1")), limit=str(p.get("limit", "")),
                 condition=str(p.get("condition", "")), queue_type="Queue", queue_name="")
    elif t == "signal":
        q.update(signal_value=str(p.get("signal", "1")), limit=str(p.get("limit", "")))
    else:
        q = {**p, **q}
        if t == "route":
            q.setdefault("units", units)
    return q


def upgrade(g: dict) -> dict:
    """Return a version-2 graph (older graphs are converted; version 2 is returned as is)."""
    if int(g.get("version", 1)) >= VERSION:
        return g
    g = dict(g)
    run = dict(g.get("run") or {})
    run.setdefault("replications", g.pop("replications", 1))
    run.setdefault("length", g.pop("length", 480))
    g.pop("replications", None)
    g.pop("length", None)
    g["run"] = run
    data = {k: dict(v or {}) for k, v in (g.get("data") or {}).items()}
    if g.get("resources"):
        data.setdefault("resources", {}).update(g.pop("resources"))
    units = str(g.get("time_units", "minutes")).capitalize()

    res = {}
    for n, r in (data.get("resources") or {}).items():
        res[n] = {"type": "Based on Schedule" if r.get("schedule") else "Fixed Capacity",
                  "capacity": str(r.get("capacity", "1") or "1"), "schedule": r.get("schedule", ""),
                  "schedule_rule": "Wait", "busy_per_hour": r.get("busy_per_hour", ""),
                  "idle_per_hour": r.get("idle_per_hour", ""), "per_use": r.get("per_use", ""),
                  "stateset": "", "initial_state": "", "failures": [], "report": True}
    sch = {}
    for n, s in (data.get("schedules") or {}).items():
        rows = []
        for seg in re.split(r"[;\n]", str(s.get("segments", ""))):
            if seg.strip():
                v, _, d = seg.partition(",")
                rows.append({"value": v.strip(), "duration": d.strip()})
        sch[n] = {"type": str(s.get("kind", "capacity")).capitalize(), "units": units, "scale": "1", "durations": rows}
        for r in res.values():
            if r["schedule"] == n:
                r["schedule_rule"] = str(s.get("rule", "ignore")).capitalize()
    fails = {}
    for n, f in (data.get("failures") or {}).items():
        fails[n] = {"type": str(f.get("kind", "time")).capitalize(), "count": f.get("up", "100"),
                    "up_time": f.get("up", "100"), "up_units": units, "down_time": f.get("down", "10"),
                    "down_units": units, "state": ""}
        for rn in _names(f.get("resources")):
            if rn in res:
                res[rn]["failures"].append({"failure": n, "rule": str(f.get("rule", "ignore")).capitalize()})
    variables = {n: {"rows": "", "columns": "", "data_type": "Real", "clear": "System",
                     "initial_values": str(v.get("init", "0")), "report": _truthy(v.get("track"))}
                 for n, v in (data.get("variables") or {}).items()}
    data.update(
        resources=res, schedules=sch, failures=fails, variables=variables,
        attributes={n: {"rows": "", "columns": "", "data_type": "Real", "initial_values": str(a.get("init", "0"))}
                    for n, a in (data.get("attributes") or {}).items()},
        entities={n: {"initial_picture": "Picture.Report", "color": e.get("color", ""),
                      "holding_cost": e.get("hold_cost", ""), "report": True}
                  for n, e in (data.get("entities") or {}).items()},
        sets={n: {"type": "Resource", "members": s.get("members", "")} for n, s in (data.get("sets") or {}).items()})
    for k in ("queues", "expressions", "statesets", "transporters", "conveyors"):
        data.setdefault(k, {})
    g["data"] = data
    g["nodes"] = [{**n, "props": _old_props(n["type"], dict(n.get("props") or {}), units, variables)}
                  for n in g.get("nodes", [])]
    g["version"] = VERSION
    return g


# --- conversion -------------------------------------------------------------------------------

def to_model_dict(g: dict) -> dict:
    g = upgrade(g)
    problems: list[dict] = []

    def problem(node, msg):
        problems.append({"node": node, "message": msg})

    base = str(g.get("time_units", "minutes")).lower()
    run = dict(g.get("run") or {})
    hpd = _num(run.get("hours_per_day", 24))
    _HOURS_PER_DAY.set(float(hpd) if isinstance(hpd, (int, float)) and 0 < hpd <= 24 else 24.0)
    data = {k: (v or {}) for k, v in (g.get("data") or {}).items()}
    flat_nodes, flat_links, problems[:] = flatten(g)
    nodes = {n["id"]: n for n in flat_nodes}
    out: dict[tuple, str] = {}
    for link in flat_links:
        if link["from"] in nodes and link["to"] in nodes:
            out[(link["from"], link.get("port", "out"))] = link["to"]

    # module names must be unique (they name queues, tallies and counters)
    seen: dict[str, str] = {}
    for nid, n in nodes.items():
        name = str((n.get("props") or {}).get("name", "")).strip()
        if not name:
            problem(nid, "module has no name")
        elif name in seen:
            problem(nid, f'name "{name}" is also used by another module')
        else:
            seen[name] = nid

    md: dict[str, Any] = {"name": g.get("name", "Model"), "time_units": base}
    no_report: list[str] = []

    # ---- data modules
    schedules = {}
    for name, sc in data.get("schedules", {}).items():
        rows = [r for r in sc.get("durations") or [] if str(r.get("value", "")).strip() != ""]
        if not rows:
            problem(None, f'schedule "{name}" needs at least one value/duration row')
            continue
        segs, repeat = [], True
        for i, r in enumerate(rows):
            d, v = _num(r.get("duration")), _num(r.get("value"))
            if d is None or (isinstance(d, str) and d.lower() in ("infinite", "inf")):
                if i != len(rows) - 1:
                    problem(None, f'schedule "{name}": only the last duration may be blank (infinite)')
                segs.append([v, 1e300])
                repeat = False
                continue
            if not isinstance(v, (int, float)) or not isinstance(d, (int, float)):
                problem(None, f'schedule "{name}": values and durations must be numbers')
                break
            segs.append([v, _time(d, sc.get("units"), base)])
        kind = str(sc.get("type", "Capacity")).lower()
        if str(sc.get("end_logic", "")).startswith("Remain"):
            repeat = False  # Arena's "Remain at Capacity/Arrival Rate/Value": the last value holds
        schedules[name] = {"segments": segs, "kind": kind, "repeat": repeat,
                           "scale": 1.0 if kind == "capacity" else float(_or(sc.get("scale"), 1.0))}

    failure_defs = data.get("failures", {})
    failures = []
    resources = {}
    for name, r in data.get("resources", {}).items():
        spec: dict[str, Any] = {}
        if r.get("type") == "Based on Schedule":
            if r.get("schedule") not in schedules:
                problem(None, f'resource "{name}" is based on schedule "{r.get("schedule", "")}", which is not defined')
            elif schedules[r["schedule"]]["kind"] != "capacity":
                problem(None, f'resource "{name}": schedule "{r["schedule"]}" is not of type Capacity')
            spec.update(capacity=1, schedule=r.get("schedule"), schedule_rule=str(r.get("schedule_rule", "Wait")).lower())
        else:
            spec["capacity"] = _infinite(r.get("capacity")) if str(r.get("capacity", "")).strip() else 1
        for k in ("busy_per_hour", "idle_per_hour", "per_use"):
            if isinstance(_num(r.get(k)), (int, float)):
                spec[k] = float(_num(r.get(k)))
        if r.get("stateset"):
            ss = data.get("statesets", {}).get(r["stateset"])
            if ss is None:
                problem(None, f'resource "{name}" uses unknown StateSet "{r["stateset"]}"')
            else:
                spec["stateset"] = {str(s.get("autostate", "")).upper(): s["state"]
                                    for s in ss.get("states") or [] if s.get("autostate") and s.get("state")}
                if r.get("initial_state"):
                    spec["initial_state"] = r["initial_state"]
        for fr in r.get("failures") or []:
            fname = str(fr.get("failure", "")).strip()
            f = failure_defs.get(fname)
            if f is None:
                problem(None, f'resource "{name}" uses unknown failure "{fname}"')
                continue
            count = f.get("type", "Time") == "Count"
            failures.append({
                "name": fname, "resources": [name], "kind": "count" if count else "time",
                "up": _or(f.get("count"), 100) if count else _time(_or(f.get("up_time"), 100), f.get("up_units"), base),
                "down": _time(_or(f.get("down_time"), 0), f.get("down_units"), base),
                "rule": str(fr.get("rule", "Ignore")).lower(),
                "uptime_in_state": None if count else (str(f.get("state") or "").strip() or None)})
        if not _truthy(r.get("report"), True):
            no_report.append(name)
        resources[name] = spec

    def dims(spec) -> list:
        rows, cols = _num(spec.get("rows")), _num(spec.get("columns"))
        if rows is not None and not isinstance(rows, int) or cols is not None and not isinstance(cols, int):
            problem(None, "rows and columns must be whole numbers")
            return []
        return [rows, cols] if rows and cols else [rows] if rows else []

    def init_values(name, spec, what):
        vals = _values(spec.get("initial_values", ""))
        string = spec.get("data_type") == "String"
        if string:
            vals = [str(v) for v in vals]
        d = dims(spec)
        zero = "" if string else 0
        if not d:
            if len(vals) > 1:
                problem(None, f'{what} "{name}" has several initial values but no rows')
            return (vals[0] if vals else zero), d
        n = d[0] * (d[1] if len(d) > 1 else 1)
        if len(vals) > n:
            problem(None, f'{what} "{name}" has more initial values than its {"x".join(map(str, d))} elements')
        # like Arena: missing values repeat the last one given
        vals = (vals + [vals[-1] if vals else zero] * n)[:n]
        if len(d) == 1:
            return vals, d
        return [vals[i * d[1]:(i + 1) * d[1]] for i in range(d[0])], d  # row-major

    variables = {}
    for name, v in data.get("variables", {}).items():
        init, d = init_values(name, v, "variable")
        variables[name] = {"init": init, "dims": d,
                           "track": _truthy(v.get("report")) and not d and v.get("data_type") != "String",
                           "clear": str(v.get("clear", "System")).lower()}
    attributes: dict[str, Any] = {}
    for name, a in data.get("attributes", {}).items():
        init, d = init_values(name, a, "attribute")
        attributes[name] = {"init": init, "dims": d} if d else init
    entities = {}
    for name, e in data.get("entities", {}).items():
        spec = {"picture": e.get("initial_picture") or "Picture.Report",
                "hold_cost_rate": float(_or(e.get("holding_cost"), 0))}
        for k, key in (("initial_va", "va"), ("initial_nva", "nva"), ("initial_wait", "wait"),
                       ("initial_transfer", "tran"), ("initial_other", "other")):
            if isinstance(_num(e.get(k)), (int, float)):
                spec[f"initial_{key}_cost"] = float(_num(e.get(k)))
        if not _truthy(e.get("report"), True):
            no_report.append(name)
        entities[name] = spec
    queues = {}
    for name, q in data.get("queues", {}).items():
        rk = RANKING.get(q.get("type", "First In First Out"), "FIFO")
        if rk in ("LVF", "HVF") and not q.get("attribute"):
            problem(None, f'queue "{name}" is ranked by attribute but names none')
        queues[name] = {"ranking": rk, "attribute": q.get("attribute") or None}
        if not _truthy(q.get("report"), True):
            no_report.append(name)
    sets = {name: _names(s.get("members")) for name, s in data.get("sets", {}).items()}
    expressions = {name: _or(x.get("expression"), 0) for name, x in data.get("expressions", {}).items()}
    transporters = {}
    for name, t in data.get("transporters", {}).items():
        transporters[name] = {"units": int(_or(t.get("units"), 1)), "velocity": float(_or(t.get("velocity"), 1)),
                              "initial_station": t.get("initial_station") or None,
                              "distances": [list(x) for x in _pairs(t.get("distances"))]}
    conveyors = {}
    for name, c in data.get("conveyors", {}).items():
        segs = [list(x) for x in _pairs(c.get("segments"))]
        if not segs:
            problem(None, f'conveyor "{name}" needs segments like "In-Out: 20"')
            continue
        conveyors[name] = {"segments": segs, "velocity": float(_or(c.get("velocity"), 1)),
                           "cell_size": float(_or(c.get("cell_size"), 1)), "type": c.get("type", "nonaccumulating")}

    stations = {str((n.get("props") or {}).get("station") or (n.get("props") or {}).get("name")).strip()
                for n in nodes.values() if n["type"] == "station"}
    counters: dict[str, dict] = {}
    tallies: set[str] = set()

    def need_resource(rname):
        if rname and rname not in resources and rname not in sets:
            resources[rname] = {"capacity": 1}  # like Arena: naming a resource defines it

    def need_set(nid, sname, what="set") -> bool:
        if sname not in sets:
            problem(nid, f'{what} "{sname}" is not defined in the Sets table')
            return False
        return True

    def need_station(nid, sname, what):
        if sname and sname.upper() != "SEQ" and sname not in stations:
            problem(nid, f'{what} "{sname}" is not the name of any Station module')

    def need_attr(aname):
        if aname and aname not in attributes and "." not in aname and "(" not in aname:
            attributes[aname] = 0

    def resource_rows(nid, rows, allowed, releasing=False) -> list:
        """Resource repeat group -> [name, qty] pairs and set dicts for the loader."""
        items = []
        for i, r in enumerate(rows or []):
            kind = r.get("type", "Resource")
            q = _or(r.get("quantity"), 1)
            where = f"resource row {i + 1}"
            if kind not in allowed:
                problem(nid, f"{where}: type {kind} is not available in this module")
            elif kind == "Resource":
                rn = str(r.get("resource", "")).strip()
                if not rn:
                    problem(nid, f"{where} has no resource name")
                    continue
                need_resource(rn)
                cap, qn = (resources.get(rn) or {}).get("capacity"), _num(q)
                if (not releasing and isinstance(cap, (int, float)) and isinstance(qn, (int, float))
                        and qn > cap and not (resources.get(rn) or {}).get("schedule")):
                    problem(nid, f'{where}: Quantity {qn:g} is more than the Capacity {cap:g} of resource "{rn}", '
                                 f'so entities wait forever. Quantity is the units each entity seizes; '
                                 f'the number of units is the Capacity in the Resource data module')
                items.append([rn, q])
            elif kind == "Set":
                sn = str(r.get("set", "")).strip()
                if not need_set(nid, sn, "resource set"):
                    continue
                for m in sets[sn]:
                    need_resource(m)
                if releasing:
                    rule = r.get("release_rule", "Last Member Seized")
                    item = {"set": sn, "units": q, "rule": {"Specific Member": "specific",
                                                            "First Member Seized": "first"}.get(rule, "last")}
                    if rule == "Specific Member":
                        item["index"] = _or(r.get("set_index"), 1)
                    items.append(item)
                else:
                    rule = SELECT_RULE.get(r.get("rule", "Cyclical"), "CYC")
                    item = {"set": sn, "units": q, "rule": rule}
                    if rule == "ER":
                        item["index"] = _or(r.get("set_index"), 1)
                    elif str(r.get("save_attr", "")).strip():
                        item["save"] = r["save_attr"].strip()
                        need_attr(item["save"])
                    items.append(item)
            else:
                src = str(r.get("attribute" if kind == "Attribute" else "expression", "")).strip()
                if not src:
                    problem(nid, f"{where}: type {kind} needs a value")
                    continue
                if kind == "Attribute":
                    need_attr(src)
                items.append([src, q])
        return items

    def queue_steps(nid, name, p) -> list[dict]:
        """QUEUE step for Arena's Queue Type (Queue, Set, Internal, Attribute, Expression)."""
        qt = p.get("queue_type", "Queue")
        if qt == "Internal":
            return []
        if qt == "Set":
            sn = str(p.get("queue_set", "")).strip()
            if not need_set(nid, sn, "queue set"):
                return []
            for m in sets[sn]:
                queues.setdefault(m, {"ranking": "FIFO", "attribute": None})
            return [{"queue": {"queue": sets[sn][0], "choices": sets[sn], "select": _or(p.get("queue_set_index"), 1)}}]
        if qt in ("Attribute", "Expression"):
            src = str(p.get("queue_attribute" if qt == "Attribute" else "queue_expression", "")).strip()
            if not src:
                problem(nid, f"Queue Type {qt} needs a value")
                return []
            if not queues:
                problem(nid, f"Queue Type {qt}: define the queues it can choose in the Queues table")
                return []
            return [{"queue": {"queue": next(iter(queues)), "choices": list(queues), "select": src}}]
        qn = str(p.get("queue_name", "")).strip() or f"{name}.Queue"
        queues.setdefault(qn, {"ranking": "FIFO", "attribute": None})
        return [{"queue": {"queue": qn}}]

    def seize_steps(nid, name, items, priority, alloc, p) -> list[dict]:
        pairs = [it for it in items if isinstance(it, list)]
        selects = [it for it in items if isinstance(it, dict)]
        seize: dict[str, Any] = {"resources": pairs, "priority": priority, "allocation": alloc}
        if selects:
            seize["select"] = selects
        if str(p.get("resource_state", "")).strip():
            seize["state"] = p["resource_state"].strip()
        return queue_steps(nid, name, p) + [{"seize": seize}]

    # ---- flow
    flow: list[dict] = []

    def goto(src: str, port: str) -> list[dict]:
        tgt = out.get((src, port))
        if tgt is None:
            return [{"dispose": {"record_stats": False}}]
        return [{"branch": {"branches": [["ALWAYS", None, _lab(tgt)]], "max_branches": 1}}]

    def jump(src: str, port: str) -> str:
        """Label for an exit; an unconnected exit leads to a dispose step after the module."""
        tgt = out.get((src, port))
        return _lab(tgt) if tgt else f"__disp_{src}_{re.sub(r'[^0-9A-Za-z]', '_', port)}"

    def dangling(nid, ports) -> list[dict]:
        return [{"dispose": {"record_stats": False}, "label": jump(nid, pt)} for pt in ports if (nid, pt) not in out]

    for nid, n in nodes.items():
        kind = n["type"]
        p = dict(n.get("props") or {})
        name = str(p.get("name", f"{kind} {nid}")).strip()
        steps: list[dict] = []

        if kind == "create":
            how = p.get("type", "Random (Expo)")
            et = str(p.get("entity_type", "")).strip() or "Entity 1"
            spec: dict[str, Any] = {"batch_size": _or(p.get("entities_per_arrival"), 1),
                                    "max_batches": _infinite(p.get("max_arrivals")), "entity_type": et}
            if how == "Schedule":
                if p.get("schedule") not in schedules:
                    problem(nid, "choose an arrival schedule defined in the Schedules table")
                elif schedules[p["schedule"]]["kind"] != "arrival":
                    problem(nid, f'schedule "{p["schedule"]}" is not of type Arrival')
                spec["schedule"] = p.get("schedule")
            else:
                spec["first"] = _time(_or(p.get("first_creation"), 0), p.get("units"), base)
                if how == "Random (Expo)":
                    spec["interval"] = f"EXPO({_time(_or(p.get('value'), 1), p.get('units'), base)})"
                elif how == "Constant":
                    spec["interval"] = _time(_or(p.get("value"), 1), p.get("units"), base)
                else:
                    spec["interval"] = _time(_or(p.get("expression"), 1), p.get("units"), base)
            entities.setdefault(et, {})
            flow.append({"create": spec, "node": nid})
            if (nid, "out") not in out:
                problem(nid, "Create module is not connected to anything")
            flow.extend({**s, "node": nid} for s in goto(nid, "out"))
            continue

        if kind == "process":
            action = p.get("action", "Seize Delay Release")
            rows = p.get("resources") or []
            items = resource_rows(nid, rows, ("Resource", "Set")) if action != "Delay" else []
            if action != "Delay" and not rows:
                problem(nid, f'action "{action}" needs at least one resource')
            dt = p.get("delay_type", "Triangular")
            mn, val, mx, sd = (_or(p.get(k), d) for k, d in (("minimum", 0.5), ("value", 1), ("maximum", 1.5),
                                                              ("std_dev", 0.2)))
            delay = {"Constant": val, "Normal": f"NORM({val}, {sd})", "Triangular": f"TRIA({mn}, {val}, {mx})",
                     "Uniform": f"UNIF({mn}, {mx})"}.get(dt, _or(p.get("expression"), 1))
            alloc = ALLOC.get(p.get("allocation", "Value Added"), "value_added")
            report = _truthy(p.get("report"), True)
            # Arena's process statistics: Number In/Out and time per entity by category
            key = re.sub(r"\W", "_", name)
            t0, t1 = f"__t0_{key}", f"__t1_{key}"
            cat = ALLOC_STAT.get(alloc, "Other")
            # cost per entity (Arena's Process costs): the change in the entity's cost attributes
            costing = report and _truthy(run.get("stats_costing"), True)
            c0, c1, ct = f"__c0_{key}", f"__c1_{key}", f"__ct_{key}"
            all_cost = "(" + " + ".join(COST_ATTR.values()) + ")"
            if report:
                attributes[t0] = attributes[t1] = 0
                counters.setdefault(f"{name}.NumberIn", {})
                counters.setdefault(f"{name}.NumberOut", {})
                steps.append({"record": {"type": "count", "counter": f"{name}.NumberIn", "value": 1, "name": name}})
                steps.append({"assign": {"assignments": [[t0, "TNOW"]]}})
            if costing:
                attributes[c0] = attributes[c1] = attributes[ct] = 0
                steps.append({"assign": {"assignments": [[c0, COST_ATTR["Wait"]], [ct, all_cost]]}})
            if "Seize" in action:
                steps += seize_steps(nid, name, items, _priority(p), alloc, {"queue_name": f"{name}.Queue"})
                if report and cat != "Wait":  # a Wait delay is added to the queue wait below
                    tallies.add(f"{name}.WaitTimePerEntity")
                    steps.append({"tally": {"tally": f"{name}.WaitTimePerEntity", "value": f"INT({t0})"}})
                    if costing:
                        tallies.add(f"{name}.WaitCostPerEntity")
                        steps.append({"tally": {"tally": f"{name}.WaitCostPerEntity", "value": f"{COST_ATTR['Wait']} - {c0}"}})
            if report:
                steps.append({"assign": {"assignments": [[t1, "TNOW"]]}})
            if costing and not (cat == "Wait" and "Seize" in action):
                steps.append({"assign": {"assignments": [[c1, COST_ATTR[cat]]]}})
            steps.append({"delay": {"duration": _time(delay, p.get("units"), base), "allocation": alloc}})
            if report:
                tallies.add(f"{name}.{cat}TimePerEntity")
                start = t0 if cat == "Wait" and "Seize" in action else t1
                steps.append({"tally": {"tally": f"{name}.{cat}TimePerEntity", "value": f"INT({start})"}})
                if costing:
                    tallies.add(f"{name}.{cat}CostPerEntity")
                    cstart = c0 if cat == "Wait" and "Seize" in action else c1
                    steps.append({"tally": {"tally": f"{name}.{cat}CostPerEntity", "value": f"{COST_ATTR[cat]} - {cstart}"}})
            if "Release" in action:
                rel = []
                for it in items:
                    if isinstance(it, list):
                        rel.append(it)
                    elif it["rule"] == "ER":
                        rel.append({"set": it["set"], "rule": "specific", "index": it["index"], "units": it["units"]})
                    elif "save" in it:  # the saved index names the member to release
                        rel.append({"set": it["set"], "rule": "specific", "index": it["save"], "units": it["units"]})
                    else:
                        rel.append({"set": it["set"], "rule": "last", "units": it["units"]})
                steps.append({"release": {"resources": rel}})
            if report:
                tallies.add(f"{name}.TotalTimePerEntity")
                steps.append({"tally": {"tally": f"{name}.TotalTimePerEntity", "value": f"INT({t0})"}})
                if costing:
                    tallies.add(f"{name}.TotalCostPerEntity")
                    steps.append({"tally": {"tally": f"{name}.TotalCostPerEntity", "value": f"{all_cost} - {ct}"}})
                steps.append({"record": {"type": "count", "counter": f"{name}.NumberOut", "value": 1, "name": name}})
            elif "Seize" in action:
                no_report.append(f"{name}.Queue")
            steps += goto(nid, "out")

        elif kind == "seize":
            rows = p.get("resources") or []
            if not rows:
                problem(nid, "Seize needs at least one resource")
            items = resource_rows(nid, rows, ("Resource", "Set", "Attribute", "Expression"))
            steps += seize_steps(nid, name, items, _priority(p), ALLOC.get(p.get("allocation", "Other"), "other"), p)
            steps += goto(nid, "out")

        elif kind == "delay":
            steps.append({"delay": {"duration": _time(_or(p.get("delay_time"), 0), p.get("units"), base),
                                    "allocation": ALLOC.get(p.get("allocation", "Other"), "other")}})
            steps += goto(nid, "out")

        elif kind == "release":
            rows = p.get("resources") or []
            if not rows:
                problem(nid, "Release needs at least one resource")
            items = resource_rows(nid, rows, ("Resource", "Set", "Attribute", "Expression"), releasing=True)
            steps.append({"release": {"resources": items}})
            steps += goto(nid, "out")

        elif kind == "decide":
            mode = p.get("type", "2-way by Chance")
            ports = ports_of(n)
            br = []
            if mode == "2-way by Chance":
                pct = _num(_or(p.get("percent_true"), 50))
                if isinstance(pct, (int, float)):
                    if not 0 <= pct <= 100:
                        problem(nid, "Percent True must be from 0 to 100")
                        pct = 50
                    br = [["WITH", pct / 100, jump(nid, "true")], ["WITH", 1 - pct / 100, jump(nid, "false")]]
                else:  # Arena allows an expression, evaluated for each entity
                    br = [["WITH", f"({pct}) / 100", jump(nid, "true")], ["WITH", f"1 - ({pct}) / 100", jump(nid, "false")]]
            elif mode == "2-way by Condition":
                c = _condition(p)
                if c is None:
                    problem(nid, "the condition is incomplete")
                br = [["IF", c or "0", jump(nid, "true")], ["ELSE", None, jump(nid, "false")]]
            elif mode == "N-way by Chance":
                rows = p.get("percentages") or []
                if not rows:
                    problem(nid, "add at least one percentage")
                pcts = []
                for i, r in enumerate(rows):
                    x = _num(_or(r.get("percent"), 0))
                    if isinstance(x, (int, float)):
                        if x < 0:
                            problem(nid, f"percentage {i + 1} must be from 0 to 100")
                            x = 0
                        pcts.append(x / 100)
                    else:  # an expression, evaluated for each entity
                        pcts.append(f"({x}) / 100")
                nums = [x for x in pcts if isinstance(x, float)]
                if sum(nums) > 1 + 1e-9:
                    problem(nid, "percentages add up to more than 100")
                br = [["WITH", pc, jump(nid, str(i + 1))] for i, pc in enumerate(pcts)]
                rest = max(0.0, 1 - sum(nums)) if len(nums) == len(pcts) else "1 - (" + " + ".join(str(x) for x in pcts) + ")"
                br.append(["WITH", rest, jump(nid, "else")])
            else:
                rows = p.get("conditions") or []
                if not rows:
                    problem(nid, "add at least one condition")
                for i, r in enumerate(rows):
                    c = _condition(r)
                    if c is None:
                        problem(nid, f"condition {i + 1} is incomplete")
                    br.append(["IF", c or "0", jump(nid, str(i + 1))])
                br.append(["ELSE", None, jump(nid, "else")])
            if any((nid, pt) not in out for pt in ports):
                problem(nid, "a Decide exit is not connected; entities taking it are disposed")
            steps.append({"branch": {"branches": br, "max_branches": 1}})
            steps += dangling(nid, ports)

        elif kind == "assign":
            pairs = []
            rows = p.get("assignments") or []
            if not rows:
                problem(nid, "add at least one assignment")
            for i, r in enumerate(rows):
                t = r.get("type", "Variable")
                val = _or(r.get("value"), 0)
                where = f"assignment {i + 1}"
                if t.startswith("Variable"):
                    vn = str(r.get("variable", "")).strip()
                    if not vn:
                        problem(nid, f"{where}: choose a variable")
                        continue
                    if vn not in variables:
                        if t != "Variable":
                            problem(nid, f'{where}: define "{vn}" with rows (and columns) in the Variables table')
                            continue
                        variables[vn] = {"init": 0, "dims": [], "track": False, "clear": "system"}
                    elif t == "Variable" and variables[vn]["dims"]:
                        problem(nid, f'{where}: "{vn}" is an array; use Variable Array (1D) or (2D)')
                        continue
                    pairs.append([_array_ref(vn, t, r.get("row"), r.get("column")), val])
                elif t == "Attribute":
                    an = str(r.get("attribute", "")).strip()
                    if not an:
                        problem(nid, f"{where}: choose an attribute")
                        continue
                    need_attr(an)
                    pairs.append([an, val])
                elif t == "Entity Type":
                    et = str(r.get("entity_type", "")).strip()
                    if not et:
                        problem(nid, f"{where}: choose an entity type")
                        continue
                    entities.setdefault(et, {})
                    pairs.append(["Entity.Type", _quote(et)])
                elif t == "Entity Picture":
                    pairs.append(["Entity.Picture", _quote(str(r.get("entity_picture", "")).strip() or "Picture.Report")])
                else:
                    tgt = str(r.get("other", "")).strip()
                    if not tgt:
                        problem(nid, f"{where}: type the system variable to assign in Other")
                        continue
                    pairs.append([tgt, val])
            steps.append({"assign": {"assignments": pairs}})
            steps += goto(nid, "out")

        elif kind == "batch":
            by_attr = p.get("rule") == "By Attribute"
            if by_attr and not str(p.get("attribute", "")).strip():
                problem(nid, "Rule By Attribute needs an attribute name")
            if by_attr:
                need_attr(str(p.get("attribute")).strip())
            rep = str(p.get("rep_type", "")).strip()
            if rep:
                entities.setdefault(rep, {})
            steps.append({"batch": {"name": name, "size": _or(p.get("batch_size"), 2),
                                    "type": str(p.get("type", "Permanent")).lower(),
                                    "save": str(p.get("save_criterion", "Last")).lower(),
                                    "by_attribute": str(p.get("attribute")).strip() if by_attr else None,
                                    "representative_type": rep or None}})
            steps += goto(nid, "out")

        elif kind == "separate":
            if str(p.get("type", "Duplicate Original")).startswith("Split"):
                ma = str(p.get("member_attrs", "Retain Original Entity Values"))
                mode: Any = "retain"
                if ma.startswith("Take All"):
                    mode = "all"
                elif ma.startswith("Take Specific"):
                    mode = [str(r.get("attribute", "")).strip() for r in p.get("attributes") or []
                            if str(r.get("attribute", "")).strip()]
                    if not mode:
                        problem(nid, "list the attributes to take from the representative entity")
                steps.append({"separate": {"type": "split", "member_attributes": mode}})
                steps += goto(nid, "original")
            else:
                if (nid, "duplicate") not in out:
                    problem(nid, "the duplicate exit is not connected; duplicates are disposed")
                steps.append({"separate": {"type": "duplicate", "copies": _or(p.get("duplicates"), 1),
                                           "to": jump(nid, "duplicate"), "cost_percent": _or(p.get("percent_cost"), 50)}})
                steps += goto(nid, "original")
                steps += dangling(nid, ["duplicate"])

        elif kind == "record":
            rt = p.get("type", "Count")
            spec = {"type": rt.lower().replace(" ", "_"), "name": name}
            if _truthy(p.get("record_into_set")) and rt != "Entity Statistics":
                key = "counter_set" if rt == "Count" else "tally_set"
                sn = str(p.get(key, "")).strip()
                if need_set(nid, sn, key.replace("_", " ")):
                    spec.update(set=sn, index=_or(p.get("set_index"), 1))
                    for m in sets[sn]:
                        if rt == "Count":
                            counters.setdefault(m, {})
                        else:
                            tallies.add(m)
            elif rt == "Count":
                spec["counter"] = str(p.get("counter_name", "")).strip() or name
                counters.setdefault(spec["counter"], {})
            elif rt != "Entity Statistics":
                spec["tally"] = str(p.get("tally_name", "")).strip() or name
                tallies.add(spec["tally"])
            if rt == "Count":
                spec["value"] = _or(p.get("value"), 1)
            elif rt == "Expression":
                spec["value"] = _or(p.get("value"), 0)
            elif rt == "Time Interval":
                a = str(p.get("attribute", "")).strip()
                if not a:
                    problem(nid, "Time Interval needs the attribute that holds the start time")
                need_attr(a)
                spec["attribute"] = a or "Entity.CreateTime"
            steps.append({"record": spec})
            steps += goto(nid, "out")

        elif kind == "hold":
            ht = p.get("type", "Wait for Signal")
            steps += queue_steps(nid, name, p)
            if ht == "Scan for Condition":
                if not str(p.get("condition", "")).strip():
                    problem(nid, "Scan for Condition needs a condition")
                steps.append({"scan": {"condition": _or(p.get("condition"), 1)}})
            elif ht == "Infinite Hold":
                steps.append({"hold": {}})
            else:
                steps.append({"wait": {"signal_code": _or(p.get("wait_value"), 1), "limit": _infinite(p.get("limit"))}})
            steps += goto(nid, "out")

        elif kind == "signal":
            steps.append({"signal": {"code": _or(p.get("signal_value"), 1), "limit": _infinite(p.get("limit"))}})
            steps += goto(nid, "out")

        elif kind == "remove":
            qn = str(p.get("queue_name", "")).strip()
            if not qn:
                problem(nid, "choose the queue to remove an entity from")
            queues.setdefault(qn, {"ranking": "FIFO", "attribute": None})
            if (nid, "removed") not in out:
                problem(nid, "the removed-entity exit is not connected; removed entities are disposed")
            steps.append({"remove": {"queue": qn, "rank": _or(p.get("rank"), 1), "destination": jump(nid, "removed")}})
            steps += goto(nid, "original")
            steps += dangling(nid, ["removed"])

        elif kind == "station":
            steps.append({"station": {"station": p.get("station") or name}})
            steps += goto(nid, "out")
        elif kind == "route":
            dest = str(p.get("destination", "")).strip()
            need_station(nid, dest, "destination")
            steps.append({"route": {"duration": _time(_or(p.get("time"), 0), p.get("units"), base),
                                    "destination": dest or "SEQ"}})
        elif kind in ("request", "transport", "free"):
            tr = p.get("transporter", "")
            if tr not in transporters:
                problem(nid, f'choose a transporter defined in the Transporters table (got "{tr}")')
            if kind == "request":
                steps += [{"queue": {"queue": f"{name}.Queue"}},
                          {"request": {"transporter": tr, "rule": p.get("rule", "SDS")}}]
                steps += goto(nid, "out")
            elif kind == "transport":
                dest = str(p.get("destination", "")).strip()
                need_station(nid, dest, "destination")
                steps.append({"transport": {"transporter": tr, "destination": dest or "SEQ"}})
            else:
                steps.append({"free": {"transporter": tr}})
                steps += goto(nid, "out")
        elif kind in ("access", "convey", "exit"):
            cv = p.get("conveyor", "")
            if cv not in conveyors:
                problem(nid, f'choose a conveyor defined in the Conveyors table (got "{cv}")')
            if kind == "access":
                steps += [{"queue": {"queue": f"{name}.Queue"}},
                          {"access": {"conveyor": cv, "cells": _or(p.get("cells"), 1)}}]
                steps += goto(nid, "out")
            elif kind == "convey":
                dest = str(p.get("destination", "")).strip()
                need_station(nid, dest, "destination")
                steps.append({"convey": {"conveyor": cv, "destination": dest or "SEQ"}})
            else:
                steps.append({"exit": {"conveyor": cv}})
                steps += goto(nid, "out")
        elif kind == "dispose":
            steps.append({"dispose": {"record_stats": _truthy(p.get("record_stats"), True)}})
        else:
            problem(nid, f"unknown module type {kind}")
            continue
        steps[0] = {**steps[0], "label": _lab(nid)} if "label" not in steps[0] else steps[0]
        if steps[0].get("label") != _lab(nid):
            steps.insert(0, {"assign": {"assignments": []}, "label": _lab(nid)})
        flow.extend({**s, "node": nid} for s in steps)

    # ---- Statistic data module (Advanced Process): reported under User Specified
    dstats, frequencies, outputs = {}, {}, {}
    for name, s in data.get("statistics", {}).items():
        st = s.get("type", "Time-Persistent")
        label = str(s.get("report_label") or "").strip() or name
        expr = str(s.get("expression", "") or "").strip()
        if st in ("Time-Persistent", "Output") or (st == "Frequency" and s.get("frequency_type", "Value") == "Value"):
            if not expr:
                problem(None, f'statistic "{name}" needs an Expression')
                continue
        if st == "Time-Persistent":
            dstats[label] = expr
        elif st == "Output":
            outputs[label] = expr
        elif st == "Tally":
            tallies.add(name)
        elif st == "Counter":
            spec = counters.setdefault(name, {})
            lim = _infinite(s.get("limit", "Infinite"))
            if lim != "INF":
                spec["limit"] = lim
            if str(s.get("initial_value", "") or "").strip() not in ("", "0"):
                spec["initial"] = _num(s.get("initial_value"))
        elif st == "Frequency":
            if s.get("frequency_type") == "State":
                rname = str(s.get("resource", "") or "").strip()
                if not rname:
                    problem(None, f'statistic "{name}" needs a Resource Name')
                    continue
                need_resource(rname)
                expr = f"STATE({rname})"
            cats, excluded = [], []
            for c in s.get("categories") or []:
                is_range = c.get("kind") == "Range"
                lo = _num(c.get("value", ""))
                hi = _num(c.get("high", "")) if is_range else lo
                if lo in ("", None) or hi in ("", None):
                    problem(None, f'statistic "{name}": every category needs a Value' + (" and High Value" if is_range else ""))
                    continue
                cl = str(c.get("name", "") or "").strip() or (f"{lo} to {hi}" if is_range else str(lo))
                cats.append([cl, lo, hi])
                if c.get("option") == "Exclude":
                    excluded.append(cl)
            frequencies[label] = {"expr": expr, "categories": cats or None, "excluded": excluded}
        else:
            problem(None, f'statistic "{name}" has unknown Type {st}')

    # ---- Run Setup (Arena's Replication Parameters and Statistics Collection)
    reps = _num(run.get("replications", 1))
    if not isinstance(reps, int) or reps < 1:
        problem(None, "Run Setup: Number of Replications must be a whole number of at least 1")
        reps = 1
    length = _infinite(run.get("length", 480))
    if length != "Infinite" and length is not None:
        length = _time(length, run.get("length_units") or base, base)
    term = str(run.get("terminating", "") or "").strip()
    replicate = {"replications": reps, "length": length,
                 "warmup": _time(_or(run.get("warmup"), 0), run.get("warmup_units") or base, base),
                 "initialize_system": _truthy(run.get("init_system"), True),
                 "initialize_stats": _truthy(run.get("init_stats"), True)}
    if term:
        replicate["terminating_condition"] = term
    if length in ("Infinite", None) and not term and not any(
            str((n.get("props") or {}).get("max_arrivals", "Infinite")).strip().lower() not in ("", "infinite")
            for n in nodes.values() if n["type"] == "create"):
        problem(None, "Run Setup: the run has no Replication Length, Terminating Condition or limited arrivals, "
                      "so it may never end (End stops it); entities are disposed as usual")
    if not _truthy(run.get("stats_entities"), True):
        no_report.extend(entities)
    if not _truthy(run.get("stats_queues"), True):
        no_report.extend(queues)
    if not _truthy(run.get("stats_resources"), True):
        no_report.extend(resources)
    if not _truthy(run.get("stats_processes"), True):
        no_report.extend(k[:-len(".NumberIn")] for k in counters if k.endswith(".NumberIn"))
        no_report.extend(k for k in counters if k.endswith((".NumberIn", ".NumberOut")))

    if not any(n["type"] == "create" for n in nodes.values()):
        problem(None, "the model has no Create module")
    errors = [p for p in problems if "disposed" not in p["message"]]
    if errors:
        raise GraphError(problems)

    md.update({
        "replicate": replicate,
        "rng_mode": run.get("rng_mode", "arena"),
        "disable_randomness": _truthy(run.get("disable_randomness", False)),
        "resources": resources, "queues": queues, "schedules": schedules, "failures": failures,
        "variables": variables, "attributes": attributes, "expressions": expressions,
        "entity_types": entities, "sets": sets, "counters": counters, "tallies": sorted(tallies),
        "dstats": dstats, "frequencies": frequencies, "outputs": outputs,
        "transporters": {k: {kk: vv for kk, vv in v.items() if vv is not None} for k, v in transporters.items()},
        "conveyors": conveyors, "no_report": no_report, "flow": flow,
    })
    md["_warnings"] = problems
    return md
