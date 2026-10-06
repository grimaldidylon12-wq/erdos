"""Solver interface shared by all problem modules.

A solver turns a finite search into a `Result` carrying a JSON certificate.
Its `check` method must re-derive the claim through an independent code path
(different algorithm and/or implementation) and returns a `CheckReport`.
Publication tooling refuses results whose check did not pass.
"""
from __future__ import annotations

import datetime as _dt
import platform
import time
from dataclasses import asdict, dataclass, field
from typing import Any, ClassVar

from .. import __version__

#: Outcomes, from strongest to weakest.
COUNTEREXAMPLE = "counterexample"        # settles a falsifiable problem (negatively)
EXAMPLE = "example"                      # settles a verifiable problem (positively)
VERIFIED_TO_BOUND = "verified_to_bound"  # no counterexample in a finite range
SEQUENCE = "sequence"                    # computed terms of an associated sequence
NO_CONCLUSION = "no_conclusion"

SETTLING_OUTCOMES = {COUNTEREXAMPLE, EXAMPLE}


@dataclass
class Result:
    problem: int
    solver: str
    outcome: str
    params: dict[str, Any]
    summary: str
    certificate: dict[str, Any]
    stats: dict[str, Any] = field(default_factory=dict)
    frontier: float | None = None  # the bound reached, when applicable
    engine_version: str = __version__
    created: str = field(default_factory=lambda: _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"))
    host: str = field(default_factory=lambda: f"{platform.system()} {platform.machine()} py{platform.python_version()}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Result":
        return cls(**d)

    @property
    def settles_problem(self) -> bool:
        return self.outcome in SETTLING_OUTCOMES


@dataclass
class CheckReport:
    ok: bool
    checker: str
    details: list[str] = field(default_factory=list)
    seconds: float = 0.0

    def fail(self, msg: str) -> "CheckReport":
        self.ok = False
        self.details.append("FAIL: " + msg)
        return self

    def note(self, msg: str) -> None:
        self.details.append(msg)


class Solver:
    """Base class.  Subclasses set the ClassVars and implement run/check."""

    problem: ClassVar[int]
    name: ClassVar[str]
    title: ClassVar[str]
    statement_tex: ClassVar[str]
    #: what kind of finite certificate could settle the problem
    finite_kind: ClassVar[str] = "falsifiable"
    tags: ClassVar[tuple[str, ...]] = ()
    references: ClassVar[tuple[str, ...]] = ()  # BibTeX keys in publish/refs.bib
    #: parameters for a quick smoke run (used by tests and `erdos-engine demo`)
    quick_params: ClassVar[dict[str, Any]] = {}

    def run(self, **params: Any) -> Result:  # pragma: no cover - abstract
        raise NotImplementedError

    def check(self, result: Result) -> CheckReport:  # pragma: no cover - abstract
        raise NotImplementedError

    def method_tex(self, result: Result) -> str:
        """LaTeX paragraph(s) describing the method, for the paper."""
        return ""

    def results_tex(self, result: Result) -> str:
        """LaTeX describing the outcome."""
        return _tex_escape(result.summary)

    def abstract_tex(self, result: Result) -> str:
        """One or two sentences of LaTeX for the abstract."""
        return _tex_escape(result.summary)

    # helpers -------------------------------------------------------------
    def _result(self, outcome: str, params: dict, summary: str, certificate: dict,
                stats: dict | None = None, frontier: float | None = None) -> Result:
        return Result(self.problem, self.name, outcome, params, summary, certificate,
                      stats or {}, frontier)


class Timer:
    def __enter__(self):
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.seconds = time.perf_counter() - self.t0
        return False


_ESC = {"&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
        "~": r"\textasciitilde{}", "^": r"\textasciicircum{}", "\\": r"\textbackslash{}"}


def _tex_escape(s: str) -> str:
    return "".join(_ESC.get(ch, ch) for ch in s)
