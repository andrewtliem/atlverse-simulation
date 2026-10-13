import unittest

from simcore import *
from simcore import transfer as T


class TestTransporter(unittest.TestCase):
    def test_request_transport_free(self):
        # One forklift at B, velocity 2. Entity at A requests (B->A = 10 / 2 = 5),
        # transports to B (10 / 2 = 5), frees. Total time 10.
        m = Model()
        T.transporter(m, "Fork", units=1, velocity=2, distances={("A", "B"): 10}, initial_station="B")
        m.add(Create(interval=100, max_batches=1, first=0), Station(station="A"),
              T.Request(transporter="Fork"), T.Transport(transporter="Fork", destination="B"),
              Station(station="B"), T.Free(transporter="Fork"),
              TallyBlock(tally="done", value="TNOW"), Dispose())
        m.replicate(length=1000)
        t = m.run().replications[0]["tallies"]["done"]
        self.assertEqual((t["observations"], t["min"]), (1, 10.0))

    def test_waiting_for_unit(self):
        m = Model()
        T.transporter(m, "Fork", units=1, velocity=1, distances={("A", "B"): 4}, initial_station="A")
        m.add(Create(interval=1, max_batches=2, first=0), Station(station="A"),
              Queue("Wait for fork"), T.Request(transporter="Fork"),
              T.Transport(transporter="Fork", destination="B"),
              Station(station="B"), T.Free(transporter="Fork"),
              TallyBlock(tally="done", value="TNOW"), Dispose())
        m.replicate(length=1000)
        t = m.run().replications[0]["tallies"]["done"]
        # #1: 0->4. Fork freed at B at t=4; #2 requests: move B->A 4, transport 4 -> 12
        self.assertEqual((t["min"], t["max"]), (4.0, 12.0))


class TestConveyor(unittest.TestCase):
    def _model(self, kind):
        # Leader rides In -> Out (10 cells); follower (1 time unit later) rides In -> Mid
        # (5 cells) and dwells 5 there before exiting. On a non-accumulating belt the
        # follower's stop at Mid (t=6..11) halts the leader as well.
        m = Model()
        m.attribute("dest", "")
        T.conveyor(m, "Belt", segments=[("In", "Mid", 5), ("Mid", "Out", 5)], velocity=1,
                   cell_size=1, type=kind)
        m.add(Create(interval=1, max_batches=2, first=0), Station(station="In"),
              Assign(assignments=[("dest", "Entity.SerialNumber")]),
              Queue("Belt.Queue"), T.Access(conveyor="Belt", cells=1),
              Call(fn=lambda sim, e: "toOut" if e.attrs["dest"] == 1 else None),
              T.Convey(conveyor="Belt", destination="Mid"),
              T.Convey(conveyor="Belt", destination="Out", label="toOut"),
              Station(station="Mid"), Delay(duration=5), T.Exit(conveyor="Belt"),
              TallyBlock(tally="mid", value="TNOW"), Dispose(),
              Station(station="Out"), T.Exit(conveyor="Belt"),
              TallyBlock(tally="out", value="TNOW"), Dispose())
        m.replicate(length=1000)
        return m.run().replications[0]["tallies"]

    def test_accumulating(self):
        t = self._model("accumulating")
        self.assertEqual(t["out"]["min"], 10.0)   # leader is never held up
        self.assertEqual(t["mid"]["min"], 11.0)   # follower: on at 1, Mid at 6, exits 11

    def test_nonaccumulating_stops_whole_belt(self):
        t = self._model("nonaccumulating")
        self.assertEqual(t["mid"]["min"], 11.0)
        self.assertEqual(t["out"]["min"], 15.0)   # belt stopped 6..11 while follower dwelt

if __name__ == "__main__":
    unittest.main()
