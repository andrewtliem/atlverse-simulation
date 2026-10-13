import unittest

from simcore import *
from simcore import guided as G
from simcore import transfer as T


def loop_model(n_vehicles, control="start", jobs=1):
    # Line A -> B -> C, 2 zones of length 5 per link, velocity 1, point intersections.
    m = Model()
    G.network(m, "Net", links=[("L1", "A", "B", 2, 5, "bidirectional"),
                               ("L2", "B", "C", 2, 5, "bidirectional")],
              stations={"SA": "A", "SB": "B", "SC": "C"})
    G.guided_transporter(m, "AGV", "Net", units=n_vehicles, velocity=1,
                         initial_station=["SA", "SB"][:n_vehicles], control=control)
    return m


class TestGuided(unittest.TestCase):
    def test_single_vehicle_travel_time(self):
        m = loop_model(1)
        m.add(Create(interval=100, max_batches=1, first=0), Station(station="SA"),
              T.Request(transporter="AGV"), T.Transport(transporter="AGV", destination="SC"),
              Station(station="SC"), T.Free(transporter="AGV"),
              TallyBlock(tally="t", value="TNOW"), Dispose())
        m.replicate(length=1000)
        self.assertEqual(m.run().replications[0]["tallies"]["t"]["min"], 20.0)

    def test_blocked_by_parked_vehicle(self):
        # Vehicle 2 is parked on intersection B (idle). Vehicle 1 must pass through B
        # to reach C, so it waits on the last zone before B until B is free: it never is
        # within the run, so the job does not finish.
        m = loop_model(2)
        m.add(Create(interval=100, max_batches=1, first=0), Station(station="SA"),
              T.Request(transporter="AGV", unit=1), T.Transport(transporter="AGV", destination="SC"),
              Station(station="SC"), T.Free(transporter="AGV"),
              TallyBlock(tally="t", value="TNOW"), Dispose())
        m.replicate(length=1000)
        self.assertEqual(m.run().replications[0]["tallies"]["t"]["observations"], 0)

    def test_follow_behind(self):
        # Two vehicles on a one-way line; the follower is held one zone behind the leader.
        m = Model()
        G.network(m, "Net", links=[("L1", "A", "B", 4, 5, "unidirectional")],
                  stations={"SA": "A", "SB": "B", "S0": "O", "SF": "A"})
        m.network_specs["Net"]["links"].append(("L0", "O", "A", 1, 5, "unidirectional"))
        G.guided_transporter(m, "AGV", "Net", units=2, velocity=1, initial_station=["SA", "S0"])
        m.add(Create(interval=100, max_batches=1, first=0), Station(station="SA"),
              T.Request(transporter="AGV", unit=1), T.Transport(transporter="AGV", destination="SB"),
              Station(station="SB"), TallyBlock(tally="lead", value="TNOW"), Dispose(),
              Create(interval=100, max_batches=1, first=0), Station(station="S0", label="s0"),
              T.Request(transporter="AGV", unit=2), T.Transport(transporter="AGV", destination="SF"),
              Station(station="SF"), TallyBlock(tally="follow", value="TNOW"), Dispose())
        m.replicate(length=1000)
        r = m.run().replications[0]["tallies"]
        self.assertEqual(r["lead"]["min"], 20.0)
        # follower needs intersection A, which the leader frees on entering L1 zone 1 (t=0)
        self.assertEqual(r["follow"]["min"], 5.0)


if __name__ == "__main__":
    unittest.main()
