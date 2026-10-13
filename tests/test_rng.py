import math
import unittest

from simcore import rng


class TestMRG32k3a(unittest.TestCase):
    def test_reference_first_output(self):
        # RngStreams reference normalisation (1/(m1+1)); value printed by testRngStream.
        g = rng.MRG32k3a([12345] * 6, norm=rng._NORM_REF)
        self.assertAlmostEqual(g.next(), 0.127011122046577, places=14)

    def test_arena_normalisation(self):
        # Arena-compatible mode divides by m1, not m1 + 1.
        self.assertEqual(rng._NORM_ARENA, 1.0 / 4294967087)
        a = rng.MRG32k3a([12345] * 6).next()
        r = rng.MRG32k3a([12345] * 6, norm=rng._NORM_REF).next()
        self.assertAlmostEqual(a / r, (rng._M1 + 1) / rng._M1, places=12)

    def test_jump_matrices_against_known_values(self):
        # Published RngStreams constants (L'Ecuyer et al. 2002) vs computed powers.
        self.assertEqual(rng._A1P76[0], (82758667, 1871391091, 4127413238))
        self.assertEqual(rng._A2P76[0], (1511326704, 3759209742, 1610795712))
        self.assertEqual(rng._A1P127[0], (2427906178, 3580155704, 949770784))
        self.assertEqual(rng._A2P127[0], (1464411153, 277697599, 1610723613))

    def test_substreams_per_replication(self):
        s = rng.Streams()
        first = [s[10].u() for _ in range(3)]
        s.begin_replication(2)
        second = [s[10].u() for _ in range(3)]
        g = rng.MRG32k3a(rng.mrg_stream_seed(10))
        g.reset_next_substream()
        self.assertEqual(second, [g.next() for _ in range(3)])
        self.assertNotEqual(first, second)

    def test_late_stream_catches_up(self):
        s = rng.Streams()
        s.begin_replication(3)
        g = rng.MRG32k3a(rng.mrg_stream_seed(4))
        g.reset_next_substream()
        g.reset_next_substream()
        self.assertEqual(s[4].u(), g.next())


class TestLegacy(unittest.TestCase):
    def test_lcg_matches_minimal_standard(self):
        # Park-Miller: seed 1 -> 16807 after one step; 10000th value 1043618065.
        g = rng.LegacyStream(1)
        g.next()
        self.assertEqual(g.current, 16807)
        g = rng.LegacyStream(1)
        for _ in range(10000):
            g.next()
        self.assertEqual(g.current, 1043618065)

    def test_antithetic_pairs(self):
        g = rng.LegacyStream(14561, "antithetic")
        g.begin_replication(1)
        a = [g.next() for _ in range(5)]
        g.begin_replication(2)
        b = [g.next() for _ in range(5)]
        for x, y in zip(a, b):
            self.assertAlmostEqual(x + y, 2147483647 * 4.656612875e-10, places=9)
        g.begin_replication(3)
        c = [g.next() for _ in range(5)]
        self.assertNotEqual(a, c)

    def test_common_jump(self):
        g = rng.LegacyStream(14561, "common")
        g.begin_replication(1)
        g.begin_replication(2)
        self.assertEqual(g.current, 14561 * 104470702 % 2147483647)

    def test_seeds_switch_to_legacy(self):
        s = rng.Streams({3: (777, "yes")})
        self.assertIsInstance(s[3].gen, rng.LegacyStream)
        self.assertEqual(s[1].gen.initial, 14561)
        with self.assertRaises(ValueError):
            s[11]


class TestDistributions(unittest.TestCase):
    def _mean(self, mode, name, args, n=40000):
        smp = rng.Sampler(mode)
        st = rng.Stream(rng.MRG32k3a(rng.mrg_stream_seed(1)))
        f = getattr(smp, name)
        return sum(f(*args, st) for _ in range(n)) / n

    def test_means_both_modes(self):
        cases = [("expo", (2.0,), 2.0), ("unif", (1, 3), 2.0), ("tria", (1, 2, 6), 3.0),
                 ("norm", (5, 1), 5.0), ("erla", (1.5, 3), 4.5), ("gamm", (2, 3), 6.0),
                 ("gamm", (2, 0.7), 1.4), ("gamm", (1, 25), 25.0), ("weib", (2, 1), 2.0),
                 ("pois", (4,), 4.0), ("pois", (30,), 30.0), ("logn", (3, 1), 3.0),
                 ("beta", (2, 3), 0.4)]
        for mode in ("arena", "exact"):
            for name, args, mean in cases:
                with self.subTest(mode=mode, dist=name, args=args):
                    self.assertAlmostEqual(self._mean(mode, name, args) / mean, 1.0, delta=0.03)

    def test_disabled_returns_means(self):
        smp = rng.Sampler("arena", disabled=True)
        st = rng.Stream(rng.MRG32k3a(), disabled=True)
        self.assertEqual(smp.expo(3, st), 3)
        self.assertEqual(smp.tria(1, 2, 6, st), 3)
        self.assertEqual(smp.gamm(2, 3, st), 6)
        self.assertAlmostEqual(smp.weib(2, 1, st), 2)

    def test_arena_normal_one_uniform_per_sample(self):
        smp = rng.Sampler("arena")
        g = rng.MRG32k3a()
        st = rng.Stream(g)
        smp.norm(0, 1, st)
        g2 = rng.MRG32k3a()
        g2.next()
        self.assertEqual(g.cg, g2.cg)


if __name__ == "__main__":
    unittest.main()
