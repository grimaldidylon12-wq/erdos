r"""Erdős Problem #848 (decidable): is the maximum size of A ⊆ {1..N} such that
ab + 1 is never squarefree (all a, b in A, a = b allowed) attained by the
residue class 7 (mod 25)?

Sawhney proved this for all sufficiently large N, and forum work reduced the
threshold to an explicit N_0 ≈ 2.6e17, leaving a finite (but enormous) check.
This solver computes the exact maximum f(N) for small N by maximum-clique
search and compares it with |{n <= N : n ≡ 7 (mod 25)}|; it can find small-N
exceptions to the literal statement and produces the sequence f(N).

Independent check: the witness set is re-validated with trial-division
squarefreeness, and optimality is re-derived with a different exact
algorithm (Bron--Kerbosch with pivoting, tracking the maximum).
"""
from __future__ import annotations

import math
import time

from .. import nt
from .base import SEQUENCE, CheckReport, Result, Solver, Timer


def squarefree_sieve(M: int) -> bytearray:
    sf = bytearray([1]) * (M + 1)
    sf[0] = 0
    for p in nt.primes_upto(int(M**0.5) + 1):
        sf[p * p :: p * p] = bytearray(len(range(p * p, M + 1, p * p)))
    return sf


def is_squarefree_td(n: int) -> bool:
    return all(e == 1 for e in nt.factorize(n).values())


def has_square_factor(m: int, primes: list[int] | None = None) -> bool:
    """True iff p^2 | m for some prime p (direct division; independent of the sieve)."""
    for p in primes if primes is not None else nt.primes_upto(math.isqrt(m)):
        if p * p > m:
            break
        if m % (p * p) == 0:
            return True
    return False


def build_graph(N: int):
    sf = squarefree_sieve(N * N + 1)
    verts = [a for a in range(1, N + 1) if not sf[a * a + 1]]
    idx = {a: i for i, a in enumerate(verts)}
    nbr = [0] * len(verts)
    for i, a in enumerate(verts):
        for j in range(i + 1, len(verts)):
            b = verts[j]
            if not sf[a * b + 1]:
                nbr[i] |= 1 << j
                nbr[j] |= 1 << i
    return verts, nbr


def max_clique(nbr: list[int], lower: int = 0) -> int:
    """Exact maximum clique (bitset branch and bound with greedy-colouring bound).
    Returns the clique as a bitmask."""
    best = [0, 0]  # size, mask

    def colour_bound(P: int) -> list[tuple[int, int]]:
        # greedy sequential colouring; returns vertices with colour numbers
        order = []
        colour = 0
        U = P
        while U:
            colour += 1
            Q = U
            while Q:
                v = (Q & -Q).bit_length() - 1
                Q &= ~(1 << v)
                Q &= ~nbr[v]
                U &= ~(1 << v)
                order.append((v, colour))
        return order

    def expand(R: int, rsize: int, P: int) -> None:
        order = colour_bound(P)
        for v, col in reversed(order):
            if rsize + col <= best[0]:
                return
            R2 = R | (1 << v)
            P2 = P & nbr[v]
            if P2:
                expand(R2, rsize + 1, P2)
            elif rsize + 1 > best[0]:
                best[0], best[1] = rsize + 1, R2
            P &= ~(1 << v)

    best[0] = max(lower - 1, 0)
    expand(0, 0, (1 << len(nbr)) - 1)
    return best[1]


def bron_kerbosch_max(nbr: list[int]) -> int:
    best = 0

    def bk(r: int, P: int, X: int) -> None:
        nonlocal best
        if not P and not X:
            best = max(best, r)
            return
        if r + bin(P).count("1") <= best:
            return
        U = P | X
        members = [i for i in range(len(nbr)) if (U >> i) & 1]
        u = max(members, key=lambda i: bin(P & nbr[i]).count("1"))
        C = P & ~nbr[u]
        while C:
            v = (C & -C).bit_length() - 1
            C &= C - 1
            bk(r + 1, P & nbr[v], X & nbr[v])
            P &= ~(1 << v)
            X |= 1 << v

    bk(0, (1 << len(nbr)) - 1, 0)
    return best


def class_size(N: int, r: int = 7, m: int = 25) -> int:
    return 0 if N < r else (N - r) // m + 1


class Problem848(Solver):
    problem = 848
    name = "p848-ab-plus-one-nonsquarefree"
    title = r"sets with $ab+1$ never squarefree"
    statement_tex = (r"Is the maximum size of a set $A\subseteq\{1,\ldots,N\}$ such that $ab+1$ is never "
                     r"squarefree (for all $a,b\in A$) achieved by taking those $n\equiv 7\pmod{25}$?")
    finite_kind = "decidable"
    tags = ("number theory",)
    references = ("erdosproblems848",)
    quick_params = {"N": 150}

    def run(self, N: int = 300, step: int = 1) -> Result:
        seq, exceptions, witnesses = [], [], {}
        with Timer() as t:
            verts, nbr = build_graph(N)
            prev = 0
            last: list[int] = []
            for n in range(1, N + 1, step):
                k = sum(1 for a in verts if a <= n)
                sub = nbr[:k]
                mask_all = (1 << k) - 1
                sub = [x & mask_all for x in sub]
                cl = max_clique(sub, lower=prev) if k else 0
                size = bin(cl).count("1")
                if size <= prev:  # monotone: the previous optimum is still optimal
                    size = prev
                else:  # store a witness only where the maximum grows
                    last = [verts[i] for i in range(k) if (cl >> i) & 1]
                    witnesses[n] = last
                prev = size
                c7 = class_size(n)
                seq.append([n, size, c7])
                if size > c7:
                    exceptions.append([n, size, c7, last])
        cert = {"N": N, "sequence": seq, "exceptions": exceptions,
                "witnesses": {str(k): v for k, v in witnesses.items()}, "vertices": len(verts)}
        summ = (f"Computed f(N) for N <= {N}. " +
                (f"{len(exceptions)} N with f(N) > |7 mod 25 class|, first: N={exceptions[0][0]} "
                 f"(f={exceptions[0][1]} vs {exceptions[0][2]}, A={exceptions[0][3]})"
                 if exceptions else "The class 7 (mod 25) attains the maximum for every N in range."))
        return self._result(SEQUENCE, {"N": N}, summ, cert, {"seconds": round(t.seconds, 2)}, float(N))

    def check(self, result: Result, bk_upto: int = 120) -> CheckReport:
        rep = CheckReport(True, "p848-bron-kerbosch")
        t0 = time.perf_counter()
        c = result.certificate
        seq = {n: f for n, f, _ in c["sequence"]}
        products: set[int] = set()
        for n_s, A in c["witnesses"].items():
            n = int(n_s)
            if len(A) != seq[n] or len(set(A)) != len(A) or any(not 1 <= a <= n for a in A):
                return rep.fail(f"witness for N={n} has wrong size or range")
            products.update(a * b + 1 for i, a in enumerate(A) for b in A[i:])
        # every value where the sequence grows must carry a witness
        prev = 0
        for n, f, _ in c["sequence"]:
            if f > prev and str(n) not in c["witnesses"]:
                return rep.fail(f"f grows at N={n} without a witness")
            prev = f
        for n, f, c7, A in c["exceptions"]:
            if not (A and len(A) == f > c7 and max(A) <= n):
                return rep.fail(f"exception at N={n} lacks a valid witness")
            products.update(a * b + 1 for i, a in enumerate(A) for b in A[i:])
        # each distinct product checked once: divisible by p^2 for some prime p
        P = nt.primes_upto(math.isqrt(max(products))) if products else []
        bad = [m for m in products if not has_square_factor(m, P)]
        if bad:
            return rep.fail(f"witness product {min(bad)} is squarefree")
        rep.note(f"{len(c['witnesses'])} witness sets ({len(products)} distinct products ab+1) "
                 f"re-validated by direct division by prime squares")
        prev = 0
        for n, f, c7 in c["sequence"]:
            if f < prev or f < (1 if n >= 7 else 0) or c7 != class_size(n):
                return rep.fail(f"sequence inconsistent at N={n}")
            prev = f
        verts, nbr = build_graph(min(bk_upto, c["N"]))
        for n, f, _ in c["sequence"]:
            if n > bk_upto:
                break
            k = sum(1 for a in verts if a <= n)
            sub = [x & ((1 << k) - 1) for x in nbr[:k]]
            if (bron_kerbosch_max(sub) if k else 0) != f:
                return rep.fail(f"Bron-Kerbosch disagrees at N={n}")
        rep.note(f"optimality re-derived by Bron-Kerbosch for N <= {min(bk_upto, c['N'])}")
        rep.seconds = time.perf_counter() - t0
        return rep

    def method_tex(self, result: Result) -> str:
        return (r"The admissible $a$ (those with $a^2+1$ not squarefree) form the vertices of a graph "
                r"with $a\sim b$ iff $ab+1$ is not squarefree; $f(N)$ is its clique number restricted "
                r"to $[1,N]$, computed by bitset branch and bound with a greedy-colouring bound and "
                r"re-derived by Bron--Kerbosch with pivoting.")
