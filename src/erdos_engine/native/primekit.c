/*
 * primekit.c -- small, self-contained number-theory kernels for erdos_engine.
 *
 * Everything here works on unsigned 128-bit integers using two-limb
 * Montgomery arithmetic, so moduli up to 2^127 are supported.  Primality is
 * decided by the Miller-Rabin test with the first 13 prime bases, which is
 * deterministic for n < 3317044064679887385961981 (Sorenson & Webster, 2015).
 * Larger inputs are rejected with a sentinel (-1) rather than answered
 * probabilistically.
 *
 * The file is compiled into a shared library and driven from Python via
 * ctypes (see erdos_engine/native/__init__.py).  128-bit values cross the FFI
 * boundary as (hi, lo) pairs of uint64.
 */
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

typedef unsigned __int128 u128;
typedef uint64_t u64;

/* psi_13: smallest strong pseudoprime to all of the first 13 prime bases. */
static const u128 PSI13 =
    (((u128)179817ULL) << 64) | (u128)5885577656943027709ULL; /* 3317044064679887385961981 */

static const u64 BASES[13] = {2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41};

/* ---------------------------------------------------------------- 256-bit */

static inline void mul_full(u128 a, u128 b, u128 *hi, u128 *lo) {
    u64 a0 = (u64)a, a1 = (u64)(a >> 64);
    u64 b0 = (u64)b, b1 = (u64)(b >> 64);
    u128 p00 = (u128)a0 * b0;
    u128 p01 = (u128)a0 * b1;
    u128 p10 = (u128)a1 * b0;
    u128 p11 = (u128)a1 * b1;
    u128 mid = (p00 >> 64) + (u64)p01 + (u64)p10;
    *lo = (u128)(u64)p00 | (mid << 64);
    *hi = p11 + (p01 >> 64) + (p10 >> 64) + (mid >> 64);
}

/* ------------------------------------------------------------- Montgomery */

typedef struct {
    u128 n;     /* odd modulus, n < 2^127 */
    u128 ninv;  /* -n^{-1} mod 2^128 */
    u128 r1;    /* 2^128 mod n  (Montgomery form of 1) */
} mont_t;

static inline u128 redc(const mont_t *m, u128 hi, u128 lo) {
    u128 q = lo * m->ninv;
    u128 mh, ml;
    mul_full(q, m->n, &mh, &ml);
    u128 s = lo + ml;
    u128 carry = s < lo;
    u128 t = hi + mh + carry;
    if (t >= m->n) t -= m->n;
    return t;
}

static inline u128 mont_mul(const mont_t *m, u128 a, u128 b) {
    u128 hi, lo;
    mul_full(a, b, &hi, &lo);
    return redc(m, hi, lo);
}

static void mont_init(mont_t *m, u128 n) {
    m->n = n;
    u128 x = n; /* correct to 3 bits for odd n */
    for (int i = 0; i < 7; i++) x *= (u128)2 - n * x;
    m->ninv = (u128)0 - x;
    m->r1 = ((u128)0 - n) % n;
}

/* x * a mod n for a Montgomery residue x and a small plain integer a.
 * Because (X R) a = (X a) R, the result is the Montgomery form of X a. */
static inline u128 mul_small(const mont_t *m, u128 x, u64 a) {
    u128 n = m->n, r = 0;
    for (int b = 63 - __builtin_clzll(a); b >= 0; b--) {
        r <<= 1; /* n < 2^127: no overflow */
        if (r >= n) r -= n;
        if ((a >> b) & 1) {
            r += x;
            if (r >= n) r -= n;
        }
    }
    return r;
}

/* a^e in Montgomery form, for small a: left-to-right binary powering in which
 * the multiplications are by the small base only (cheap shift/add chains). */
static u128 mont_pow_small(const mont_t *m, u64 a, u128 e) {
    if (e == 0) return m->r1;
    int top = 127;
    while (!((e >> top) & 1)) top--;
    u128 x = mul_small(m, m->r1, a);
    for (int b = top - 1; b >= 0; b--) {
        x = mont_mul(m, x, x);
        if ((e >> b) & 1) x = mul_small(m, x, a);
    }
    return x;
}

/* b^e in Montgomery form for an arbitrary Montgomery residue b. */
static u128 mont_pow(const mont_t *m, u128 b, u128 e) {
    u128 r = m->r1;
    while (e) {
        if (e & 1) r = mont_mul(m, r, b);
        b = mont_mul(m, b, b);
        e >>= 1;
    }
    return r;
}

static inline u128 from_mont(const mont_t *m, u128 x) { return redc(m, 0, x); }

static u128 gcd128(u128 a, u128 b) {
    while (b) {
        u128 t = a % b;
        a = b;
        b = t;
    }
    return a;
}

/* Strong probable-prime test to base a.  Requires odd n > a, precomputed m. */
static int strong_prp(const mont_t *m, u128 d, int s, u64 a) {
    u128 n = m->n;
    u128 one = m->r1;
    u128 minus_one = n - one;
    u128 x = mont_pow_small(m, a, d);
    if (x == one || x == minus_one) return 1;
    for (int r = 1; r < s; r++) {
        x = mont_mul(m, x, x);
        if (x == minus_one) return 1;
        if (x == one) return 0;
    }
    return 0;
}

static const u64 SMALL_PRIMES[] = {
    3,   5,   7,   11,  13,  17,  19,  23,  29,  31,  37,  41,  43,  47,  53,  59,  61,
    67,  71,  73,  79,  83,  89,  97,  101, 103, 107, 109, 113, 127, 131, 137, 139, 149,
    151, 157, 163, 167, 173, 179, 181, 191, 193, 197, 199, 211, 223, 227, 229, 233};
#define N_SMALL (sizeof(SMALL_PRIMES) / sizeof(SMALL_PRIMES[0]))

static int mr_deterministic(u128 n);

/* Returns 1 prime, 0 composite, -1 if n is outside the proven range. */
static int is_prime128(u128 n) {
    if (n < 2) return 0;
    if (n < 4) return 1;
    if ((n & 1) == 0) return 0;
    for (size_t i = 0; i < N_SMALL; i++) {
        u64 p = SMALL_PRIMES[i];
        if (n == p) return 1;
        if (n % p == 0) return 0;
    }
    if (n < (u128)233 * 233) return 1;
    return mr_deterministic(n);
}

/* Deterministic Miller-Rabin for odd n > 41 with no tiny factors assumed. */
static int mr_deterministic(u128 n) {
    if (n >= PSI13) return -1;
    mont_t m;
    mont_init(&m, n);
    u128 d = n - 1;
    int s = 0;
    while ((d & 1) == 0) { d >>= 1; s++; }
    for (int i = 0; i < 13; i++)
        if (!strong_prp(&m, d, s, BASES[i])) return 0;
    return 1;
}

/* ------------------------------------------------------------ public API */

static inline u128 mk(u64 hi, u64 lo) { return ((u128)hi << 64) | lo; }

int pk_is_prime(u64 hi, u64 lo) { return is_prime128(mk(hi, lo)); }

/* next prime strictly greater than n; out = (hi, lo). returns -1 on range error */
int pk_next_prime(u64 hi, u64 lo, u64 *out_hi, u64 *out_lo) {
    u128 n = mk(hi, lo);
    if (n < 2) { *out_hi = 0; *out_lo = 2; return 0; }
    u128 c = n + 1;
    if ((c & 1) == 0 && c != 2) c++;
    for (;; c += 2) {
        int r = is_prime128(c);
        if (r < 0) return -1;
        if (r) { *out_hi = (u64)(c >> 64); *out_lo = (u64)c; return 0; }
    }
}

/* previous prime strictly less than n (n > 2). returns -1 on error */
int pk_prev_prime(u64 hi, u64 lo, u64 *out_hi, u64 *out_lo) {
    u128 n = mk(hi, lo);
    if (n <= 2) return -1;
    if (n == 3) { *out_hi = 0; *out_lo = 2; return 0; }
    u128 c = n - 1;
    if ((c & 1) == 0) c--;
    for (;; c -= 2) {
        int r = is_prime128(c);
        if (r < 0) return -1;
        if (r) { *out_hi = (u64)(c >> 64); *out_lo = (u64)c; return 0; }
    }
}

/* -------------------------------------------- segmented sieve helpers */

/* Fill primes <= limit into buf (caller-sized).  Returns count. */
static size_t simple_sieve(u64 limit, u64 *buf) {
    char *is = calloc(limit + 1, 1);
    size_t cnt = 0;
    for (u64 i = 2; i <= limit; i++) {
        if (!is[i]) {
            buf[cnt++] = i;
            for (u64 j = i * i; j <= limit; j += i) is[j] = 1;
        }
    }
    free(is);
    return cnt;
}

static u64 isqrt64(u64 n) {
    u64 r = (u64)__builtin_sqrtl((long double)n);
    while (r * r > n) r--;
    while ((r + 1) * (r + 1) <= n) r++;
    return r;
}

/*
 * Erdos #458 square scan.
 *
 * For every pair of consecutive primes q < q' with q in [qlo, qhi), find a
 * prime witness r in (q^2, q'^2) and record the offset r - q^2.  The pair "fails" if
 * r >= q'^2, i.e. the open interval (q^2, q'^2) contains no prime -- which
 * would put both prime squares inside a single prime gap.
 *
 * The witness r is chosen by square_witness() below (Pocklington-certified
 * when possible).  Results:
 *   stats[0] = number of primes q processed
 *   stats[1] = number of failing pairs
 *   stats[2] = maximal offset r - q^2 seen
 *   stats[3] = q attaining the maximal offset
 *   stats[4] = first failing q (0 if none)
 *   stats[5] = 64-bit FNV-1a digest of the sequence (q, offset) in order
 *   stats[6] = number of q with primality outside proven range (must be 0)
 *   stats[7] = last prime q processed
 *   stats[8] = number of q whose witness needed the generic (MR) fallback
 * The digest lets an independent implementation confirm it computed the
 * identical witness sequence.
 */
#define FNV_OFF 1469598103934665603ULL
#define FNV_PRIME 1099511628211ULL

static inline u64 fnv_u64(u64 h, u64 v) {
    for (int i = 0; i < 8; i++) {
        h ^= (v >> (8 * i)) & 0xff;
        h *= FNV_PRIME;
    }
    return h;
}

/* Odd primes used to pre-sieve the window above q^2 before Miller-Rabin. */
#define N_TD 48
#define WIN 384 /* odd candidates q^2 + 2, q^2 + 4, ..., q^2 + 2*WIN */

/* least j > 0 (j even) such that q^2 + j is prime, for odd prime q.
 * qmod[i] = q mod td[i].  Returns 0 if a primality query left the proven
 * range (caller records this as an error). */
static u64 least_prime_offset(u128 q2, const uint32_t *td, const uint32_t *qmod) {
    unsigned char comp[WIN];
    memset(comp, 0, sizeof comp);
    for (int i = 0; i < N_TD; i++) {
        uint32_t p = td[i];
        uint32_t r = (qmod[i] * qmod[i]) % p;  /* q^2 mod p  (p < 2^16) */
        /* want q^2 + 2k == 0 (mod p), k >= 1:  k == -r * inv2 (mod p) */
        uint32_t k = (r == 0) ? 0 : ((p - r) * ((p + 1) / 2)) % p;
        if (k == 0) k = p;
        for (u64 t = k; t <= WIN; t += p) comp[t - 1] = 1;
    }
    for (u64 t = 1; t <= WIN; t++) {
        if (comp[t - 1]) continue;
        /* candidates exceed every sieving prime, so skip trial division */
        int r = mr_deterministic(q2 + 2 * t);
        if (r < 0) return 0;
        if (r) return 2 * t;
    }
    /* window exhausted (astronomically rare): continue unsieved */
    for (u64 j = 2 * WIN + 2;; j += 2) {
        int r = is_prime128(q2 + j);
        if (r < 0) return 0;
        if (r) return j;
    }
}

/*
 * Pocklington witness.  Let P be prime and N = P m + 1 with m even.  Then
 * F = 2P is a fully factored divisor of N - 1, and if F > sqrt(N) the
 * Pocklington--Lehmer criterion says N is prime as soon as some a satisfies
 *     a^(N-1) == 1,  gcd(a^((N-1)/P) - 1, N) = 1,  gcd(a^((N-1)/2) - 1, N) = 1.
 * Returns 1 if N was certified prime, 0 if shown composite, -1 if undecided
 * (the caller then falls back to deterministic Miller--Rabin).
 */
static int pocklington(u128 N, u64 P, u64 m) {
    mont_t mt;
    mont_init(&mt, N);
    u128 d = N - 1;
    int sh = 0;
    while ((d & 1) == 0) { d >>= 1; sh++; }
    if (!strong_prp(&mt, d, sh, 2)) return 0;
    for (int i = 0; i < 13; i++) {
        u64 a = BASES[i];
        u128 y = mont_pow_small(&mt, a, (u128)m);            /* a^((N-1)/P) */
        u128 t = mont_pow(&mt, y, (u128)P);                  /* a^(N-1)     */
        if (t != mt.r1) return 0;                            /* Fermat witness */
        u128 yn = from_mont(&mt, y);
        if (gcd128(yn == 0 ? N : yn - 1, N) != 1) continue;
        u128 z = mont_pow_small(&mt, a, (u128)P * (m / 2));  /* a^((N-1)/2) */
        u128 zn = from_mont(&mt, z);
        if (gcd128(zn == 0 ? N : zn - 1, N) != 1) continue;
        return 1;
    }
    return -1;
}

#define RING 32

/*
 * Witness for the consecutive primes (q, q').  ring[0..nring) holds q and the
 * primes just below it, largest first.  Scanning P in that order and, for each
 * P, even m in increasing order, take the first prime N = P m + 1 lying in
 * (q^2, q'^2) with 2P > q'.  If none exists, fall back to the least prime
 * > q^2.  The witness is a pure function of (q, q') -- an independent
 * implementation following the same rule must reproduce it exactly.
 *
 * Returns the offset N - q^2 (0 on range error); *kind = 1 (Pocklington) or
 * 2 (generic Miller--Rabin fallback).
 */
static u64 square_witness(u64 q, u64 qn, const u64 *ring, int nring,
                          const uint32_t *td, const uint32_t *qmod, int *kind) {
    u128 q2 = (u128)q * q;
    u128 nq2 = (u128)qn * qn;
    for (int k = 0; k < nring; k++) {
        u64 P = ring[k];
        if (2 * P <= qn) break;
        uint32_t pm[N_TD];
        for (int i = 0; i < N_TD; i++) pm[i] = (uint32_t)(P % td[i]);
        u64 m = (u64)(q2 / P) + 1;           /* least m with P m + 1 > q^2 */
        if (m & 1) m++;
        for (;; m += 2) {
            u128 N = (u128)P * m + 1;
            if (N >= nq2) break;
            int bad = 0;
            for (int i = 0; i < N_TD; i++) {
                uint32_t p = td[i];
                if (((uint64_t)pm[i] * (m % p) + 1) % p == 0) { bad = 1; break; }
            }
            if (bad) continue;
            int r = pocklington(N, P, m);
            if (r < 0) r = mr_deterministic(N);
            if (r < 0) return 0;
            if (r == 1) { *kind = 1; return (u64)(N - q2); }
        }
    }
    *kind = 2;
    return least_prime_offset(q2, td, qmod);
}

int pk_scan_squares(u64 qlo, u64 qhi, u64 *stats) {
    memset(stats, 0, 9 * sizeof(u64));
    stats[5] = FNV_OFF;
    if (qhi <= qlo) return 0;
    u64 hi_ext = qhi + 20000; /* room for the prime following the last q */
    u64 root = isqrt64(hi_ext) + 1;
    if (root < 1000) root = 1000;
    u64 *base = malloc(sizeof(u64) * (root / 2 + 100));
    size_t nb = simple_sieve(root, base);

    uint32_t td[N_TD], qmod[N_TD];
    for (int i = 0; i < N_TD; i++) td[i] = (uint32_t)base[i + 1]; /* odd primes 3.. */
    int qmod_valid = 0;
    u64 qmod_of = 0;
    u64 ring[RING];
    int nring = 0;

    const u64 SEG = 1 << 22;
    char *seg = malloc(SEG);
    u64 prev_q = 0;
    int have_prev = 0;
    /* start below qlo so the ring of preceding primes is full */
    u64 seg_lo = qlo > 4000 ? qlo - 4000 : 2;
    int done = 0;
    while (!done && seg_lo < hi_ext) {
        u64 seg_hi = seg_lo + SEG; /* exclusive */
        if (seg_hi > hi_ext) seg_hi = hi_ext;
        memset(seg, 0, SEG);
        for (size_t i = 0; i < nb; i++) {
            u64 p = base[i];
            if (p * p >= seg_hi) break;
            u64 start = (seg_lo + p - 1) / p * p;
            if (start < p * p) start = p * p;
            for (u64 j = start; j < seg_hi; j += p) seg[j - seg_lo] = 1;
        }
        for (u64 x = seg_lo; x < seg_hi; x++) {
            if (seg[x - seg_lo]) continue;
            /* x is prime */
            if (have_prev) {
                u128 q2 = (u128)prev_q * prev_q;
                u128 nq2 = (u128)x * x;
                u64 off;
                if (prev_q == 2) {
                    off = 1; /* 4 + 1 = 5 is prime */
                } else if (prev_q < 300) {
                    /* tiny q: the sieve primes may coincide with candidates */
                    u64 j = 2;
                    for (;; j += 2) if (is_prime128(q2 + j) == 1) break;
                    off = j;
                } else {
                    /* maintain q mod p incrementally across consecutive q */
                    if (qmod_valid && prev_q - qmod_of < 1000) {
                        uint32_t g = (uint32_t)(prev_q - qmod_of);
                        for (int i = 0; i < N_TD; i++) qmod[i] = (qmod[i] + g) % td[i];
                    } else {
                        for (int i = 0; i < N_TD; i++) qmod[i] = (uint32_t)(prev_q % td[i]);
                    }
                    qmod_valid = 1;
                    qmod_of = prev_q;
                    int kind = 0;
                    off = square_witness(prev_q, x, ring, nring, td, qmod, &kind);
                    if (off == 0) stats[6]++;
                    if (kind == 2) stats[8]++;
                }
                stats[0]++;
                stats[7] = prev_q;
                stats[5] = fnv_u64(fnv_u64(stats[5], prev_q), off);
                if (off > stats[2]) { stats[2] = off; stats[3] = prev_q; }
                if (off == 0 || q2 + off >= nq2) {
                    stats[1]++;
                    if (!stats[4]) stats[4] = prev_q;
                }
                have_prev = 0;
            }
            if (x >= qhi) { done = 1; break; }
            /* ring buffer of recent primes, largest first */
            memmove(ring + 1, ring, sizeof(u64) * (RING - 1));
            ring[0] = x;
            if (nring < RING) nring++;
            if (x >= qlo) {
                have_prev = 1;
                prev_q = x;
            }
        }
        seg_lo = seg_hi;
    }
    free(seg);
    free(base);
    return 0;
}
