"""ctypes bridge to primekit.c, compiled on first use.

The shared library is cached under $ERDOS_ENGINE_CACHE (default
~/.cache/erdos_engine) keyed by a hash of the C source, so edits trigger a
rebuild.  If no C compiler is available, `available()` returns False and
callers fall back to the pure-Python implementations in erdos_engine.nt.
"""
from __future__ import annotations

import ctypes
import hashlib
import os
import shutil
import subprocess
import threading
from pathlib import Path

_SRC = Path(__file__).with_name("primekit.c")
_lock = threading.Lock()
_lib = None
_err: str | None = None

U64 = ctypes.c_uint64
MASK64 = (1 << 64) - 1

#: Miller-Rabin with the first 13 primes is proven only below this bound.
PSI13 = 3317044064679887385961981


def _cache_dir() -> Path:
    d = Path(os.environ.get("ERDOS_ENGINE_CACHE", Path.home() / ".cache" / "erdos_engine"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _build() -> ctypes.CDLL:
    src = _SRC.read_bytes()
    tag = hashlib.sha256(src).hexdigest()[:16]
    so = _cache_dir() / f"primekit-{tag}.so"
    if not so.exists():
        cc = os.environ.get("CC") or shutil.which("gcc") or shutil.which("cc") or shutil.which("clang")
        if not cc:
            raise RuntimeError("no C compiler found")
        tmp = so.with_suffix(f".{os.getpid()}.tmp")
        cmd = [cc, "-O3", "-shared", "-fPIC", "-o", str(tmp), str(_SRC), "-lm"]
        if os.environ.get("ERDOS_ENGINE_NATIVE_ARCH", "1") == "1":
            cmd.insert(2, "-march=native")
        subprocess.run(cmd, check=True, capture_output=True)
        os.replace(tmp, so)
    lib = ctypes.CDLL(str(so))
    lib.pk_is_prime.argtypes = [U64, U64]
    lib.pk_is_prime.restype = ctypes.c_int
    for name in ("pk_next_prime", "pk_prev_prime"):
        fn = getattr(lib, name)
        fn.argtypes = [U64, U64, ctypes.POINTER(U64), ctypes.POINTER(U64)]
        fn.restype = ctypes.c_int
    lib.pk_scan_squares.argtypes = [U64, U64, ctypes.POINTER(U64)]
    lib.pk_scan_squares.restype = ctypes.c_int
    return lib


def lib() -> ctypes.CDLL:
    global _lib, _err
    if _lib is None:
        with _lock:
            if _lib is None:
                if os.environ.get("ERDOS_ENGINE_NO_NATIVE") == "1":
                    _err = "disabled by ERDOS_ENGINE_NO_NATIVE"
                    raise RuntimeError(_err)
                try:
                    _lib = _build()
                except Exception as e:  # pragma: no cover - environment dependent
                    _err = str(e)
                    raise
    return _lib


def available() -> bool:
    try:
        lib()
        return True
    except Exception:
        return False


def _split(n: int) -> tuple[int, int]:
    if n < 0 or n >> 128:
        raise ValueError("argument must be in [0, 2^128)")
    return n >> 64, n & MASK64


def is_prime(n: int) -> bool:
    r = lib().pk_is_prime(*_split(n))
    if r < 0:
        raise ValueError(f"{n} is beyond the proven deterministic range")
    return bool(r)


def _step(fn, n: int) -> int:
    hi, lo = U64(), U64()
    if fn(*_split(n), ctypes.byref(hi), ctypes.byref(lo)) != 0:
        raise ValueError(f"no proven answer near {n}")
    return (hi.value << 64) | lo.value


def next_prime(n: int) -> int:
    """Least prime > n (deterministic)."""
    return _step(lib().pk_next_prime, n)


def prev_prime(n: int) -> int:
    """Greatest prime < n, for n > 2 (deterministic)."""
    if n <= 2:
        raise ValueError("no prime below 2")
    return _step(lib().pk_prev_prime, n)


SCAN_FIELDS = (
    "count", "fails", "max_offset", "argmax_offset", "first_fail",
    "digest", "range_errors", "last_q", "generic",
)


def scan_squares(qlo: int, qhi: int) -> dict:
    """Run the #458 square-witness scan over primes q in [qlo, qhi)."""
    stats = (U64 * 9)()
    lib().pk_scan_squares(qlo, qhi, stats)
    return dict(zip(SCAN_FIELDS, (int(x) for x in stats)))
