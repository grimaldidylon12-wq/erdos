"""Erdős #458: reduction, certificate, checker, and adversarial tests."""
import copy
import math

import pytest

from erdos_engine import native, nt
from erdos_engine.solvers import p458
from erdos_engine.solvers.base import COUNTEREXAMPLE, VERIFIED_TO_BOUND
from erdos_engine.solvers.p458 import Problem458


@pytest.fixture(scope="module")
def run_1e12():
    return Problem458().run(X=10**12, brute_limit=2000, sieve_limit=10**5, workers=2, chunk=300000)


def test_literal_lcm_holds_small():
    rows = p458.brute_force_lcm(4000)
    assert rows and all(ok for _, _, ok in rows)
    assert len(rows) == len(nt.primes_upto(4000)) - 1


def test_reduction_matches_literal_statement():
    """Product criterion <=> lcm inequality, gap by gap."""
    prods = p458.gap_products_by_sieve(4000)
    for p, r, ok in p458.brute_force_lcm(4000):
        assert ok == (prods.get((p, r), 1) < p)


def test_reduction_ratio_exact():
    """lcm(1..r-1)/lcm(1..p) equals the product of bases, exactly."""
    primes = nt.primes_upto(600)
    prods = p458.gap_products_by_sieve(600)
    for p, r in zip(primes, primes[1:]):
        ratio = math.lcm(*range(1, r)) // math.lcm(*range(1, p + 1))
        assert ratio == prods.get((p, r), 1)


def test_known_worst_gap_is_7_11():
    hp = p458.analyse_high_power_gaps(10**9, use_native=False)
    p, r, prod, mem = hp["worst_ratio"][0]
    assert (p, r, prod) == (7, 11, 6) and sorted(map(tuple, mem)) == [(2, 3), (3, 2)]
    assert not hp["failures"]


def test_high_power_analysis_native_equals_python():
    a = p458.analyse_high_power_gaps(10**14, use_native=True)
    b = p458.analyse_high_power_gaps(10**14, use_native=False)
    assert a["digest_sha256"] == b["digest_sha256"] and a["prime_powers"] == b["prime_powers"]


def test_high_power_gap_products_agree_with_sieve():
    X = 10**6
    hp = p458.analyse_high_power_gaps(X, use_native=False)
    sieve = p458.gap_products_by_sieve(X + 1000)
    for p, r, prod, _ in hp["multi_power_gaps"] + hp["worst_ratio"]:
        if r <= X:
            assert sieve[(p, r)] == prod


def test_higher_powers_enumeration():
    hp = p458.higher_powers(10**6)
    assert len(hp) == len({h for h, _, _ in hp})
    assert all(nt.is_prime(q) and a >= 3 and q**a == h <= 10**6 for h, q, a in hp)
    brute = sorted(q**a for q in nt.primes_upto(100) for a in range(3, 21) if q**a <= 10**6)
    assert [h for h, _, _ in hp] == brute


def test_square_chunks_tile():
    ch = p458.square_chunks(10**6 + 7, chunk=123457)
    assert ch[0][0] == 2 and ch[-1][1] == 10**6 + 8
    assert all(a[1] == b[0] for a, b in zip(ch, ch[1:]))


def test_run_and_check(run_1e12):
    r = run_1e12
    assert r.outcome == VERIFIED_TO_BOUND and r.frontier == 1e12
    sq = r.certificate["squares"]
    assert sum(c["count"] for c in sq["chunks"]) == len(nt.primes_upto(10**6))
    rep = Problem458().check(r, sample_chunks=3)
    assert rep.ok, rep.details


def test_python_only_run_agrees_with_native():
    a = Problem458().run(X=10**9, brute_limit=500, sieve_limit=10**4, use_native=False, chunk=10**4)
    b = Problem458().run(X=10**9, brute_limit=500, sieve_limit=10**4, use_native=True, chunk=10**4, workers=1)
    da = [(c["lo"], c["count"], c["digest"]) for c in a.certificate["squares"]["chunks"]]
    db = [(c["lo"], c["count"], c["digest"]) for c in b.certificate["squares"]["chunks"]]
    assert da == db
    assert a.certificate["high_powers"]["digest_sha256"] == b.certificate["high_powers"]["digest_sha256"]


def test_checkpoint_resume(tmp_path):
    ck = tmp_path / "chunks.jsonl"
    first = p458.run_square_scan(10**5, chunk=20000, workers=1, checkpoint=ck)
    lines = ck.read_text().splitlines()
    assert len(lines) == len(first)
    ck.write_text("\n".join(lines[:2]) + "\n")  # simulate interruption
    again = p458.run_square_scan(10**5, chunk=20000, workers=1, checkpoint=ck)
    assert [c["digest"] for c in again] == [c["digest"] for c in first]
    assert len(ck.read_text().splitlines()) == len(first)


# ---------------------------------------------------------------- tampering

def _tampered(r, fn):
    t = copy.deepcopy(r)
    fn(t.certificate)
    return t


def test_tamper_chunk_digest_detected(run_1e12):
    def f(c):
        c["squares"]["chunks"][0]["digest"] ^= 1
    rep = Problem458().check(_tampered(run_1e12, f), sample_chunks=0)
    assert not rep.ok and "not reproduced" in rep.details[-1]


def test_tamper_missing_chunk_detected(run_1e12):
    def f(c):
        del c["squares"]["chunks"][1]
    assert not Problem458().check(_tampered(run_1e12, f), sample_chunks=0).ok


def test_tamper_count_detected(run_1e12):
    def f(c):
        ch = c["squares"]["chunks"]
        ch[len(ch) - 1]["count"] -= 1
    rep = Problem458().check(_tampered(run_1e12, f), sample_chunks=len(run_1e12.certificate["squares"]["chunks"]))
    assert not rep.ok


def test_tamper_high_power_digest_detected(run_1e12):
    def f(c):
        c["high_powers"]["digest_sha256"] = "0" * 64
    assert not Problem458().check(_tampered(run_1e12, f), sample_chunks=0).ok


def test_tamper_bound_detected(run_1e12):
    def f(c):
        c["X"] = 10**13  # claim more than was computed
    assert not Problem458().check(_tampered(run_1e12, f), sample_chunks=0).ok


def test_reported_failure_is_never_verified(run_1e12):
    def f(c):
        c["squares"]["chunks"][2]["fails"] = 1
    assert not Problem458().check(_tampered(run_1e12, f), sample_chunks=0).ok


# ---------------------------------------------------------------- mutations

def test_checker_catches_buggy_primality(monkeypatch, run_1e12):
    """A subtly wrong primality test on the checker side changes which witness
    is chosen, so the witness-sequence digest no longer matches the search."""
    real = nt.is_prime
    monkeypatch.setattr(nt, "is_prime", lambda n: real(n) and (n < 10**6 or n % 7 != 1))
    rep = Problem458().check(run_1e12, sample_chunks=1, recompute_high=False)
    assert not rep.ok and "not reproduced" in rep.details[-1]


def test_checker_catches_wrong_witness_rule(monkeypatch, run_1e12):
    monkeypatch.setattr(p458, "witness_offset_py", lambda q, qn, ring: (2, 0))
    assert not Problem458().check(run_1e12, sample_chunks=1, recompute_high=False).ok


def test_counterexample_path(monkeypatch):
    """If part (A) finds a gap with product >= p, the outcome must be a counterexample."""
    orig = p458.analyse_high_power_gaps

    def fake(X, use_native=True, progress=None):
        hp = orig(X, use_native=use_native)
        hp["failures"] = [[7, 11, 77, [[7, 2], [11, 2]]]]
        return hp

    monkeypatch.setattr(p458, "analyse_high_power_gaps", fake)
    r = Problem458().run(X=10**8, brute_limit=200, sieve_limit=10**4, workers=1)
    assert r.outcome == COUNTEREXAMPLE and r.settles_problem


def test_missing_square_witness_is_not_a_counterexample(monkeypatch):
    def fake_scan(qmax, chunk, workers, checkpoint, progress):
        return [{"lo": 2, "hi": qmax + 1, "count": 5, "fails": 1, "first_fail": 3, "digest": 0,
                 "generic": 0, "range_errors": 0, "last_q": 7}]
    monkeypatch.setattr(p458, "run_square_scan", fake_scan)
    r = Problem458().run(X=100, brute_limit=50, sieve_limit=100, workers=1)
    assert r.outcome == "no_conclusion"


def test_latex_fragments(run_1e12):
    s = Problem458()
    assert "10^{12}" in s.results_tex(run_1e12)
    assert "10^{12}" in s.abstract_tex(run_1e12)
    assert "@@" not in s.results_tex(run_1e12)
    assert p458._tex_num(3 * 10**21) == "3\\cdot 10^{21}"


def test_parallel_check(run_1e12):
    rep = Problem458().check(run_1e12, sample_chunks=3, workers=2, recompute_high=False)
    assert rep.ok and sum("reproduced exactly" in d for d in rep.details) >= 3


def test_forum_markdown_mentions_prior_only_when_beyond(run_1e12):
    s = Problem458()
    assert "10^{20}" not in s.forum_markdown(run_1e12)
    big = copy.deepcopy(run_1e12)
    big.certificate["X"] = 10**21
    assert "10^{20}" in s.forum_markdown(big)


def test_agrees_with_independent_forum_computation():
    """bhowerton (forum, 12 Jun 2026): 341805 prime powers q^a, a >= 3, below 1.05e20,
    and the only two within 1854 of each other (beyond the small range checked directly)
    are 73^3 = 389017 and 5^8 = 390625."""
    hp = p458.higher_powers(105 * 10**18)
    assert len(hp) == 341805
    close = [(a, b) for (a, _, _), (b, _, _) in zip(hp, hp[1:]) if b - a <= 1854]
    assert close[-1] == (389017, 390625) and all(b < 10**6 for _, b in close)


def test_tamper_count_caught_by_prime_pi(run_1e12):
    def f(c):
        c["squares"]["chunks"][-1]["count"] += 1
    rep = Problem458().check(_tampered(run_1e12, f), sample_chunks=0)
    assert not rep.ok and "pi(" in rep.details[-1]
