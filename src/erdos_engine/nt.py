"""Pure-Python number theory used by checkers and as a fallback.

This module deliberately shares no code with native/primekit.c so that it can
serve as an independent implementation when re-validating certificates.
Primality is decided by deterministic Miller-Rabin (first 13 prime bases,
proven for n < 3.317e24, Sorenson-Webster 2015); larger inputs raise.
"""
from __future__ import annotations

import math
from typing import Iterator

PSI13 = 3317044064679887385961981
MR_BASES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41)
_SMALL = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47)


def is_prime(n: int) -> bool:
    if n < 2:
        return False
    for p in _SMALL:
        if n % p == 0:
            return n == p
    if n < 49 * 49:
        return True
    if n >= PSI13:
        raise ValueError(f"{n} exceeds the proven deterministic Miller-Rabin range")
    d, s = n - 1, 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for a in MR_BASES:
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(s - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def next_prime(n: int) -> int:
    c = max(n + 1, 2)
    while not is_prime(c):
        c += 1
    return c


def prev_prime(n: int) -> int:
    if n <= 2:
        raise ValueError("no prime below 2")
    c = n - 1
    while not is_prime(c):
        c -= 1
    return c


def primes_upto(n: int) -> list[int]:
    """All primes <= n (simple bytearray sieve)."""
    if n < 2:
        return []
    sieve = bytearray([1]) * (n + 1)
    sieve[0] = sieve[1] = 0
    for i in range(2, math.isqrt(n) + 1):
        if sieve[i]:
            sieve[i * i :: i] = bytearray(len(range(i * i, n + 1, i)))
    return [i for i in range(n + 1) if sieve[i]]


def primes_between(lo: int, hi: int) -> Iterator[int]:
    """Primes p with lo <= p < hi via a segmented sieve."""
    lo = max(lo, 2)
    if hi <= lo:
        return
    base = primes_upto(math.isqrt(hi) + 1)
    seg = 1 << 20
    start = lo
    while start < hi:
        end = min(start + seg, hi)
        mark = bytearray([1]) * (end - start)
        for p in base:
            if p * p >= end:
                break
            s = max(p * p, (start + p - 1) // p * p)
            mark[s - start :: p] = bytearray(len(range(s, end, p)))
        for i, v in enumerate(mark):
            if v:
                yield start + i
        start = end


def factorize(n: int) -> dict[int, int]:
    """Trial-division factorisation (for modest n only)."""
    out: dict[int, int] = {}
    d = 2
    while d * d <= n:
        while n % d == 0:
            out[d] = out.get(d, 0) + 1
            n //= d
        d += 1 if d == 2 else 2
    if n > 1:
        out[n] = out.get(n, 0) + 1
    return out


def tau(n: int) -> int:
    r = 1
    for e in factorize(n).values():
        r *= e + 1
    return r


def tau_sieve(n: int) -> list[int]:
    """tau(k) for 0 <= k <= n (tau(0) reported as 0)."""
    t = [0] * (n + 1)
    for d in range(1, n + 1):
        for m in range(d, n + 1, d):
            t[m] += 1
    return t


def integer_root(n: int, k: int) -> int:
    """floor(n^(1/k)) exactly."""
    if n < 0:
        raise ValueError
    if n < 2:
        return n
    r = int(round(n ** (1.0 / k)))
    while r**k > n:
        r -= 1
    while (r + 1) ** k <= n:
        r += 1
    return r


def pocklington_certifies(N: int, P: int, m: int, bases=MR_BASES) -> bool:
    """True iff some base proves N = P*m + 1 prime with F = 2P > sqrt(N).

    Requires P prime, m even.  Used to double-check native certificates.
    """
    if N != P * m + 1 or m % 2 or (2 * P) ** 2 <= N:
        return False
    for a in bases:
        if pow(a, N - 1, N) != 1:
            return False
        if math.gcd(pow(a, m, N) - 1, N) == 1 and math.gcd(pow(a, (N - 1) // 2, N) - 1, N) == 1:
            return True
    return False


FNV_OFF = 1469598103934665603
FNV_PRIME = 1099511628211
_M64 = (1 << 64) - 1


def fnv_u64(h: int, v: int) -> int:
    for i in range(8):
        h ^= (v >> (8 * i)) & 0xFF
        h = (h * FNV_PRIME) & _M64
    return h
