"""The deterministic RAG-color engine — now a pure INTERPRETER over a rulebook.

The color is a pure function of (signals, rulebook). No LLM, no eval, no domain
code: the engine loops the validated rules from a Rulebook (see rulebook.py) and
applies whitelisted operators. Point it at a different rulebook and it grades a
marketing launch or a construction schedule identically — the governance skeleton
(team, color precedence Red>Amber>Green, worst-team rollup) stays fixed; only the
domain rules change.

`signals` is a plain dict {signal_name: number} of ONLY the signals a human actually
provided; a signal that is absent means "not provided", and every rule on it is
skipped (never evaluated against a phantom 0). Validation/cleaning of the dict lives
in models.validate_signals(); here we assume an already-validated dict.
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


import re as _re


def _pluralize(text: str, *, plural: bool) -> str:
    """Resolve inline pluralization markers by count. Two markers are supported so a
    reason template reads naturally at n==1 and n!=1:
      * 'issue(s)'  -> 'issue'  / 'issues'   (regular; stem may be alphanumeric, so
                       'P1(s)' -> 'P1' / 'P1s' also works)
      * 'dependency(ies)' -> 'dependency' / 'dependencies'  (y->ies plural)
    Run the '(ies)' rule first so it doesn't collide with the '(s)' rule."""
    text = _re.sub(r"(\w+)y\(ies\)",
                   lambda m: m.group(1) + ("ies" if plural else "y"), text)
    text = _re.sub(r"(\w+)\(s\)",
                   lambda m: m.group(1) + ("s" if plural else ""), text)
    return text


def _fmt(reason: str, *, signal: str = "", op: str = "", value: float = 0, n: float = 0) -> str:
    """Fill a rule's reason template. {n} = the signal's value; also {signal}/{op}/{value}.
    Resolves pluralization markers ('issue(s)', 'P1(s)', 'dependency(ies)') by n."""
    n_str = f"{n:g}"
    try:
        out = reason.format(n=n_str, signal=signal, op=op, value=f"{value:g}")
    except (KeyError, IndexError):
        out = reason
    return _pluralize(out, plural=abs(n) != 1)


def evaluate_team(team: str, signals: dict[str, float], rulebook: Rulebook | str) -> Verdict:
    """Compute a team's color from its signals + a rulebook. Pure and deterministic."""
    rb = rulebook if isinstance(rulebook, Rulebook) else load_rulebook(rulebook)

    fired: dict[str, list[str]] = {"Red": [], "Amber": [], "Green": []}

    # plain single-signal rules — a signal that was NOT provided is skipped, never
    # treated as 0. A blank cell means "no data", so its rules simply don't fire
    # (and aren't mentioned); a genuinely-entered 0 is present in `signals` and fires.
    for rule in rb.rules:
        if rule.signal not in signals:
            continue
        val = float(signals[rule.signal])
        if OPERATORS[rule.op](val, rule.value):
            fired[rule.color].append(_fmt(rule.reason, signal=rule.signal, op=rule.op,
                                          value=rule.value, n=val))
    # derived rules (e.g. milestone miss %) — need BOTH operands provided.
    for d in rb.derived_rules:
        if d.total not in signals or d.hit not in signals:
            continue
        total = float(signals[d.total])
        hit = float(signals[d.hit])
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
