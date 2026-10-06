"""Catalogue parsing, forum parsing, frontier extraction, novelty gate."""
import pytest

from erdos_engine import catalog as C
from erdos_engine import literature as L


def test_parse_yaml(catalog):
    p = catalog.get(458)
    assert p.status == "falsifiable" and p.finite_check_possible and p.is_open
    assert p.oeis == ["A056604"] and "primes" in p.tags
    assert catalog.get(1).status == "disproved" and not catalog.get(1).is_open
    assert catalog.get(3).prize == "$5000"


def test_page_parse(catalog):
    pg = catalog.page(458)
    assert pg["statement"].startswith("Let $[1,\\ldots,n]$ denote the least common multiple")
    assert "Legendre" in pg["remarks"]
    assert pg["status_banner"] == "falsifiable"


def test_page_parse_neutral_layout():
    from pathlib import Path
    html = (Path(__file__).parent / "fixtures" / "page_458_neutral.html").read_text()
    pg = C.parse_problem_page(html)
    assert pg["statement"].startswith("Let $[1,\\ldots,n]$ denote")
    assert pg["statement"].endswith("?\\]")
    assert pg["status_banner"] == "" and "Legendre" in pg["remarks"]


def test_page_parse_all_fixtures():
    from pathlib import Path
    for f in (Path(__file__).parent / "fixtures").glob("page_*.html"):
        pg = C.parse_problem_page(f.read_text())
        assert 20 < len(pg["statement"]) < 1000, f
        assert "Forum" not in pg["statement"] and "Additional thanks" not in pg["remarks"]


def test_forum_parse(catalog):
    cs = catalog.forum(458)
    assert [c.author for c in cs] == ["bhowerton", "Zeraoulia Rafik", "DesmondWeisenberg"]
    assert cs[0].when == "21:22 on 12 Jun 2026"
    assert "10^{20}" in cs[0].text


def test_forum_fallback_on_flat_text():
    html = "<p>first body</p> alice — 10:00 on 1 Jan 2026 <p>second</p> bob — 11:00 on 2 Jan 2026"
    cs = C.parse_forum(html)
    assert [(c.author, c.text) for c in cs] == [("alice", "first body"), ("bob", "second")]


@pytest.mark.parametrize("text,value", [
    ("I verified it up to $10^{20}$.", 1e20),
    ("no counterexample below $4\\times 10^{18}$", 4e18),
    ("checked all n up to 1e12 with no solution", 1e12),
    ("search complete to $10^{22}$", 1e22),
    ("exhaustive: all 109,972,410,221 trees", 109972410221),
    ("verified for $n\\le 1.9 \\cdot 10^{10}$", 1.9e10),
])
def test_extract_claims(text, value):
    vals = [c.value for c in L.extract_claims(text, "t")]
    assert value in vals


def test_extract_claims_ignores_non_claims():
    assert L.extract_claims("The constant is 10^{20} times bigger.", "t") == []


def test_custom_pattern():
    cl = L.extract_claims("exhaustive verification now extends to n = 32.", "t",
                          pattern=r"n\s*(?:=|\\le|<=)\s*(\d{1,3})\b")
    assert [c.value for c in cl] == [32.0]


def test_dossier_and_frontiers(catalog):
    d = L.build_dossier(647, catalog)
    assert d.frontier.value == 1e22 and d.frontier.author == "veljjanoski"
    assert d.ai_disclosures >= 1
    d993 = L.build_dossier(993, catalog, frontier_regex=r"n\s*(?:=|\\le|<=|≤)\s*(\d{1,3})\b")
    assert d993.frontier.value == 32
    d458 = L.build_dossier(458, catalog)
    assert 1e20 <= d458.frontier.value <= 1.1e20


def test_novelty_verdicts(catalog):
    d = L.build_dossier(458, catalog)
    assert L.assess_novelty(1e21, False, d).verdict == "new-frontier"
    assert L.assess_novelty(1e12, False, d).verdict == "replication"
    assert L.assess_novelty(1e21, True, d).verdict == "settles-problem"
    assert L.assess_novelty(None, False, d).verdict == "unknown"
    nv = L.assess_novelty(1e21, False, d, prior_override=1e20, prior_note="read the thread")
    assert nv.prior_value == 1e20 and nv.prior_source == "read the thread"
    assert nv.needs_human_review


def test_novelty_without_prior_claims(catalog):
    d = L.build_dossier(458, catalog)
    d.claims = []
    nv = L.assess_novelty(1e21, False, d)
    assert nv.verdict == "unknown" and "does NOT" in nv.explanation


def test_triage(catalog):
    rows = C.triage(catalog, [458, 647])
    top = [r["number"] for r in rows[:2]]
    assert set(top) == {458, 647}
    assert all(r["status"] in C.OPEN_STATUSES for r in rows)


def test_cached_fetch_uses_cache():
    calls = []

    def f(url):
        calls.append(url)
        return "x"

    assert C.cached_fetch("https://example.org/a", f) == "x"
    assert C.cached_fetch("https://example.org/a", f) == "x"
    assert len(calls) == 1
    C.cached_fetch("https://example.org/a", f, refresh=True)
    assert len(calls) == 2


def test_oeis_and_arxiv_parsers():
    oeis_json = '[{"number": 87280, "name": "Numbers n such that ...", "data": "1,2,3"}]'
    assert L.oeis_search([2, 3, 4], fetch=lambda u: oeis_json)[0]["number"] == "A087280"
    assert L.oeis_search([1], fetch=lambda u: "not json") == []
    atom = ('<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/1</id>'
            '<title>On Erdos  problems</title><published>2026-01-01T00:00:00Z</published></entry></feed>')
    assert L.arxiv_search("x", fetch=lambda u: atom) == [
        {"id": "http://arxiv.org/abs/1", "title": "On Erdos problems", "published": "2026-01-01"}]
