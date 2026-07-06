"""Rulebook loading + validation.

A rulebook is DATA (YAML): a list of signals + a list of rules that map a
threshold on one signal to a color. The engine interprets it purely, so the
Red/Amber/Green is a function of (signals, rulebook) — both inspectable.

SAFETY: operators are a fixed WHITELIST; there is no expression language and no
eval. Validation FAILS CLOSED — an unknown signal, operator, or malformed rule
raises and the engine refuses to run, so an edited rulebook can never silently
mis-grade a program.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

RULEBOOK_DIR = Path(__file__).resolve().parent.parent / "rulebooks"

# The only comparisons a rule may use. No expressions, no code.
OPERATORS = {
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    ">":  lambda a, b: a > b,
    "<":  lambda a, b: a < b,
    "==": lambda a, b: a == b,
    "abs>=": lambda a, b: abs(a) >= b,
    "abs<=": lambda a, b: abs(a) <= b,
}

COLORS = {"Green", "Amber", "Red"}


class RulebookError(ValueError):
    """Raised on any malformed rulebook — the engine refuses to run."""


@dataclass(frozen=True)
class Signal:
    name: str
    label: str
    help: str = ""
    allow_negative: bool = False


@dataclass(frozen=True)
class Rule:
    color: str
    signal: str
    op: str
    value: float
    reason: str


@dataclass(frozen=True)
class DerivedRule:
    color: str
    kind: str            # currently only "milestone_miss_pct"
    total: str
    hit: str
    op: str
    value: float
    reason: str


@dataclass(frozen=True)
class Rulebook:
    domain: str
    signals: list[Signal]
    rules: list[Rule]
    derived_rules: list[DerivedRule] = field(default_factory=list)

    @property
    def signal_names(self) -> set[str]:
        return {s.name for s in self.signals}


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise RulebookError(msg)


def load_rulebook(source: str | Path | dict) -> Rulebook:
    """Load + validate a rulebook from a path, a YAML string, or a dict.
    Fails closed on any structural or referential error."""
    if isinstance(source, dict):
        data = source
    else:
        p = Path(source)
        if p.exists():
            data = yaml.safe_load(p.read_text())
        else:
            # allow a bare name like "software" -> rulebooks/software.yaml
            named = RULEBOOK_DIR / f"{source}.yaml"
            if named.exists():
                data = yaml.safe_load(named.read_text())
            else:
                data = yaml.safe_load(str(source))  # treat as inline YAML
    _require(isinstance(data, dict), "rulebook must be a mapping")

    signals = [Signal(name=s["name"], label=s.get("label", s["name"]),
                      help=s.get("help", ""), allow_negative=bool(s.get("allow_negative", False)))
               for s in data.get("signals", [])]
    _require(bool(signals), "rulebook has no signals")
    names = {s.name for s in signals}
    _require(len(names) == len(signals), "duplicate signal names")

    def _mk_rule(r: dict, idx: int) -> Rule:
        _require(r.get("color") in COLORS, f"rule {idx}: color must be one of {COLORS}")
        _require(r.get("signal") in names, f"rule {idx}: unknown signal {r.get('signal')!r}")
        _require(r.get("op") in OPERATORS, f"rule {idx}: unknown operator {r.get('op')!r}")
        _require(isinstance(r.get("value"), (int, float)), f"rule {idx}: value must be numeric")
        return Rule(color=r["color"], signal=r["signal"], op=r["op"],
                    value=float(r["value"]), reason=r.get("reason", "{signal} {op} {value}"))

    rules = [_mk_rule(r, i) for i, r in enumerate(data.get("rules", []))]
    _require(bool(rules), "rulebook has no rules")

    def _mk_derived(r: dict, idx: int) -> DerivedRule:
        _require(r.get("color") in COLORS, f"derived {idx}: bad color")
        _require(r.get("kind") == "milestone_miss_pct", f"derived {idx}: unknown kind {r.get('kind')!r}")
        _require(r.get("total") in names and r.get("hit") in names,
                 f"derived {idx}: total/hit must reference declared signals")
        _require(r.get("op") in OPERATORS, f"derived {idx}: unknown operator")
        _require(isinstance(r.get("value"), (int, float)), f"derived {idx}: value must be numeric")
        return DerivedRule(color=r["color"], kind=r["kind"], total=r["total"], hit=r["hit"],
                           op=r["op"], value=float(r["value"]), reason=r.get("reason", "derived"))

    derived = [_mk_derived(r, i) for i, r in enumerate(data.get("derived_rules", []))]

    return Rulebook(domain=data.get("domain", "Program"), signals=signals,
                    rules=rules, derived_rules=derived)
