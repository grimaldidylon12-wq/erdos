r"""Erdős Problem #993 (falsifiable): the independence sequence of every tree
(or forest) is unimodal.

Search: all free trees on n vertices are produced from rooted trees
(Beyer--Hedetniemi level sequences), canonicalised by an AHU encoding rooted
at the centre(s), and deduplicated; per-order counts are compared against
OEIS A000055.  Independence polynomials are computed by the standard rooted
DP (in/out vertex).  Forests reduce to trees: a product of log-concave
sequences is log-concave, so only non-log-concave trees could combine into a
non-unimodal forest; those are recorded.

Independent check: polynomials recomputed by the deletion recurrence
I(G) = I(G - v) + x I(G - N[v]) on graphs given as adjacency sets (a
different algorithm), brute-force subset enumeration for small n, and an
independent tree generator via Prüfer sequences for small n.
"""
from __future__ import annotations

import itertools
import random
import time
from functools import lru_cache

from .base import COUNTEREXAMPLE, VERIFIED_TO_BOUND, CheckReport, Result, Solver, Timer

#: OEIS A000055: number of free trees on n unlabeled nodes, n = 0..25
A000055 = [1, 1, 1, 1, 2, 3, 6, 11, 23, 47, 106, 235, 551, 1301, 3159, 7741, 19320, 48629,
           123867, 317955, 823065, 2144505, 5623756, 14828074, 39299897, 104636890]


# ----------------------------------------------------------------- generation

def rooted_level_sequences(n: int):
    """Beyer--Hedetniemi: all rooted trees on n nodes as canonical level sequences."""
    if n == 1:
        yield [0]
        return
    L = list(range(n))  # path, the first sequence
    while True:
        yield list(L)
        p = n - 1
        while p > 0 and L[p] == 1:
            p -= 1
        if p == 0:
            return
        q = p - 1
        while L[q] != L[p] - 1:
            q -= 1
        for i in range(p, n):
            L[i] = L[i - p + q]


def level_seq_to_adj(L: list[int]) -> list[list[int]]:
    adj: list[list[int]] = [[] for _ in L]
    stack: list[int] = []
    for v, d in enumerate(L):
        while len(stack) > d:
            stack.pop()
        if stack:
            adj[v].append(stack[-1])
            adj[stack[-1]].append(v)
        stack.append(v)
    return adj


def centers(adj: list[list[int]]) -> list[int]:
    n = len(adj)
    if n <= 2:
        return list(range(n))
    deg = [len(a) for a in adj]
    layer = [v for v in range(n) if deg[v] == 1]
    remaining = n
    while remaining > 2:
        remaining -= len(layer)
        nxt = []
        for v in layer:
            for u in adj[v]:
                deg[u] -= 1
                if deg[u] == 1:
                    nxt.append(u)
        layer = nxt
    return layer


def ahu(adj: list[list[int]], root: int, parent: int = -1) -> str:
    return "(" + "".join(sorted(ahu(adj, c, root) for c in adj[root] if c != parent)) + ")"


def canonical(adj: list[list[int]]) -> str:
    return min(ahu(adj, c) for c in centers(adj))


def free_trees(n: int) -> list[list[list[int]]]:
    """All non-isomorphic free trees on n vertices (as adjacency lists)."""
    if n == 0:
        return []
    seen: dict[str, list[list[int]]] = {}
    for L in rooted_level_sequences(n):
        adj = level_seq_to_adj(L)
        key = canonical(adj)
        if key not in seen:
            seen[key] = adj
    return list(seen.values())


# ------------------------------------------------------------- polynomials

def _padd(a: list[int], b: list[int]) -> list[int]:
    if len(a) < len(b):
        a, b = b, a
    return [x + (b[i] if i < len(b) else 0) for i, x in enumerate(a)]


def _pmul(a: list[int], b: list[int]) -> list[int]:
    out = [0] * (len(a) + len(b) - 1)
    for i, x in enumerate(a):
        if x:
            for j, y in enumerate(b):
                out[i + j] += x * y
    return out


def independence_poly_tree(adj: list[list[int]]) -> list[int]:
    """Coefficients i_0, i_1, ... via the rooted in/out DP (iterative)."""
    n = len(adj)
    if n == 0:
        return [1]
    order, parent = [0], [-1] * n
    parent[0] = 0
    for v in order:
        for u in adj[v]:
            if parent[u] == -1:
                parent[u] = v
                order.append(u)
    out_: list[list[int]] = [None] * n  # type: ignore[list-item]
    in_: list[list[int]] = [None] * n   # type: ignore[list-item]
    for v in reversed(order):
        o, i = [1], [0, 1]
        for u in adj[v]:
            if u != 0 and parent[u] == v:  # u is a child of v
                o = _pmul(o, _padd(out_[u], in_[u]))
                i = _pmul(i, out_[u])
        out_[v], in_[v] = o, i
    return _padd(out_[0], in_[0])


def is_unimodal(a: list[int]) -> bool:
    i = 0
    while i + 1 < len(a) and a[i] <= a[i + 1]:
        i += 1
    while i + 1 < len(a) and a[i] >= a[i + 1]:
        i += 1
    return i >= len(a) - 1


def is_log_concave(a: list[int]) -> bool:
    return all(a[k] * a[k] >= a[k - 1] * a[k + 1] for k in range(1, len(a) - 1))


# ---------------------------------------------------------- independent side

def independence_poly_deletion(adjsets: dict[int, frozenset]) -> list[int]:
    """I(G) = I(G - v) + x I(G - N[v]); memoised on the vertex set."""
    @lru_cache(maxsize=None)
    def rec(vs: frozenset) -> tuple[int, ...]:
        if not vs:
            return (1,)
        v = min(vs, key=lambda w: (-len(adjsets[w] & vs), w))
        a = rec(vs - {v})
        b = rec(vs - {v} - adjsets[v])
        out = list(a) + [0] * max(0, len(b) + 1 - len(a))
        for k, c in enumerate(b):
            out[k + 1] += c
        return tuple(out)
    return list(rec(frozenset(adjsets)))


def independence_poly_brute(adj: list[list[int]]) -> list[int]:
    n = len(adj)
    nb = [sum(1 << u for u in adj[v]) for v in range(n)]
    out = [0] * (n + 1)
    for S in range(1 << n):
        ok = True
        T = S
        while T:
            v = (T & -T).bit_length() - 1
            if nb[v] & S:
                ok = False
                break
            T &= T - 1
        if ok:
            out[bin(S).count("1")] += 1
    while len(out) > 1 and out[-1] == 0:
        out.pop()
    return out


def prufer_trees(n: int) -> set[str]:
    """Canonical forms of all labelled trees on n vertices (independent generator)."""
    if n <= 2:
        return {canonical([[1], [0]])} if n == 2 else ({canonical([[]])} if n == 1 else set())
    keys = set()
    for seq in itertools.product(range(n), repeat=n - 2):
        degree = [1] * n
        for x in seq:
            degree[x] += 1
        adj: list[list[int]] = [[] for _ in range(n)]
        for x in seq:
            leaf = min(i for i in range(n) if degree[i] == 1)
            adj[leaf].append(x)
            adj[x].append(leaf)
            degree[leaf] -= 1
            degree[x] -= 1
        u, v = [i for i in range(n) if degree[i] == 1]
        adj[u].append(v)
        adj[v].append(u)
        keys.add(canonical(adj))
    return keys


# -------------------------------------------------------------------- solver

class Problem993(Solver):
    problem = 993
    name = "p993-tree-unimodality"
    title = "unimodality of independence sequences of trees"
    statement_tex = (r"The independent set sequence of any tree or forest is unimodal: if $i_k(T)$ "
                     r"counts independent sets of size $k$ in a tree or forest $T$, then for some $m$, "
                     r"$i_0\le\cdots\le i_m\ge i_{m+1}\ge\cdots$.")
    finite_kind = "falsifiable"
    tags = ("graph theory",)
    references = ("AMSE87", "KadrawiLevit2023", "erdosproblems993")
    quick_params = {"N": 12}
    frontier_regex = r"n\s*(?:=|\\le|<=|≤)\s*(\d{1,3})\b"

    def run(self, N: int = 16) -> Result:
        per_n = []
        failures, non_lc = [], []
        with Timer() as t:
            for n in range(1, N + 1):
                trees = free_trees(n)
                bad = 0
                for adj in trees:
                    poly = independence_poly_tree(adj)
                    if not is_unimodal(poly):
                        failures.append({"n": n, "tree": canonical(adj), "poly": poly})
                        bad += 1
                    elif not is_log_concave(poly):
                        non_lc.append({"n": n, "tree": canonical(adj), "poly": poly})
                per_n.append({"n": n, "trees": len(trees), "non_unimodal": bad,
                              "oeis_A000055": A000055[n] if n < len(A000055) else None})
        count_ok = all(r["oeis_A000055"] in (None, r["trees"]) for r in per_n)
        cert = {"N": N, "per_n": per_n, "failures": failures, "non_log_concave": non_lc,
                "counts_match_A000055": count_ok}
        if failures:
            return self._result(COUNTEREXAMPLE, {"N": N}, f"Non-unimodal tree found: {failures[0]}",
                                cert, {"seconds": t.seconds}, float(N))
        return self._result(VERIFIED_TO_BOUND, {"N": N},
                            f"All {sum(r['trees'] for r in per_n)} trees with at most {N} vertices have "
                            f"unimodal independence sequences ({len(non_lc)} are not log-concave); "
                            f"tree counts match A000055: {count_ok}.",
                            cert, {"seconds": round(t.seconds, 2)}, float(N))

    def check(self, result: Result, brute_upto: int = 11, prufer_upto: int = 8,
              samples: int = 300, seed: int = 0) -> CheckReport:
        rep = CheckReport(True, "p993-deletion-recurrence")
        t0 = time.perf_counter()
        c = result.certificate
        N = c["N"]
        for row in c["per_n"]:
            n = row["n"]
            if n < len(A000055) and row["trees"] != A000055[n]:
                return rep.fail(f"tree count for n={n} is {row['trees']}, A000055 says {A000055[n]}")
        rep.note("per-order tree counts agree with OEIS A000055")
        for n in range(1, min(prufer_upto, N) + 1):
            if len(prufer_trees(n)) != c["per_n"][n - 1]["trees"]:
                return rep.fail(f"Prüfer enumeration disagrees at n={n}")
        rep.note(f"independent Prüfer-sequence enumeration agrees for n <= {min(prufer_upto, N)}")
        rng = random.Random(seed)
        for n in range(1, N + 1):
            trees = free_trees(n)
            pick = trees if n <= brute_upto else rng.sample(trees, min(samples, len(trees)))
            for adj in pick:
                sets = {v: frozenset(adj[v]) for v in range(n)}
                p1 = independence_poly_deletion(sets)
                p2 = independence_poly_tree(adj)
                if p1 != p2:
                    return rep.fail(f"DP and deletion recurrence disagree on {canonical(adj)}")
                if n <= brute_upto and independence_poly_brute(adj) != p1:
                    return rep.fail(f"brute force disagrees on {canonical(adj)}")
                if not is_unimodal(p1) and not c["failures"]:
                    return rep.fail(f"non-unimodal tree missed: {canonical(adj)}")
        rep.note(f"polynomials re-derived by deletion recurrence (all trees n <= {brute_upto}, also by "
                 f"brute force; {samples} sampled per larger n)")
        rep.seconds = time.perf_counter() - t0
        return rep

    def method_tex(self, result: Result) -> str:
        return (r"Free trees were generated from Beyer--Hedetniemi level sequences of rooted trees, "
                r"canonicalised by AHU codes at the centre, and counted against OEIS A000055. "
                r"Independence polynomials were computed by the rooted in/out dynamic programme and "
                r"re-derived for checking by the deletion recurrence "
                r"$I(G)=I(G-v)+xI(G-N[v])$ and, for small orders, by subset enumeration.")
