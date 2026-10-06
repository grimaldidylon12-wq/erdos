"""Other solvers: known values, cross-checks, and tampering."""
import copy
import math

import pytest

from erdos_engine import nt
from erdos_engine.solvers import REGISTRY, get_solver
from erdos_engine.solvers import p375, p647, p699, p848, p993
from erdos_engine.solvers.base import CheckReport, Result


@pytest.mark.parametrize("n", sorted(REGISTRY))
def test_quick_run_and_check(n):
    s = get_solver(n)
    r = s.run(**s.quick_params)
    assert r.problem == n and r.outcome in {"verified_to_bound", "sequence"}
    rep = s.check(r)
    assert rep.ok, rep.details
    rt = Result.from_dict(r.to_dict())
    assert rt == r


def test_registry_unknown():
    with pytest.raises(KeyError):
        get_solver(1)


def test_solver_metadata_complete():
    for n, cls in REGISTRY.items():
        assert cls.problem == n and cls.name and cls.statement_tex and cls.references
        assert cls.finite_kind in {"falsifiable", "verifiable", "decidable", "open"}


# ------------------------------------------------------------------ #647

def test_p647_known_solutions():
    r = get_solver(647).run(N=50000)
    assert r.certificate["solutions"] == [2, 3, 4, 5, 6, 8, 10, 12, 24]  # cf. OEIS A087280


def test_p647_two_tau_methods_agree():
    a = p647.tau_array(30000)
    b = p647.tau_spf(30000)
    assert [int(x) for x in a[1:]] == b[1:]


def test_p647_tamper_fake_solution():
    s = get_solver(647)
    r = s.run(N=20000)
    r.certificate["solutions"].append(30)
    assert not s.check(r).ok


# ------------------------------------------------------------------ #699

def test_p699_erdos_szekeres_exception():
    r = get_solver(699).run(N=40)
    assert (28, 5, 14) in [tuple(x) for x in r.certificate["strict_exceptions_i_ge_4"]]
    g = math.gcd(math.comb(28, 5), math.comb(28, 14))
    assert nt.factorize(g) == {2: 3, 3: 3, 5: 1}


def test_p699_kummer_vs_direct():
    primes = nt.primes_upto(60)
    for n in range(2, 61):
        masks = p699.prime_masks(n, primes)
        for k in range(1, n // 2 + 1):
            direct = {p for p in primes if math.comb(n, k) % p == 0}
            got = {primes[t] for t in range(len(primes)) if masks[k] >> t & 1}
            assert direct == got


def test_p699_tamper():
    s = get_solver(699)
    r = s.run(N=50)
    r.certificate["failures"].append([30, 2, 3])
    assert not s.check(r).ok


# ------------------------------------------------------------------ #993

def test_p993_counts_match_oeis():
    for n in range(1, 13):
        assert len(p993.free_trees(n)) == p993.A000055[n]


def test_p993_small_polynomials():
    path4 = [[1], [0, 2], [1, 3], [2]]
    star = [[1, 2, 3], [0], [0], [0]]
    assert p993.independence_poly_tree(path4) == [1, 4, 3]
    assert p993.independence_poly_tree(star) == [1, 4, 3, 1]
    assert p993.independence_poly_brute(star) == [1, 4, 3, 1]


def test_p993_unimodal_and_lc_helpers():
    assert p993.is_unimodal([1, 3, 3, 2]) and not p993.is_unimodal([1, 3, 2, 3])
    assert p993.is_log_concave([1, 4, 3]) and not p993.is_log_concave([1, 1, 2])
    assert p993.is_unimodal([1]) and p993.is_unimodal([])


def test_p993_three_polynomial_methods_agree():
    for adj in p993.free_trees(9):
        sets = {v: frozenset(adj[v]) for v in range(9)}
        a = p993.independence_poly_tree(adj)
        assert a == p993.independence_poly_deletion(sets) == p993.independence_poly_brute(adj)


def test_p993_tamper_count():
    s = get_solver(993)
    r = s.run(N=9)
    r.certificate["per_n"][7]["trees"] += 1
    assert not s.check(r).ok


def test_p993_canonical_is_isomorphism_invariant():
    # relabelled paths are the same tree
    a = [[1], [0, 2], [1, 3], [2]]
    b = [[2], [3], [0, 3], [1, 2]]
    assert p993.canonical(a) == p993.canonical(b)
    assert p993.canonical(a) != p993.canonical([[1, 2, 3], [0], [0], [0]])


# ------------------------------------------------------------------ #848

def test_p848_class_attains_max_small():
    r = get_solver(848).run(N=300)
    assert not r.certificate["exceptions"]
    seq = {n: f for n, f, _ in r.certificate["sequence"]}
    assert seq[6] == 0 and seq[7] == 1 and seq[32] == 2 and seq[300] == 12


def test_p848_two_clique_algorithms():
    verts, nbr = p848.build_graph(200)
    for k in (5, 10, len(verts)):
        sub = [x & ((1 << k) - 1) for x in nbr[:k]]
        assert bin(p848.max_clique(sub)).count("1") == p848.bron_kerbosch_max(sub)


def test_p848_squarefree_sieve():
    sf = p848.squarefree_sieve(5000)
    assert all(bool(sf[n]) == p848.is_squarefree_td(n) for n in range(1, 5001))


def test_p848_tamper_witness():
    s = get_solver(848)
    r = s.run(N=100)
    r.certificate["witnesses"]["100"] = [7, 32, 57, 1]
    assert not s.check(r).ok


# ------------------------------------------------------------------ #375

def test_p375_matching():
    assert p375.bipartite_match([[2], [2]]) is None
    m = p375.bipartite_match([[2, 3], [2]])
    assert m == {0: 3, 1: 2}


def test_p375_shortcut_equals_full_matching():
    r = get_solver(375).run(N=30000)
    assert r.outcome == "verified_to_bound"
    assert get_solver(375).check(r, prefix=30000).ok


def test_p375_tamper_assignment():
    s = get_solver(375)
    r = s.run(N=20000)
    h = r.certificate["hard_runs"][0]
    k = next(iter(h["assign"]))
    h["assign"][k] = 4  # not prime
    assert not s.check(r).ok
