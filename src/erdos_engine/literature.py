"""Prior-work dossier and novelty gate.

Before anything is written up, the engine gathers what is already claimed:
forum comments on erdosproblems.com (where most computational frontiers are
posted), the problem page remarks, OEIS, and arXiv.  From the text it
extracts numeric "verified up to B" claims and decides whether a new result
actually goes beyond them.  The gate is deliberately conservative: when in
doubt the result is labelled a replication, never a new frontier.
"""
from __future__ import annotations

import json
import math
import re
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from typing import Iterable

from .catalog import Catalog, Comment, Fetcher, cached_fetch

OEIS_SEARCH = "https://oeis.org/search?q={q}&fmt=json"
ARXIV_API = "http://export.arxiv.org/api/query?search_query={q}&max_results={k}"

# --------------------------------------------------------------------------
# numeric claim extraction
# --------------------------------------------------------------------------

_NUM = r"(?:(?P<mant>\d+(?:\.\d+)?)\s*(?:\\times|\\cdot|×|\*|x)\s*)?10\s*\^\s*\{?\s*(?P<exp>\d+)\s*\}?"
_SCI = r"(?P<smant>\d+(?:\.\d+)?)[eE](?P<sexp>\d+)"
_PLAIN = r"(?<![\d.])(?P<plain>\d{1,3}(?:,\d{3}){2,}|\d{7,})(?![\d.])"
NUMBER_RE = re.compile(f"{_NUM}|{_SCI}|{_PLAIN}")

#: words signalling an exhaustive verification/search claim nearby
CLAIM_WORDS = re.compile(
    r"verif|checked|exhaustive|no (?:counter-?example|solution|example)s?|search|frontier|"
    r"extend|confirmed|holds for|true for|there (?:is|are) no", re.I)


@dataclass
class FrontierClaim:
    value: float
    text: str
    source: str
    author: str = ""
    when: str = ""


def parse_number(m: re.Match) -> float:
    if m.group("exp") is not None:
        mant = float(m.group("mant")) if m.group("mant") else 1.0
        return mant * 10.0 ** int(m.group("exp"))
    if m.group("sexp") is not None:
        return float(m.group("smant")) * 10.0 ** int(m.group("sexp"))
    return float(m.group("plain").replace(",", ""))


def extract_claims(text: str, source: str, author: str = "", when: str = "",
                   window: int = 160, pattern: str | None = None) -> list[FrontierClaim]:
    """Numeric claims near verification vocabulary.

    `pattern` (a regex whose group 1 is the number) replaces the generic
    number recogniser, for problems whose frontier is not a magnitude like
    10^20 (e.g. "n <= 32" vertices)."""
    out = []
    if pattern:
        for m in re.finditer(pattern, text):
            ctx = text[max(0, m.start() - window): m.end() + 60]
            if CLAIM_WORDS.search(ctx):
                out.append(FrontierClaim(float(m.group(1)), ctx.strip(), source, author, when))
        return out
    for m in NUMBER_RE.finditer(text):
        lo, hi = max(0, m.start() - window), min(len(text), m.end() + 60)
        ctx = text[lo:hi]
        if not CLAIM_WORDS.search(ctx):
            continue
        try:
            v = parse_number(m)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(v):
            continue
        out.append(FrontierClaim(v, ctx.strip(), source, author, when))
    return out


def max_claim(claims: Iterable[FrontierClaim]) -> FrontierClaim | None:
    best = None
    for c in claims:
        if best is None or c.value > best.value:
            best = c
    return best


# --------------------------------------------------------------------------
# external searches
# --------------------------------------------------------------------------

def oeis_search(terms: Iterable[int], fetch: Fetcher | None = None, k: int = 10) -> list[dict]:
    """Look up a run of terms; returns [{'number': 'A000045', 'name': ...}, ...]."""
    q = ",".join(str(t) for t in terms)
    txt = cached_fetch(OEIS_SEARCH.format(q=urllib.parse.quote(q)), fetch)
    try:
        data = json.loads(txt)
    except json.JSONDecodeError:
        return []
    results = data if isinstance(data, list) else (data.get("results") or [])
    out = []
    for r in (results or [])[:k]:
        out.append({"number": f"A{int(r['number']):06d}", "name": r.get("name", ""),
                    "data": r.get("data", "")})
    return out


def arxiv_search(query: str, fetch: Fetcher | None = None, k: int = 10) -> list[dict]:
    url = ARXIV_API.format(q=urllib.parse.quote(query), k=k)
    txt = cached_fetch(url, fetch)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    try:
        root = ET.fromstring(txt)
    except ET.ParseError:
        return out
    for e in root.findall("a:entry", ns):
        out.append({
            "id": (e.findtext("a:id", default="", namespaces=ns) or "").strip(),
            "title": re.sub(r"\s+", " ", e.findtext("a:title", default="", namespaces=ns) or "").strip(),
            "published": (e.findtext("a:published", default="", namespaces=ns) or "")[:10],
        })
    return out


# --------------------------------------------------------------------------
# dossier + novelty
# --------------------------------------------------------------------------

@dataclass
class Dossier:
    number: int
    status: str
    statement: str
    remarks: str
    oeis: list[str]
    comments: list[dict]
    claims: list[FrontierClaim]
    arxiv: list[dict] = field(default_factory=list)
    ai_disclosures: int = 0

    @property
    def frontier(self) -> FrontierClaim | None:
        return max_claim(self.claims)

    def to_dict(self) -> dict:
        d = asdict(self)
        f = self.frontier
        d["frontier"] = asdict(f) if f else None
        return d


_AI_RE = re.compile(r"\b(Claude|GPT|ChatGPT|Gemini|Aristotle|AlphaProof|AI[- ]assist|LLM)\b", re.I)


def build_dossier(n: int, catalog: Catalog, with_arxiv: bool = False,
                  fetch: Fetcher | None = None, frontier_regex: str | None = None) -> Dossier:
    rec = catalog.get(n)
    page = catalog.page(n)
    comments: list[Comment] = catalog.forum(n)
    claims = extract_claims(page["remarks"], source="problem page", pattern=frontier_regex)
    for c in comments:
        claims += extract_claims(c.text, source="forum", author=c.author, when=c.when,
                                 pattern=frontier_regex)
    arx = arxiv_search(f'all:"Erdos problem {n}"', fetch) if with_arxiv else []
    return Dossier(
        number=n, status=rec.status, statement=page["statement"], remarks=page["remarks"],
        oeis=rec.oeis, comments=[asdict(c) for c in comments], claims=claims, arxiv=arx,
        ai_disclosures=sum(1 for c in comments if _AI_RE.search(c.text)),
    )


@dataclass
class Novelty:
    verdict: str          # "new-frontier" | "replication" | "settles-problem" | "unknown"
    our_value: float | None
    prior_value: float | None
    prior_source: str
    explanation: str
    #: True when the claim number was extracted automatically and a human must
    #: still read the thread to confirm what was actually verified.
    needs_human_review: bool = True


def assess_novelty(our_frontier: float | None, settles: bool, dossier: Dossier,
                   prior_override: float | None = None, prior_note: str = "") -> Novelty:
    if settles:
        return Novelty("settles-problem", our_frontier, None, "",
                       "Result claims to settle the problem by a finite certificate. "
                       "Check the forum and the literature carefully: an existing "
                       "resolution would make this a replication.", True)
    prior = dossier.frontier
    prior_v = prior_override if prior_override is not None else (prior.value if prior else None)
    src = prior_note or (f"{prior.source} ({prior.author}, {prior.when})" if prior else "")
    if our_frontier is None:
        return Novelty("unknown", None, prior_v, src, "Result has no numeric frontier.")
    if prior_v is None:
        return Novelty("unknown", our_frontier, None, "",
                       "No prior numeric claim was found automatically; this does NOT "
                       "mean none exists. A literature search by a human is required.")
    if our_frontier > prior_v * (1 + 1e-9):
        return Novelty("new-frontier", our_frontier, prior_v, src,
                       f"Our bound {our_frontier:.3g} exceeds the largest claim found "
                       f"({prior_v:.3g}).")
    return Novelty("replication", our_frontier, prior_v, src,
                   f"Our bound {our_frontier:.3g} does not exceed the existing claim "
                   f"({prior_v:.3g}); the result is an independent replication.")
