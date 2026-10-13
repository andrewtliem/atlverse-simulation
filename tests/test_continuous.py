import math
import unittest

from simcore import *
from simcore import continuous as C


class TestContinuous(unittest.TestCase):
    def test_exponential_decay_ode(self):
        m = Model()
        C.level(m, "S", init=1.0, rate="-S")
        C.settings(m, max_step=0.05)
        m.add(Create(interval=1000, max_batches=1), Dispose())
        m.replicate(length=2.0)
        r = m.run().replications[0]
        self.assertAlmostEqual(r["levels"]["S"], math.exp(-2), places=6)

    def test_tank_fill_detect(self):
        # Tank fills at rate 2 from 0; DETECT at level 10 (t=5) records the time and
        # empties the tank. Detections at 5, 10, 15, ...
        m = Model()
        m.variable("fill", 2.0)
        C.level(m, "Tank", init=0.0, rate="fill")
        C.cstat(m, "TankLevel", "Tank")
        C.settings(m, max_step=1.0)
        m.add(C.Detect(crossing="Tank", direction="positive", threshold=10, tolerance=1e-9),
              TallyBlock(tally="full", value="TNOW"), Assign(assignments=[("Tank", 0)]), Dispose())
        m.replicate(length=21)
        r = m.run().replications[0]
        t = r["tallies"]["full"]
        self.assertEqual(t["observations"], 4)
        self.assertAlmostEqual(t["min"], 5.0, places=6)
        self.assertAlmostEqual(t["max"], 20.0, places=6)
        self.assertAlmostEqual(r["continuous"]["TankLevel"]["average"], (4 * 25 + 1) / 21, places=3)

    def test_rate_changed_by_event(self):
        m = Model()
        m.variable("r", 1.0)
        C.level(m, "S", rate="r")
        m.add(Create(interval=1000, max_batches=1, first=3), Assign(assignments=[("r", -1)]), Dispose())
        m.replicate(length=5)
        self.assertAlmostEqual(m.run().replications[0]["levels"]["S"], 1.0, places=9)


if __name__ == "__main__":
    unittest.main()
