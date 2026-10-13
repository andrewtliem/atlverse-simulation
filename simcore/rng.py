"""Random number streams and SIMAN distributions.

Two sampling modes:

  "arena"  Arena-compatible sampling:
           - Uniforms: L'Ecuyer MRG32k3a (RngStreams) with package seed 12345 x 6.
             Stream k is the k-th RngStreams stream (2^127 apart); before every
             replication after the first, each stream moves to its next substream
             (2^76 apart). Arena normalises with 1/m1 rather than 1/(m1+1).
           - If the model defines SEEDS, streams 1..N use the legacy SIMAN
             multiplicative generator 16807 * x mod (2^31 - 1) (Schrage), u = x / 2^31,
             with the reinitialisation options No / Yes / Common / Antithetic.
           - Classic fast approximations: Beasley-Springer inverse normal (AS 111),
             Burr / Weibull approximations of the gamma, normal-approximation Poisson
             for large means, ...
  "exact"  Same streams, but statistically exact samplers (Marsaglia-Tsang gamma,
           Box-Muller normal, exact Poisson, ...).

With `disable_randomness`, every distribution returns its mean (Arena's
"randomness disabled" switch) and raw uniforms return 0.5.
"""

from __future__ import annotations

import math
from typing import Sequence

# --- MRG32k3a -----------------------------------------------------------------
_M1 = 4294967087
_M2 = 4294944443
_A12, _A13N = 1403580, 810728
_A21, _A23N = 527612, 1370589
_NORM_REF = 1.0 / (_M1 + 1)        # RngStreams reference
_NORM_ARENA = 1.0 / _M1            # Arena-compatible: 2.328306549837829e-10

_A1 = ((0, 1, 0), (0, 0, 1), (_M1 - _A13N, _A12, 0))
_A2 = ((0, 1, 0), (0, 0, 1), (_M2 - _A23N, 0, _A21))


def _matmul(a, b, m):
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) % m for j in range(3)) for i in range(3))


def _matpow2(a, e, m):
    for _ in range(e):
        a = _matmul(a, a, m)
    return a


def _matvec(a, s, m):
    return [sum(a[i][j] * s[j] for j in range(3)) % m for i in range(3)]


# Substream (2^76) and stream (2^127) jumps, computed rather than transcribed.
_A1P76, _A2P76 = _matpow2(_A1, 76, _M1), _matpow2(_A2, 76, _M2)
_A1P127, _A2P127 = _matpow2(_A1, 127, _M1), _matpow2(_A2, 127, _M2)

PACKAGE_SEED = (12345,) * 6


class MRG32k3a:
    """One RngStreams stream: Cg (current), Bg (substream start), Ig (stream start)."""

    def __init__(self, seed: Sequence[int] | int = PACKAGE_SEED, norm: float = _NORM_ARENA) -> None:
        if isinstance(seed, int):
            seed = [(seed * (i + 1)) % (_M1 - 1) + 1 for i in range(3)] + \
                   [(seed * (i + 7)) % (_M2 - 1) + 1 for i in range(3)]
        self.ig = list(seed[:6])
        self.bg = self.ig[:]
        self.cg = self.ig[:]
        self.norm = norm
        self.anti = False

    def next(self) -> float:
        c = self.cg
        p1 = (_A12 * c[1] - _A13N * c[0]) % _M1
        p2 = (_A21 * c[5] - _A23N * c[3]) % _M2
        self.cg = [c[1], c[2], p1, c[4], c[5], p2]
        z = p1 - p2 if p1 > p2 else p1 - p2 + _M1
        u = z * self.norm
        return 1.0 - u if self.anti else u

    def reset_start_stream(self) -> None:
        self.bg = self.ig[:]
        self.cg = self.ig[:]

    def reset_start_substream(self) -> None:
        self.cg = self.bg[:]

    def reset_next_substream(self) -> None:
        self.bg = _matvec(_A1P76, self.bg[:3], _M1) + _matvec(_A2P76, self.bg[3:], _M2)
        self.cg = self.bg[:]

    # backwards-compatible helpers
    def jump_substream(self, k: int = 1) -> None:
        for _ in range(k):
            self.reset_next_substream()

    def reset(self) -> None:
        self.reset_start_stream()


def mrg_stream_seed(k: int, package_seed: Sequence[int] = PACKAGE_SEED) -> list[int]:
    """Initial state of RngStreams stream k (1-based)."""
    s = list(package_seed)
    for _ in range(k - 1):
        s = _matvec(_A1P127, s[:3], _M1) + _matvec(_A2P127, s[3:], _M2)
    return s


# --- legacy SIMAN generator --------------------------------------------------------------

_LCG_M = 2147483647
_COMMON_MULT = 934 * 203 * 551  # 104470702: seed jump between replications for "Common"
DEFAULT_SEEDS = (14561, 25971, 31131, 22553, 12121, 32323, 19991, 18765, 14327, 32535)


class LegacyStream:
    """16807 multiplicative generator with SIMAN SEEDS semantics.

    `initial` carries the antithetic flag in its sign."""

    def __init__(self, seed: int, reinit: str = "no") -> None:
        self.initial = int(seed)
        self.current = abs(int(seed))
        self.reinit = reinit.lower()

    def next(self) -> float:
        x = self.current
        x = 16807 * (x % 127773) - 2836 * (x // 127773)  # Schrage's method, no overflow
        if x < 0:
            x += _LCG_M
        self.current = x
        if self.initial < 0:
            x = _LCG_M - x
        return x * 4.656612875e-10

    def begin_replication(self, rep: int) -> None:
        """rep is 1-based: reinitialise the stream for a new replication (No/Yes/Common/Antithetic)."""
        if rep == 1:
            self.current = abs(self.initial)
            return
        opt = self.reinit
        if opt == "yes":
            self.current = abs(self.initial)
        elif opt == "common":
            self.initial = (abs(self.initial) * _COMMON_MULT) % _LCG_M
            self.current = abs(self.initial)
        elif opt == "antithetic":
            if rep % 2 == 1:
                self.initial = -self.initial
                self.current = abs(self.initial)
            else:
                start = abs(self.initial)
                self.initial = -self.current
                self.current = start


class Stream:
    """User-visible stream wrapper exposing u()."""

    def __init__(self, gen, disabled: bool = False) -> None:
        self.gen = gen
        self.disabled = disabled

    def u(self) -> float:
        return 0.5 if self.disabled else self.gen.next()

    def begin_replication(self, rep: int) -> None:
        g = self.gen
        if isinstance(g, LegacyStream):
            g.begin_replication(rep)
        elif rep > 1:
            g.reset_next_substream()


class Streams:
    """Stream table. seeds: {stream: (seed, reinit)} switches to the legacy generator."""

    def __init__(self, seeds: dict[int, tuple[int, str]] | None = None, disabled: bool = False) -> None:
        self.seeds = dict(seeds or {})
        self.disabled = disabled
        self.rep = 1
        self._s: dict[int, Stream] = {}
        if self.seeds:
            n = max(10, max(self.seeds))
            for k in range(1, n + 1):
                seed, reinit = self.seeds.get(k, (DEFAULT_SEEDS[k - 1] if k <= 10 else 0, "no"))
                if seed:
                    self._s[k] = Stream(LegacyStream(seed, reinit), disabled)

    def __getitem__(self, k: int) -> Stream:
        k = int(k)
        s = self._s.get(k)
        if s is None:
            if self.seeds:
                raise ValueError(f"random number stream {k} is not defined in SEEDS")
            if k <= 0:
                raise ValueError(f"invalid random number stream {k}")
            g = MRG32k3a(mrg_stream_seed(k))
            for _ in range(self.rep - 1):  # streams created mid-run catch up
                g.reset_next_substream()
            s = self._s[k] = Stream(g, self.disabled)
        return s

    def begin_replication(self, rep: int) -> None:
        """rep is 1-based."""
        self.rep = rep
        for s in self._s.values():
            s.begin_replication(rep)


# --- Distributions -----------------------------------------------------------------------
# All take the Stream last. `mode` selects Arena-compatible or exact algorithms.

DEFAULT_STREAM = 10


class DistError(ValueError):
    pass


def _gamma_fn_arena(x1: float) -> float:
    """Gamma(x1) for x1 >= 1 by recursion down to [1, 2) and a polynomial there."""
    g = 1.0
    d = x1
    if d != 1.0:
        while d > 2.0:
            d -= 1.0
            g *= d
        if d < 2.0:
            x = d - 1.0
            g *= (((((((0.2548205 - x * 0.0514993) * x - 0.5684729) * x + 0.8328212) * x
                     - 0.8764218) * x + 0.985854) * x - 0.5711017) * x + 1.0)
    return g


class Sampler:
    def __init__(self, mode: str = "arena", disabled: bool = False) -> None:
        if mode not in ("arena", "exact"):
            raise ValueError("mode must be 'arena' or 'exact'")
        self.mode = mode
        self.disabled = disabled
        self._burr_cache: dict[float, tuple] = {}

    # --- continuous ----------------------------------------------------------------
    def expo(self, mean, s):
        if mean <= 0:
            raise DistError("EXPO mean must be positive")
        if self.disabled:
            return mean
        return -mean * math.log(s.u())

    def unif(self, lo, hi, s):
        if hi < lo:
            raise DistError("UNIF max < min")
        if self.disabled:
            return (lo + hi) * 0.5
        return (hi - lo) * s.u() + lo

    def tria(self, lo, mode, hi, s):
        if mode < lo or hi < mode:
            raise DistError("TRIA requires min <= mode <= max")
        if self.disabled:
            return (lo + mode + hi) / 3.0
        r = hi - lo
        u = s.u()
        if lo < mode < hi:
            if u - (mode - lo) / r > 0.0:
                return hi - math.sqrt((1.0 - u) * r * (hi - mode))
            return math.sqrt(u * r * (mode - lo)) + lo
        if mode == hi:
            return math.sqrt(u) * r + lo
        if mode == lo:
            return hi - math.sqrt(1.0 - u) * r
        return lo

    def norm(self, mean, sd, s):
        if sd <= 0:
            return 0.0 if self.mode == "arena" else mean
        if self.disabled:
            return mean
        if self.mode == "exact":
            u1, u2 = s.u(), s.u()
            return mean + sd * math.sqrt(-2.0 * math.log(u1)) * math.cos(2 * math.pi * u2)
        # Beasley-Springer (Applied Statistics AS 111) inverse normal, one uniform.
        u = s.u()
        q = u - 0.5
        if abs(q) < 0.42:
            r = q * q
            z = q * (((-25.44106049637 * r + 41.39119773534) * r - 18.61500062529) * r + 2.50662823884) / \
                ((((3.13082909833 * r - 21.06224101826) * r + 23.08336743743) * r - 8.4735109309) * r + 1.0)
            return z * sd + mean
        r = 1.0 - u if q > 0 else u
        if r <= 0:
            return mean
        r = math.sqrt(-math.log(r))
        z = (((2.32121276858 * r + 4.85014127135) * r - 2.29796479134) * r - 2.78718931138) / \
            ((1.63706781897 * r + 3.54388924762) * r + 1.0)
        if q < 0:
            z = -z
        return z * sd + mean

    def logn(self, mean, sd, s):
        if mean <= 0 or sd <= 0:
            raise DistError("LOGN parameters must be positive")
        if self.disabled:
            return mean
        sigma2 = math.log((sd / mean) ** 2 + 1.0)
        mu = math.log(mean) - sigma2 * 0.5
        return math.exp(self.norm(mu, math.sqrt(sigma2), s))

    def gamm(self, beta, alpha, s):
        """GAMM(Beta = scale, Alpha = shape)."""
        if beta <= 0 or alpha <= 0:
            raise DistError("GAMM parameters must be positive")
        if self.disabled:
            return beta * alpha
        if self.mode == "exact":
            return beta * self._gamma_mt(alpha, s)
        if alpha < 1.5:
            # Weibull approximation with fitted shape c(alpha), matched mean.
            c = ((((alpha * 0.97279251 - 3.95097728) * alpha + 6.00914764) * alpha - 4.34611961)
                 * alpha + 2.10299768) * alpha + 0.2177
            g = _gamma_fn_arena(1.0 / c + 1.0)
            lam = (g / (beta * alpha)) ** c
            return (-math.log(s.u()) / lam) ** (1.0 / c)  # = beta*alpha/g * (-ln u)^(1/c)
        a, b, mean, sd = self._burr(alpha)
        u = min(s.u(), 0.999999)
        x = ((1.0 - u) ** (-1.0 / a) - 1.0) ** (1.0 / b)
        return ((x - mean) * math.sqrt(alpha) / sd + alpha) * beta

    def _burr(self, alpha):
        """Burr XII parameters (k, c) approximating a gamma shape, and the Burr mean/sd."""
        hit = self._burr_cache.get(alpha)
        if hit:
            return hit
        x = alpha
        if x >= 5000.0:
            k, c = 6.1578411, 4.873702
        elif x >= 100.0:
            k = ((7.2018e-12 * x - 6.072e-08) * x + 0.00016757) * x + 5.93774
            c = ((x * 7.6775e-11 - 6.839e-07) * x + 0.0017123) * x + 3.81189
        elif x >= 10.0:
            k = (((5.06417e-07 * x - 0.000106345) * x + 0.007613387) * x - 0.23164737) * x + 8.6961632
            c = (((3.714831e-05 - x * 1.68262e-07) * x - 0.00294484) * x + 0.1136208) * x + 1.6796465
        elif x >= 2.0:
            k = math.exp((0.40668 - 0.01323 * x) * x + 3.3814 - 1.81468 * math.log(x))
            c = ((0.001333397 * x - 0.03645654) * x + 0.41672355) * x + 0.70137167
        else:
            k = math.exp((0.40668 - 0.01323 * x) * x + 3.3814 - 1.81468 * math.log(x))
            c = ((0.0018353 * x - 0.046124) * x + 0.47358) * x + 0.603061
        lg = math.lgamma
        mean = math.exp(lg(1.0 / c) + lg((k * c - 1.0) / c) - lg(k)) / c
        m2 = math.exp(lg(2.0 / c) + lg((k * c - 2.0) / c) - lg(k)) * 2.0 / c
        sd = math.sqrt(m2 - mean * mean)
        self._burr_cache[alpha] = (k, c, mean, sd)
        return self._burr_cache[alpha]

    def _gamma_mt(self, alpha, s):
        if alpha < 1:
            return self._gamma_mt(alpha + 1, s) * s.u() ** (1 / alpha)
        d = alpha - 1 / 3
        c = 1 / math.sqrt(9 * d)
        while True:
            x = self.norm(0.0, 1.0, s) if self.mode == "exact" else math.sqrt(-2 * math.log(s.u())) * math.cos(2 * math.pi * s.u())
            v = (1 + c * x) ** 3
            if v <= 0:
                continue
            if math.log(s.u()) < 0.5 * x * x + d - d * v + d * math.log(v):
                return d * v

    def erla(self, mean, k, s):
        k = int(k)
        if mean <= 0 or k <= 0:
            raise DistError("ERLA parameters must be positive")
        if self.disabled:
            return k * mean
        if self.mode == "exact":
            p = 1.0
            for _ in range(k):
                p *= s.u()
            return -mean * math.log(p)
        return self.gamm(mean, float(k), s)

    def beta(self, b, a, s):
        """BETA(Beta, Alpha) = G(Beta) / (G(Beta) + G(Alpha)) with unit-scale gammas."""
        if b <= 0 or a <= 0:
            raise DistError("BETA parameters must be positive")
        if self.disabled:
            return b / (a + b)
        x = self.gamm(1.0, b, s)
        y = self.gamm(1.0, a, s)
        return x / (y + x)

    def weib(self, beta, alpha, s):
        """WEIB(Beta = scale, Alpha = shape)."""
        if beta <= 0 or alpha <= 0:
            raise DistError("WEIB parameters must be positive")
        if self.disabled:
            return beta / alpha * math.exp(math.lgamma(1.0 / alpha))
        return (-math.log(s.u())) ** (1.0 / alpha) * beta

    def johnson(self, gamma, delta, lam, xi, s):
        """JOHN(Gamma, Delta, Lambda, Xi): Delta > 0 bounded (SB), Delta < 0 unbounded (SU)."""
        if lam <= 0:
            raise DistError("JOHN lambda must be positive")
        if self.disabled:
            if delta < 0:
                return xi - math.sinh(gamma / delta) * lam * math.exp(1 / (2 * delta * delta))
            return lam / (math.exp(gamma / delta) + 1.0) + xi
        y = (self.norm(0.0, 1.0, s) - gamma) / abs(delta)
        if delta < 0:
            return (math.exp(y) - math.exp(-y)) * 0.5 * lam + xi
        return 1.0 / (math.exp(-y) + 1.0) * lam + xi

    # --- discrete ----------------------------------------------------------------------
    def pois(self, mean, s):
        if mean <= 0:
            raise DistError("POIS mean must be positive")
        if self.disabled:
            return mean
        if self.mode == "arena" and mean > 12.0:
            while True:
                x = self.norm(mean, math.sqrt(mean), s)
                k = int(x + 0.5) if x >= 0 else int(x - 0.5)
                if k >= 0:
                    return float(k)
        u = s.u()
        p = math.exp(-mean)
        f = p
        k = 0.0
        while u >= f and k < 5000.0:
            k += 1.0
            p = mean * p / k
            f += p
        return k

    def disc(self, *args):
        *pairs, s = args
        if self.disabled:
            return sum(v * (cp - pc) for (pc, _), (cp, v) in
                       zip([(0.0, None)] + list(zip(pairs[::2], pairs[1::2]))[:-1], zip(pairs[::2], pairs[1::2])))
        u = s.u()
        prev = 0.0
        for cp, v in zip(pairs[::2], pairs[1::2]):
            if cp < prev or cp > 1:
                raise DistError("DISC cumulative probabilities must increase to at most 1")
            if u <= cp:
                return v
            prev = cp
        return 0.0

    def cont(self, *args):
        *pairs, s = args
        cps, vals = pairs[::2], pairs[1::2]
        u = 0.0 if self.disabled else s.u()
        prev = 0.0
        for i, cp in enumerate(cps):
            if cp < prev or cp > 1:
                raise DistError("CONT cumulative probabilities must increase to at most 1")
            if self.disabled:
                prev = cp
                continue
            if u <= cp:
                if i == 0:
                    return vals[0]
                return (vals[i] - vals[i - 1]) * ((u - cps[i - 1]) / (cp - cps[i - 1])) + vals[i - 1]
            prev = cp
        if self.disabled:  # mean of the piecewise-linear distribution
            return sum((cps[i] - cps[i - 1]) * (vals[i] + vals[i - 1]) / 2 for i in range(1, len(cps))) + \
                cps[0] * vals[0]
        return 0.0


NAMES = {
    "EXPO": "expo", "EX": "expo", "UNIF": "unif", "UN": "unif", "TRIA": "tria", "TR": "tria",
    "NORM": "norm", "RN": "norm", "LOGN": "logn", "RL": "logn", "GAMM": "gamm", "GA": "gamm",
    "ERLA": "erla", "ER": "erla", "BETA": "beta", "BE": "beta", "WEIB": "weib", "WE": "weib",
    "POIS": "pois", "PO": "pois", "DISC": "disc", "DP": "disc", "CONT": "cont", "CP": "cont",
    "JOHN": "johnson", "RJ": "johnson",
}
N_PARAMS = {"expo": 1, "unif": 2, "tria": 3, "norm": 2, "logn": 2, "gamm": 2, "erla": 2, "beta": 2,
            "weib": 2, "pois": 1, "johnson": 4}

# Module-level exact samplers kept for direct use: rng.expo(mean, stream), ...
_exact = Sampler("exact")
expo, unif, tria, norm, logn = _exact.expo, _exact.unif, _exact.tria, _exact.norm, _exact.logn
gamm, erla, beta, weib, pois = _exact.gamm, _exact.erla, _exact.beta, _exact.weib, _exact.pois
disc, cont, johnson = _exact.disc, _exact.cont, _exact.johnson
DISTRIBUTIONS = {k: getattr(_exact, v) for k, v in NAMES.items()}
