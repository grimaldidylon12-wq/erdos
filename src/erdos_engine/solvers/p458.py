r"""Erdős Problem #458 (falsifiable).

Statement.  Let $[1,\dots,n]$ denote $\operatorname{lcm}(1,\dots,n)$ and $p_k$ the
$k$-th prime.  Is it true that for all $k\ge1$
    $[1,\dots,p_{k+1}-1] < p_k\,[1,\dots,p_k]$ ?

Reduction.  The quotient $[1,\dots,p_{k+1}-1]/[1,\dots,p_k]$ equals the product
of the bases $q$ of all prime powers $q^a$ ($a\ge2$) lying strictly inside the
gap $(p_k,p_{k+1})$, so the inequality is equivalent to
    $\Pi(p_k,p_{k+1}) := \prod_{q^a\in(p_k,p_{k+1})} q < p_k$.

Certificate for "true for every k with p_{k+1} <= X" (no prime-gap tables used):
  (A) every gap containing a prime power with exponent >= 3 is located exactly
      and its product computed (all prime powers inside it, squares included);
  (B) for every pair of consecutive primes q < q' with q <= sqrt(X), a prime is
      exhibited in (q^2, q'^2), so no gap contains two prime squares;
  (C) a gap containing no exponent->=3 power therefore has product 1 or a single
      q with q^2 > p_k, and q < p_k because a prime lies in (q, q^2).
Part (B) is the expensive part and is done by the native kernel in chunks; each
chunk records an FNV-1a digest of its witness sequence so an independent
implementation can confirm it reproduces the identical witnesses.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Iterable

from .. import nt
from .base import VERIFIED_TO_BOUND, COUNTEREXAMPLE, CheckReport, Result, Solver, Timer

RING = 32
SQUARE_CHUNK = 10**7


# --------------------------------------------------------------------------
# Reference implementations (small ranges, fully independent of the reduction)
# --------------------------------------------------------------------------

def brute_force_lcm(limit: int) -> list[tuple[int, int, bool]]:
    """Check the original lcm inequality literally for all p_{k+1} <= limit."""
    primes = nt.primes_upto(limit)
    out = []
    L = 1  # lcm(1..n)
    n = 0
    lcm_at: dict[int, int] = {}
    need = set(primes) | {r - 1 for r in primes}
    for n in range(1, limit + 1):
        L = math.lcm(L, n)
        if n in need:
            lcm_at[n] = L
    for p, r in zip(primes, primes[1:]):
        out.append((p, r, lcm_at[r - 1] < p * lcm_at[p]))
    return out


def gap_products_by_sieve(limit: int) -> dict[tuple[int, int], int]:
    """Pi(p, r) for every consecutive prime pair with r <= limit, via direct
    enumeration of all prime powers (exponent >= 2) up to limit."""
    primes = nt.primes_upto(limit)
    import bisect
    prods: dict[tuple[int, int], int] = {}
    for q in primes:
        if q * q > limit:
            break
        h = q * q
        while h <= limit:
            i = bisect.bisect_left(primes, h)
            if i < len(primes):
                key = (primes[i - 1], primes[i])
                prods[key] = prods.get(key, 1) * q
            h *= q
    return prods


# --------------------------------------------------------------------------
# Part (A): gaps containing a prime power with exponent >= 3
# --------------------------------------------------------------------------

def _prime_ops(use_native: bool):
    if use_native:
        from .. import native
        if native.available():
            return native.is_prime, native.prev_prime, native.next_prime
    return nt.is_prime, nt.prev_prime, nt.next_prime


def higher_powers(X: int) -> list[tuple[int, int, int]]:
    """All (q^a, q, a) with q prime, a >= 3, q^a <= X, sorted by value."""
    out = []
    a = 3
    while 2**a <= X:
        for q in nt.primes_upto(nt.integer_root(X, a)):
            out.append((q**a, q, a))
        a += 1
    out.sort()
    return out


def analyse_high_power_gaps(X: int, use_native: bool = True,
                            progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    is_prime, prev_prime, next_prime = _prime_ops(use_native)
    powers = higher_powers(X)
    gaps: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for idx, (h, q, a) in enumerate(powers):
        p = prev_prime(h)
        r = next_prime(h)
        gaps.setdefault((p, r), []).append((q, a))
        if progress and idx % 100000 == 0:
            progress(f"high powers: {idx}/{len(powers)}")
    records = []
    for (p, r), members in gaps.items():
        members = list(members)
        n = math.isqrt(p) + 1
        while n * n < r:
            if is_prime(n):
                members.append((n, 2))
            n += 1
        prod = 1
        for q, _ in members:
            prod *= q
        records.append((p, r, prod, sorted(members)))
    records.sort()
    h = hashlib.sha256()
    for p, r, prod, _ in records:
        h.update(f"{p},{r},{prod}\n".encode())
    in_range = [rec for rec in records if rec[1] <= X]
    failures = [rec for rec in in_range if rec[2] >= rec[0]]
    multi = [rec for rec in records if len(rec[3]) >= 2]
    worst = sorted(in_range, key=lambda rec: rec[2] / rec[0], reverse=True)[:10]
    js = lambda recs: [[p, r, prod, [list(m) for m in mem]] for p, r, prod, mem in recs]
    return {
        "X": X,
        "prime_powers": len(powers),
        "gaps": len(records),
        "digest_sha256": h.hexdigest(),
        "failures": js(failures),
        "multi_power_gaps": js(multi),
        "worst_ratio": js(worst),
    }


# --------------------------------------------------------------------------
# Part (B): square witnesses
# --------------------------------------------------------------------------

def witness_offset_py(q: int, qn: int, ring: list[int]) -> tuple[int, int]:
    """Independent re-implementation of the native witness rule.

    Returns (offset, kind) with the witness prime = q^2 + offset.
    ring = the (up to RING) largest primes <= q, largest first.
    """
    q2 = q * q
    if q == 2:
        return 1, 0
    if q < 300:
        j = 2
        while not nt.is_prime(q2 + j):
            j += 2
        return j, 0
    nq2 = qn * qn
    for P in ring:
        if 2 * P <= qn:
            break
        m = q2 // P + 1
        if m % 2:
            m += 1
        while True:
            N = P * m + 1
            if N >= nq2:
                break
            if nt.is_prime(N):
                return N - q2, 1
            m += 2
    j = 2
    while not nt.is_prime(q2 + j):
        j += 2
    return j, 2


def scan_chunk_py(lo: int, hi: int) -> dict[str, int]:
    """Pure-Python equivalent of native.scan_squares (slow; for checking)."""
    plist = list(nt.primes_between(max(2, lo - 4000), hi + 20000))
    stats = dict(count=0, fails=0, first_fail=0, digest=nt.FNV_OFF, generic=0, last_q=0)
    for i, q in enumerate(plist):
        if q < lo:
            continue
        if q >= hi:
            break
        qn = plist[i + 1]
        ring = plist[max(0, i - RING + 1): i + 1][::-1]
        off, kind = witness_offset_py(q, qn, ring)
        stats["count"] += 1
        stats["last_q"] = q
        stats["digest"] = nt.fnv_u64(nt.fnv_u64(stats["digest"], q), off)
        if kind == 2:
            stats["generic"] += 1
        if not (q * q < q * q + off < qn * qn):
            stats["fails"] += 1
            stats["first_fail"] = stats["first_fail"] or q
    return stats


def _scan_native(args: tuple[int, int]) -> dict[str, Any]:
    lo, hi = args
    from .. import native
    t0 = time.perf_counter()
    s = native.scan_squares(lo, hi)
    return {"lo": lo, "hi": hi, "count": s["count"], "fails": s["fails"],
            "first_fail": s["first_fail"], "digest": s["digest"], "generic": s["generic"],
            "range_errors": s["range_errors"], "last_q": s["last_q"],
            "seconds": round(time.perf_counter() - t0, 3)}


def square_chunks(qmax: int, chunk: int = SQUARE_CHUNK) -> list[tuple[int, int]]:
    """Tile [2, qmax] (inclusive) into half-open chunks."""
    out, lo = [], 2
    while lo <= qmax:
        hi = min(lo + chunk, qmax + 1)
        out.append((lo, hi))
        lo = hi
    return out


def run_square_scan(qmax: int, chunk: int = SQUARE_CHUNK, workers: int | None = None,
                    checkpoint: Path | None = None,
                    progress: Callable[[str], None] | None = None) -> list[dict[str, Any]]:
    """Scan all chunks, resuming from (and appending to) a JSONL checkpoint."""
    done: dict[tuple[int, int], dict] = {}
    if checkpoint and checkpoint.exists():
        for line in checkpoint.read_text().splitlines():
            if line.strip():
                rec = json.loads(line)
                done[(rec["lo"], rec["hi"])] = rec
    todo = [c for c in square_chunks(qmax, chunk) if c not in done]
    workers = workers or max(1, (os.cpu_count() or 2))
    fh = checkpoint.open("a") if checkpoint else None
    try:
        if todo:
            with ProcessPoolExecutor(max_workers=workers) as ex:
                futs = [ex.submit(_scan_native, c) for c in todo]
                for k, f in enumerate(as_completed(futs), 1):
                    rec = f.result()
                    done[(rec["lo"], rec["hi"])] = rec
                    if fh:
                        fh.write(json.dumps(rec) + "\n")
                        fh.flush()
                    if progress and (k % 10 == 0 or k == len(todo)):
                        progress(f"square scan: {k}/{len(todo)} chunks (last hi={rec['hi']})")
    finally:
        if fh:
            fh.close()
    return [done[c] for c in square_chunks(qmax, chunk)]


# --------------------------------------------------------------------------
# Solver
# --------------------------------------------------------------------------

class Problem458(Solver):
    problem = 458
    name = "p458-lcm-prime-gaps"
    title = "lcm of $1,\\dots,p_{k+1}-1$ versus $p_k\\,\\mathrm{lcm}(1,\\dots,p_k)$"
    statement_tex = (r"Let $[1,\ldots,n]$ denote the least common multiple of $\{1,\ldots,n\}$ and "
                     r"$p_k$ the $k$-th prime. Is it true that, for all $k\geq 1$, "
                     r"\[[1,\ldots,p_{k+1}-1]< p_k[1,\ldots,p_k]?\]")
    finite_kind = "falsifiable"
    tags = ("number theory", "primes")
    references = ("ErGr80", "SorensonWebster2017", "OeSHP2014", "Pocklington1914", "BLS75", "erdosproblems458")
    quick_params = {"X": 10**12, "brute_limit": 3000, "sieve_limit": 10**6, "workers": 2}

    def run(self, X: int = 10**12, brute_limit: int = 3000, sieve_limit: int = 10**6,
            workers: int | None = None, chunk: int = SQUARE_CHUNK,
            checkpoint: str | os.PathLike | None = None, use_native: bool = True,
            progress: Callable[[str], None] | None = None) -> Result:
        params = dict(X=X, brute_limit=brute_limit, sieve_limit=sieve_limit, chunk=chunk)
        qmax = math.isqrt(X)
        with Timer() as t_small:
            brute = brute_force_lcm(brute_limit)
            brute_fail = [(p, r) for p, r, ok in brute if not ok]
            prods = gap_products_by_sieve(sieve_limit)
            sieve_fail = [(p, r, v) for (p, r), v in prods.items() if v >= p]
        with Timer() as t_high:
            high = analyse_high_power_gaps(X, use_native=use_native, progress=progress)
        with Timer() as t_sq:
            if use_native:
                chunks = run_square_scan(qmax, chunk, workers,
                                         Path(checkpoint) if checkpoint else None, progress)
            else:
                chunks = []
                for lo, hi in square_chunks(qmax, chunk):
                    s = scan_chunk_py(lo, hi)
                    chunks.append({"lo": lo, "hi": hi, **s, "range_errors": 0})
        sq_fails = [c for c in chunks if c["fails"] or c["range_errors"]]
        total_q = sum(c["count"] for c in chunks)
        generic = sum(c["generic"] for c in chunks)
        failures = brute_fail or sieve_fail or high["failures"] or sq_fails
        if high["failures"] or brute_fail or sieve_fail:
            outcome = COUNTEREXAMPLE
            summary = f"Counterexample candidate(s) found: {failures[:3]}"
        elif sq_fails:
            # A missing square witness is not itself a counterexample: it only
            # means part (B) of the certificate is incomplete there.
            outcome = "no_conclusion"
            summary = f"Square-witness scan incomplete in {len(sq_fails)} chunk(s); first: {sq_fails[0]}"
        else:
            outcome = VERIFIED_TO_BOUND
            summary = (f"The inequality holds for every k with p_(k+1) <= {X:.3e}; "
                       f"{high['prime_powers']} prime powers with exponent >= 3 located, "
                       f"{total_q} square witnesses exhibited.")
        cert = {
            "X": X,
            "brute_force": {"limit": brute_limit, "pairs": len(brute), "failures": brute_fail},
            "sieve_products": {"limit": sieve_limit, "gaps_with_powers": len(prods), "failures": sieve_fail},
            "high_powers": high,
            "squares": {"qmax": qmax, "chunk": chunk, "ring": RING, "chunks": chunks,
                        "witness_rule": ("q=2: 5; q<300: least prime > q^2; otherwise first prime "
                                         "N=P*m+1 in (q^2,q'^2), P over the 32 largest primes <= q "
                                         "(descending, stop when 2P<=q'), m even ascending; "
                                         "fallback least prime > q^2"),
                        "digest": "FNV-1a 64 over (q, offset) as little-endian u64 pairs"},
        }
        stats = {"seconds_small": round(t_small.seconds, 2), "seconds_high_powers": round(t_high.seconds, 2),
                 "seconds_squares_wall": round(t_sq.seconds, 2),
                 "cpu_seconds_squares": round(sum(c.get("seconds", 0) for c in chunks), 1),
                 "square_witnesses": total_q, "generic_fallbacks": generic,
                 "worst_ratio": high["worst_ratio"][:1]}
        return self._result(outcome, params, summary, cert, stats, frontier=float(X))

    # ------------------------------------------------------------------
    def check(self, result: Result, sample_chunks: int = 4, seed: int = 0,
              recompute_high: bool = True, time_budget: float | None = None,
              workers: int = 1) -> CheckReport:
        rep = CheckReport(True, "p458-independent-python")
        t0 = time.perf_counter()
        c = result.certificate
        X = c["X"]
        if result.outcome != VERIFIED_TO_BOUND:
            rep.note(f"outcome is {result.outcome}; checking counterexample claims")
            for p, r, prod, _ in c["high_powers"]["failures"]:
                if not (nt.is_prime(p) and nt.is_prime(r) and nt.next_prime(p) == r):
                    return rep.fail(f"({p},{r}) is not a prime gap")
            return rep
        # small ranges: literal lcm statement, recomputed from scratch
        lim = min(c["brute_force"]["limit"], 3000)
        bad = [(p, r) for p, r, ok in brute_force_lcm(lim) if not ok]
        if bad:
            return rep.fail(f"literal lcm inequality fails at {bad[:3]}")
        rep.note(f"literal lcm inequality re-verified for p_(k+1) <= {lim}")
        # cross-check the reduction itself on a range: product criterion == lcm criterion
        prods = gap_products_by_sieve(lim)
        for p, r, ok in brute_force_lcm(lim):
            if ok != (prods.get((p, r), 1) < p):
                return rep.fail(f"reduction disagrees with lcm at gap ({p},{r})")
        rep.note("reduction (product criterion) agrees with literal lcm on that range")
        # (A) recompute high-power analysis in pure Python
        if recompute_high:
            hp = analyse_high_power_gaps(X, use_native=False)
            if hp["digest_sha256"] != c["high_powers"]["digest_sha256"]:
                return rep.fail("high-power gap digest mismatch")
            if hp["failures"]:
                return rep.fail(f"high-power gap fails: {hp['failures'][:2]}")
            rep.note(f"(A) {hp['prime_powers']} prime powers / {hp['gaps']} gaps recomputed independently; digest matches")
        # (B) coverage + sampled recomputation
        sq = c["squares"]
        qmax = sq["qmax"]
        if qmax != math.isqrt(X):
            return rep.fail("qmax != isqrt(X)")
        chunks = sq["chunks"]
        expect = square_chunks(qmax, sq["chunk"])
        if [(ch["lo"], ch["hi"]) for ch in chunks] != expect:
            return rep.fail("square chunks do not tile [2, isqrt(X)]")
        if any(ch["fails"] or ch["range_errors"] for ch in chunks):
            return rep.fail("a chunk reports a missing witness")
        n_primes = sum(ch["count"] for ch in chunks)
        rep.note(f"(B) {len(chunks)} chunks tile [2, {qmax}] with {n_primes} primes, no failures reported")
        if qmax <= 2 * 10**11:
            pi = nt.prime_pi(qmax)
            if pi != n_primes:
                return rep.fail(f"witness count {n_primes} != pi({qmax}) = {pi}")
            rep.note(f"(B) witness count equals pi({qmax}) = {pi}, computed by the Lucy_Hedgehog "
                     "recursion (no sieve): every prime q <= sqrt(X) has a witness")
        rng = random.Random(seed)
        picks = [0] + rng.sample(range(1, len(chunks)), min(sample_chunks, len(chunks) - 1)) if len(chunks) > 1 else [0]
        # always include the last chunk too (largest q, where witnesses are biggest)
        if len(chunks) > 1 and len(chunks) - 1 not in picks and sample_chunks > 0:
            picks.append(len(chunks) - 1)
        if workers > 1 and len(picks) > 1:
            with ProcessPoolExecutor(max_workers=workers) as ex:
                futs = {ex.submit(scan_chunk_py, chunks[i]["lo"], chunks[i]["hi"]): i for i in picks}
                recomputed = {futs[f]: f.result() for f in as_completed(futs)}
        else:
            recomputed = {}
        for i in picks:
            if time_budget and time.perf_counter() - t0 > time_budget:
                rep.note("time budget exhausted; remaining samples skipped")
                break
            ch = chunks[i]
            s = recomputed.get(i) or scan_chunk_py(ch["lo"], ch["hi"])
            if (s["count"], s["digest"], s["fails"]) != (ch["count"], ch["digest"], 0):
                return rep.fail(f"chunk {ch['lo']}..{ch['hi']} not reproduced "
                                f"(py count={s['count']} digest={s['digest']}, cert {ch['count']} {ch['digest']})")
            rep.note(f"chunk [{ch['lo']}, {ch['hi']}) reproduced exactly: {s['count']} witnesses")
        rep.seconds = time.perf_counter() - t0
        return rep

    # ------------------------------------------------------------------
    def method_tex(self, result: Result) -> str:
        c = result.certificate
        return METHOD_TEX

    def forum_markdown(self, result: Result) -> str:
        c = result.certificate
        hp = c["high_powers"]
        st = result.stats
        X = _tex_num(c["X"])
        return (
            f"I have verified that the inequality holds for every $k$ with $p_{{k+1}} \\le {X}$, by a "
            "certificate that does not use any table of maximal prime gaps. With "
            "$\\Pi(p,r)=\\prod_{q^a\\in(p,r),\\,a\\ge2} q$ the statement for the gap $(p_k,p_{k+1})$ is "
            "$\\Pi(p_k,p_{k+1})<p_k$, and the certificate has three parts:\n\n"
            f"1. **Higher powers.** All {hp['prime_powers']:,} prime powers $q^a\\le {X}$ with $a\\ge3$ were "
            f"placed in their exact prime gaps ({hp['gaps']:,} gaps), every prime power inside each such gap "
            "(squares included) was listed, and $\\Pi<p_k$ was checked. The worst ratio is still the gap "
            "$(7,11)$ with $\\Pi=6$.\n"
            f"2. **Squares.** For every pair of consecutive primes $q<q'$ with $q\\le {c['squares']['qmax']:,}$ "
            f"a prime was exhibited in $(q^2,q'^2)$ ({st.get('square_witnesses', 0):,} witnesses), so no gap "
            "contains two prime squares. Witnesses have the form $N=Pm+1$ with $P$ a prime just below $q$ "
            "and $2P>\\sqrt N$, so each is proved prime by a Pocklington certificate (deterministic "
            "13-base Miller-Rabin, valid below $3.3\\cdot 10^{24}$, as fallback).\n"
            "3. **Everything else.** Any other gap holds at most one prime square $q^2$, so "
            "$\\Pi\\le q<p_k$."
            + ("\n\nCompared with the $10^{20}$ verification above, this extends the range and does not "
               "depend on the (unrefereed) distributed prime gap search above $4\\cdot10^{18}$."
               if c["X"] > 10**20 else "")
        )

    def abstract_tex(self, result: Result) -> str:
        c = result.certificate
        return (r"Erd\H{o}s and Graham asked whether $\operatorname{lcm}(1,\ldots,p_{k+1}-1)<"
                r"p_k\operatorname{lcm}(1,\ldots,p_k)$ for every $k$, where $p_k$ is the $k$-th prime. "
                rf"We verify this for all $k$ with $p_{{k+1}}\le {_tex_num(c['X'])}$. The proof is "
                r"self-contained: it locates every prime power with exponent at least $3$ below the "
                r"bound exactly and exhibits a Pocklington-certified prime between every pair of "
                r"consecutive prime squares, so it does not rely on tables of maximal prime gaps.")

    def results_tex(self, result: Result) -> str:
        c = result.certificate
        hp = c["high_powers"]
        st = result.stats
        cdot = " \\cdot "
        rows = "\n".join(
            "$(%d,\\,%d)$ & $%s$ & $%d$ \\\\" % (p, r, cdot.join(f"{q}^{{{a}}}" for q, a in mem), prod)
            for p, r, prod, mem in hp["worst_ratio"][:6])
        return fill(RESULTS_TEX,
            X=_tex_num(c["X"]), npow=hp["prime_powers"], ngaps=hp["gaps"],
            nsq=st.get("square_witnesses", 0), generic=st.get("generic_fallbacks", 0),
            qmax=c["squares"]["qmax"], nchunks=len(c["squares"]["chunks"]),
            cpu=f"{st.get('cpu_seconds_squares', 0) / 3600:.1f}", rows=rows,
            nmulti=len(hp["multi_power_gaps"]), brute=c["brute_force"]["limit"],
        )


def fill(template: str, **kw: Any) -> str:
    """Substitute @@key@@ placeholders (LaTeX-friendly, unlike str.format)."""
    for k, v in kw.items():
        template = template.replace(f"@@{k}@@", str(v))
    return template


def _tex_num(x: int) -> str:
    e = int(math.floor(math.log10(x)))
    m = x / 10**e
    return f"10^{{{e}}}" if abs(m - 1) < 1e-12 else f"{m:.3g}\\cdot 10^{{{e}}}"


METHOD_TEX = r"""
\paragraph{Reduction.} For consecutive primes $p<r$ the primes dividing
$[1,\ldots,r-1]/[1,\ldots,p]$ are exactly the bases $q$ of prime powers
$q^a$ ($a\ge 2$) in the open interval $(p,r)$, each contributing one factor
$q$ per such power. Hence the inequality for the gap $(p_k,p_{k+1})$ is
equivalent to $\Pi(p_k,p_{k+1})<p_k$, where $\Pi(p,r)=\prod_{q^a\in(p,r)}q$.
(This reformulation also appears in the forum discussion of the problem.)

\paragraph{Certificate.} We prove the statement for all $k$ with
$p_{k+1}\le X$ without using any table of maximal prime gaps:
\begin{enumerate}
\item[(A)] For every prime power $h=q^a\le X$ with $a\ge 3$ we determine the
enclosing gap $(p,r)\ni h$ exactly (deterministic primality testing of
every integer between), list \emph{all} prime powers inside it, squares
included, and verify $\Pi(p,r)<p$.
\item[(B)] For every pair of consecutive primes $q<q'$ with $q\le\sqrt{X}$ we
exhibit a prime in $(q^2,q'^2)$. Consequently no prime gap contains two
prime squares.
\item[(C)] A gap with $r\le X$ containing no prime power of exponent $\ge3$
thus contains at most one prime square $q^2$, so $\Pi(p,r)\le q<p$ (there
is a prime in $(q,q^2)$ by Bertrand's postulate).
\end{enumerate}

\paragraph{Primality.} All primality decisions use either the Miller--Rabin
test with the first 13 prime bases, which is deterministic below
$3.317\cdot10^{24}$ \cite{SorensonWebster2017}, or a Pocklington--Lehmer
certificate \cite{Pocklington1914,BLS75}: the witnesses in (B) are chosen of
the form $N=Pm+1$ with $P$ one of the 32 largest primes $\le q$ and $m$ even,
so that $F=2P>\sqrt N$ is a completely factored divisor of $N-1$ and a single
base $a$ with $a^{N-1}\equiv1$, $\gcd(a^{(N-1)/P}-1,N)=\gcd(a^{(N-1)/2}-1,N)=1$
proves $N$ prime. Compositeness is only ever asserted from an explicit failed
strong-probable-prime test, which is a proof.

\paragraph{Independent checking.} The search is implemented in C (two-limb
Montgomery arithmetic). A separate pure-Python implementation, sharing no
code with it, (i) re-verifies the literal lcm inequality and the reduction on
an initial range, (ii) recomputes part (A) in full and compares a SHA-256
digest of all gap records, and (iii) recomputes randomly sampled chunks of
part (B), comparing a 64-bit FNV-1a digest of the entire witness sequence.
The witness rule is a pure function of $(q,q')$, so agreement of digests means
both implementations produced identical witnesses.
"""

RESULTS_TEX = r"""
\begin{theorem}
For every $k$ with $p_{k+1}\le @@X@@$,
\[[1,\ldots,p_{k+1}-1]<p_k\,[1,\ldots,p_k].\]
\end{theorem}

Part (A) located $@@npow@@$ prime powers with exponent $\ge3$, lying in
$@@ngaps@@$ distinct prime gaps, of which $@@nmulti@@$ contain more than one prime
power. Part (B) exhibited $@@nsq@@$ witnesses (one per prime $q\le @@qmax@@$),
in $@@nchunks@@$ chunks; $@@generic@@$ of them needed the Miller--Rabin fallback
rather than a Pocklington certificate. The square scan used about
$@@cpu@@$ CPU-hours. The literal lcm inequality was additionally checked
directly for $p_{k+1}\le @@brute@@$.

The gaps with the largest ratio $\Pi(p,r)/p$ are all small:
\begin{center}
\begin{tabular}{lll}
gap $(p,r)$ & prime powers inside & $\Pi(p,r)$ \\ \hline
@@rows@@
\end{tabular}
\end{center}
"""
