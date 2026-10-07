"""Run storage, integrity, publication packet and its gates, CLI."""
import json
import shutil
import tarfile

import pytest

from erdos_engine import certify, publish
from erdos_engine.cli import _parse_kv, main
from erdos_engine.literature import assess_novelty, build_dossier
from erdos_engine.publish import Author, PublicationBlocked, build_packet
from erdos_engine.solvers import get_solver
from erdos_engine.solvers.base import CheckReport


@pytest.fixture(scope="module")
def run458(tmp_path_factory):
    s = get_solver(458)
    r = s.run(X=10**10, brute_limit=500, sieve_limit=10**4, workers=1)
    rep = s.check(r, sample_chunks=1)
    d = tmp_path_factory.mktemp("run")
    certify.save_run(r, rep, d)
    return d


def _copy(src, tmp_path):
    dst = tmp_path / "run"
    shutil.copytree(src, dst)
    return dst


def test_roundtrip(run458):
    r, c = certify.load_run(run458)
    assert r.problem == 458 and c.ok
    assert certify.verify_manifest(run458) == []


def test_manifest_detects_edit(run458, tmp_path):
    d = _copy(run458, tmp_path)
    j = json.loads((d / "result.json").read_text())
    j["frontier"] = 1e30
    (d / "result.json").write_text(json.dumps(j))
    assert any("modified" in e for e in certify.verify_manifest(d))


def test_manifest_detects_extra_and_missing(run458, tmp_path):
    d = _copy(run458, tmp_path)
    (d / "extra.txt").write_text("x")
    (d / "check.json").unlink()
    errs = certify.verify_manifest(d)
    assert any("not covered" in e for e in errs) and any("missing" in e for e in errs)


def test_packet_full(run458, tmp_path, catalog):
    r, _ = certify.load_run(run458)
    d = build_dossier(458, catalog)
    nv = assess_novelty(r.frontier, r.settles_problem, d)
    rep = build_packet(run458, tmp_path / "pk", [Author("Ada Lovelace", "Analytical Engines Ltd")], d, nv,
                       compile=shutil.which("pdflatex") is not None, today="2026-10-06")
    out = tmp_path / "pk"
    for f in ("paper/main.tex", "paper/refs.bib", "paper/arxiv-submission.tar.gz", "forum_comment.md",
              "database_update.md", "oeis.md", "data/result.json", "data/check.json", "data/.zenodo.json",
              "data/CITATION.cff", "CHECKLIST.md", "novelty.json"):
        assert (out / f).exists(), f
    tex = (out / "paper/main.tex").read_text()
    assert "Ada Lovelace" in tex and "@@" not in tex and "Use of AI tools" in tex
    assert "bhowerton" in tex  # prior work attributed
    assert "replication" in (out / "CHECKLIST.md").read_text()
    assert "No change warranted" in (out / "database_update.md").read_text()
    assert "AI-usage disclosure" in (out / "forum_comment.md").read_text()
    oeis = (out / "oeis.md").read_text()
    assert "forbids" in oeis and "%N" not in oeis and "%S" not in oeis
    z = json.loads((out / "data/.zenodo.json").read_text())
    assert z["creators"][0]["name"] == "Ada Lovelace" and z["upload_type"] == "dataset"
    if shutil.which("pdflatex"):
        assert rep.pdf_built and (out / "paper/main.pdf").stat().st_size > 10000
        names = tarfile.open(out / "paper/arxiv-submission.tar.gz").getnames()
        assert set(names) == {"main.tex", "refs.bib", "main.bbl"}
    assert "Independent replication" in rep.venue


def test_packet_blocks_failed_check(run458, tmp_path):
    d = _copy(run458, tmp_path)
    r, c = certify.load_run(d)
    certify.save_run(r, CheckReport(False, "x", ["FAIL: boom"]), d)
    with pytest.raises(PublicationBlocked, match="FAILED"):
        build_packet(d, tmp_path / "pk", compile=False)


def test_packet_blocks_tampering(run458, tmp_path):
    d = _copy(run458, tmp_path)
    (d / "result.json").write_text((d / "result.json").read_text().replace('"X": 10000000000', '"X": 10000000001'))
    with pytest.raises(PublicationBlocked, match="integrity"):
        build_packet(d, tmp_path / "pk", compile=False)


def test_packet_blocks_missing_check(run458, tmp_path):
    d = _copy(run458, tmp_path)
    (d / "check.json").unlink()
    certify.write_manifest(d)
    with pytest.raises(PublicationBlocked, match="check"):
        build_packet(d, tmp_path / "pk", compile=False)


def test_packet_blocks_inconclusive(run458, tmp_path):
    d = _copy(run458, tmp_path)
    r, c = certify.load_run(d)
    r.outcome = "no_conclusion"
    certify.save_run(r, c, d)
    with pytest.raises(PublicationBlocked, match="inconclusive"):
        build_packet(d, tmp_path / "pk", compile=False)


def test_counterexample_packet_proposes_status_change(run458, tmp_path):
    d = _copy(run458, tmp_path)
    r, c = certify.load_run(d)
    r.outcome = "counterexample"
    certify.save_run(r, c, d)
    rep = build_packet(d, tmp_path / "pk", compile=False, today="2026-10-06")
    db = (tmp_path / "pk/database_update.md").read_text()
    assert 'state: "disproved"' in db and "moderators" in db
    assert "SETTLES THE PROBLEM" in rep.venue


def test_sequence_packet_writes_bfile(tmp_path):
    s = get_solver(848)
    r = s.run(N=60)
    certify.save_run(r, s.check(r), tmp_path / "run")
    build_packet(tmp_path / "run", tmp_path / "pk", compile=False)
    b = (tmp_path / "pk" / "b-file-p848.txt").read_text().splitlines()
    assert b[0] == "1 0" and b[59] == "60 3"


def test_tex_helpers():
    assert publish.tex_escape("50% & $x_1$") == r"50\% \& \$x\_1\$"
    with pytest.raises(ValueError):
        publish.fill("@@a@@ @@b@@", a=1)
    assert publish.fill("@@a@@", a="x") == "x"


def test_parse_kv():
    assert _parse_kv(["X=10**12", "N=1e6", "s=abc", "w=3", "f=0.5"]) == \
        {"X": 10**12, "N": 1000000, "s": "abc", "w": 3, "f": 0.5}
    with pytest.raises(SystemExit):
        _parse_kv(["oops"])


def test_cli_end_to_end(tmp_path, capsys):
    out = tmp_path / "run"
    assert main(["run", "699", "N=40", "--out", str(out)]) == 0
    assert main(["check", str(out)]) == 0
    assert main(["publish", str(out), "--offline", "--no-pdf", "--author", "A. Person"]) == 0
    assert (out / "packet" / "CHECKLIST.md").exists()
    assert main(["solvers"]) == 0
    text = capsys.readouterr().out
    assert "p699-binomial-gcd" in text


def test_cli_check_detects_tampering(tmp_path, capsys):
    out = tmp_path / "run"
    main(["run", "647", "N=1000", "--out", str(out)])
    (out / "check.json").write_text("{}")
    assert main(["check", str(out)]) == 3


def test_prior_override_reaches_paper(run458, tmp_path, catalog):
    r, _ = certify.load_run(run458)
    d = build_dossier(458, catalog)
    nv = assess_novelty(1e21, False, d, prior_override=1e20, prior_note="read by a human")
    build_packet(run458, tmp_path / "pk", None, d, nv, compile=False)
    tex = (tmp_path / "pk/paper/main.tex").read_text()
    assert "$10^{20}$ (read by a human)" in tex and "1.05" not in tex.split("Prior work")[1].split("\\section")[0]


def test_summarize_details():
    d = ["a", "chunk [2, 10) reproduced exactly: 4 witnesses", "chunk [10, 20) reproduced exactly: 3 witnesses"]
    out = publish.summarize_details(d)
    assert out[0] == "a" and "2 chunks" in out[1] and "7 witnesses" in out[1]
