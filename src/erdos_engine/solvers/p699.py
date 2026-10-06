r"""Erdős Problem #699 (falsifiable): for every 1 <= i < j <= n/2, is there a
prime p >= i dividing gcd(C(n,i), C(n,j))?

Search: for each n, a bitmask of the primes dividing C(n,k) is built from
Kummer's theorem (p | C(n,k) iff adding k and n-k in base p carries).
Independent check: gcd(C(n,i), C(n,j)) is computed with exact big integers
and stripped of all primes < i; the pair is good iff something > 1 remains.

Also records the exceptions to the strict variant (p > i), which Erdős and
Szekeres noted, e.g. gcd(C(28,5), C(28,14)) = 2^3 3^3 5.
"""
from __future__ import annotations

import math
import random
import time

from .. import nt
from .base import COUNTEREXAMPLE, VERIFIED_TO_BOUND, CheckReport, Result, Solver, Timer


def carries(a: int, b: int, p: int) -> bool:
    c = 0
    while a or b:
        s = a % p + b % p + c
        if s >= p:
            return True
        c = 0
        a //= p
        b //= p
    return False


def prime_masks(n: int, primes: list[int]) -> list[int]:
    """mask[k] has bit t set iff primes[t] divides C(n, k), for 0 <= k <= n//2."""
    masks = [0] * (n // 2 + 1)
    for t, p in enumerate(primes):
        if p > n:
            break
        bit = 1 << t
        for k in range(1, n // 2 + 1):
            if carries(k, n - k, p):
                masks[k] |= bit
    return masks


def check_n(n: int, primes: list[int]) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """Return (failing pairs for p >= i, failing pairs for the strict p > i)."""
    masks = prime_masks(n, primes)
    import bisect
    fails, strict = [], []
    for i in range(1, n // 2 + 1):
        ge = ~((1 << bisect.bisect_left(primes, i)) - 1)
        gt = ~((1 << bisect.bisect_right(primes, i)) - 1)
        mi_ge = masks[i] & ge
        mi_gt = masks[i] & gt
        for j in range(i + 1, n // 2 + 1):
            if not (mi_ge & masks[j]):
                fails.append((i, j))
            if not (mi_gt & masks[j]):
                strict.append((i, j))
    return fails, strict


def pair_ok_bigint(n: int, i: int, j: int, strict: bool = False) -> bool:
    g = math.gcd(math.comb(n, i), math.comb(n, j))
    for p in nt.primes_upto(i if strict else i - 1):
        while g % p == 0:
            g //= p
    return g > 1


class Problem699(Solver):
    problem = 699
    name = "p699-binomial-gcd"
    title = r"large prime factors of $\gcd\binom{n}{i},\binom{n}{j}$"
    statement_tex = (r"Is it true that for every $1\leq i<j\leq n/2$ there exists some prime $p\geq i$ "
                     r"such that \[p\mid \gcd\left(\binom{n}{i}, \binom{n}{j}\right)?\]")
    finite_kind = "falsifiable"
    tags = ("number theory", "binomial coefficients")
    references = ("ErSz78", "erdosproblems699")
    quick_params = {"N": 80}

    def run(self, N: int = 200) -> Result:
        primes = nt.primes_upto(N)
        fails, strict = [], []
        with Timer() as t:
            for n in range(2, N + 1):
                f, s = check_n(n, primes)
                fails += [(n, i, j) for i, j in f]
                strict += [(n, i, j) for i, j in s if i >= 4]
        cert = {"N": N, "failures": fails, "strict_exceptions_i_ge_4": strict}
        if fails:
            return self._result(COUNTEREXAMPLE, {"N": N}, f"Counterexample(s): {fails[:5]}", cert,
                                {"seconds": t.seconds}, float(N))
        return self._result(VERIFIED_TO_BOUND, {"N": N},
                            f"Holds for all n <= {N}. Strict-variant exceptions with i >= 4: {strict}",
                            cert, {"seconds": round(t.seconds, 2)}, float(N))

    def check(self, result: Result, full_upto: int = 60, samples: int = 3000, seed: int = 0) -> CheckReport:
        rep = CheckReport(True, "p699-bigint-gcd")
        t0 = time.perf_counter()
        c = result.certificate
        N = c["N"]
        for n, i, j in c["failures"]:
            if pair_ok_bigint(n, i, j):
                return rep.fail(f"claimed counterexample ({n},{i},{j}) is not one")
        for n, i, j in c["strict_exceptions_i_ge_4"]:
            if pair_ok_bigint(n, i, j, strict=True):
                return rep.fail(f"claimed strict exception ({n},{i},{j}) is not one")
        claimed = {tuple(x) for x in c["failures"]}
        claimed_strict = {tuple(x) for x in c["strict_exceptions_i_ge_4"]}
        for n in range(2, min(full_upto, N) + 1):
            for i in range(1, n // 2 + 1):
                for j in range(i + 1, n // 2 + 1):
                    if (not pair_ok_bigint(n, i, j)) != ((n, i, j) in claimed):
                        return rep.fail(f"disagreement at ({n},{i},{j})")
                    if i >= 4 and (not pair_ok_bigint(n, i, j, True)) != ((n, i, j) in claimed_strict):
                        return rep.fail(f"strict disagreement at ({n},{i},{j})")
        rep.note(f"every pair with n <= {min(full_upto, N)} recomputed with exact gcds")
        rng = random.Random(seed)
        for _ in range(samples):
            n = rng.randint(4, N)
            i = rng.randint(1, n // 2 - 1) if n >= 4 else 1
            j = rng.randint(i + 1, n // 2) if i < n // 2 else None
            if j is None:
                continue
            if (not pair_ok_bigint(n, i, j)) != ((n, i, j) in claimed):
                return rep.fail(f"disagreement at sampled ({n},{i},{j})")
        rep.note(f"{samples} random pairs with n <= {N} recomputed with exact gcds")
        rep.seconds = time.perf_counter() - t0
        return rep

    def method_tex(self, result: Result) -> str:
        return (r"For each $n$ we determined the set of primes dividing $\binom nk$ by Kummer's "
                r"theorem ($p\mid\binom nk$ iff adding $k$ and $n-k$ in base $p$ produces a carry), "
                r"stored as bitmasks, and tested every pair $i<j\le n/2$. The check recomputed "
                r"$\gcd(\binom ni,\binom nj)$ exactly and removed all primes $<i$.")
