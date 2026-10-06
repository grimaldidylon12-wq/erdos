r"""Erdős Problem #647 (verifiable): is there n > 24 with
max_{m<n} (m + tau(m)) <= n + 2 ?

Search: a divisor-count sieve over [1, N] and a running prefix maximum.
Independent check: tau recomputed by trial-division factorisation (a
different algorithm from the additive sieve) at every n where the prefix
maximum is tight (within 3 of the threshold) plus a random sample, and the
whole computation repeated with a smallest-prime-factor sieve on a prefix.
The frontier claimed on the forum (10^22, GPU search) is far beyond what this
solver reaches; it exists to exercise the pipeline and to replicate.
"""
from __future__ import annotations

import random
import time

from .. import nt
from .base import EXAMPLE, VERIFIED_TO_BOUND, CheckReport, Result, Solver, Timer


def tau_array(N: int):
    """tau(0..N); uses numpy when available."""
    try:
        import numpy as np
    except ImportError:  # pragma: no cover
        return nt.tau_sieve(N)
    t = np.zeros(N + 1, dtype=np.int32)
    for d in range(1, N + 1):
        t[d::d] += 1
    return t


def tau_spf(N: int) -> list[int]:
    """tau via smallest-prime-factor sieve (independent second method)."""
    spf = list(range(N + 1))
    for i in range(2, int(N**0.5) + 1):
        if spf[i] == i:
            for j in range(i * i, N + 1, i):
                if spf[j] == j:
                    spf[j] = i
    t = [0] * (N + 1)
    if N >= 1:
        t[1] = 1
    for n in range(2, N + 1):
        p, m, e = spf[n], n, 0
        while m % p == 0:
            m //= p
            e += 1
        t[n] = t[m] * (e + 1)
    return t


def solutions(t, N: int) -> tuple[list[int], list[int]]:
    """(all n in [2, N] satisfying the condition, n where the slack is <= 3)."""
    best = 0
    sols, tight = [], []
    for n in range(2, N + 1):
        v = (n - 1) + int(t[n - 1])
        if v > best:
            best = v
        if best <= n + 2:
            sols.append(n)
        if best <= n + 5:
            tight.append(n)
    return sols, tight


class Problem647(Solver):
    problem = 647
    name = "p647-tau-prefix-max"
    title = r"$\max_{m<n}(m+\tau(m))\le n+2$"
    statement_tex = (r"Let $\tau(n)$ count the divisors of $n$. Is there some $n>24$ such that "
                     r"\[\max_{m<n}(m+\tau(m))\leq n+2?\]")
    finite_kind = "verifiable"
    tags = ("number theory", "divisors")
    references = ("erdosproblems647",)
    quick_params = {"N": 200000}

    def run(self, N: int = 10**6) -> Result:
        with Timer() as t:
            tau = tau_array(N)
            sols, tight = solutions(tau, N)
        big = [n for n in sols if n > 24]
        cert = {"N": N, "solutions": sols, "near_misses": [n for n in tight if n > 24][:200]}
        if big:
            return self._result(EXAMPLE, {"N": N}, f"Found n = {big[0]} > 24.", cert,
                                {"seconds": t.seconds}, float(N))
        return self._result(VERIFIED_TO_BOUND, {"N": N},
                            f"No n with 24 < n <= {N}; all solutions up to N: {sols}.",
                            cert, {"seconds": round(t.seconds, 2)}, float(N))

    def check(self, result: Result, prefix: int = 200000, samples: int = 2000, seed: int = 0) -> CheckReport:
        rep = CheckReport(True, "p647-spf-and-trial-division")
        t0 = time.perf_counter()
        c = result.certificate
        N = c["N"]
        # (1) any claimed solution: recheck literally with trial-division tau
        for n in c["solutions"]:
            if n > 5000 and result.outcome != EXAMPLE:
                return rep.fail("unexpected large solution in a verification certificate")
            if n <= 5000:
                if max((m + nt.tau(m) for m in range(1, n)), default=0) > n + 2:
                    return rep.fail(f"claimed solution {n} is not one")
        # (2) independent recomputation on a prefix with a different tau algorithm
        P = min(prefix, N)
        sols2, _ = solutions(tau_spf(P), P)
        if sols2 != [n for n in c["solutions"] if n <= P]:
            return rep.fail(f"spf-sieve recomputation disagrees on [2,{P}]")
        rep.note(f"solutions on [2,{P}] recomputed with an spf sieve: {sols2}")
        # (3) the prefix maximum beyond P: since m + tau(m) >= m + 1, the
        # maximum over m < n is at least n; a solution needs tau(n-k) <= k+2
        # for k = 1..n-1. Re-verify every recorded near miss and random n by
        # exhibiting a violating m with trial-division tau.
        rng = random.Random(seed)
        probes = list(c["near_misses"]) + [rng.randint(25, N) for _ in range(samples)]
        for n in probes:
            if n <= 24:
                continue
            for k in range(1, min(n, 5000)):
                if nt.tau(n - k) > k + 2:
                    break
            else:
                return rep.fail(f"no violating m found for n={n} within 5000 steps")
        rep.note(f"{len(probes)} values of n > 24 refuted by an explicit m with tau(m) > n+2-m")
        rep.seconds = time.perf_counter() - t0
        return rep

    def method_tex(self, result: Result) -> str:
        return (r"We computed $\tau(m)$ for all $m\le N$ by the additive divisor sieve and "
                r"maintained $M(n)=\max_{m<n}(m+\tau(m))$. The check recomputed $\tau$ with a "
                r"smallest-prime-factor sieve on an initial segment and, for sampled $n$, exhibited "
                r"an explicit $m<n$ with $m+\tau(m)>n+2$ using trial-division factorisation.")
