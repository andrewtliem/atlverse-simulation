"""Editor modules with Arena's dialog fields (graph version 2)."""

import unittest

from simcore.loader import from_dict
from simcore.web.graph import GraphError, to_model_dict


def N(i, t, **props):
    return {"id": str(i), "type": t, "x": 0, "y": 0, "props": {"name": props.pop("name", f"{t} {i}"), **props}}


def L(a, b, port="out"):
    return {"from": str(a), "to": str(b), "port": port}


def graph(nodes, links, data=None, units="minutes", **run):
    return {"version": 2, "name": "T", "time_units": units, "run": {"replications": 1, "length": 1000, **run},
            "data": data or {}, "nodes": nodes, "links": links}


def run(g, reps=None):
    md = to_model_dict(g)
    md.pop("_warnings")
    res = from_dict(md).run(reps)
    return res.replications[0] if reps is None else res


def CREATE(i, n=10, **kw):
    return N(i, "create", **{"type": "Constant", "value": "1", "units": "Minutes", "max_arrivals": str(n),
                             "entity_type": "Part", **kw})


class TestAssign(unittest.TestCase):
    def test_every_assignment_type(self):
        data = {"variables": {"Total": {"initial_values": "0"},
                              "Row": {"rows": "3", "initial_values": "0"},
                              "Grid": {"rows": "2", "columns": "2", "initial_values": "1, 2, 3, 4"}},
                "attributes": {"Size": {"initial_values": "0"}}}
        g = graph([CREATE(1, 5),
                   N(2, "assign", assignments=[
                       {"type": "Variable", "variable": "Total", "value": "Total + 1"},
                       {"type": "Variable Array (1D)", "variable": "Row", "row": "2", "value": "Row(2) + 10"},
                       {"type": "Variable Array (2D)", "variable": "Grid", "row": "2", "column": "1",
                        "value": "Grid(2, 1) * 2"},
                       {"type": "Attribute", "attribute": "Size", "value": "Entity.SerialNumber"},
                       {"type": "Entity Type", "entity_type": "Done Part"},
                       {"type": "Entity Picture", "entity_picture": "Picture.Blue Ball"},
                       {"type": "Other", "other": "MR(Machine)", "value": "3"}]),
                   N(3, "decide", type="2-way by Condition", if_type="Entity Type", named="Done Part"),
                   N(4, "record", type="Count", counter_name="typed"),
                   N(5, "record", type="Expression", tally_name="grid", value="Grid(2, 1)"),
                   N(6, "record", type="Expression", tally_name="cap", value="MR(Machine)"),
                   N(7, "dispose")],
                  [L(1, 2), L(2, 3), L(3, 4, "true"), L(3, 7, "false"), L(4, 5), L(5, 6), L(6, 7)],
                  {**data, "resources": {"Machine": {"type": "Fixed Capacity", "capacity": "1"}}})
        r = run(g)
        self.assertEqual(r["counters"]["typed"], 5)
        self.assertEqual(r["tallies"]["grid"]["max"], 3 * 2 ** 5)   # doubled once per entity
        self.assertEqual(r["tallies"]["cap"]["max"], 3)
        self.assertEqual(r["entities"]["out"].get("Done Part"), 5)

    def test_assign_errors(self):
        g = graph([CREATE(1), N(2, "assign", assignments=[
            {"type": "Variable Array (1D)", "variable": "Nope", "row": "1", "value": "1"},
            {"type": "Attribute", "attribute": "", "value": "1"}]), N(3, "dispose")], [L(1, 2), L(2, 3)])
        with self.assertRaises(GraphError) as cm:
            to_model_dict(g)
        msgs = " | ".join(p["message"] for p in cm.exception.problems)
        self.assertIn("Variables table", msgs)
        self.assertIn("choose an attribute", msgs)


class TestProcess(unittest.TestCase):
    def test_delay_types_and_units(self):
        # 2 seconds in a model in minutes, constant
        g = graph([CREATE(1, 1),
                   N(2, "process", action="Delay", delay_type="Constant", value="120", units="Seconds"),
                   N(3, "dispose")], [L(1, 2), L(2, 3)])
        r = run(g)
        self.assertAlmostEqual(r["tallies"]["process 2.TotalTimePerEntity"]["average"], 2.0)

    def test_resource_set_with_save_attribute(self):
        data = {"resources": {n: {"type": "Fixed Capacity", "capacity": "1"} for n in ("A", "B", "C")},
                "sets": {"Clerks": {"type": "Resource", "members": "A, B, C"}}}
        g = graph([CREATE(1, 6, value="10"),
                   N(2, "process", action="Seize Delay Release", priority="High (1)",
                     resources=[{"type": "Set", "set": "Clerks", "quantity": "1", "rule": "Cyclical",
                                 "save_attr": "who"}],
                     delay_type="Constant", value="1", units="Minutes"),
                   N(3, "record", type="Expression", tally_name="idx", value="who"), N(4, "dispose")],
                  [L(1, 2), L(2, 3), L(3, 4)], data)
        r = run(g)
        self.assertEqual([r["resources"][n]["times_used"] for n in "ABC"], [2, 2, 2])
        self.assertEqual((r["tallies"]["idx"]["min"], r["tallies"]["idx"]["max"]), (1, 3))

    def test_seize_set_then_release_last_member(self):
        data = {"sets": {"Pool": {"type": "Resource", "members": "R1, R2"}}}
        g = graph([CREATE(1, 4, value="5"),
                   N(2, "seize", resources=[{"type": "Set", "set": "Pool", "rule": "Preferred Order"}]),
                   N(3, "delay", delay_time="1", units="Minutes"),
                   N(4, "release", resources=[{"type": "Set", "set": "Pool", "release_rule": "Last Member Seized"}]),
                   N(5, "dispose")], [L(1, 2), L(2, 3), L(3, 4), L(4, 5)], data)
        r = run(g)
        self.assertEqual(r["resources"]["R1"]["times_used"], 4)
        self.assertEqual(r["resources"]["R2"]["times_used"], 0)


class TestDecide(unittest.TestCase):
    def test_conditions_on_variables_attributes_arrays(self):
        data = {"variables": {"Lim": {"initial_values": "3"}, "V": {"rows": "2", "initial_values": "5, 7"}}}
        g = graph([CREATE(1, 10),
                   N(2, "assign", assignments=[{"type": "Attribute", "attribute": "n", "value": "Entity.SerialNumber"}]),
                   N(3, "decide", type="N-way by Condition", conditions=[
                       {"if_type": "Attribute", "named": "n", "is": "<=", "value": "Lim"},
                       {"if_type": "Variable Array (1D)", "named": "V", "row": "2", "is": "==", "value": "7"}]),
                   N(4, "record", type="Count", counter_name="low"), N(5, "record", type="Count", counter_name="arr"),
                   N(6, "record", type="Count", counter_name="else"), N(7, "dispose")],
                  [L(1, 2), L(2, 3), L(3, 4, "1"), L(3, 5, "2"), L(3, 6, "else"), L(4, 7), L(5, 7), L(6, 7)], data)
        c = run(g)["counters"]
        self.assertEqual((c["low"], c["arr"], c.get("else", 0)), (3, 7, 0))

    def test_n_way_chance(self):
        g = graph([CREATE(1, 3000), N(2, "decide", type="N-way by Chance",
                                      percentages=[{"percent": "25"}, {"percent": "25"}]),
                   N(3, "record", type="Count", counter_name="a"), N(4, "record", type="Count", counter_name="b"),
                   N(5, "record", type="Count", counter_name="c"), N(6, "dispose")],
                  [L(1, 2), L(2, 3, "1"), L(2, 4, "2"), L(2, 5, "else"), L(3, 6), L(4, 6), L(5, 6)], length=5000)
        c = run(g)["counters"]
        self.assertAlmostEqual(c["c"] / 3000, 0.5, delta=0.04)


class TestBatchSeparateRecord(unittest.TestCase):
    def test_batch_by_attribute_and_split_take_all(self):
        g = graph([CREATE(1, 8),
                   N(2, "assign", assignments=[{"type": "Variable", "variable": "n", "value": "n + 1"},
                                               {"type": "Attribute", "attribute": "color", "value": "MOD(n, 2)"}]),
                   N(3, "batch", type="Temporary", batch_size="2", rule="By Attribute", attribute="color",
                     save_criterion="Sum", rep_type="Box"),
                   N(4, "record", type="Count", counter_name="boxes"),
                   N(5, "separate", type="Split Existing Batch", member_attrs="Take All Representative Values"),
                   N(6, "record", type="Expression", tally_name="color", value="color"),
                   N(7, "dispose")],
                  [L(1, 2), L(2, 3), L(3, 4), L(4, 5), L(5, 6, "original"), L(6, 7)])
        r = run(g)
        self.assertEqual(r["counters"]["boxes"], 4)
        self.assertEqual(r["tallies"]["color"]["observations"], 8)
        self.assertEqual(r["tallies"]["color"]["max"], 2)  # sum of two 1s, copied to members
        self.assertEqual(r["entities"]["out"].get("Box"), 8)

    def test_duplicate_cost_share(self):
        data = {"entities": {"Part": {"initial_va": "100"}}}
        g = graph([CREATE(1, 1), N(2, "separate", type="Duplicate Original", duplicates="2", percent_cost="50"),
                   N(3, "record", type="Expression", tally_name="orig", value="Entity.VACost"),
                   N(4, "record", type="Expression", tally_name="dup", value="Entity.VACost"), N(5, "dispose")],
                  [L(1, 2), L(2, 3, "original"), L(2, 4, "duplicate"), L(3, 5), L(4, 5)], data)
        t = run(g)["tallies"]
        self.assertAlmostEqual(t["orig"]["average"], 50)
        self.assertAlmostEqual(t["dup"]["average"], 25)
        self.assertEqual(t["dup"]["observations"], 2)

    def test_record_into_sets_and_time_between(self):
        data = {"sets": {"Lines": {"type": "Counter", "members": "Line 1, Line 2"}}}
        g = graph([CREATE(1, 6),
                   N(2, "assign", assignments=[{"type": "Attribute", "attribute": "k",
                                                "value": "MOD(Entity.SerialNumber, 2) + 1"}]),
                   N(3, "record", type="Count", record_into_set=True, counter_set="Lines", set_index="k"),
                   N(4, "record", type="Time Between", tally_name="tbe"),
                   N(5, "record", type="Entity Statistics"), N(6, "dispose")],
                  [L(1, 2), L(2, 3), L(3, 4), L(4, 5), L(5, 6)], data)
        r = run(g)
        self.assertEqual((r["counters"]["Line 1"], r["counters"]["Line 2"]), (3, 3))
        self.assertAlmostEqual(r["tallies"]["tbe"]["average"], 1.0)
        self.assertEqual(r["tallies"]["Part.TotalTime"]["observations"], 12)  # Record + Dispose


class TestHoldQueues(unittest.TestCase):
    def test_infinite_hold_and_remove(self):
        g = graph([CREATE(1, 3, first_creation="0"), N(2, "hold", type="Infinite Hold", queue_name="Parked"),
                   N(3, "dispose", name="never"),
                   CREATE(4, 1, first_creation="10", entity_type="Ctl"),
                   N(5, "remove", queue_name="Parked", rank="1"),
                   N(6, "record", type="Count", counter_name="removed"), N(7, "dispose", name="ctl out")],
                  [L(1, 2), L(2, 3), L(4, 5), L(5, 7, "original"), L(5, 6, "removed"), L(6, 7)])
        r = run(g)
        self.assertEqual(r["counters"]["removed"], 1)
        self.assertEqual(r["queues"]["Parked"]["number_waiting"]["final"], 2)

    def test_seize_queue_set_and_hold_limit(self):
        data = {"sets": {"Lanes": {"type": "Queue", "members": "Lane A, Lane B"}}}
        g = graph([CREATE(1, 6),
                   N(2, "assign", assignments=[{"type": "Attribute", "attribute": "lane",
                                                "value": "MOD(Entity.SerialNumber, 2) + 1"}]),
                   N(3, "seize", resources=[{"type": "Resource", "resource": "M"}], queue_type="Set",
                     queue_set="Lanes", queue_set_index="lane"),
                   N(4, "delay", delay_time="3", units="Minutes"),
                   N(5, "release", resources=[{"type": "Resource", "resource": "M"}]), N(6, "dispose")],
                  [L(1, 2), L(2, 3), L(3, 4), L(4, 5), L(5, 6)], data)
        r = run(g)
        self.assertEqual(r["resources"]["M"]["times_used"], 6)
        self.assertGreater(r["queues"]["Lane A"]["waiting_time"]["observations"], 0)
        self.assertGreater(r["queues"]["Lane B"]["waiting_time"]["observations"], 0)


class TestProcessArena(unittest.TestCase):
    def test_process_statistics(self):
        g = graph([CREATE(1, 5), N(2, "process", name="Work", action="Seize Delay Release",
                                   resources=[{"type": "Resource", "resource": "M", "quantity": "1"}],
                                   delay_type="Constant", value="3", units="Minutes", allocation="Non-Value Added"),
                   N(3, "dispose")], [L(1, 2), L(2, 3)])
        r = run(g)
        self.assertEqual(r["counters"]["Work.NumberIn"], 5)
        self.assertEqual(r["counters"]["Work.NumberOut"], 5)
        self.assertAlmostEqual(r["tallies"]["Work.NVATimePerEntity"]["average"], 3.0)
        # arrivals every minute, 3 minutes of work: waits 0, 2, 4, 6, 8
        self.assertAlmostEqual(r["tallies"]["Work.WaitTimePerEntity"]["average"], 4.0)
        self.assertAlmostEqual(r["tallies"]["Work.TotalTimePerEntity"]["average"], 7.0)

    def test_submodel(self):
        inner = {"nodes": [{"id": "1", "type": "sub_in", "x": 0, "y": 0, "props": {"name": "Entry"}},
                           N(2, "assign", name="Mark", assignments=[{"type": "Attribute", "attribute": "a", "value": "7"}]),
                           N(3, "process", name="Inner Work", action="Delay", delay_type="Constant", value="2",
                             units="Minutes"),
                           {"id": "4", "type": "sub_out", "x": 0, "y": 0, "props": {"name": "Exit"}}],
                 "links": [L(1, 2), L(2, 3), L(3, 4)]}
        sub = N(2, "process", name="Cell", type="Submodel")
        sub["sub"] = inner
        g = graph([CREATE(1, 4), sub, N(3, "record", type="Expression", tally_name="a", value="a"), N(4, "dispose")],
                  [L(1, 2), L(2, 3), L(3, 4)])
        md = to_model_dict(g)
        self.assertIn("2/3", {s.get("node") for s in md["flow"]})
        r = run(g)
        self.assertEqual(r["tallies"]["a"]["average"], 7)
        self.assertEqual(r["counters"]["Inner Work.NumberOut"], 4)
        self.assertNotIn("Cell.NumberIn", r["counters"])

    def test_submodel_without_entry_link(self):
        sub = N(2, "process", name="Cell", type="Submodel")
        sub["sub"] = {"nodes": [{"id": "1", "type": "sub_in", "x": 0, "y": 0, "props": {"name": "Entry"}}], "links": []}
        with self.assertRaises(GraphError):
            to_model_dict(graph([CREATE(1, 1), sub], [L(1, 2)]))

    def test_seize_by_attribute_and_resource_number(self):
        data = {"resources": {"A": {"capacity": "1"}, "B": {"capacity": "1"}}}
        for val in ("B", "2"):
            g = graph([CREATE(1, 4), N(2, "assign", assignments=[{"type": "Attribute", "attribute": "who", "value": val}]),
                       N(3, "seize", resources=[{"type": "Attribute", "attribute": "who"}]),
                       N(4, "delay", delay_time="3", units="Minutes"),
                       N(5, "release", resources=[{"type": "Expression", "expression": "who"}]), N(6, "dispose")],
                      [L(1, 2), L(2, 3), L(3, 4), L(4, 5), L(5, 6)], data)
            r = run(g)
            self.assertEqual((r["resources"]["A"]["times_used"], r["resources"]["B"]["times_used"]), (0, 4), val)

    def test_signal_limit_counts_across_holds(self):
        g = graph([CREATE(1, 4), N(2, "hold", wait_value="1"), N(3, "record", type="Count", counter_name="h1"),
                   N(4, "dispose"), CREATE(5, 4, entity_type="X"), N(6, "hold", wait_value="1"),
                   N(7, "record", type="Count", counter_name="h2"),
                   CREATE(8, 1, first_creation="20", entity_type="S"), N(9, "signal", signal_value="1", limit="3")],
                  [L(1, 2), L(2, 3), L(3, 4), L(5, 6), L(6, 7), L(7, 4), L(8, 9), L(9, 4)])
        r = run(g)
        self.assertEqual(r["counters"]["h1"] + r["counters"]["h2"], 3)


class TestDataModules(unittest.TestCase):
    def test_schedule_resource_and_other_schedule(self):
        data = {"schedules": {"Shift": {"type": "Capacity", "units": "Hours",
                                        "durations": [{"value": "2", "duration": "1"}, {"value": "0", "duration": "1"}]},
                              "Factor": {"type": "Other", "units": "Minutes", "scale": "2",
                                         "durations": [{"value": "1", "duration": "50"}, {"value": "3", "duration": ""}]}},
                "resources": {"Crew": {"type": "Based on Schedule", "schedule": "Shift", "schedule_rule": "Ignore"}}}
        g = graph([CREATE(1, 1, first_creation="100"),
                   N(2, "record", type="Expression", tally_name="f", value="SchedValue(Factor)"),
                   N(3, "record", type="Expression", tally_name="mr", value="MR(Crew)"), N(4, "dispose")],
                  [L(1, 2), L(2, 3), L(3, 4)], data)
        t = run(g)["tallies"]
        self.assertEqual(t["f"]["average"], 6)   # after the infinite last value, times the scale
        self.assertEqual(t["mr"]["average"], 0)  # minute 100 is in the second hour (capacity 0)

    def test_variable_clear_none_keeps_value(self):
        data = {"variables": {"Seen": {"initial_values": "0", "clear": "None"},
                              "Fresh": {"initial_values": "0", "clear": "System"}}}
        g = graph([CREATE(1, 2), N(2, "assign", assignments=[
            {"type": "Variable", "variable": "Seen", "value": "Seen + 1"},
            {"type": "Variable", "variable": "Fresh", "value": "Fresh + 1"}]),
                   N(3, "record", type="Expression", tally_name="seen", value="Seen"),
                   N(4, "record", type="Expression", tally_name="fresh", value="Fresh"), N(5, "dispose")],
                  [L(1, 2), L(2, 3), L(3, 4), L(4, 5)], data)
        res = run(g, reps=3)
        self.assertEqual(res.replications[2]["tallies"]["seen"]["max"], 6)
        self.assertEqual(res.replications[2]["tallies"]["fresh"]["max"], 2)

    def test_failure_uptime_in_busy_state(self):
        # Busy only between 0 and 10: a 5-minute busy-time failure happens once, at t = 5.
        data = {"failures": {"Wear": {"type": "Time", "up_time": "5", "up_units": "Minutes", "down_time": "1",
                                      "down_units": "Minutes", "state": "Busy"}},
                "resources": {"M": {"type": "Fixed Capacity", "capacity": "1",
                                    "failures": [{"failure": "Wear", "rule": "Wait"}]}}}
        g = graph([CREATE(1, 1), N(2, "process", action="Seize Delay Release",
                                   resources=[{"type": "Resource", "resource": "M"}],
                                   delay_type="Constant", value="10", units="Minutes"), N(3, "dispose")],
                  [L(1, 2), L(2, 3)], data, length=100)
        r = run(g)
        st = r["resources"]["M"]["states"]
        self.assertAlmostEqual(st["FAILED"]["time"] if "time" in st["FAILED"] else st["FAILED"]["standard_percent"],
                               1 if "time" in st["FAILED"] else 1.0, delta=1e-6)

    def test_report_statistics_unchecked(self):
        data = {"resources": {"Hidden": {"type": "Fixed Capacity", "capacity": "1", "report": False}},
                "entities": {"Part": {"report": False}}}
        g = graph([CREATE(1, 2), N(2, "process", resources=[{"type": "Resource", "resource": "Hidden"}],
                                   delay_type="Constant", value="1", report=False), N(3, "dispose")],
                  [L(1, 2), L(2, 3)], data)
        r = run(g)
        self.assertNotIn("Hidden", r["resources"])
        self.assertNotIn("Part.TotalTime", r["tallies"])
        self.assertNotIn("process 2.TotalTimePerEntity", r["tallies"])


if __name__ == "__main__":
    unittest.main()


class TestRunSetup(unittest.TestCase):
    def test_length_and_warmup_units_hours_per_day(self):
        g = graph([CREATE(1, 100000), N(2, "record", type="Count", counter_name="n"), N(3, "dispose")],
                  [L(1, 2), L(2, 3)], length="1", length_units="Days", hours_per_day="8",
                  warmup="2", warmup_units="Hours")
        md = to_model_dict(g)
        self.assertEqual(md["replicate"]["length"], 480)
        self.assertEqual(md["replicate"]["warmup"], 120)
        r = run(g)
        self.assertEqual(r["time"], 480)
        self.assertEqual(r["counters"]["n"], 361)  # arrivals at 120, 121, ..., 480 (after the warm-up)

    def test_infinite_length_with_terminating_condition(self):
        g = graph([CREATE(1, 100000), N(2, "record", type="Count", counter_name="n"), N(3, "dispose")],
                  [L(1, 2), L(2, 3)], length="", terminating="TNOW >= 50")
        r = run(g)
        self.assertAlmostEqual(r["time"], 50)

    def test_statistics_collection_switches(self):
        g = graph([CREATE(1, 5), N(2, "process", name="P", resources=[{"type": "Resource", "resource": "S"}],
                                   delay_type="Constant", value="1", units="Minutes"), N(3, "dispose")],
                  [L(1, 2), L(2, 3)], stats_queues=False, stats_resources=False, stats_processes=False,
                  stats_entities=False)
        r = run(g)
        self.assertEqual((r["queues"], r["resources"]), ({}, {}))
        self.assertNotIn("P.NumberIn", r["counters"])
        self.assertNotIn("Part.TotalTime", r["tallies"])

    def test_stop_from_monitor_keeps_results(self):
        md = to_model_dict(graph([CREATE(1, 10 ** 9, value="0.01"), N(2, "dispose")], [L(1, 2)],
                                 length="", replications="5"))
        md.pop("_warnings")
        m = from_dict(md)
        m.monitor = lambda sim: sim.now > 100
        res = m.run()
        self.assertEqual(len(res.sims), 1)
        self.assertTrue(res.sims[0].stopped)
        self.assertLess(res.replications[0]["time"], 110)
