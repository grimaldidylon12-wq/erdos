"""On-disk run records with integrity manifests.

A run directory contains
    result.json    the Result (including the certificate)
    check.json     the independent CheckReport
    manifest.json  SHA-256 of every other file + engine version
Any modification of result.json or check.json after the fact is detected by
`verify_manifest`, and publication tooling refuses tampered runs.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from . import __version__
from .solvers.base import CheckReport, Result


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def run_id(result: Result) -> str:
    stamp = result.created.replace(":", "").replace("-", "").replace("+0000", "Z")[:15]
    return f"p{result.problem}-{result.outcome}-{stamp}"


def save_run(result: Result, check: CheckReport | None, outdir: Path) -> Path:
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "result.json").write_text(json.dumps(result.to_dict(), indent=1, sort_keys=True))
    if check is not None:
        (outdir / "check.json").write_text(json.dumps(asdict(check), indent=1, sort_keys=True))
    write_manifest(outdir)
    return outdir


def write_manifest(outdir: Path) -> dict:
    files = {p.name: sha256_file(p) for p in sorted(Path(outdir).iterdir())
             if p.is_file() and p.name != "manifest.json"}
    man = {"engine_version": __version__, "files": files}
    (Path(outdir) / "manifest.json").write_text(json.dumps(man, indent=1, sort_keys=True))
    return man


def verify_manifest(outdir: Path) -> list[str]:
    """Return a list of problems (empty if the run directory is intact)."""
    outdir = Path(outdir)
    mpath = outdir / "manifest.json"
    if not mpath.exists():
        return ["manifest.json missing"]
    man = json.loads(mpath.read_text())
    errs = []
    for name, digest in man.get("files", {}).items():
        p = outdir / name
        if not p.exists():
            errs.append(f"{name} missing")
        elif sha256_file(p) != digest:
            errs.append(f"{name} modified (sha256 mismatch)")
    for p in outdir.iterdir():
        if p.is_file() and p.name not in man.get("files", {}) and p.name != "manifest.json":
            errs.append(f"{p.name} not covered by manifest")
    return errs


def load_run(outdir: Path) -> tuple[Result, CheckReport | None]:
    outdir = Path(outdir)
    result = Result.from_dict(json.loads((outdir / "result.json").read_text()))
    cp = outdir / "check.json"
    check = CheckReport(**json.loads(cp.read_text())) if cp.exists() else None
    return result, check
