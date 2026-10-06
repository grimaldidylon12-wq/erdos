"""Publication packet: everything needed to take a checked result public.

`build_packet` turns a run directory into

    paper/main.tex, refs.bib, main.pdf, arxiv-submission.tar.gz
    forum_comment.md          draft for the problem's erdosproblems.com thread
    database_update.md        what (if anything) to change in teorth/erdosproblems
    oeis.md (+ b-file)        OEIS notes; never a drafted submission (see policy)
    data/                     certificate, check report, manifest, .zenodo.json, CITATION.cff
    novelty.json              the prior-work comparison
    CHECKLIST.md              gates passed + the steps only a human can do

Hard gates (PublicationBlocked): the run's manifest must verify, the
independent check must have passed, and the outcome must be conclusive.
The packet never submits anything: posting, uploading and submitting need the
author's accounts and judgement, and community policies (arXiv authorship,
OEIS's ban on AI-generated submissions, erdosproblems.com's AI-disclosure
norm) put those steps in human hands.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .. import __version__
from ..certify import load_run, verify_manifest
from ..literature import Dossier, Novelty
from ..solvers import get_solver
from ..solvers.base import (COUNTEREXAMPLE, EXAMPLE, NO_CONCLUSION, SEQUENCE, VERIFIED_TO_BOUND,
                            CheckReport, Result)

TEMPLATES = Path(__file__).with_name("templates")

AI_DISCLOSURE = ("The search and checking software was written with the assistance of an AI coding "
                 "assistant (Claude, Anthropic). All numerical claims come from executed runs whose "
                 "certificates were re-validated by an independent implementation; the author(s) "
                 "reviewed the code and the mathematics and take full responsibility for the content.")


class PublicationBlocked(RuntimeError):
    pass


@dataclass
class Author:
    name: str
    affiliation: str = ""
    email: str = ""
    orcid: str = ""


PLACEHOLDER_AUTHOR = Author("AUTHOR NAME (fill in)", "Affiliation (fill in)", "email@example.org")


@dataclass
class PacketReport:
    out_dir: str
    files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    venue: str = ""
    pdf_built: bool = False


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

_TEX_ESC = {"&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
            "~": r"\textasciitilde{}", "^": r"\textasciicircum{}", "\\": r"\textbackslash{}"}


def tex_escape(s: str) -> str:
    return "".join(_TEX_ESC.get(ch, ch) for ch in s)


def fill(template: str, **kw) -> str:
    for k, v in kw.items():
        template = template.replace(f"@@{k}@@", str(v))
    left = re.findall(r"@@[a-z_]+@@", template)
    if left:
        raise ValueError(f"unfilled placeholders: {sorted(set(left))}")
    return template


def site_bib_entry(n: int, today: str) -> str:
    return (f"@misc{{erdosproblems{n},\n  author = {{Bloom, Thomas F.}},\n"
            f"  title = {{Erd{{\\H{{o}}}}s Problem \\#{n}}},\n"
            f"  howpublished = {{\\url{{https://www.erdosproblems.com/{n}}}}},\n"
            f"  note = {{Accessed {today}}}\n}}\n")


def bib_keys(text: str) -> set[str]:
    return set(re.findall(r"@\w+\{([^,]+),", text))


def summarize_details(details: list[str]) -> list[str]:
    """Collapse per-chunk 'reproduced exactly' lines into one summary line."""
    rx = re.compile(r"chunk \[(\d+), (\d+)\) reproduced exactly: (\d+) witnesses")
    hits = [rx.search(d) for d in details]
    rest = [d for d, h in zip(details, hits) if not h]
    hits = [h for h in hits if h]
    if hits:
        total = sum(int(h.group(3)) for h in hits)
        rest.append(f"{len(hits)} chunks (including the first and the last, the others chosen at random) "
                    f"recomputed from scratch and reproduced exactly: {total:,} witnesses in total")
    return rest


def venue_recommendation(result: Result, novelty: Novelty | None) -> str:
    if result.outcome in (COUNTEREXAMPLE, EXAMPLE):
        return ("SETTLES THE PROBLEM (if correct). Do not post publicly before an independent human "
                "re-verification. Then: post on the problem's erdosproblems.com thread (the "
                "moderators update the official status), prepare an arXiv preprint (math.NT or "
                "math.CO), and consider a journal (e.g. Integers, Journal of Integer Sequences, "
                "Experimental Mathematics, Mathematics of Computation, depending on depth).")
    verdict = novelty.verdict if novelty else "unknown"
    if result.outcome == SEQUENCE:
        return ("Sequence data: compare with the OEIS. If it matches an existing entry, open a PR "
                "against teorth/erdosproblems adding the A-number. A new OEIS entry must be written "
                "and submitted by a human (OEIS forbids AI-generated submissions).")
    if verdict == "new-frontier":
        return ("Extends the published computational frontier. Standard venue: a comment on the "
                "problem's erdosproblems.com thread with code and data deposited (GitHub + Zenodo "
                "DOI). A short arXiv note is optional; journals (e.g. Mathematics of Computation, "
                "Experimental Mathematics) generally want more than a range extension unless the "
                "method is new.")
    if verdict == "replication":
        return ("Independent replication of an existing frontier. At most a brief forum comment "
                "saying so; not suitable for arXiv or a journal on its own.")
    return ("Novelty undetermined: a human must survey the forum thread, the problem page and the "
            "literature before choosing a venue.")


# --------------------------------------------------------------------------
# paper
# --------------------------------------------------------------------------

PAPER_TEX = r"""\documentclass[11pt]{amsart}
\usepackage[T1]{fontenc}
\IfFileExists{lmodern.sty}{\usepackage{lmodern}}{}
\usepackage{amssymb,amsmath}
\usepackage[hidelinks]{hyperref}
\newtheorem{theorem}{Theorem}
\newtheorem{lemma}[theorem]{Lemma}

% Generated by erdos-engine @@version@@ on @@today@@.
% TODO(human): every passage marked TODO must be checked and rewritten by the
% author before this goes anywhere.

\title{@@title@@}
@@authors@@
\date{@@today@@}
\subjclass[2020]{@@msc@@}

\begin{document}
\begin{abstract}
@@abstract@@
\end{abstract}
\maketitle

\section{The problem}
Erd\H{o}s Problem \#@@n@@ \cite{erdosproblems@@n@@} asks the following.
\begin{quote}
@@statement@@
\end{quote}
At the time of writing it is listed as \emph{@@status@@} in the community
database \cite{ErdosDB}: @@status_gloss@@

\subsection*{Prior work}
% TODO(human): the sentence below was assembled automatically from the
% problem's forum thread.  Read the thread and the literature, and rewrite.
@@prior@@

\section{Method}
@@method@@

\section{Results}
@@results@@

\section{Verification and reproducibility}
The certificate produced by the search was re-validated by an independent
implementation (``@@checker@@'') that shares no code with the search:
\begin{itemize}
@@check_items@@
\end{itemize}
The raw certificate (\texttt{result.json}, SHA-256
\texttt{@@sha_result@@}) and the check report are deposited
with the software. % TODO(human): add repository URL and Zenodo DOI.

\section*{Use of AI tools}
@@ai@@

\bibliographystyle{amsplain}
\bibliography{refs}
\end{document}
"""

_STATUS_GLOSS = {
    "falsifiable": "it is open, but a counterexample, if one exists, is a finite object.",
    "verifiable": "it is open, but an example, if one exists, is a finite object.",
    "decidable": "it has been reduced to a finite (but so far infeasible) computation.",
    "open": "it is open.",
}

_MSC = {"number theory": "11Y11", "primes": "11A41", "graph theory": "05C69",
        "divisors": "11A25", "binomial coefficients": "11B65"}


def build_paper(result: Result, check: CheckReport, authors: list[Author], dossier: Dossier | None,
                novelty: Novelty | None, today: str, sha_result: str) -> tuple[str, str, list[str]]:
    solver = get_solver(result.problem)
    warnings: list[str] = []
    n = result.problem
    if result.outcome == COUNTEREXAMPLE:
        title = f"A counterexample to Erd\\H{{o}}s Problem \\#{n}"
    elif result.outcome == EXAMPLE:
        title = f"A solution of Erd\\H{{o}}s Problem \\#{n}"
    elif result.outcome == SEQUENCE:
        title = f"Computations for Erd\\H{{o}}s Problem \\#{n}"
    else:
        title = f"A certified computational verification for Erd\\H{{o}}s Problem \\#{n}"
    auth = "\n".join(
        f"\\author{{{tex_escape(a.name)}}}" + (f"\n\\address{{{tex_escape(a.affiliation)}}}" if a.affiliation else "")
        + (f"\n\\email{{{tex_escape(a.email)}}}" if a.email else "") for a in authors)
    if any(a is PLACEHOLDER_AUTHOR or "fill in" in a.name for a in authors):
        warnings.append("author block contains placeholders")
    if novelty and novelty.prior_value is not None and dossier:
        # the novelty record carries any human override of the extracted claim
        prior = (f"The forum thread for the problem contains {len(dossier.comments)} comments. "
                 f"The largest verification bound reported there is "
                 f"${_tex_sci(novelty.prior_value)}$ ({tex_escape(novelty.prior_source)}). ")
    elif dossier and dossier.frontier:
        f = dossier.frontier
        prior = (f"The forum thread for the problem contains {len(dossier.comments)} comments. "
                 f"The largest verification bound we found reported there is approximately "
                 f"${_tex_sci(f.value)}$ (comment by {tex_escape(f.author or 'an anonymous user')}, "
                 f"{tex_escape(f.when)}). ")
    else:
        prior = ""
    if prior:
        if novelty and novelty.verdict == "new-frontier":
            prior += "The present computation goes beyond that bound."
        elif novelty and novelty.verdict == "replication":
            prior += "The present computation is an independent replication; it does not extend that bound."
    else:
        prior = ("TODO(human): no prior computational claim was found automatically. This does not "
                 "mean none exists; survey the forum thread and the literature.")
        warnings.append("prior-work paragraph needs a human literature survey")
    status = dossier.status if dossier else solver.finite_kind
    tagmsc = sorted({_MSC.get(t, "11Y99") for t in solver.tags}) or ["11Y99"]
    abstract = (solver.abstract_tex(result) +
                " Every claim is backed by a certificate that was re-validated by an independent implementation.")
    items = "\n".join(f"\\item {tex_escape(d)}" for d in summarize_details(check.details)) or "\\item (no details recorded)"
    tex = fill(PAPER_TEX, version=__version__, today=today, title=title, authors=auth,
               msc=", ".join(tagmsc[:1]) + (f" (secondary {', '.join(tagmsc[1:])})" if len(tagmsc) > 1 else ""),
               abstract=abstract, n=n, statement=solver.statement_tex, status=status,
               status_gloss=_STATUS_GLOSS.get(status, ""), prior=prior,
               method=solver.method_tex(result) or "TODO(human): describe the method.",
               results=solver.results_tex(result), checker=tex_escape(check.checker),
               check_items=items, sha_result=" ".join(sha_result[i:i + 16] for i in range(0, len(sha_result), 16)), ai=AI_DISCLOSURE)
    base = (TEMPLATES / "refs.bib").read_text()
    bib = base + "\n" + site_bib_entry(n, today)
    have = bib_keys(bib)
    for key in solver.references:
        if key not in have:
            warnings.append(f"reference {key} has no BibTeX entry")
    # cite every reference the solver lists, so they appear even if not \cite'd inline
    tex = tex.replace(r"\bibliographystyle{amsplain}",
                      "\\nocite{" + ",".join(k for k in solver.references if k in have) + "}\n\\bibliographystyle{amsplain}")
    return tex, bib, warnings


def _tex_sci(x: float) -> str:
    if x >= 1e7:
        e = len(str(int(x))) - 1
        m = x / 10**e
        return f"10^{{{e}}}" if abs(m - 1) < 1e-9 else f"{m:.3g}\\cdot 10^{{{e}}}"
    return f"{x:g}"


def compile_pdf(paper_dir: Path, timeout: int = 180) -> tuple[bool, str]:
    if not shutil.which("pdflatex"):
        return False, "pdflatex not installed"
    log = []
    steps = [["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "main.tex"]]
    if shutil.which("bibtex"):
        steps.append(["bibtex", "main"])
    steps += [steps[0], steps[0]]
    for cmd in steps:
        p = subprocess.run(cmd, cwd=paper_dir, capture_output=True, text=True, timeout=timeout)
        log.append(p.stdout[-2000:])
        if p.returncode != 0 and cmd[0] == "pdflatex":
            return False, "\n".join(log)
    return (paper_dir / "main.pdf").exists(), "\n".join(log)


def arxiv_tarball(paper_dir: Path) -> Path:
    """arXiv wants sources plus the .bbl (it does not run BibTeX reliably)."""
    out = paper_dir / "arxiv-submission.tar.gz"
    with tarfile.open(out, "w:gz") as tar:
        for name in ("main.tex", "refs.bib", "main.bbl"):
            if (paper_dir / name).exists():
                tar.add(paper_dir / name, arcname=name)
    return out


# --------------------------------------------------------------------------
# other artefacts
# --------------------------------------------------------------------------

def forum_comment(result: Result, check: CheckReport, novelty: Novelty | None) -> str:
    solver = get_solver(result.problem)
    lines = []
    if novelty and novelty.verdict == "replication":
        lines.append("(Independent replication; this does not extend the existing frontier.)")
        lines.append("")
    lines.append(solver.forum_markdown(result))
    lines.append("")
    lines.append(f"Checking: an independent implementation sharing no code with the search ({check.checker}) "
                 "re-validated the certificate:")
    for d in summarize_details(check.details):
        lines.append(f"- {d}")
    lines.append("")
    lines.append("Code, certificate and logs: <REPOSITORY URL> (DOI: <ZENODO DOI>).")
    lines.append("")
    lines.append("AI-usage disclosure: Claude (Anthropic) was used as a coding assistant; all numerical "
                 "claims come from the executed runs, which I have reviewed.")
    lines.append("")
    lines.append("<!-- Draft generated by erdos-engine. Edit before posting; erdosproblems.com asks that "
                 "comments stay mathematical and on topic. Post only after reading the existing thread. -->")
    return "\n".join(lines) + "\n"


def _md(tex: str) -> str:
    s = re.sub(r"\\paragraph\{([^}]*)\}", r"**\1**", tex)
    s = re.sub(r"\\(begin|end)\{(enumerate|itemize)\}", "", s)
    s = re.sub(r"\\item\[([^\]]*)\]", r"\n\1", s)
    s = s.replace(r"\item", "\n-").replace(r"\emph", "").replace("~", " ")
    s = re.sub(r"\\cite\{[^}]*\}", "", s)
    return re.sub(r"[ \t]+", " ", s)


def database_update(result: Result, novelty: Novelty | None, today: str) -> str:
    n = result.problem
    if result.outcome in (COUNTEREXAMPLE, EXAMPLE):
        state = "disproved" if result.outcome == COUNTEREXAMPLE else "proved"
        return (f"# Database update for problem #{n}\n\n"
                "Only after the erdosproblems.com moderators accept the result, propose this change "
                "to `data/problems.yaml` in https://github.com/teorth/erdosproblems (edit "
                "`informal_status` only; `status` is derived automatically):\n\n"
                f"```yaml\n- number: \"{n}\"\n  informal_status:\n    state: \"{state}\"\n"
                f"    last_update: \"{today}\"\n```\n")
    if result.outcome == SEQUENCE:
        return (f"# Database update for problem #{n}\n\nIf the computed sequence matches an existing "
                "OEIS entry (definitions compared, not just terms -- see issue #356 in the database "
                "repo), add its A-number to the `oeis` list of this problem. Otherwise no change.\n")
    return (f"# Database update for problem #{n}\n\nNo change warranted. CONTRIBUTING.md asks that "
            "search bounds and computational frontiers go in the problem's erdosproblems.com thread, "
            "not in the database `comments` field, and a verification to a finite bound does not "
            "change the problem's status.\n")


OEIS_POLICY = ("OEIS policy (https://oeis.org/wiki/Use_of_AI_for_OEIS_Submissions_is_Forbidden) forbids "
               "AI-generated submissions. This packet therefore does NOT draft an OEIS entry. If the data "
               "below is to be submitted, a human must independently understand and verify it and write "
               "the entry themselves.")


def oeis_notes(result: Result, out: Path) -> list[Path]:
    files = []
    text = f"# OEIS notes for problem #{result.problem}\n\n{OEIS_POLICY}\n"
    if result.outcome == SEQUENCE and "sequence" in result.certificate:
        b = out / f"b-file-p{result.problem}.txt"
        rows = result.certificate["sequence"]
        b.write_text("".join(f"{r[0]} {r[1]}\n" for r in rows))
        files.append(b)
        text += (f"\nComputed terms (n, a(n)) are in `{b.name}` (raw data, not a formatted b-file "
                 "submission). Search the OEIS for the first terms before doing anything else.\n")
    else:
        text += "\nThis result has no associated integer sequence.\n"
    p = out / "oeis.md"
    p.write_text(text)
    return [p] + files


def zenodo_metadata(result: Result, authors: list[Author], today: str) -> dict:
    return {
        "title": f"Certificate and software for a computation on Erdős Problem #{result.problem}",
        "upload_type": "dataset",
        "description": result.summary,
        "creators": [{"name": a.name, **({"affiliation": a.affiliation} if a.affiliation else {}),
                      **({"orcid": a.orcid} if a.orcid else {})} for a in authors],
        "license": "cc-by-4.0",
        "keywords": ["Erdős problems", f"Erdős problem {result.problem}", "computational number theory",
                     "certificate"],
        "related_identifiers": [{"identifier": f"https://www.erdosproblems.com/{result.problem}",
                                 "relation": "isSupplementTo", "scheme": "url"}],
        "publication_date": today,
        "version": __version__,
    }


def citation_cff(result: Result, authors: list[Author], today: str) -> str:
    lines = ["cff-version: 1.2.0", "message: If you use this data, please cite it as below.",
             f"title: Certificate for a computation on Erdős Problem #{result.problem}",
             f"date-released: {today}", f"version: {__version__}", "authors:"]
    for a in authors:
        parts = a.name.rsplit(" ", 1)
        if len(parts) == 2:
            lines += [f"  - family-names: \"{parts[1]}\"", f"    given-names: \"{parts[0]}\""]
        else:
            lines += [f"  - name: \"{a.name}\""]
        if a.orcid:
            lines.append(f"    orcid: \"https://orcid.org/{a.orcid}\"")
    return "\n".join(lines) + "\n"


CHECKLIST = """# Publication checklist -- Erdős Problem #@@n@@

Generated @@today@@ by erdos-engine @@version@@.

## Automated gates (all passed, or this file would not exist)
- [x] Run manifest verified (no file modified since the run)
- [x] Independent check passed (`@@checker@@`)
- [x] Outcome is conclusive: `@@outcome@@`

## Novelty
Verdict: **@@verdict@@** -- @@explanation@@
Prior claim used: @@prior@@

## Recommended venue
@@venue@@

## Steps only a human can do
1. Read the whole forum thread https://www.erdosproblems.com/forum/thread/@@n@@ and the
   problem page; confirm the novelty verdict above (it comes from automatic text extraction).
2. Read the code that produced the certificate and re-run the checker yourself
   (`erdos-engine check <run dir> --thorough`), ideally on different hardware.
3. Decide authorship. AI tools cannot be authors (arXiv, most journals); keep the AI-use
   disclosure in the paper and in any forum post.
4. Fill in the author block and every `TODO(human)` in `paper/main.tex`; rebuild the PDF.
5. Push the code and run directory to a public repository; deposit `data/` on Zenodo
   (metadata in `data/.zenodo.json`) to get a DOI; put the URL and DOI in the paper and the
   forum comment.
6. Post `forum_comment.md` (edited) on the problem's thread.
7. Optional, per the venue advice: submit `paper/arxiv-submission.tar.gz` to arXiv (first-time
   submitters may need an endorsement for the category), then a journal.
8. Database (`database_update.md`) and OEIS (`oeis.md`): follow the notes; OEIS entries must be
   written by a human.

## Warnings
@@warnings@@
"""


# --------------------------------------------------------------------------

def build_packet(run_dir: Path, out_dir: Path, authors: list[Author] | None = None,
                 dossier: Dossier | None = None, novelty: Novelty | None = None,
                 compile: bool = True, today: str | None = None) -> PacketReport:
    run_dir, out_dir = Path(run_dir), Path(out_dir)
    today = today or _dt.date.today().isoformat()
    problems = verify_manifest(run_dir)
    if problems:
        raise PublicationBlocked("run directory failed integrity check: " + "; ".join(problems))
    result, check = load_run(run_dir)
    if check is None:
        raise PublicationBlocked("no independent check report (check.json) in the run directory")
    if not check.ok:
        raise PublicationBlocked("independent check FAILED: " + "; ".join(check.details[-3:]))
    if result.outcome == NO_CONCLUSION:
        raise PublicationBlocked("result is inconclusive; nothing to publish")
    authors = authors or [PLACEHOLDER_AUTHOR]
    rep = PacketReport(str(out_dir))
    out_dir.mkdir(parents=True, exist_ok=True)
    data = out_dir / "data"
    data.mkdir(exist_ok=True)
    for name in ("result.json", "check.json", "manifest.json"):
        shutil.copy2(run_dir / name, data / name)
    from ..certify import sha256_file
    sha = sha256_file(run_dir / "result.json")

    paper = out_dir / "paper"
    paper.mkdir(exist_ok=True)
    tex, bib, warns = build_paper(result, check, authors, dossier, novelty, today, sha)
    rep.warnings += warns
    (paper / "main.tex").write_text(tex)
    (paper / "refs.bib").write_text(bib)
    if compile:
        ok, log = compile_pdf(paper)
        rep.pdf_built = ok
        if not ok:
            rep.warnings.append("PDF build failed: " + log[-400:])
    arxiv_tarball(paper)

    (out_dir / "forum_comment.md").write_text(forum_comment(result, check, novelty))
    (out_dir / "database_update.md").write_text(database_update(result, novelty, today))
    oeis_notes(result, out_dir)
    (data / ".zenodo.json").write_text(json.dumps(zenodo_metadata(result, authors, today), indent=1))
    (data / "CITATION.cff").write_text(citation_cff(result, authors, today))
    (out_dir / "novelty.json").write_text(json.dumps(asdict(novelty) if novelty else None, indent=1))
    if novelty and novelty.needs_human_review:
        rep.warnings.append("novelty verdict comes from automatic extraction; a human must confirm it")
    if novelty is None:
        rep.warnings.append("no prior-work dossier supplied; novelty unknown")
    rep.venue = venue_recommendation(result, novelty)
    (out_dir / "CHECKLIST.md").write_text(fill(
        CHECKLIST, n=result.problem, today=today, version=__version__, checker=check.checker,
        outcome=result.outcome, verdict=novelty.verdict if novelty else "unknown",
        explanation=novelty.explanation if novelty else "no dossier",
        prior=(f"{novelty.prior_value:.4g} from {novelty.prior_source}" if novelty and novelty.prior_value else "none"),
        venue=rep.venue, warnings="\n".join(f"- {w}" for w in rep.warnings) or "- none"))
    rep.files = sorted(str(p.relative_to(out_dir)) for p in out_dir.rglob("*") if p.is_file())
    return rep
