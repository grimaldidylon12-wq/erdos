"""Command-line interface: `erdos-engine <command> ...`.

    sync                      refresh the problem database and show status counts
    triage [--limit N]        rank open problems by amenability to this engine
    solvers                   list available solvers
    dossier N                 prior work: statement, forum frontier claims, AI disclosures
    run N [k=v ...]           run solver N, check it independently, save a run directory
    check RUN_DIR             re-run the independent checker (use --thorough for more samples)
    publish RUN_DIR           build the publication packet (gated on the check)
    demo                      quick run + check of every solver
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import time
from dataclasses import asdict
from pathlib import Path

from . import __version__


def _parse_kv(items: list[str]) -> dict:
    out = {}
    for it in items:
        if "=" not in it:
            raise SystemExit(f"parameter {it!r} must look like key=value")
        k, v = it.split("=", 1)
        m = re.fullmatch(r"\s*(\d+)\s*\*\*\s*(\d+)\s*", v)
        if m:
            out[k] = int(m.group(1)) ** int(m.group(2))
            continue
        try:
            out[k] = ast.literal_eval(v)
        except (ValueError, SyntaxError):
            if "e" in v.lower():
                try:
                    out[k] = int(float(v)) if float(v).is_integer() else float(v)
                    continue
                except ValueError:
                    pass
            out[k] = v
    return out


def _log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, file=sys.stderr, flush=True)


def cmd_sync(a) -> int:
    from .catalog import Catalog
    cat = Catalog(refresh=True)
    print(f"{len(cat.problems)} problems")
    for k, v in cat.counts().items():
        print(f"  {k:18s} {v}")
    return 0


def cmd_triage(a) -> int:
    from .catalog import Catalog, triage
    from .solvers import REGISTRY
    rows = triage(Catalog(), REGISTRY)
    for r in rows[: a.limit]:
        print(f"#{r['number']:<5} score={r['score']:<2} {r['status']:12s} {'; '.join(r['reasons'])}")
    return 0


def cmd_solvers(a) -> int:
    from .solvers import REGISTRY
    for n, cls in sorted(REGISTRY.items()):
        print(f"#{n:<5} {cls.name:32s} {cls.finite_kind:12s} quick={cls.quick_params}")
    return 0


def _dossier(n: int, arxiv: bool = False):
    from .catalog import Catalog
    from .literature import build_dossier
    from .solvers import REGISTRY
    rx = getattr(REGISTRY.get(n), "frontier_regex", None)
    return build_dossier(n, Catalog(), with_arxiv=arxiv, frontier_regex=rx)


def cmd_dossier(a) -> int:
    d = _dossier(a.problem, a.arxiv)
    if a.json:
        print(json.dumps(d.to_dict(), indent=1, default=str))
        return 0
    print(f"Problem #{d.number}  status={d.status}  OEIS={d.oeis}")
    print("Statement:", d.statement)
    print(f"Forum comments: {len(d.comments)} ({d.ai_disclosures} mention AI tools)")
    f = d.frontier
    if f:
        print(f"Largest numeric claim found: {f.value:.4g}  [{f.source}, {f.author}, {f.when}]")
        print("   context:", f.text[:300])
    else:
        print("No numeric frontier claims found (a human should still check).")
    for c in d.comments[:5]:
        print(f"- {c['author']} ({c['when']}): {c['text'][:160]}")
    return 0


def cmd_run(a) -> int:
    from .certify import run_id, save_run
    from .solvers import get_solver
    solver = get_solver(a.problem)
    params = dict(solver.quick_params) if a.quick else {}
    params.update(_parse_kv(a.params))
    if "progress" in solver.run.__code__.co_varnames:
        params.setdefault("progress", _log)
    _log(f"running {solver.name} with {params}")
    res = solver.run(**params)
    _log(f"{res.outcome}: {res.summary}")
    _log("independent check ...")
    rep = solver.check(res)
    _log(f"check {'PASSED' if rep.ok else 'FAILED'} in {rep.seconds:.1f}s")
    for d in rep.details:
        _log("  " + d)
    out = Path(a.out) if a.out else Path("results") / f"p{a.problem}" / run_id(res)
    save_run(res, rep, out)
    print(out)
    return 0 if rep.ok else 2


def cmd_check(a) -> int:
    from .certify import load_run, save_run, verify_manifest
    from .solvers import get_solver
    errs = verify_manifest(Path(a.run_dir))
    if errs:
        print("INTEGRITY FAILURE:", "; ".join(errs))
        return 3
    res, _ = load_run(Path(a.run_dir))
    solver = get_solver(res.problem)
    kw = {}
    if a.thorough and res.problem == 458:
        import os
        kw = {"sample_chunks": 24, "workers": os.cpu_count() or 1}
    rep = solver.check(res, **kw)
    print("PASSED" if rep.ok else "FAILED")
    for d in rep.details:
        print(" ", d)
    if a.update:
        save_run(res, rep, Path(a.run_dir))
    return 0 if rep.ok else 2


def cmd_publish(a) -> int:
    from .certify import load_run
    from .literature import assess_novelty
    from .publish import Author, PublicationBlocked, build_packet
    res, _ = load_run(Path(a.run_dir))
    dossier = novelty = None
    if not a.offline:
        try:
            dossier = _dossier(res.problem)
            novelty = assess_novelty(res.frontier, res.settles_problem, dossier,
                                     prior_override=a.prior, prior_note=a.prior_note or "")
        except Exception as e:  # network trouble should not block a draft
            _log(f"could not build dossier ({e}); novelty will be marked unknown")
    authors = [Author(n.strip()) for n in a.author] if a.author else None
    out = Path(a.out) if a.out else Path(a.run_dir) / "packet"
    try:
        rep = build_packet(Path(a.run_dir), out, authors, dossier, novelty, compile=not a.no_pdf)
    except PublicationBlocked as e:
        print("BLOCKED:", e)
        return 4
    print(f"packet written to {rep.out_dir} (pdf: {rep.pdf_built})")
    print("venue:", rep.venue)
    for w in rep.warnings:
        print("warning:", w)
    return 0


def cmd_demo(a) -> int:
    from .solvers import REGISTRY
    ok = True
    for n, cls in sorted(REGISTRY.items()):
        s = cls()
        t = time.perf_counter()
        r = s.run(**s.quick_params)
        c = s.check(r)
        ok &= c.ok
        print(f"#{n:<4} {r.outcome:18s} check={'ok' if c.ok else 'FAIL'} {time.perf_counter() - t:6.1f}s  {r.summary[:90]}")
    return 0 if ok else 2


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="erdos-engine", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sync").set_defaults(fn=cmd_sync)
    t = sub.add_parser("triage")
    t.add_argument("--limit", type=int, default=30)
    t.set_defaults(fn=cmd_triage)
    sub.add_parser("solvers").set_defaults(fn=cmd_solvers)
    d = sub.add_parser("dossier")
    d.add_argument("problem", type=int)
    d.add_argument("--json", action="store_true")
    d.add_argument("--arxiv", action="store_true")
    d.set_defaults(fn=cmd_dossier)
    r = sub.add_parser("run")
    r.add_argument("problem", type=int)
    r.add_argument("params", nargs="*", help="solver parameters as key=value (e.g. X=1e15)")
    r.add_argument("--quick", action="store_true", help="start from the solver's quick parameters")
    r.add_argument("--out")
    r.set_defaults(fn=cmd_run)
    c = sub.add_parser("check")
    c.add_argument("run_dir")
    c.add_argument("--thorough", action="store_true")
    c.add_argument("--update", action="store_true", help="store the new check report")
    c.set_defaults(fn=cmd_check)
    pb = sub.add_parser("publish")
    pb.add_argument("run_dir")
    pb.add_argument("--out")
    pb.add_argument("--author", action="append", help="author name (repeatable)")
    pb.add_argument("--offline", action="store_true", help="skip the prior-work dossier")
    pb.add_argument("--no-pdf", action="store_true")
    pb.add_argument("--prior", type=float, help="override the prior frontier (after reading the thread)")
    pb.add_argument("--prior-note", help="source description for --prior")
    pb.set_defaults(fn=cmd_publish)
    sub.add_parser("demo").set_defaults(fn=cmd_demo)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
