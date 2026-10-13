"""Plain-text summary report in the spirit of the SIMAN .out file."""

from __future__ import annotations

import math


def _f(x) -> str:
    if x is None:
        return "--"
    if isinstance(x, float):
        if math.isnan(x):
            return "(Insuf)"
        if math.isinf(x):
            return "(Corr)" if x > 0 else "-inf"
        return f"{x:.4f}"
    return str(x)


def _table(title: str, header: list[str], rows: list[list]) -> list[str]:
    if not rows:
        return []
    widths = [max(len(str(h)), *(len(_f(r[i])) for r in rows)) for i, h in enumerate(header)]
    out = ["", title, "  ".join(h.ljust(w) for h, w in zip(header, widths)),
           "  ".join("-" * w for w in widths)]
    out += ["  ".join(_f(c).ljust(w) for c, w in zip(r, widths)) for r in rows]
    return out


def summary_report(result) -> str:
    m = result.model
    lines = [f"Summary for {m.name}  ({len(result.sims)} replication(s), time units: {m.time_units})"]
    for sim in result.sims:
        r = sim.results
        lines += ["", f"=== Replication {sim.rep}   ended at time {r['time']:.4f}"]
        lines += _table("TALLY VARIABLES", ["Identifier", "Average", "Half Width", "Minimum", "Maximum", "Observations"],
                        [[n, t["average"], t["half_width"], t["min"] if t["observations"] else None,
                          t["max"] if t["observations"] else None, t["observations"]]
                         for n, t in sorted(r["tallies"].items())] +
                        [[f"{n}.WaitingTime", q["waiting_time"]["average"], q["waiting_time"]["half_width"],
                          q["waiting_time"]["min"] if q["waiting_time"]["observations"] else None,
                          q["waiting_time"]["max"] if q["waiting_time"]["observations"] else None,
                          q["waiting_time"]["observations"]]
                         for n, q in sorted(r["queues"].items()) if not n.startswith("__")])
        dc = [[f"{n}.NumberInQueue", q["number_waiting"]["average"], q["number_waiting"]["half_width"],
               q["number_waiting"]["min"], q["number_waiting"]["max"], q["number_waiting"]["final"]]
              for n, q in sorted(r["queues"].items()) if not n.startswith("__")]
        for n, x in sorted(r["resources"].items()):
            dc.append([f"{n}.NumberBusy", x["number_busy"], None, None, None, None])
            dc.append([f"{n}.NumberScheduled", x["number_scheduled"], None, None, None, None])
            dc.append([f"{n}.Utilization", x["instantaneous_utilization"], None, None, None, None])
        dc += [[n, d["average"], d.get("half_width"), d["min"], d["max"], d["final"]] for n, d in sorted(r["dstats"].items())]
        lines += _table("DISCRETE-CHANGE VARIABLES", ["Identifier", "Average", "Half Width", "Minimum", "Maximum", "Final Value"], dc)
        fr = []
        for n, x in sorted(r["resources"].items()):
            for state, s in x["states"].items():
                fr.append([f"{n}.States", state, s["number"], s["avg_time"], s["standard_percent"]])
        for n, f in sorted(r.get("frequencies", {}).items()):
            for cat, x in f.items():
                fr.append([n, cat, x["number"], x["avg_time"], x["standard_percent"]])
        lines += _table("FREQUENCIES", ["Identifier", "Category", "Number", "AvgTime", "Standard Percent"], fr)
        lines += _table("COUNTERS", ["Identifier", "Count"], [[n, c] for n, c in sorted(r["counters"].items())])
        lines += _table("OUTPUTS", ["Identifier", "Value"], [[n, v] for n, v in sorted(r["outputs"].items())])
    return "\n".join(lines)
