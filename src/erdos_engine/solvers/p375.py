r"""Erdős Problem #375 (falsifiable) -- Grimm's conjecture: if n+1, ..., n+k are
all composite then there are distinct primes p_i with p_i | n+i.

Search: for every maximal run of composites between consecutive primes up to
N, elements having a prime factor > k are assigned that factor (such a prime
divides at most one element of a run of length k); the remaining k-smooth
elements are matched to primes <= k by augmenting paths.
Independent check: Kuhn's matching on the *full* bipartite graph (all prime
divisors, no smoothness shortcut) for every run on a prefix, plus validation
of the stored assignments of the hardest runs.
Laishram and Shorey verified the conjecture for n <= 1.9e10; this solver is a
replication-scale tool.
"""
from __future__ import annotations

import bisect
import time

from .. import nt
from .base import COUNTEREXAMPLE, VERIFIED_TO_BOUND, CheckReport, Result, Solver, Timer


def bipartite_match(left: list[list[int]]) -> dict[int, int] | None:
    """Kuhn's algorithm; left[i] = admissible right labels. Returns i -> label or None."""
    match_r: dict[int, int] = {}

    def try_(i: int, seen: set) -> bool:
        for r in left[i]:
            if r in seen:
                continue
            seen.add(r)
            if r not in match_r or try_(match_r[r], seen):
                match_r[r] = i
                return True
        return False

    for i in range(len(left)):
        if not try_(i, set()):
            return None
    return {i: r for r, i in match_r.items()}


def small_prime_factors(m: int, primes: list[int]) -> tuple[list[int], int]:
    fs = []
    for p in primes:
        if m % p == 0:
            fs.append(p)
            while m % p == 0:
                m //= p
    return fs, m


class Problem375(Solver):
    problem = 375
    name = "p375-grimm"
    title = "Grimm's conjecture"
    statement_tex = (r"Is it true that for any $n,k\geq 1$, if $n+1,\ldots,n+k$ are all composite then "
                     r"there are distinct primes $p_1,\ldots,p_k$ such that $p_i\mid n+i$ for "
                     r"$1\leq i\leq k$?")
    finite_kind = "falsifiable"
    tags = ("number theory", "primes")
    references = ("Grimm69", "LaishramShorey06", "erdosproblems375")
    quick_params = {"N": 200000}

    def run(self, N: int = 10**6) -> Result:
        plist = list(nt.primes_between(2, N + 2000))
        failures, hard = [], []
        runs = smooth_total = 0
        with Timer() as t:
            for p, q in zip(plist, plist[1:]):
                if p > N:
                    break
                k = q - p - 1
                if k < 2:
                    continue
                runs += 1
                small = plist[:bisect.bisect_right(plist, k)]
                left, elems = [], []
                for m in range(p + 1, q):
                    fs, rest = small_prime_factors(m, small)
                    if rest == 1:  # k-smooth: must use a prime <= k
                        left.append(fs)
                        elems.append(m)
                smooth_total += len(elems)
                if not elems:
                    continue
                match = bipartite_match(left)
                if match is None:
                    failures.append([p, q])
                elif len(elems) >= 2:
                    hard.append({"run": [p, q], "assign": {str(elems[i]): r for i, r in match.items()}})
        cert = {"N": N, "runs": runs, "smooth_elements": smooth_total, "failures": failures,
                "hard_runs": hard[:500], "hard_run_count": len(hard)}
        if failures:
            return self._result(COUNTEREXAMPLE, {"N": N}, f"Grimm fails for the run after {failures[0][0]}",
                                cert, {"seconds": t.seconds}, float(N))
        return self._result(VERIFIED_TO_BOUND, {"N": N},
                            f"Grimm's property holds for all {runs} composite runs (length >= 2) below {N}; "
                            f"{len(hard)} runs needed a non-trivial matching.",
                            cert, {"seconds": round(t.seconds, 2)}, float(N))

    def check(self, result: Result, prefix: int = 100000) -> CheckReport:
        rep = CheckReport(True, "p375-full-kuhn")
        t0 = time.perf_counter()
        c = result.certificate
        for h in c["hard_runs"]:
            p, q = h["run"]
            used = set()
            for m_s, r in h["assign"].items():
                m = int(m_s)
                if not (p < m < q) or m % r or not nt.is_prime(r) or r in used:
                    return rep.fail(f"bad assignment in run ({p},{q}): {m}->{r}")
                used.add(r)
        rep.note(f"{len(c['hard_runs'])} stored assignments validated")
        P = min(prefix, c["N"])
        plist = list(nt.primes_between(2, P + 2000))
        n_runs = 0
        for p, q in zip(plist, plist[1:]):
            if p > P:
                break
            if q - p - 1 < 2:
                continue
            n_runs += 1
            left = [list(nt.factorize(m)) for m in range(p + 1, q)]
            if bipartite_match(left) is None and [p, q] not in c["failures"]:
                return rep.fail(f"full matching fails at run ({p},{q}) but was not reported")
        rep.note(f"full (no-shortcut) matching re-done for all {n_runs} runs below {P}")
        rep.seconds = time.perf_counter() - t0
        return rep

    def method_tex(self, result: Result) -> str:
        return (r"For a run $n+1,\ldots,n+k$ of composites, any prime $p>k$ divides at most one "
                r"element, so elements with such a factor are assigned it; the $k$-smooth elements "
                r"are matched to primes $\le k$ by augmenting paths. The check repeated the matching "
                r"on the full bipartite graph of all prime divisors.")
