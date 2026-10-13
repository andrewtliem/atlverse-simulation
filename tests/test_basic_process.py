"""Basic Process panel checked against hand-worked results and queueing theory."""

import math
import unittest

from simcore.loader import from_dict
from simcore.web.graph import to_model_dict
from test_arena_modules import CREATE, L, N, graph


def run(g):
    md = to_model_dict(g)
    md.pop("_warnings")
    return from_dict(md).run().replications[0]


def RES(**rows):
    return {"resources": {k: {"capacity": str(v)} for k, v in rows.items()}}


class TestCreate(unittest.TestCase):
    def test_constant_first_creation_batch_and_max(self):
        g = graph([CREATE(1, 4, value="5", first_creation="2", entities_per_arrival="3"),
                   N(2, "record", type="Expression", tally_name="t", value="TNOW"), N(3, "dispose")],
                  [L(1, 2), L(2, 3)])
        r = run(g)
        self.assertEqual(r["tallies"]["t"]["observations"], 12)  # Max Arrivals counts arrivals
        self.assertEqual((r["tallies"]["t"]["min"], r["tallies"]["t"]["max"]), (2, 17))
        self.assertAlmostEqual(r["tallies"]["t"]["average"], (2 + 7 + 12 + 17) / 4)

    def test_units_convert_to_base(self):
        g = graph([CREATE(1, 3, value="1", units="Hours", first_creation="0.5"),
                   N(2, "record", type="Expression", tally_name="t", value="TNOW"), N(3, "dispose")],
                  [L(1, 2), L(2, 3)])
        r = run(g)
        self.assertEqual((r["tallies"]["t"]["min"], r["tallies"]["t"]["max"]), (30, 150))

    def test_random_expo_mean(self):
        g = graph([N(1, "create", type="Random (Expo)", value="2", units="Minutes", entity_type="P"),
                   N(2, "record", type="Time Between", tally_name="tb"), N(3, "dispose")],
                  [L(1, 2), L(2, 3)], length=200000)
        tb = run(g)["tallies"]["tb"]
        self.assertAlmostEqual(tb["average"], 2.0, delta=0.05)
        self.assertAlmostEqual(tb["std"], 2.0, delta=0.08)  # exponential: sd = mean

    def test_arrival_schedule_rate_per_hour(self):
        data = {"schedules": {"Arr": {"type": "Arrival", "units": "Hours",
                                      "durations": [{"value": "60", "duration": "1"}, {"value": "0", "duration": "1"}]}}}
        g = graph([N(1, "create", type="Schedule", schedule="Arr", entity_type="P"),
                   N(2, "record", type="Count", counter_name="n"), N(3, "dispose")],
                  [L(1, 2), L(2, 3)], data, length=1200 * 60)  # 600 two-hour cycles
        n = run(g)["counters"]["n"]
        self.assertAlmostEqual(n / 600, 60, delta=2.5)  # repeats; 60/hour in the first hour of each cycle


class TestProcess(unittest.TestCase):
    def mm(self, c, lam_mean, mu_mean, length=400000):
        g = graph([N(1, "create", type="Random (Expo)", value=str(lam_mean), units="Minutes", entity_type="P"),
                   N(2, "process", name="Serve", resources=[{"type": "Resource", "resource": "S", "quantity": "1"}],
                     delay_type="Expression", expression=f"EXPO({mu_mean})", units="Minutes"),
                   N(3, "dispose")], [L(1, 2), L(2, 3)], RES(S=c), length=length)
        return run(g)

    @staticmethod
    def erlang_wq(c, lam, mu):
        a, rho = lam / mu, lam / (c * mu)
        p0 = 1 / (sum(a ** k / math.factorial(k) for k in range(c)) + a ** c / (math.factorial(c) * (1 - rho)))
        lq = p0 * a ** c * rho / (math.factorial(c) * (1 - rho) ** 2)
        return lq / lam, lq

    def test_mm1(self):
        r = self.mm(1, 1.0, 0.8)
        wq, lq = self.erlang_wq(1, 1.0, 1.25)          # Wq = 3.2, Lq = 3.2
        self.assertAlmostEqual(r["queues"]["Serve.Queue"]["waiting_time"]["average"], wq, delta=0.25)
        self.assertAlmostEqual(r["queues"]["Serve.Queue"]["number_waiting"]["average"], lq, delta=0.25)
        self.assertAlmostEqual(r["resources"]["S"]["instantaneous_utilization"], 0.8, delta=0.01)
        self.assertAlmostEqual(r["tallies"]["Serve.TotalTimePerEntity"]["average"], wq + 0.8, delta=0.25)
        self.assertAlmostEqual(r["tallies"]["Serve.VATimePerEntity"]["average"], 0.8, delta=0.01)

    def test_mm3(self):
        r = self.mm(3, 1.0, 2.7)
        wq, _ = self.erlang_wq(3, 1.0, 1 / 2.7)
        self.assertAlmostEqual(r["queues"]["Serve.Queue"]["waiting_time"]["average"], wq, delta=0.3 * wq)
        self.assertAlmostEqual(r["resources"]["S"]["instantaneous_utilization"], 0.9, delta=0.01)
        self.assertAlmostEqual(r["resources"]["S"]["number_busy"], 2.7, delta=0.05)

    def test_delay_type_means(self):
        cases = {"Normal": dict(value="5", std_dev="1"), "Triangular": dict(minimum="1", value="2", maximum="6"),
                 "Uniform": dict(minimum="2", maximum="4"), "Constant": dict(value="2.5")}
        expect = {"Normal": 5, "Triangular": 3, "Uniform": 3, "Constant": 2.5}
        for dt, kw in cases.items():
            g = graph([CREATE(1, 20000), N(2, "process", name="P", action="Delay", delay_type=dt, units="Minutes", **kw),
                       N(3, "dispose")], [L(1, 2), L(2, 3)], length=100000)
            r = run(g)
            self.assertAlmostEqual(r["tallies"]["P.VATimePerEntity"]["average"], expect[dt], delta=0.05, msg=dt)

    def test_priority_between_modules(self):
        # both modules want S; when S frees, the High priority waiter goes first
        g = graph([CREATE(1, 1, entity_type="Hog"),
                   N(2, "process", name="Hog", resources=[{"type": "Resource", "resource": "S"}], delay_type="Constant",
                     value="10", units="Minutes"), N(3, "dispose"),
                   CREATE(4, 1, first_creation="1", entity_type="Lo"),
                   N(5, "process", name="Lo", priority="Low (3)", resources=[{"type": "Resource", "resource": "S"}],
                     delay_type="Constant", value="1", units="Minutes"),
                   CREATE(6, 1, first_creation="2", entity_type="Hi"),
                   N(7, "process", name="Hi", priority="High (1)", resources=[{"type": "Resource", "resource": "S"}],
                     delay_type="Constant", value="1", units="Minutes")],
                  [L(1, 2), L(2, 3), L(4, 5), L(5, 3), L(6, 7), L(7, 3)], RES(S=1))
        r = run(g)
        self.assertAlmostEqual(r["tallies"]["Hi.WaitTimePerEntity"]["average"], 8)   # 2 -> 10
        self.assertAlmostEqual(r["tallies"]["Lo.WaitTimePerEntity"]["average"], 10)  # 1 -> 11

    def test_seize_delay_then_delay_release(self):
        g = graph([CREATE(1, 3, value="10"),
                   N(2, "process", name="A", action="Seize Delay", resources=[{"type": "Resource", "resource": "S"}],
                     delay_type="Constant", value="2", units="Minutes"),
                   N(3, "process", name="B", action="Delay Release", resources=[{"type": "Resource", "resource": "S"}],
                     delay_type="Constant", value="3", units="Minutes"), N(4, "dispose")],
                  [L(1, 2), L(2, 3), L(3, 4)], RES(S=1), length=30)
        r = run(g)
        self.assertAlmostEqual(r["resources"]["S"]["number_busy"], 15 / 30)  # held for 5 of every 10
        self.assertEqual(r["counters"]["B.NumberOut"], 3)

    def test_quantity_two_units(self):
        g = graph([CREATE(1, 2, value="0.0001"),
                   N(2, "process", name="P", resources=[{"type": "Resource", "resource": "S", "quantity": "2"}],
                     delay_type="Constant", value="5", units="Minutes"), N(3, "dispose")],
                  [L(1, 2), L(2, 3)], RES(S=3), length=20)
        r = run(g)  # 3 units, 2 per entity: they cannot overlap
        self.assertAlmostEqual(r["tallies"]["P.WaitTimePerEntity"]["max"], 5, delta=0.001)

    def test_resource_costs(self):
        data = {"resources": {"S": {"capacity": "1", "busy_per_hour": "60", "idle_per_hour": "6", "per_use": "1"}}}
        g = graph([CREATE(1, 1), N(2, "process", name="P", resources=[{"type": "Resource", "resource": "S"}],
                                   delay_type="Constant", value="30", units="Minutes"), N(3, "dispose")],
                  [L(1, 2), L(2, 3)], data, length=60)
        s = run(g)["resources"]["S"]
        self.assertAlmostEqual(s["busy_cost"], 30)
        self.assertAlmostEqual(s["idle_cost"], 3)
        self.assertAlmostEqual(s["usage_cost"], 1)


class TestCosting(unittest.TestCase):
    """Arena's cost allocation: (Entity.HoldCostRate + busy rates of held resources) * time,
    into the category of the activity; queue waits go to Wait."""

    def test_mortgage_style_costs(self):
        # clerk $12/hour busy and idle; two applications at time 0, each reviewed for 2 hours (VA);
        # holding cost $1/hour per application
        data = {"resources": {"Clerk": {"capacity": "1", "busy_per_hour": "12", "idle_per_hour": "12"}},
                "entities": {"App": {"holding_cost": "1"}}}
        g = graph([N(1, "create", type="Constant", value="100", units="Hours", entity_type="App",
                     entities_per_arrival="2", max_arrivals="1"),
                   N(2, "process", name="Review", resources=[{"type": "Resource", "resource": "Clerk"}],
                     delay_type="Constant", value="2", units="Hours"), N(3, "dispose")],
                  [L(1, 2), L(2, 3)], data, units="hours", length="10")
        r = run(g)
        # VA: (1 + 12) * 2 = 26 each; the second waited 2 hours holding nothing: wait cost 2
        self.assertAlmostEqual(r["tallies"]["App.va_cost"]["average"], 26)
        self.assertAlmostEqual(r["tallies"]["App.wait_cost"]["average"], 1)
        self.assertAlmostEqual(r["tallies"]["App.TotalCost"]["average"], 27)
        self.assertAlmostEqual(r["tallies"]["Review.VACostPerEntity"]["average"], 26)
        self.assertAlmostEqual(r["tallies"]["Review.WaitCostPerEntity"]["average"], 1)
        self.assertAlmostEqual(r["tallies"]["Review.TotalCostPerEntity"]["average"], 27)
        res = r["resources"]["Clerk"]
        self.assertAlmostEqual(res["busy_cost"], 48)
        self.assertAlmostEqual(res["idle_cost"], 72)  # idle 6 of the 10 hours

    def test_held_resource_charges_a_later_delay(self):
        data = {"resources": {"M": {"capacity": "1", "busy_per_hour": "60"}}}
        g = graph([CREATE(1, 1), N(2, "process", name="A", action="Seize Delay", resources=[{"type": "Resource", "resource": "M"}],
                                   delay_type="Constant", value="30", units="Minutes", allocation="Non-Value Added"),
                   N(3, "process", name="B", action="Delay Release", resources=[{"type": "Resource", "resource": "M"}],
                     delay_type="Constant", value="15", units="Minutes", allocation="Transfer"), N(4, "dispose")],
                  [L(1, 2), L(2, 3), L(3, 4)], data, length="100")
        r = run(g)
        self.assertAlmostEqual(r["tallies"]["Part.nva_cost"]["average"], 30)
        self.assertAlmostEqual(r["tallies"]["Part.tran_cost"]["average"], 15)


class TestDecide(unittest.TestCase):
    def test_two_way_chance(self):
        g = graph([CREATE(1, 20000), N(2, "decide", percent_true="30"),
                   N(3, "record", type="Count", counter_name="t"), N(4, "dispose")],
                  [L(1, 2), L(2, 3, "true"), L(2, 4, "false"), L(3, 4)], length=100000)
        self.assertAlmostEqual(run(g)["counters"]["t"] / 20000, 0.30, delta=0.012)

    def test_percent_true_expression(self):
        # Arena: Percent True is an expression; here it comes from an attribute set per entity
        g = graph([CREATE(1, 20000), N(2, "assign", assignments=[{"type": "Attribute", "attribute": "pt",
                                                                   "value": "(MOD(Entity.SerialNumber, 2) == 0) * 80"}]),
                   N(3, "decide", percent_true="pt"),
                   N(4, "record", type="Count", counter_name="t"), N(5, "dispose")],
                  [L(1, 2), L(2, 3), L(3, 4, "true"), L(3, 5, "false"), L(4, 5)], length=100000)
        self.assertAlmostEqual(run(g)["counters"]["t"] / 20000, 0.40, delta=0.012)

    def test_priority_expression_from_attribute(self):
        # two Process modules wait for S; Priority "Other" = an attribute. The lower value goes first,
        # whichever module it waits in
        def proc(i, name):
            return N(i, "process", name=name, priority="Other", priority_expr="urg",
                     resources=[{"type": "Resource", "resource": "S"}], delay_type="Constant", value="1", units="Minutes")
        g = graph([CREATE(1, 1, entity_type="Hog"),
                   N(2, "process", name="Hog", resources=[{"type": "Resource", "resource": "S"}], delay_type="Constant",
                     value="10", units="Minutes"), N(3, "dispose"),
                   CREATE(4, 1, first_creation="1", entity_type="A"),
                   N(5, "assign", assignments=[{"type": "Attribute", "attribute": "urg", "value": "5"}]), proc(6, "PA"),
                   CREATE(7, 1, first_creation="2", entity_type="B"),
                   N(8, "assign", assignments=[{"type": "Attribute", "attribute": "urg", "value": "-3"}]), proc(9, "PB")],
                  [L(1, 2), L(2, 3), L(4, 5), L(5, 6), L(6, 3), L(7, 8), L(8, 9), L(9, 3)], RES(S=1))
        r = run(g)
        self.assertAlmostEqual(r["tallies"]["PB.WaitTimePerEntity"]["average"], 8)   # -3 counts as 0: first
        self.assertAlmostEqual(r["tallies"]["PA.WaitTimePerEntity"]["average"], 10)

    def test_n_way_condition_first_true_wins(self):
        g = graph([CREATE(1, 10), N(2, "assign", assignments=[{"type": "Attribute", "attribute": "x",
                                                                "value": "Entity.SerialNumber"}]),
                   N(3, "decide", type="N-way by Condition", conditions=[
                       {"if_type": "Attribute", "named": "x", "is": "<=", "value": "3"},
                       {"if_type": "Attribute", "named": "x", "is": "<=", "value": "7"}]),
                   N(4, "record", type="Count", counter_name="c1"), N(5, "record", type="Count", counter_name="c2"),
                   N(6, "record", type="Count", counter_name="ce"), N(7, "dispose")],
                  [L(1, 2), L(2, 3), L(3, 4, "1"), L(3, 5, "2"), L(3, 6, "else"), L(4, 7), L(5, 7), L(6, 7)])
        c = run(g)["counters"]
        self.assertEqual((c["c1"], c["c2"], c["ce"]), (3, 4, 3))

    def test_entity_type_condition(self):
        g = graph([CREATE(1, 4, entity_type="A"), CREATE(2, 6, entity_type="B"),
                   N(3, "decide", type="2-way by Condition", if_type="Entity Type", named="B"),
                   N(4, "record", type="Count", counter_name="b"), N(5, "dispose")],
                  [L(1, 3), L(2, 3), L(3, 4, "true"), L(3, 5, "false"), L(4, 5)])
        self.assertEqual(run(g)["counters"]["b"], 6)


class TestBatchSeparate(unittest.TestCase):
    def test_permanent_batch_counts(self):
        g = graph([CREATE(1, 10), N(2, "batch", batch_size="3", type="Permanent"),
                   N(3, "record", type="Count", counter_name="out"), N(4, "dispose")],
                  [L(1, 2), L(2, 3), L(3, 4)])
        r = run(g)
        self.assertEqual(r["counters"]["out"], 3)
        self.assertEqual(r["queues"]["batch 2.Queue"]["number_waiting"]["final"], 1)

    def test_temporary_batch_split_restores_members(self):
        g = graph([CREATE(1, 9), N(2, "batch", batch_size="3", type="Temporary"),
                   N(3, "record", type="Count", counter_name="groups"),
                   N(4, "separate", type="Split Existing Batch"),
                   N(5, "record", type="Count", counter_name="members"), N(6, "dispose")],
                  [L(1, 2), L(2, 3), L(3, 4), L(4, 5, "original"), L(5, 6)])
        r = run(g)
        self.assertEqual((r["counters"]["groups"], r["counters"]["members"]), (3, 9))
        self.assertEqual(r["entities"]["out"]["Part"], 9)

    def test_batch_sum_criterion(self):
        g = graph([CREATE(1, 4), N(2, "assign", assignments=[{"type": "Variable", "variable": "n", "value": "n + 1"},
                                                             {"type": "Attribute", "attribute": "w", "value": "n"}]),
                   N(3, "batch", batch_size="2", save_criterion="Sum"),
                   N(4, "record", type="Expression", tally_name="w", value="w"), N(5, "dispose")],
                  [L(1, 2), L(2, 3), L(3, 4), L(4, 5)])
        t = run(g)["tallies"]["w"]
        self.assertEqual((t["min"], t["max"]), (3, 7))  # 1+2, 3+4

    def test_duplicates(self):
        g = graph([CREATE(1, 5), N(2, "separate", duplicates="2"),
                   N(3, "record", type="Count", counter_name="dup"), N(4, "dispose")],
                  [L(1, 2), L(2, 4, "original"), L(2, 3, "duplicate"), L(3, 4)])
        r = run(g)
        self.assertEqual(r["counters"]["dup"], 10)
        g["nodes"][2]["props"] = {"name": "dup", "type": "Expression", "tally_name": "sn", "value": "Entity.SerialNumber"}
        self.assertEqual(run(g)["tallies"]["sn"]["average"], 3)  # duplicates keep the original's serial number
        self.assertEqual(r["entities"]["out"]["Part"], 15)


class TestAssignRecord(unittest.TestCase):
    def test_assignments_run_in_order(self):
        g = graph([CREATE(1, 1), N(2, "assign", assignments=[
                       {"type": "Variable", "variable": "v", "value": "2"},
                       {"type": "Attribute", "attribute": "a", "value": "v * 10"},
                       {"type": "Variable", "variable": "v", "value": "a + v"}]),
                   N(3, "record", type="Expression", tally_name="v", value="v"), N(4, "dispose")],
                  [L(1, 2), L(2, 3), L(3, 4)])
        self.assertEqual(run(g)["tallies"]["v"]["average"], 22)

    def test_names_with_spaces(self):
        # Arena allows spaces in symbol names, e.g. the attribute "Total Reworks"
        g = graph([CREATE(1, 3), N(2, "assign", assignments=[
                       {"type": "Attribute", "attribute": "Total Reworks", "value": "Total Reworks + 2"},
                       {"type": "Variable", "variable": "Grand Total", "value": "Grand Total + Total Reworks"}]),
                   N(3, "record", type="Expression", tally_name="Reworks per Job", value="Total Reworks"),
                   N(4, "record", type="Expression", tally_name="gt", value="Grand Total"), N(5, "dispose")],
                  [L(1, 2), L(2, 3), L(3, 4), L(4, 5)])
        r = run(g)
        self.assertEqual(r["tallies"]["Reworks per Job"]["average"], 2)
        self.assertEqual(r["tallies"]["gt"]["max"], 6)

    def test_capacity_cut_while_busy_like_alter(self):
        # 2 units, both busy for 10 minutes; at 5 MR(S) = MR(S) - 1 and at 6 MR(S) = MR(S) + 1.
        # Arena: MR is 1 at once (not 2 until a release), so the increase brings it back to 2, not 3.
        g = graph([CREATE(1, 2, value="0.0001"), N(2, "process", name="P", resources=[{"type": "Resource", "resource": "S"}],
                                                   delay_type="Constant", value="10", units="Minutes"), N(3, "dispose"),
                   CREATE(4, 1, first_creation="5", entity_type="Ctl"),
                   N(5, "assign", assignments=[{"type": "Other", "other": "MR(S)", "value": "MR(S) - 1"}]),
                   N(6, "record", type="Expression", tally_name="mr5", value="MR(S)"),
                   N(7, "process", name="Wait1", action="Delay", delay_type="Constant", value="1", units="Minutes"),
                   N(8, "assign", assignments=[{"type": "Other", "other": "MR(S)", "value": "MR(S) + 1"}]),
                   N(9, "record", type="Expression", tally_name="mr6", value="MR(S)"), N(10, "dispose")],
                  [L(1, 2), L(2, 3), L(4, 5), L(5, 6), L(6, 7), L(7, 8), L(8, 9), L(9, 10)], RES(S=2), length="30")
        r = run(g)
        self.assertEqual((r["tallies"]["mr5"]["average"], r["tallies"]["mr6"]["average"]), (1, 2))

    def test_record_types(self):
        g = graph([CREATE(1, 5, value="2"),
                   N(2, "assign", assignments=[{"type": "Attribute", "attribute": "t0", "value": "TNOW"}]),
                   N(3, "process", name="P", action="Delay", delay_type="Constant", value="3", units="Minutes"),
                   N(4, "record", type="Time Interval", attribute="t0", tally_name="ti"),
                   N(5, "record", type="Time Between", tally_name="tb"),
                   N(6, "record", type="Count", value="2", counter_name="c"),
                   N(7, "record", type="Expression", value="Entity.SerialNumber", tally_name="sn"),
                   N(8, "dispose", record_stats=False)],
                  [L(1, 2), L(2, 3), L(3, 4), L(4, 5), L(5, 6), L(6, 7), L(7, 8)])
        r = run(g)
        self.assertAlmostEqual(r["tallies"]["ti"]["average"], 3)
        self.assertAlmostEqual(r["tallies"]["tb"]["average"], 2)
        self.assertEqual(r["tallies"]["tb"]["observations"], 4)  # first entity only starts the clock
        self.assertEqual(r["counters"]["c"], 10)
        self.assertAlmostEqual(r["tallies"]["sn"]["average"], 3)
        self.assertNotIn("Part.TotalTime", r["tallies"])

    def test_dispose_entity_statistics(self):
        g = graph([CREATE(1, 4, value="1"), N(2, "process", name="P", action="Delay", delay_type="Constant", value="2",
                                              units="Minutes", allocation="Non-Value Added"), N(3, "dispose")],
                  [L(1, 2), L(2, 3)])
        r = run(g)
        self.assertAlmostEqual(r["tallies"]["Part.TotalTime"]["average"], 2)
        self.assertEqual(r["entities"]["out"]["Part"], 4)


class TestDataModules(unittest.TestCase):
    def queue_order(self, ranking, attribute=""):
        data = {"queues": {"P.Queue": {"type": ranking, "attribute": attribute}}}
        g = graph([CREATE(1, 4, value="0.001"),
                   N(2, "assign", assignments=[{"type": "Attribute", "attribute": "k", "value": "MOD(Entity.SerialNumber * 3, 4)"}]),
                   N(3, "process", name="P", resources=[{"type": "Resource", "resource": "S"}],
                     delay_type="Constant", value="1", units="Minutes"),
                   N(4, "assign", assignments=[{"type": "Variable", "variable": "seq", "value": "seq * 10 + k"}]),
                   N(5, "dispose")], [L(1, 2), L(2, 3), L(3, 4), L(4, 5)], {**data, **RES(S=1)})
        md = to_model_dict(g); md.pop("_warnings")
        m = from_dict(md); res = m.run()
        return res.replications[0]

    def test_queue_rankings(self):
        # serials 1..4 -> k = 3, 2, 1, 0; entity 1 is served at once
        for ranking, attr, expect in [("First In First Out", "", 3210), ("Last In First Out", "", 3012),
                                      ("Lowest Attribute Value", "k", 3012), ("Highest Attribute Value", "k", 3210)]:
            g = graph([CREATE(1, 4, value="0.001"),
                       N(2, "assign", assignments=[{"type": "Attribute", "attribute": "k", "value": "MOD(Entity.SerialNumber * 3, 4)"}]),
                       N(3, "process", name="P", resources=[{"type": "Resource", "resource": "S"}],
                         delay_type="Constant", value="1", units="Minutes"),
                       N(4, "assign", assignments=[{"type": "Variable", "variable": "seq", "value": "seq * 10 + k"}]),
                       N(5, "record", type="Expression", tally_name="seq", value="seq"), N(6, "dispose")],
                      [L(1, 2), L(2, 3), L(3, 4), L(4, 5), L(5, 6)],
                      {"queues": {"P.Queue": {"type": ranking, "attribute": attr}}, **RES(S=1)})
            self.assertEqual(run(g)["tallies"]["seq"]["max"], expect, ranking)

    def test_queue_ranking_by_expression(self):
        # like SIMAN's HVF(expression): rank by k * 10 - serial, highest first
        g = graph([CREATE(1, 4, value="0.001"),
                   N(2, "assign", assignments=[{"type": "Attribute", "attribute": "k", "value": "MOD(Entity.SerialNumber * 3, 4)"}]),
                   N(3, "process", name="P", resources=[{"type": "Resource", "resource": "S"}],
                     delay_type="Constant", value="1", units="Minutes"),
                   N(4, "assign", assignments=[{"type": "Variable", "variable": "seq", "value": "seq * 10 + k"}]),
                   N(5, "record", type="Expression", tally_name="seq", value="seq"), N(6, "dispose")],
                  [L(1, 2), L(2, 3), L(3, 4), L(4, 5), L(5, 6)],
                  {"queues": {"P.Queue": {"type": "Lowest Attribute Value", "attribute": "10 - k * 2"}}, **RES(S=1)})
        self.assertEqual(run(g)["tallies"]["seq"]["max"], 3210)

    def test_capacity_schedule_wait_rule(self):
        # capacity 1 for 60 min, 0 for 60 min, repeating; a job started at 55 finishes its 10 minutes (Wait)
        data = {"schedules": {"Sh": {"type": "Capacity", "units": "Minutes",
                                     "durations": [{"value": "1", "duration": "60"}, {"value": "0", "duration": "60"}]}},
                "resources": {"S": {"type": "Based on Schedule", "schedule": "Sh", "schedule_rule": "Wait"}}}
        g = graph([CREATE(1, 2, value="10", first_creation="55"),
                   N(2, "process", name="P", resources=[{"type": "Resource", "resource": "S"}],
                     delay_type="Constant", value="10", units="Minutes"),
                   N(3, "record", type="Expression", tally_name="done", value="TNOW"), N(4, "dispose")],
                  [L(1, 2), L(2, 3), L(3, 4)], data, length=400)
        t = run(g)["tallies"]["done"]
        # first: 55 -> 65; the break then starts and still lasts 60 minutes (to 125); second: 125 -> 135
        self.assertEqual(t["min"], 65)
        self.assertEqual(t["max"], 135)

    def test_capacity_schedule_ignore_rule(self):
        data = {"schedules": {"Sh": {"type": "Capacity", "units": "Minutes",
                                     "durations": [{"value": "1", "duration": "60"}, {"value": "0", "duration": "60"}]}},
                "resources": {"S": {"type": "Based on Schedule", "schedule": "Sh", "schedule_rule": "Ignore"}}}
        g = graph([CREATE(1, 2, value="10", first_creation="55"),
                   N(2, "process", name="P", resources=[{"type": "Resource", "resource": "S"}],
                     delay_type="Constant", value="10", units="Minutes"),
                   N(3, "record", type="Expression", tally_name="done", value="TNOW"), N(4, "dispose")],
                  [L(1, 2), L(2, 3), L(3, 4)], data, length=400)
        t = run(g)["tallies"]["done"]
        self.assertEqual((t["min"], t["max"]), (65, 130))  # break is not delayed: next shift starts at 120

    def utilization_case(self, shifts, busy):
        """Arena help, 'Instantaneous Utilization Vs. Scheduled Utilization': two 4-hour shifts."""
        data = {"schedules": {"Sh": {"type": "Capacity", "units": "Hours", "durations": [
                    {"value": str(shifts[0]), "duration": "4"}, {"value": str(shifts[1]), "duration": "4"}]}},
                "resources": {"W": {"type": "Based on Schedule", "schedule": "Sh", "schedule_rule": "Ignore"}}}
        nodes, links = [N(9, "dispose")], []
        for i, (start, n, hours) in enumerate(busy):
            c, pr = 10 * i + 1, 10 * i + 2
            nodes += [CREATE(c, 1, entity_type="J", first_creation=str(start), units="Hours"),
                      N(pr, "process", name=f"P{i}", resources=[{"type": "Resource", "resource": "W", "quantity": str(n)}],
                        delay_type="Constant", value=str(hours), units="Hours")]
            links += [L(c, pr), L(pr, 9)]
        r = run(graph(nodes, links, data, units="hours", length="8"))["resources"]["W"]
        return r["instantaneous_utilization"], r["scheduled_utilization"], r["number_busy"], r["number_scheduled"]

    def test_arena_utilization_cases(self):
        cases = {"A": ((150, 150), [(0, 50, 8)], 1 / 3, 1 / 3), "B": ((200, 100), [(4, 100, 4)], 0.5, 1 / 3),
                 "C": ((200, 100), [(0, 50, 8)], 0.375, 1 / 3), "D": ((0, 300), [(4, 100, 4)], 1 / 6, 1 / 3)}
        for name, (shifts, busy, inst, sched) in cases.items():
            i, s, nb, ns = self.utilization_case(shifts, busy)
            self.assertAlmostEqual(i, inst, msg=name)
            self.assertAlmostEqual(s, sched, msg=name)
            self.assertAlmostEqual((nb, ns), (50, 150), msg=name)

    def test_busy_and_idle_state_times(self):
        g = graph([CREATE(1, 10, value="10"), N(2, "process", name="P", resources=[{"type": "Resource", "resource": "S"}],
                                               delay_type="Constant", value="4", units="Minutes"), N(3, "dispose")],
                  [L(1, 2), L(2, 3)], RES(S=1), length="100")
        st = run(g)["resources"]["S"]["states"]
        self.assertAlmostEqual(st["BUSY"]["standard_percent"], 40)
        self.assertAlmostEqual(st["IDLE"]["standard_percent"], 60)

    def test_hourly_capacity_day_repeats(self):
        # 24 one-hour slots: closed at night, 2 from 08:00, 3 from 10:00 to 12:00, 1 until 17:00
        day = [0] * 8 + [2, 2, 3, 3] + [1] * 5 + [0] * 7
        data = {"schedules": {"Day": {"type": "Capacity", "units": "Hours",
                                      "durations": [{"value": str(v), "duration": "1"} for v in day]}},
                "resources": {"S": {"type": "Based on Schedule", "schedule": "Day", "schedule_rule": "Ignore"}}}
        g = graph([CREATE(1, 48, value="60", first_creation="30"),
                   N(2, "record", type="Expression", tally_name="mr", value="MR(S) * 1000 + Entity.SerialNumber"),
                   N(3, "dispose")], [L(1, 2), L(2, 3)], data, length=str(48 * 60))
        r = run(g)
        # average MR over the 48 half-past readings equals the average of the day's slots
        self.assertAlmostEqual((r["tallies"]["mr"]["average"] - 24.5) / 1000, sum(day) / 24)
        self.assertAlmostEqual(r["resources"]["S"]["number_scheduled"], sum(day) / 24)
        self.assertEqual(r["tallies"]["mr"]["max"], 3000 + 36)  # 11:30 on day 2

    def test_schedule_remain_at_value(self):
        data = {"schedules": {"Ramp": {"type": "Capacity", "units": "Hours", "end_logic": "Remain at Value",
                                       "durations": [{"value": "1", "duration": "1"}, {"value": "4", "duration": "1"}]}},
                "resources": {"S": {"type": "Based on Schedule", "schedule": "Ramp"}}}
        g = graph([CREATE(1, 1, first_creation="600"), N(2, "record", type="Expression", tally_name="mr", value="MR(S)"),
                   N(3, "dispose")], [L(1, 2), L(2, 3)], data, length="700")
        self.assertEqual(run(g)["tallies"]["mr"]["average"], 4)  # repeating would give 1 at 10:00

    def test_arrival_schedule_half_hour_slots(self):
        data = {"schedules": {"Arr": {"type": "Arrival", "units": "Halfhours",
                                      "durations": [{"value": "60", "duration": "1"}, {"value": "0", "duration": "1"}]}}}
        g = graph([N(1, "create", type="Schedule", schedule="Arr", entity_type="P"),
                   N(2, "record", type="Count", counter_name="n"), N(3, "dispose")],
                  [L(1, 2), L(2, 3)], data, length=str(500 * 60))
        self.assertAlmostEqual(run(g)["counters"]["n"] / 500, 30, delta=1.5)  # 60 per hour, half of the time

    def test_variable_array_initial_values(self):
        data = {"variables": {"Tab": {"rows": "2", "columns": "3", "initial_values": "1, 2, 3, 4, 5, 6"}}}
        g = graph([CREATE(1, 1), N(2, "record", type="Expression", tally_name="x", value="Tab(2, 1) * 10 + Tab(1, 3)"),
                   N(3, "dispose")], [L(1, 2), L(2, 3)], data)
        self.assertEqual(run(g)["tallies"]["x"]["average"], 43)

    def test_resource_set_preferred_order(self):
        data = {**RES(A=1, B=1), "sets": {"Pool": {"type": "Resource", "members": "A, B"}}}
        g = graph([CREATE(1, 6, value="10"),
                   N(2, "process", name="P", resources=[{"type": "Set", "set": "Pool", "rule": "Preferred Order"}],
                     delay_type="Constant", value="1", units="Minutes"), N(3, "dispose")],
                  [L(1, 2), L(2, 3)], data, length=100)
        r = run(g)
        self.assertEqual((r["resources"]["A"]["times_used"], r["resources"]["B"]["times_used"]), (6, 0))


if __name__ == "__main__":
    unittest.main()
