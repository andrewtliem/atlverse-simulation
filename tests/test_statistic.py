"""Statistic data module (Advanced Process): Time-Persistent, Tally, Counter, Output, Frequency."""

import unittest

from test_arena_modules import CREATE, L, N, graph, run
from simcore.web.graph import GraphError, to_model_dict


def serve(i, minutes):   # one unit of S busy for `minutes` per entity
    return N(i, "process", name="Serve", action="Seize Delay Release",
             resources=[{"type": "Resource", "resource": "S", "quantity": "1"}],
             delay_type="Expression", expression=str(minutes), units="Minutes")


def model(stats, n=1000, **run_kw):
    # an arrival every 10 minutes, served for 4: S is busy 40% of the time
    return graph([CREATE(1, n, value="10"), serve(2, 4), N(3, "record", type="Count", counter_name="Done"),
                  N(4, "dispose")], [L(1, 2), L(2, 3), L(3, 4)], {"statistics": stats}, **run_kw)


class TestStatistic(unittest.TestCase):
    def test_time_persistent_and_output(self):
        r = run(model({"Busy S": {"type": "Time-Persistent", "expression": "NR(S)"},
                       "Twice": {"type": "Output", "expression": "2 * TFIN", "report_label": "Twice the end"}}))
        self.assertAlmostEqual(r["dstats"]["Busy S"]["average"], 0.4, places=6)
        self.assertEqual((r["dstats"]["Busy S"]["min"], r["dstats"]["Busy S"]["max"]), (0, 1))
        self.assertAlmostEqual(r["outputs"]["Twice the end"], 2000)   # the Report Label names it

    def test_frequency_by_value(self):
        r = run(model({"Dist": {"type": "Frequency", "expression": "NR(S)"}}, n=100))   # arrivals at 0..990
        f = r["frequencies"]["Dist"]
        self.assertAlmostEqual(f[0]["standard_percent"], 60, places=6)   # counted from time 0
        self.assertAlmostEqual(f[1]["standard_percent"], 40, places=6)
        self.assertEqual(f[1]["number"], 100)
        self.assertAlmostEqual(f[1]["avg_time"], 4)

    def test_frequency_categories_and_exclusion(self):
        cats = [{"kind": "Constant", "value": "0", "name": "Idle", "option": "Exclude"},
                {"kind": "Range", "value": "0", "high": "1", "name": "Working"}]
        r = run(model({"Dist": {"type": "Frequency", "expression": "NR(S)", "categories": cats}}))
        f = r["frequencies"]["Dist"]
        self.assertAlmostEqual(f["Working"]["standard_percent"], 40, places=6)
        self.assertIsNone(f["Idle"]["restricted_percent"])                 # excluded from the restricted base
        self.assertAlmostEqual(f["Working"]["restricted_percent"], 100, places=6)

    def test_frequency_by_resource_state(self):
        r = run(model({"S states": {"type": "Frequency", "frequency_type": "State", "resource": "S"}}))
        f = r["frequencies"]["S states"]
        self.assertAlmostEqual(f["BUSY"]["standard_percent"], 40, places=6)
        self.assertAlmostEqual(f["IDLE"]["standard_percent"], 60, places=6)

    def test_counter_limit_ends_the_run_and_initial_value(self):
        r = run(model({"Done": {"type": "Counter", "limit": "5"}}))
        self.assertEqual(r["counters"]["Done"], 5)
        self.assertAlmostEqual(r["time"], 44)            # the 5th entity leaves Serve at 40 + 4
        r = run(model({"Done": {"type": "Counter", "limit": "5", "initial_value": "3"}}))
        self.assertEqual(r["counters"]["Done"], 5)
        self.assertAlmostEqual(r["time"], 14)

    def test_tally_is_declared_and_missing_expression_is_reported(self):
        r = run(model({"Unused": {"type": "Tally"}}))
        self.assertEqual(r["tallies"]["Unused"]["observations"], 0)
        with self.assertRaises(GraphError):
            to_model_dict(model({"Bad": {"type": "Time-Persistent", "expression": ""}}))


if __name__ == "__main__":
    unittest.main()
