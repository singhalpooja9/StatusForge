"""Calibration for a 3-class (Green/Amber/Red) health call, plus a narrative
faithfulness check.

Two things get measured:

1. ENGINE vs HUMAN color agreement on a labeled gold set. Because the classes are
   ORDINAL (Green < Amber < Red) and the errors are COST-ASYMMETRIC (calling a
   truly-Red program Green is far worse than Green->Amber), we report:
     * the full 3x3 confusion matrix,
     * quadratic-weighted Cohen's kappa (penalizes distant disagreements more),
     * a "danger rate" = fraction of truly-Red teams the engine under-called
       (the catastrophic error), with a Wilson CI.

2. NARRATIVE FAITHFULNESS: does the generated prose ever contradict the engine?
   unsupported_claim_rate = fraction of narratives that assert a different health
   level than the engine's color. This must be ~0 — the whole design promise.

All pure/deterministic given inputs, so it's unit-testable and CI-safe.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

ORDER = {"Green": 0, "Amber": 1, "Red": 2}
CLASSES = ["Green", "Amber", "Red"]


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for k/n (95% default). Stays within [0,1]."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = (z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def confusion_3x3(y_true: list[str], y_pred: list[str]) -> list[list[int]]:
    """3x3 matrix, rows = true class, cols = predicted, in CLASSES order."""
    if len(y_true) != len(y_pred):
        raise ValueError(f"length mismatch: {len(y_true)} vs {len(y_pred)}")
    if not y_true:
        raise ValueError("no labels provided")
    m = [[0, 0, 0] for _ in range(3)]
    for t, p in zip(y_true, y_pred):
        m[ORDER[t]][ORDER[p]] += 1
    return m


def quadratic_weighted_kappa(y_true: list[str], y_pred: list[str]) -> float:
    """Cohen's kappa with quadratic weights over the ordinal classes.

    Weight w_ij = (i-j)^2 / (N-1)^2 penalizes a Green<->Red miss 4x a Green<->Amber
    miss. Returns 1 = perfect, 0 = chance, negative = worse than chance.
    """
    n = len(y_true)
    if n == 0:
        return 0.0
    k = len(CLASSES)
    O = confusion_3x3(y_true, y_pred)
    # weight matrix
    W = [[((i - j) ** 2) / ((k - 1) ** 2) for j in range(k)] for i in range(k)]
    # marginals -> expected matrix
    row = [sum(O[i]) for i in range(k)]
    col = [sum(O[i][j] for i in range(k)) for j in range(k)]
    E = [[row[i] * col[j] / n for j in range(k)] for i in range(k)]
    num = sum(W[i][j] * O[i][j] for i in range(k) for j in range(k))
    den = sum(W[i][j] * E[i][j] for i in range(k) for j in range(k))
    if den == 0:
        return 1.0
    return 1.0 - num / den


@dataclass
class CalibrationReport:
    n: int
    exact_agreement: float
    quadratic_kappa: float
    confusion: list[list[int]]
    danger_rate: float               # truly-Red under-called (Amber/Green), the catastrophic error
    danger_ci: tuple[float, float]
    n_true_red: int

    def summary(self) -> str:
        rows = "\n".join(
            f"  true {CLASSES[i]:<5} | " + " ".join(f"{self.confusion[i][j]:3d}" for j in range(3))
            for i in range(3))
        return (
            f"n={self.n}  exact-agreement={self.exact_agreement:.2f}  "
            f"quadratic-weighted kappa={self.quadratic_kappa:.2f}\n"
            f"DANGER RATE (truly-Red under-called)={self.danger_rate:.2f} "
            f"(95% CI {self.danger_ci[0]:.2f}-{self.danger_ci[1]:.2f}, n_red={self.n_true_red})\n"
            f"confusion (rows=true, cols=pred Green/Amber/Red):\n{rows}")


def calibrate_colors(y_true: list[str], y_pred: list[str]) -> CalibrationReport:
    """Engine-vs-human color calibration on the ordinal, cost-asymmetric scale."""
    m = confusion_3x3(y_true, y_pred)
    n = len(y_true)
    exact = _safe_div(sum(m[i][i] for i in range(3)), n)
    # danger = true Red (row 2) predicted Green(0) or Amber(1)
    n_true_red = sum(m[2])
    under_called = m[2][0] + m[2][1]
    return CalibrationReport(
        n=n,
        exact_agreement=exact,
        quadratic_kappa=quadratic_weighted_kappa(y_true, y_pred),
        confusion=m,
        danger_rate=_safe_div(under_called, n_true_red),
        danger_ci=wilson_interval(under_called, n_true_red),
        n_true_red=n_true_red,
    )


# --------------------------------------------------------- narrative faithfulness ---
# Phrases that assert a HEALTH LEVEL (not a fact like "blocked" or "P1", which can
# legitimately appear at any color). Only genuine status-tier claims belong here.
_LEVEL_WORDS = {
    "on track": "Green", "healthy": "Green", "no risk": "Green", "all good": "Green",
    "on schedule": "Green", "green status": "Green",
    "at risk": "Red", "off track": "Red", "escalate": "Red", "red status": "Red",
    "watch": "Amber", "monitor": "Amber", "amber status": "Amber", "caution": "Amber",
}


def narrative_contradicts(color: str, narrative: str) -> bool:
    """True if the prose asserts a DIFFERENT health level than the engine color.

    Conservative: only flags an explicit opposite claim (e.g. color=Red but text
    says 'on track'). Same-or-unstated level is fine.
    """
    t = narrative.lower()
    claimed = {lvl for phrase, lvl in _LEVEL_WORDS.items() if phrase in t}
    if not claimed:
        return False
    # contradiction if it claims a level and NONE of the claimed levels match the engine
    return color not in claimed


def faithfulness_rate(colors: list[str], narratives: list[str]) -> float:
    """Fraction of narratives that do NOT contradict their engine color (1.0 = all faithful)."""
    if not colors:
        return 1.0
    ok = sum(1 for c, nrt in zip(colors, narratives) if not narrative_contradicts(c, nrt))
    return ok / len(colors)
