"""Problem catalogue: the community database plus erdosproblems.com pages.

Sources
  * https://github.com/teorth/erdosproblems  (data/problems.yaml) -- status,
    prize, OEIS links, tags for every problem;
  * https://www.erdosproblems.com/<n>          -- statement and remarks;
  * https://www.erdosproblems.com/forum/thread/<n> -- comments, where most
    recent computational frontiers are reported.

Everything fetched is cached on disk (ERDOS_ENGINE_CACHE) and every network
call goes through a `fetch(url) -> str` callable so tests can inject fixtures.
"""
from __future__ import annotations

import html as _html
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

import yaml

YAML_URL = "https://raw.githubusercontent.com/teorth/erdosproblems/main/data/problems.yaml"
PAGE_URL = "https://www.erdosproblems.com/{n}"
FORUM_URL = "https://www.erdosproblems.com/forum/thread/{n}"
USER_AGENT = "erdos-engine/0.1 (+https://github.com/; research tooling; polite single requests)"

#: statuses for which a finite computation could settle the problem
FINITE_STATUSES = ("falsifiable", "verifiable", "decidable")
OPEN_STATUSES = FINITE_STATUSES + ("open",)

Fetcher = Callable[[str], str]


def cache_dir() -> Path:
    d = Path(os.environ.get("ERDOS_ENGINE_CACHE", Path.home() / ".cache" / "erdos_engine")) / "catalog"
    d.mkdir(parents=True, exist_ok=True)
    return d


def http_fetch(url: str, timeout: float = 30.0) -> str:
    import requests
    r = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    return r.text


def cached_fetch(url: str, fetch: Fetcher | None = None, max_age: float = 86400.0,
                 refresh: bool = False) -> str:
    """Fetch through the on-disk cache (default freshness: one day)."""
    key = re.sub(r"[^A-Za-z0-9._-]+", "_", url)[-180:]
    path = cache_dir() / key
    if not refresh and path.exists() and time.time() - path.stat().st_mtime < max_age:
        return path.read_text()
    text = (fetch or http_fetch)(url)
    path.write_text(text)
    return text


# --------------------------------------------------------------------------

@dataclass
class ProblemRecord:
    number: int
    status: str
    prize: str = "no"
    oeis: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    comments: str = ""
    formalized: bool = False
    status_updated: str = ""

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES

    @property
    def finite_check_possible(self) -> bool:
        return self.status in FINITE_STATUSES

    @property
    def url(self) -> str:
        return PAGE_URL.format(n=self.number)


def parse_problems_yaml(text: str) -> dict[int, ProblemRecord]:
    out: dict[int, ProblemRecord] = {}
    for entry in yaml.safe_load(text) or []:
        n = int(entry["number"])
        inf = entry.get("informal_status") or entry.get("status") or {}
        out[n] = ProblemRecord(
            number=n,
            status=str(inf.get("state", "unknown")),
            prize=str(entry.get("prize", "no")),
            oeis=[str(x) for x in entry.get("oeis", []) or []],
            tags=[str(x) for x in entry.get("tags", []) or []],
            comments=str(entry.get("comments", "") or ""),
            formalized=(entry.get("formalized") or {}).get("state") == "yes",
            status_updated=str(inf.get("last_update", "")),
        )
    return out


def html_to_text(s: str) -> str:
    s = re.sub(r"<script.*?</script>", " ", s, flags=re.S)
    s = re.sub(r"<style.*?</style>", " ", s, flags=re.S)
    s = re.sub(r"<br\s*/?>|</p>|</div>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = _html.unescape(s)
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


_CONTENT = re.compile(r'<div class="problem-text"[^>]*>.*?<div id="content">(?P<stmt>.*?)</div>', re.S)
_REMARKS = re.compile(r'<div class="problem-additional-text">(?P<rem>.*?)(?:<div id="bib-container|<div class="citationbox">)', re.S)
_BANNER = re.compile(r'<div id="prize">.*?<span class="tooltip">\s*(?P<st>[A-Z ]+?)\s*<span', re.S)


def parse_problem_page(html: str) -> dict[str, str]:
    """Extract statement, remarks and (if shown) status banner from a problem page.

    The site serves two layouts: one with a status banner and a "neutral"
    (spoiler-free) one without; both keep the statement in div#content.
    """
    m = _CONTENT.search(html)
    if m:
        statement = re.sub(r"\s+", " ", html_to_text(m.group("stmt"))).strip()
        r = _REMARKS.search(html)
        remarks = re.sub(r"\s+", " ", html_to_text(r.group("rem"))).strip() if r else ""
        b = _BANNER.search(html)
        status = b.group("st").strip().lower() if b else ""
        return {"status_banner": status, "statement": statement, "remarks": remarks}
    # Fallback: flattened-text heuristics for unexpected markup.
    text = re.sub(r"\s+", " ", html_to_text(html))
    start = text.find("Random Open")
    body = text[start + len("Random Open"):] if start >= 0 else text
    end = body.find("Proof expositions")
    body = body[:end if end >= 0 else None].strip()
    mm = re.search(r"#(\d+)\s*:", body)
    statement, remarks = (body[:mm.start()], body[mm.end():]) if mm else (body, "")
    return {"status_banner": "", "statement": statement.strip(), "remarks": remarks.strip()}


@dataclass
class Comment:
    author: str
    when: str
    text: str


_POST = re.compile(
    r'<div class="post-body"[^>]*>(?P<body>.*?)<div class="post-meta">(?P<meta>.*?)(?=<div class="reaction-bar"|<li |</ul>)',
    re.S)
_AUTHOR = re.compile(r'<a href="/forum/user/[^"]*">(?P<a>.*?)</a>', re.S)
_WHEN = re.compile(r'#post-\d+">(?P<w>[^<]+)</a>')
_SIG = re.compile(r"(?P<author>\S+)\s+—\s+(?P<when>\d{2}:\d{2} on \d{1,2} \w{3} \d{4})")


def parse_forum(html: str) -> list[Comment]:
    """Split a forum thread into comments (structured HTML, newest first)."""
    out: list[Comment] = []
    for m in _POST.finditer(html):
        a = _AUTHOR.search(m.group("meta"))
        w = _WHEN.search(m.group("meta"))
        out.append(Comment(
            author=html_to_text(a.group("a")) if a else "",
            when=w.group("w").strip() if w else "",
            text=re.sub(r"\s+", " ", html_to_text(m.group("body"))).strip(),
        ))
    if out:
        return out
    # Fallback for unexpected markup: signatures in flattened text.
    text = re.sub(r"\s+", " ", html_to_text(html))
    pos = 0
    for m in _SIG.finditer(text):
        out.append(Comment(m.group("author"), m.group("when"), text[pos:m.start()].strip()))
        pos = m.end()
    return out


class Catalog:
    def __init__(self, fetch: Fetcher | None = None, refresh: bool = False):
        self.fetch = fetch
        self.refresh = refresh
        self._problems: dict[int, ProblemRecord] | None = None

    def _get(self, url: str) -> str:
        return cached_fetch(url, self.fetch, refresh=self.refresh)

    @property
    def problems(self) -> dict[int, ProblemRecord]:
        if self._problems is None:
            self._problems = parse_problems_yaml(self._get(YAML_URL))
        return self._problems

    def get(self, n: int) -> ProblemRecord:
        return self.problems[n]

    def page(self, n: int) -> dict[str, str]:
        return parse_problem_page(self._get(PAGE_URL.format(n=n)))

    def forum(self, n: int) -> list[Comment]:
        return parse_forum(self._get(FORUM_URL.format(n=n)))

    def by_status(self, *statuses: str) -> list[ProblemRecord]:
        return [p for p in self.problems.values() if p.status in statuses]

    def counts(self) -> dict[str, int]:
        c: dict[str, int] = {}
        for p in self.problems.values():
            c[p.status] = c.get(p.status, 0) + 1
        return dict(sorted(c.items(), key=lambda kv: -kv[1]))


def triage(catalog: Catalog, solver_ids: Iterable[int]) -> list[dict]:
    """Rank open problems by how amenable they are to this engine.

    Score: finite certificate possible (+3), a solver exists (+5),
    prize (+1), OEIS sequence attached or 'possible' (+1).
    """
    solvers = set(solver_ids)
    rows = []
    for p in catalog.problems.values():
        if not p.is_open:
            continue
        score = 0
        reasons = []
        if p.finite_check_possible:
            score += 3
            reasons.append(p.status)
        if p.number in solvers:
            score += 5
            reasons.append("solver available")
        if p.prize not in ("no", "", "None"):
            score += 1
            reasons.append(f"prize {p.prize}")
        if p.oeis and p.oeis != ["N/A"]:
            score += 1
            reasons.append("OEIS: " + ",".join(p.oeis))
        rows.append({"number": p.number, "status": p.status, "score": score,
                     "reasons": reasons, "tags": p.tags})
    rows.sort(key=lambda r: (-r["score"], r["number"]))
    return rows
