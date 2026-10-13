import unittest

from simcore.loader import from_dict
from simcore.web.graph import GraphError, to_model_dict
from simcore.web.server import run_graph


def N(i, t, **props):
    return {"id": str(i), "type": t, "x": 0, "y": 0, "props": {"name": props.pop("name", f"{t} {i}"), **props}}


def L(a, b, port="out"):
    return {"from": str(a), "to": str(b), "port": port}


def graph(nodes, links, data=None, **run):
    return {"name": "T", "time_units": "minutes", "run": {"replications": 1, "length": 100, **run},
            "data": data or {}, "nodes": nodes, "links": links}


def run(g):
    md = to_model_dict(g)
    md.pop("_warnings")
    return from_dict(md).run().replications[0]


class TestGraph(unittest.TestCase):
    def test_decide_two_way_condition(self):
        g = graph([N(1, "create", arrival_type="expression", interval="1", max="10", entity_type="P"),
                   N(2, "assign", assignments="k = MOD(Entity.SerialNumber, 2)"),
                   N(3, "decide", mode="2-way condition", condition="k == 1"),
                   N(4, "record", name="odd"), N(5, "record", name="even"), N(6, "dispose")],
                  [L(1, 2), L(2, 3), L(3, 4, "true"), L(3, 5, "false"), L(4, 6), L(5, 6)])
        c = run(g)["counters"]
        self.assertEqual((c["odd"], c["even"]), (5, 5))

    def test_decide_n_way_chance(self):
        g = graph([N(1, "create", arrival_type="expression", interval="1", max="4000"),
                   N(2, "decide", mode="n-way chance", branches="20\n30"),
                   N(3, "record", name="a"), N(4, "record", name="b"), N(5, "record", name="rest"),
                   N(6, "dispose")],
                  [L(1, 2), L(2, 3, "1"), L(2, 4, "2"), L(2, 5, "else"), L(3, 6), L(4, 6), L(5, 6)],
                  length=10000)
        c = run(g)["counters"]
        self.assertAlmostEqual(c["a"] / 4000, 0.2, delta=0.03)
        self.assertAlmostEqual(c["rest"] / 4000, 0.5, delta=0.03)

    def test_validation_problems(self):
        g = graph([N(1, "create"), N(2, "process", name="Dup", action="seize_delay_release"),
                   N(3, "process", name="Dup"), N(4, "route", destination="Nowhere")],
                  [L(1, 2), L(2, 3), L(3, 4)])
        with self.assertRaises(GraphError) as cm:
            to_model_dict(g)
        msgs = " | ".join(p["message"] for p in cm.exception.problems)
        self.assertIn("also used", msgs)
        self.assertIn("needs at least one resource", msgs)
        self.assertIn("Nowhere", msgs)

    def test_every_module_type_runs(self):
        data = {
            "resources": {"M": {"capacity": "1", "schedule": "Shift"}},
            "schedules": {"Shift": {"segments": "1, 50; 2, 50"}},
            "failures": {"Jam": {"resources": "M", "up": "EXPO(40)", "down": "2"}},
            "variables": {"gate": {"init": "0"}},
            "entities": {"Part": {"color": "#f00"}},
            "transporters": {"Cart": {"units": "1", "velocity": "10", "initial_station": "Dock",
                                      "distances": "Dock-Cell: 50\nCell-Out: 20"}},
            "conveyors": {"Belt": {"segments": "Cell-Out: 5", "velocity": "1"}},
        }
        nodes = [N(1, "create", entity_type="Part", mean="3", max="20"),
                 N(2, "station", station="Dock"), N(3, "request", transporter="Cart"),
                 N(4, "transport", transporter="Cart", destination="Cell"),
                 N(5, "station", station="Cell"), N(6, "free", transporter="Cart"),
                 N(7, "process", resources="M", delay="TRIA(1, 2, 3)"),
                 N(8, "seize", resources="M"), N(9, "delay", delay="0.5"), N(10, "release", resources="M"),
                 N(11, "assign", assignments="gate = 1\nsize = 2"),
                 N(12, "batch", size="2"), N(13, "separate", type="split"),
                 N(14, "separate", name="dup", type="duplicate", copies="1"),
                 N(15, "hold", mode="scan for condition", condition="gate == 1"),
                 N(16, "signal", signal="7"), N(17, "access", conveyor="Belt"),
                 N(18, "convey", conveyor="Belt", destination="Out"), N(19, "station", station="Out"),
                 N(20, "exit", conveyor="Belt"), N(21, "record", name="done"),
                 N(22, "record", name="flow", type="time_interval"), N(23, "dispose"),
                 N(24, "record", name="dups"), N(25, "dispose", name="dropDup"),
                 N(26, "create", name="Waiter", arrival_type="expression", interval="1000", max="1"),
                 N(27, "hold", name="WaitSig", mode="wait for signal", signal="7"),
                 N(28, "record", name="released"), N(29, "dispose", name="d3"),
                 N(30, "route", destination="Out", time="0")]
        links = [L(1, 2), L(2, 3), L(3, 4), L(5, 6), L(6, 7), L(7, 8), L(8, 9), L(9, 10), L(10, 11),
                 L(11, 12), L(12, 13), L(13, 14, "original"), L(14, 24, "duplicate"), L(24, 25),
                 L(14, 15, "original"), L(15, 16), L(16, 17), L(17, 18), L(19, 20), L(20, 21),
                 L(21, 22), L(22, 23), L(26, 27), L(27, 28), L(28, 29)]
        r = run(graph(nodes, links, data, length=2000))
        self.assertEqual(r["counters"]["done"], 20)
        self.assertEqual(r["counters"]["dups"], 20)
        self.assertEqual(r["counters"]["released"], 1)
        self.assertEqual(r["tallies"]["flow"]["observations"], 20)

    def test_run_graph_returns_animation(self):
        g = graph([N(1, "create", mean="2"), N(2, "process", name="Work", resources="R", delay="1"),
                   N(3, "dispose")], [L(1, 2), L(2, 3)])
        r = run_graph(g)
        kinds = {e[1] for e in r["anim"]}
        self.assertTrue({"move", "dispose", "resource"} <= kinds)
        self.assertIn("Work.TotalTime", r["report"])

    def test_old_file_format(self):
        g = {"name": "Old", "length": 50, "replications": 1, "resources": {"R": {"capacity": 1}},
             "nodes": [N(1, "create", mean="2"), N(2, "process", resource="R", delay="1"), N(3, "dispose")],
             "links": [L(1, 2), L(2, 3)]}
        self.assertIn("R", run_graph(g)["replications"][0]["resources"])


if __name__ == "__main__":
    unittest.main()
