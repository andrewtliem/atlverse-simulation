"""The editor's operations as plain functions on JSON-like data.

Used by the local server (server.py) and by the in-browser build, where worker.js runs
this module in Pyodide. Nothing here touches files, sockets or threads.
"""

from __future__ import annotations

import math
from typing import Callable

from ..loader import from_dict
from .graph import GraphError, to_model_dict, upgrade

__all__ = ["GraphError", "clean", "run_graph", "to_yaml", "upgrade", "validate"]


def clean(x):
    """JSON-safe numbers (NaN/inf become strings the page can display)."""
    if isinstance(x, float):
        if math.isnan(x):
            return "Insufficient"
        if math.isinf(x):
            return "Correlated" if x > 0 else "-inf"
        return x
    if isinstance(x, dict):
        return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    return x


def run_graph(graph: dict, progress: Callable[[int, int, float], bool] | None = None) -> dict:
    """Run an editor graph. progress(rep, reps, time) is called every 2000 events and
    returns True to end the run there (Arena's End button)."""
    md = to_model_dict(graph)
    warnings = md.pop("_warnings", [])
    model = from_dict(md)
    reps = md["replicate"]["replications"]
    stopped = [False]
    if progress is not None:
        def monitor(sim) -> bool:
            stopped[0] = bool(progress(sim.rep, reps, sim.now))
            return stopped[0]
        model.monitor = monitor
    batch = bool((graph.get("run") or {}).get("batch_run"))
    res = model.run(animate=not batch)
    first = res.sims[0]
    summary = {}
    if len(res.sims) > 1:
        paths = [f"tallies.{n}.average" for n in first.results["tallies"]]
        paths += [f"dstats.{n}.average" for n in first.results["dstats"]]
        paths += [f"counters.{n}" for n in first.results["counters"] if not n.endswith((".NumberIn", ".NumberOut"))]
        paths += [f"outputs.{n}" for n in first.results["outputs"]]
        paths += [f"queues.{q}.waiting_time.average" for q in first.results["queues"]]
        for pth in paths:
            try:
                summary[pth.removesuffix(".average").removesuffix(".waiting_time")] = res.across(pth)
            except (KeyError, TypeError, ValueError):
                pass
    return clean({
        "report": res.report(),
        "replications": res.replications,
        "across": summary,
        "anim": first.anim or [],
        "anim_truncated": len(first.anim or []) >= first.ANIM_LIMIT,
        "end_time": first.results["time"],
        "stopped": stopped[0],
        "replications_done": len(res.sims),
        "warnings": warnings,
    })


def to_yaml(graph: dict) -> str:
    import yaml

    md = to_model_dict(graph)
    md.pop("_warnings", None)
    return yaml.safe_dump(md, sort_keys=False)


def validate(graph: dict) -> list:
    try:
        return to_model_dict(graph).get("_warnings", [])
    except GraphError as e:
        return e.problems
