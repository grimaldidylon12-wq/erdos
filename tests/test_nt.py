"""Pure-Python number theory (the independent side of every checker)."""
import math

import pytest
from hypothesis import given, settings, strategies as st

from erdos_engine import nt

SIEVE = nt.primes_upto(100000)
SIEVE_SET = set(SIEVE)

# strong pseudoprimes to many bases: must be rejected
STRONG_PSEUDOPRIMES = [
    2047, 3215031751, 2152302898747, 3474749660383, 341550071728321,
    3825123056546413051, 318665857834031151167461,
]


def test_is_prime_matches_sieve():
    assert [n for n in range(100001) if nt.is_prime(n)] == SIEVE


@pytest.mark.parametrize("n", STRONG_PSEUDOPRIMES)
def test_strong_pseudoprimes_rejected(n):
    assert not nt.is_prime(n)


def test_known_large_primes():
    for p in (2**61 - 1, 2**64 - 59, 10**20 + 39, 2**80 - 65, 10**24 + 7):
        assert nt.is_prime(p)
    assert not nt.is_prime((2**61 - 1) * (2**19 - 1))


def test_beyond_proven_range_raises():
    # 2^89 - 1 is prime and has no small factor, so only Miller-Rabin could decide it
    with pytest.raises(ValueError):
        nt.is_prime(2**89 - 1)
    # composites with a small factor are still decided (trial division is a proof)
    assert not nt.is_prime(nt.PSI13 + 2) if (nt.PSI13 + 2) % 3 == 0 else True


def test_psi13_is_a_strong_pseudoprime_to_all_13_bases():
    n = nt.PSI13
    assert n == 1287836182261 * 2575672364521  # composite
    d, s = n - 1, 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for a in nt.MR_BASES:
        x = pow(a, d, n)
        assert x in (1, n - 1) or any(pow(x, 2**r, n) == n - 1 for r in range(1, s))
    with pytest.raises(ValueError):
        nt.is_prime(n)


@given(st.integers(min_value=3, max_value=10**15))
@settings(max_examples=200, deadline=None)
def test_next_prev_prime_inverse(n):
    p = nt.next_prime(n)
    assert p > n and nt.is_prime(p)
    assert nt.prev_prime(p) <= n
    assert all(not nt.is_prime(k) for k in range(n + 1, min(p, n + 200)))


@given(st.integers(min_value=0, max_value=200000), st.integers(min_value=0, max_value=5000))
@settings(max_examples=60, deadline=None)
def test_primes_between(lo, width):
    got = list(nt.primes_between(lo, lo + width))
    assert got == [p for p in range(max(lo, 2), lo + width) if nt.is_prime(p)]


def test_tau_and_sieve_agree():
    t = nt.tau_sieve(5000)
    assert all(t[n] == nt.tau(n) for n in range(1, 5001))
    assert nt.tau(720720) == 240


@given(st.integers(min_value=0, max_value=10**40), st.integers(min_value=2, max_value=12))
def test_integer_root(n, k):
    r = nt.integer_root(n, k)
    assert r**k <= n < (r + 1) ** k


@given(st.integers(min_value=2, max_value=10**12))
@settings(max_examples=100, deadline=None)
def test_factorize_roundtrip(n):
    f = nt.factorize(n)
    assert math.prod(p**e for p, e in f.items()) == n
    assert all(nt.is_prime(p) for p in f)


def test_pocklington_accepts_primes_and_rejects_composites():
    P = 1000003
    found_prime = found_comp = 0
    for m in range(P // 2 * 2, P // 2 * 2 + 400, 2):
        N = P * m + 1
        if (2 * P) ** 2 <= N:
            break
        if nt.is_prime(N):
            assert nt.pocklington_certifies(N, P, m)
            found_prime += 1
        else:
            assert not nt.pocklington_certifies(N, P, m)
            found_comp += 1
    assert found_prime and found_comp
    # malformed inputs are refused rather than "certified"
    assert not nt.pocklington_certifies(P * 6 + 1, P, 5)          # m odd
    assert not nt.pocklington_certifies(P * P * 8 + 1, P, P * 8)  # F too small


def test_fnv_vector():
    # FNV-1a 64 of the 8 zero bytes
    h = nt.fnv_u64(nt.FNV_OFF, 0)
    ref = nt.FNV_OFF
    for _ in range(8):
        ref = ((ref ^ 0) * nt.FNV_PRIME) % 2**64
    assert h == ref
