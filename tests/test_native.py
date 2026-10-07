"""The C kernel against the independent Python implementation."""
import random

import pytest
from hypothesis import given, settings, strategies as st

from erdos_engine import native, nt
from erdos_engine.solvers import p458

pytestmark = pytest.mark.skipif(not native.available(), reason="no C compiler")


def test_is_prime_small_range():
    assert all(native.is_prime(n) == nt.is_prime(n) for n in range(0, 50000))


@given(st.integers(min_value=0, max_value=nt.PSI13 - 1))
@settings(max_examples=3000, deadline=None)
def test_is_prime_random_wide(n):
    assert native.is_prime(n) == nt.is_prime(n)


@pytest.mark.parametrize("n", [2047, 3215031751, 3825123056546413051, 318665857834031151167461,
                               2**64 - 59, 2**64 + 13, 10**24 + 7, 2**81 - 1])
def test_is_prime_edge_cases(n):
    if n >= nt.PSI13:
        with pytest.raises(ValueError):
            native.is_prime(n)
    else:
        assert native.is_prime(n) == nt.is_prime(n)


def test_range_guard():
    with pytest.raises(ValueError):
        native.is_prime(nt.PSI13)
    with pytest.raises(ValueError):
        native.is_prime(2**130)


@given(st.integers(min_value=3, max_value=10**23))
@settings(max_examples=300, deadline=None)
def test_next_prev(n):
    assert native.next_prime(n) == nt.next_prime(n)
    assert native.prev_prime(n) == nt.prev_prime(n)


RANGES = [(2, 3000), (250, 400), (290, 310), (3990, 4100), (4001, 4500),
          (10**6, 10**6 + 3000), (2**32 - 2000, 2**32 + 2000), (10**10, 10**10 + 2000),
          (31622770000, 31622776602)]


@pytest.mark.parametrize("lo,hi", RANGES)
def test_scan_squares_matches_python(lo, hi):
    a = native.scan_squares(lo, hi)
    b = p458.scan_chunk_py(lo, hi)
    assert (a["count"], a["digest"], a["generic"], a["fails"], a["last_q"]) == \
           (b["count"], b["digest"], b["generic"], b["fails"], b["last_q"])
    assert a["range_errors"] == 0


def test_scan_squares_splits_consistently():
    whole = native.scan_squares(10**7, 10**7 + 20000)
    parts = [native.scan_squares(lo, lo + 5000) for lo in range(10**7, 10**7 + 20000, 5000)]
    assert sum(p["count"] for p in parts) == whole["count"]
    assert max(p["last_q"] for p in parts) == whole["last_q"]


def test_scan_counts_primes():
    s = native.scan_squares(2, 10**6)
    assert s["count"] == 78498 and s["fails"] == 0 and s["last_q"] == 999983


def test_witnesses_are_prime_and_inside_interval():
    """Spot-check: recompute each witness and verify it with the Python test."""
    plist = list(nt.primes_between(10**9 - 4000, 10**9 + 3000))
    for i, q in enumerate(plist):
        if q < 10**9:
            continue
        if i + 1 >= len(plist):
            break
        ring = plist[max(0, i - 31): i + 1][::-1]
        off, kind = p458.witness_offset_py(q, plist[i + 1], ring)
        w = q * q + off
        assert q * q < w < plist[i + 1] ** 2 and nt.is_prime(w)
        if kind == 1:  # also confirm the Pocklington certificate exists
            P = next(P for P in ring if (w - 1) % P == 0 and ((w - 1) // P) % 2 == 0 and 2 * P > plist[i + 1])
            assert nt.pocklington_certifies(w, P, (w - 1) // P)


def test_fallback_when_native_disabled(monkeypatch):
    monkeypatch.setenv("ERDOS_ENGINE_NO_NATIVE", "1")
    is_prime, prev_prime, next_prime = p458._prime_ops(use_native=False)
    assert is_prime is nt.is_prime
