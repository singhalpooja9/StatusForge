"""The deterministic RAG-color engine — now a pure INTERPRETER over a rulebook.

The color is a pure function of (signals, rulebook). No LLM, no eval, no domain
code: the engine loops the validated rules from a Rulebook (see rulebook.py) and
applies whitelisted operators. Point it at a different rulebook and it grades a
marketing launch or a construction schedule identically — the governance skeleton
(team, color precedence Red>Amber>Green, worst-team rollup) stays fixed; only the
domain rules change.

`signals` is a plain dict {signal_name: number}. Validation that the dict matches
the rulebook lives in models.build_signal_model(); here we assume a validated dict.
"""

from __future__ import annotations

from dataclasses import dataclass

from .rulebook import Rulebook, OPERATORS, load_rulebook

# Fixed color precedence — this is the governance skeleton, not domain content.
_PRECEDENCE = ["Red", "Amber", "Green"]


@dataclass
class Verdict:
    team: str
    color: str
    reasons: list[str]
    signals: dict[str, float]
    narrative: str = ""

    @property
    def rank(self) -> int:
        return _PRECEDENCE.index(self.color)


@dataclass
class ProgramRollup:
    program_color: str
    teams: list[Verdict]
    domain: str = ""
    summary: str = ""


def _fmt(reason: str, *, signal: str = "", op: str = "", value: float = 0, n: float = 0) -> str:
    """Fill a rule's reason template. {n} = the signal's value; also {signal}/{op}/{value}."""
    n_str = f"{n:g}"
    try:
        return reason.format(n=n_str, signal=signal, op=op, value=f"{value:g}")
    except (KeyError, IndexError):
        return reason


def evaluate_team(team: str, signals: dict[str, float], rulebook: Rulebook | str) -> Verdict:
    """Compute a team's color from its signals + a rulebook. Pure and deterministic."""
    rb = rulebook if isinstance(rulebook, Rulebook) else load_rulebook(rulebook)

    fired: dict[str, list[str]] = {"Red": [], "Amber": [], "Green": []}

    # plain single-signal rules
    for rule in rb.rules:
        val = float(signals.get(rule.signal, 0))
        if OPERATORS[rule.op](val, rule.value):
            fired[rule.color].append(_fmt(rule.reason, signal=rule.signal, op=rule.op,
                                          value=rule.value, n=val))
    # derived rules (e.g. milestone miss %)
    for d in rb.derived_rules:
        total = float(signals.get(d.total, 0))
        hit = float(signals.get(d.hit, 0))
        if total > 0:
            miss_pct = 100.0 * (total - hit) / total
            if OPERATORS[d.op](miss_pct, d.value):
                fired[d.color].append(_fmt(d.reason, n=round(miss_pct)))

    # color precedence: Red > Amber > Green
    if fired["Red"]:
        color, reasons = "Red", fired["Red"]
    elif fired["Amber"]:
        color, reasons = "Amber", fired["Amber"]
    else:
        color, reasons = "Green", ["all signals within thresholds"]

    return Verdict(team=team, color=color, reasons=reasons, signals=signals)


def evaluate_program(teams: list[tuple[str, dict[str, float]]],
                     rulebook: Rulebook | str) -> ProgramRollup:
    """Roll up (team, signals) pairs. Program color = worst team color."""
    if not teams:
        raise ValueError("no teams provided")
    rb = rulebook if isinstance(rulebook, Rulebook) else load_rulebook(rulebook)
    verdicts = [evaluate_team(name, sig, rb) for name, sig in teams]
    verdicts.sort(key=lambda v: v.rank)  # Red first
    return ProgramRollup(program_color=verdicts[0].color, teams=verdicts, domain=rb.domain)
