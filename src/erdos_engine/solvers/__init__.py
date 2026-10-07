"""Registry of problem solvers."""
from __future__ import annotations

from .base import CheckReport, Result, Solver
from .p375 import Problem375
from .p458 import Problem458
from .p647 import Problem647
from .p699 import Problem699
from .p848 import Problem848
from .p993 import Problem993

REGISTRY: dict[int, type[Solver]] = {
    cls.problem: cls for cls in (Problem375, Problem458, Problem647, Problem699, Problem848, Problem993)
}


def get_solver(problem: int) -> Solver:
    try:
        return REGISTRY[problem]()
    except KeyError:
        raise KeyError(f"no solver for problem #{problem}; available: {sorted(REGISTRY)}") from None


__all__ = ["REGISTRY", "get_solver", "Solver", "Result", "CheckReport"]
