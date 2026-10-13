import math
import unittest

from simcore import *


def run(m, length=100.0, reps=1):
    m.replicate(replications=reps, length=length)
    return m.run().replications[0]


class TestFlow(unittest.TestCase):
    def test_if_elseif_else(self):
        m = Model()
        m.attribute("x")
        m.add(Create(interval=1, max_batches=9),
              Assign(assignments=[("x", "MOD(Entity.SerialNumber, 3)")]),
              If(condition="x == 0"), Count(counter="zero"),
              ElseIf(condition="x == 1"), Count(counter="one"),
              Else(), Count(counter="two"),
              EndIf(), Dispose())
        c = run(m)["counters"]
        self.assertEqual((c["zero"], c["one"], c["two"]), (3, 3, 3))

    def test_nested_if_and_while(self):
        m = Model()
        m.attribute("i")
        m.add(Create(interval=1, max_batches=1),
              While(condition="i < 5"),
              Assign(assignments=[("i", "i + 1")]),
              If(condition="i .GT. 2"), Count(counter="big"), EndIf(),
              EndWhile(),
              Count(counter="done"), Dispose())
        c = run(m)["counters"]
        self.assertEqual((c["big"], c["done"]), (3, 1))

    def test_branch_with_probability(self):
        m = Model()
        m.add(Create(interval=1, max_batches=20000),
              Branch(branches=[("WITH", 0.25, "a"), ("WITH", 0.75, "b")], max_branches=1),
              Count(counter="A", label="a"), Dispose(),
              Count(counter="B", label="b"), Dispose())
        c = run(m, length=1e9)["counters"]
        self.assertAlmostEqual(c["A"] / 20000, 0.25, delta=0.015)

    def test_branch_always_duplicates(self):
        m = Model()
        m.add(Create(interval=1, max_batches=10),
              Branch(branches=[("ALWAYS", None, "a"), ("ALWAYS", None, "b")]),
              Count(counter="A", label="a"), Dispose(),
              Count(counter="B", label="b"), Dispose())
        c = run(m)["counters"]
        self.assertEqual((c["A"], c["B"]), (10, 10))


class TestResources(unittest.TestCase):
    def test_deterministic_queue(self):
        # arrivals every 1, service 2 on capacity 1: 10 arrivals finish at 2,4,...,20
        m = Model()
        m.resource("R")
        m.add(Create(interval=1, max_batches=10, first=0),
              Queue("Q"), Seize(resources=[("R", 1)]), Delay(duration=2), Release(resources=[("R", 1)]),
              TallyBlock(tally="flow", value="INT(Entity.CreateTime)"), Dispose())
        r = run(m, length=1000)
        t = r["tallies"]["flow"]
        self.assertEqual(t["observations"], 10)
        self.assertAlmostEqual(t["max"], 20 - 9)  # last entity created at 9, done at 20
        self.assertAlmostEqual(r["queues"]["Q"]["waiting_time"]["average"], sum(range(10)) / 10)

    def test_head_of_line_blocking(self):
        # Entity needing 2 units blocks a later entity needing 1 (SEIZE remarks).
        m = Model()
        m.attribute("need", 1)
        m.resource("R", capacity=2)
        order = []
        m.add(Create(interval=0.1, max_batches=3, first=0),
              Assign(assignments=[("need", "MN(Entity.SerialNumber, 2)")]),
              Queue("Q"), Seize(resources=[("R", "need")]),
              Call(fn=lambda sim, e: order.append(e.serial)),
              Delay(duration=1), Release(resources=[("R", "need")]), Dispose())
        run(m)
        self.assertEqual(order, [1, 2, 3])

    def test_capacity_schedule(self):
        m = Model()
        m.resource("R", schedule="shift")
        m.schedule("shift", [(1, 10), (0, 10)])
        m.add(Create(interval=1000, max_batches=1), Dispose())
        r = run(m, length=100)
        self.assertAlmostEqual(r["resources"]["R"]["number_scheduled"], 0.5)

    def test_failure_makes_resource_unavailable(self):
        m = Model()
        m.resource("R")
        m.failure("brk", ["R"], up=10, down=10)
        m.add(Create(interval=1000, max_batches=1), Dispose())
        r = run(m, length=100)
        self.assertAlmostEqual(r["resources"]["R"]["states"]["FAILED"]["standard_percent"], 50, delta=0.01)

    def test_select_cyclic(self):
        m = Model()
        for n in ("A", "B", "C"):
            m.resource(n)
        m.set("Workers", ["A", "B", "C"])
        m.attribute("who", "")
        m.add(Create(interval=10, max_batches=6),
              Seize(select={"set": "Workers", "rule": "CYC", "save": "who"}),
              Delay(duration=1), Release(resources=[("Workers(who)", 1)]),
              Count(counter="done"), Dispose())
        r = run(m)
        self.assertEqual([r["resources"][n]["times_used"] for n in "ABC"], [2, 2, 2])


class TestSync(unittest.TestCase):
    def test_wait_signal(self):
        m = Model()
        m.add(Create(interval=1, max_batches=5, first=0), Queue("Hold"), Wait(signal_code=7),
              TallyBlock(tally="released", value="TNOW"), Dispose(),
              Create(interval=1, max_batches=1, first=10), Signal(code=7), Dispose())
        t = run(m)["tallies"]["released"]
        self.assertEqual(t["observations"], 5)
        self.assertEqual(t["min"], 10)

    def test_group_split(self):
        m = Model()
        m.add(Create(interval=1, max_batches=6, first=0), Queue("G"), Group(quantity=3),
              Count(counter="groups"), Split(), Count(counter="members"), Dispose())
        c = run(m)["counters"]
        self.assertEqual((c["groups"], c["members"]), (2, 6))

    def test_scan(self):
        m = Model()
        m.variable("gate", 0)
        m.add(Create(interval=1, max_batches=3, first=0), Queue("S"), Scan(condition="gate == 1"),
              TallyBlock(tally="t", value="TNOW"), Dispose(),
              Create(interval=1, max_batches=1, first=5), Assign(assignments=[("gate", 1)]), Dispose())
        t = run(m)["tallies"]["t"]
        self.assertEqual((t["observations"], t["min"]), (3, 5))

    def test_match(self):
        m = Model()
        m.attribute("k")
        m.variable("nl", 0)
        m.variable("nr", 0)
        m.add(Create(interval=1, max_batches=4, first=0),
              Assign(assignments=[("nl", "nl + 1"), ("k", "nl")]), Detach(queue="L"),
              Create(interval=2, max_batches=4, first=0.5),
              Assign(assignments=[("nr", "nr + 1"), ("k", "5 - nr")]), Detach(queue="R"),
              Match(queues=[("L", "out"), ("R", None)], match_attr="k"),
              TallyBlock(tally="t", value="TNOW", label="out"), Dispose())
        t = run(m)["tallies"]["t"]
        # k=3 pairs first (L at t=2, R at t=2.5); k=1 last (R #4 arrives at t=6.5)
        self.assertEqual((t["observations"], t["min"], t["max"]), (4, 2.5, 6.5))


class TestStats(unittest.TestCase):
    def test_mm1_against_theory(self):
        m = Model()
        m.resource("S")
        m.add(Create(interval="EXPO(1)"), Queue("Q"), Seize(resources=[("S", 1)]),
              Delay(duration="EXPO(0.5)"), Release(resources=[("S", 1)]), Dispose())
        m.replicate(replications=4, length=20000, warmup=1000)
        res = m.run()
        wq = res.across("queues.Q.waiting_time.average")
        self.assertLess(abs(wq["average"] - 0.5), 3 * max(wq["half_width"], 0.02))  # rho/(mu-lambda) = 0.5
        u = res.across("resources.S.instantaneous_utilization")
        self.assertAlmostEqual(u["average"], 0.5, delta=0.02)


class TestBatching(unittest.TestCase):
    def test_combine_attributes(self):
        m = Model()
        m.attribute("w", 0.0)
        m.add(Create(interval=1, max_batches=3, first=0), Assign(assignments=[("w", "Entity.SerialNumber * 10")]),
              Queue("C"), Combine(quantity=3, save_criterion="sum", rep_type="Box"),
              TallyBlock(tally="w", value="w"), TallyBlock(tally="ct", value="Entity.CreateTime"),
              Count(counter="boxes"), Dispose())
        r = run(m)
        self.assertEqual(r["counters"]["boxes"], 1)
        self.assertEqual(r["tallies"]["w"]["min"], 60)      # 10 + 20 + 30
        self.assertEqual(r["tallies"]["ct"]["min"], 0)      # earliest member
        self.assertEqual(r["entities"]["wip"].get("Box", 0) + r["entities"]["wip"].get(None, 0), 0)

    def test_pickup_dropoff(self):
        m = Model()
        m.add(Create(interval=1, max_batches=4, first=0), Detach(queue="Dock"),
              Create(interval=100, max_batches=1, first=10), Pickup(queue="Dock", rank=1, quantity=3),
              Assign(assignments=[("ng", "NG")]), TallyBlock(tally="ng", value="ng"),
              Dropoff(rank=1, quantity=2, destination="off"),
              TallyBlock(tally="left", value="NG"), Dispose(),
              Count(counter="dropped", label="off"), Dispose())
        r = run(m)
        self.assertEqual(r["tallies"]["ng"]["min"], 3)
        self.assertEqual(r["counters"]["dropped"], 2)

    def test_pickq_shortest_queue(self):
        m = Model()
        for n in ("A", "B"):
            m.resource(n)
        m.add(Create(interval=1, max_batches=6, first=0), PickQ(queue_labels=["qa", "qb"], rule="SNQ"),
              Queue("QA", label="qa"), Seize(resources=[("A", 1)]), Delay(duration=10),
              Release(resources=[("A", 1)]), Dispose(),
              Queue("QB", label="qb"), Seize(resources=[("B", 1)]), Delay(duration=10),
              Release(resources=[("B", 1)]), Dispose())
        r = run(m, length=1000)
        self.assertEqual(r["resources"]["A"]["times_used"], 3)
        self.assertEqual(r["resources"]["B"]["times_used"], 3)


class TestControl(unittest.TestCase):
    def test_blockage_gate(self):
        m = Model()
        m.blockage("Gate", 1)
        m.add(Create(interval=1, max_batches=3, first=0), Queue("G"), Proceed(blockages=["Gate"]),
              TallyBlock(tally="t", value="TNOW"), Dispose(),
              Create(interval=100, max_batches=1, first=7), Unblock(blockage="Gate"), Dispose())
        t = run(m)["tallies"]["t"]
        self.assertEqual((t["observations"], t["min"], t["max"]), (3, 7, 7))

    def test_select_block(self):
        m = Model()
        m.resource("Fast")
        m.resource("Slow")
        m.add(Create(interval=1, max_batches=4, first=0), Queue("Q"),
              Select(seize_labels=["sf", "ss"], rule="POR"),
              Seize(resources=[("Fast", 1)], label="sf"), Delay(duration=1.5),
              Release(resources=[("Fast", 1)]), Dispose(),
              Seize(resources=[("Slow", 1)], label="ss"), Delay(duration=3),
              Release(resources=[("Slow", 1)]), Dispose())
        r = run(m)
        used = (r["resources"]["Fast"]["times_used"], r["resources"]["Slow"]["times_used"])
        self.assertEqual(sum(used), 4)
        self.assertGreater(used[0], used[1])


class TestElements(unittest.TestCase):
    def test_stateset_and_frequency(self):
        m = Model()
        m.resource("M", stateset={"BUSY": "Processing"})
        m.frequency("Queue bands", "NQ(Q)", categories=[("empty", -1, 0), ("some", 0, 100)])
        m.add(Create(interval=10, max_batches=2, first=0), Queue("Q"), Seize(resources=[("M", 1)]),
              Delay(duration=4), Release(resources=[("M", 1)]), Dispose())
        r = run(m, length=20)
        st = r["resources"]["M"]["states"]
        self.assertAlmostEqual(st["Processing"]["standard_percent"], 40.0)
        self.assertAlmostEqual(r["frequencies"]["Queue bands"]["empty"]["standard_percent"], 100.0)


class TestAdvancedHolds(unittest.TestCase):
    def test_qpick_por_serves_first_queue(self):
        # Server busy 0..5 with a "blocker". Two A's and one B wait in separate queues.
        # POR serves queue A first: A1 at 5, A2 at 10, then B at 15.
        m = Model()
        m.resource("S")
        m.attribute("kind", "")
        order = []
        m.add(Create(interval=100, max_batches=1, first=0), Seize(resources=[("S", 1)]),
              Delay(duration=5), Release(resources=[("S", 1)]), Dispose(),
              Create(interval=1, max_batches=2, first=1), Assign(assignments=[("kind", '"A"')]),
              Branch(branches=[("ALWAYS", None, "qa")]),
              Create(interval=100, max_batches=1, first=1.5), Assign(assignments=[("kind", '"B"')]),
              Branch(branches=[("ALWAYS", None, "qb")]),
              QueueBlock(queue="QA", label="qa"), QueueBlock(queue="QB", label="qb"),
              QPick(queue_labels=["qa", "qb"], rule="POR"), Seize(resources=[("S", 1)]),
              Call(fn=lambda sim, e: order.append((e.attrs["kind"], sim.now))),
              Delay(duration=5), Release(resources=[("S", 1)]), Dispose())
        run(m)
        self.assertEqual(order, [("A", 5), ("A", 10), ("B", 15)])

    def test_qpick_lnq(self):
        m = Model()
        m.resource("S")
        order = []
        m.attribute("kind", "")
        m.add(Create(interval=100, max_batches=1, first=0), Seize(resources=[("S", 1)]),
              Delay(duration=5), Release(resources=[("S", 1)]), Dispose(),
              Create(interval=1, max_batches=1, first=1), Assign(assignments=[("kind", '"A"')]),
              Branch(branches=[("ALWAYS", None, "qa")]),
              Create(interval=0.1, max_batches=2, first=1), Assign(assignments=[("kind", '"B"')]),
              Branch(branches=[("ALWAYS", None, "qb")]),
              QueueBlock(queue="QA", label="qa"), QueueBlock(queue="QB", label="qb"),
              QPick(queue_labels=["qa", "qb"], rule="LNQ"), Seize(resources=[("S", 1)]),
              Call(fn=lambda sim, e: order.append(e.attrs["kind"])),
              Delay(duration=5), Release(resources=[("S", 1)]), Dispose())
        run(m)
        self.assertEqual(order[0], "B")  # QB is longer when the server frees up

    def test_stack_diff(self):
        m = Model()
        m.add(Create(interval=100, max_batches=1, first=0), Stack(action="save"),
              Delay(duration=3, allocation="value_added"),
              TallyBlock(tally="dva", value="Diff.VATime"),
              Stack(action="destroy"), Dispose())
        self.assertEqual(run(m)["tallies"]["dva"]["min"], 3)

    def test_preempt_resumes_remaining_time(self):
        # Low-priority job seizes at 0 for 10. Urgent job preempts at 4 for 2.
        # Low job resumes at 6 with 6 left -> done at 12.
        m = Model()
        m.resource("M")
        m.add(Create(interval=100, max_batches=1, first=0), Seize(resources=[("M", 1)]),
              Delay(duration=10), Release(resources=[("M", 1)]),
              TallyBlock(tally="low", value="TNOW"), Dispose(),
              Create(interval=100, max_batches=1, first=4), Preempt(resource="M", priority=1),
              Delay(duration=2), Release(resources=[("M", 1)]),
              TallyBlock(tally="urgent", value="TNOW"), Dispose())
        r = run(m)["tallies"]
        self.assertEqual((r["urgent"]["min"], r["low"]["min"]), (6, 12))

    def test_preempt_needs_lower_priority_value(self):
        # A PREEMPT(priority 1) holder cannot be preempted by PREEMPT(priority 2).
        m = Model()
        m.resource("M")
        m.add(Create(interval=100, max_batches=1, first=0), Preempt(resource="M", priority=1),
              Delay(duration=10), Release(resources=[("M", 1)]), Dispose(),
              Create(interval=100, max_batches=1, first=4), Queue("PQ"), Preempt(resource="M", priority=2),
              TallyBlock(tally="second", value="TNOW"), Delay(duration=1), Release(resources=[("M", 1)]),
              Dispose())
        self.assertEqual(run(m)["tallies"]["second"]["min"], 10)


class TestElementsMore(unittest.TestCase):
    def test_onchange(self):
        m = Model()
        m.variable("level", 0)
        m.add(Create(interval=1, max_batches=5, first=0), Assign(assignments=[("level", "MN(TNOW, 2)")]),
              Dispose(),
              OnChange(variables=["level"], condition="level >= 1"), Count(counter="changes"), Dispose())
        # level: 0 (no change), 1, 2, 2 (no change), 2 (no change) -> changes at t=1, 2
        self.assertEqual(run(m)["counters"]["changes"], 2)

    def test_arrivals_element(self):
        m = Model()
        m.arrival("in", kind="time", time=5, batch=3)
        m.arrival("in", kind="every", time=10, every=10)
        m.add(Count(counter="arrived", label="in"), Dispose())
        # t=5 batch 3; every 10 from t=10 within length 35 -> 10, 20, 30
        self.assertEqual(run(m, length=35)["counters"]["arrived"], 6)

    def test_statics_by_station(self):
        m = Model()
        m.static("cycle", 9.0)
        m.recipe("Fast", {"cycle": 2.0}, stations=["S1"])
        m.add(Create(interval=100, max_batches=1, first=0), Station(station="S1"),
              Delay(duration="cycle"), Route(destination="S2"),
              Station(station="S2"), Delay(duration="cycle"),
              TallyBlock(tally="t", value="TNOW"), Dispose())
        self.assertEqual(run(m)["tallies"]["t"]["min"], 11.0)  # 2 at S1 + 9 default at S2

    def test_activity_areas_roll_up(self):
        m = Model()
        m.activity_area("Plant")
        m.activity_area("Cell", stations=["S1"], parent="Plant")
        m.add(Create(interval=10, max_batches=2, first=0), Station(station="S1"),
              Delay(duration=5), Route(destination="Out"), Station(station="Out"), Dispose())
        r = run(m, length=20)["activity_areas"]
        self.assertEqual((r["Cell"]["entered"], r["Plant"]["entered"]), (2, 2))
        self.assertAlmostEqual(r["Plant"]["wip_average"], 0.5)


if __name__ == "__main__":
    unittest.main()
