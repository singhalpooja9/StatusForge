"""The deterministic RAG-color rule engine — the load-bearing part of StatusForge.

The Red/Amber/Green color for a team is a PURE FUNCTION of its numeric signals.
No LLM is involved here. This is the whole governance point: a program's health
tier can be audited, reproduced, and unit-tested, and it can never be
hallucinated or argued up by generated prose.

The thresholds below encode the kind of judgment a senior TPM applies on a weekly
program review. They live in one place (RuleConfig) so they're inspectable and
tunable, and each rule records a human-readable reason when it fires.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import TeamSignals, Verdict, ProgramRollup, Color


@dataclass(frozen=True)
class RuleConfig:
    """Tunable thresholds. Defaults reflect a typical weekly program review.

    A team goes RED if ANY red rule fires; else AMBER if any amber rule fires;
    else GREEN. Red rules are the ones a TPM escalates on.
    """
    # Red thresholds
    red_slip_days: int = 5            # >= this many critical-path slip days => Red
    red_open_p1s: int = 1             # any open P1 => Red
    red_ownerless_blocked: int = 1    # any blocked dep with no owner => Red
    red_scope_delta_pct: float = 25.0 # scope moved >= this (abs) => Red

    # Amber thresholds (only reached if no red rule fired)
    amber_slip_days: int = 2
    amber_blocked_deps: int = 1
    amber_scope_delta_pct: float = 10.0
    amber_milestone_miss_pct: float = 20.0  # missing >= this % of milestones => Amber


def evaluate_team(signals: TeamSignals, cfg: RuleConfig | None = None) -> Verdict:
    """Compute a team's RAG color from its signals. Deterministic and pure."""
    cfg = cfg or RuleConfig()
    red_reasons: list[str] = []
    amber_reasons: list[str] = []

    # ---- RED rules ----
    if signals.open_p1s >= cfg.red_open_p1s:
        red_reasons.append(f"{signals.open_p1s} open P1(s)")
    if signals.critical_path_slip_days >= cfg.red_slip_days:
        red_reasons.append(f"critical path slipped {signals.critical_path_slip_days}d "
                           f"(>= {cfg.red_slip_days}d)")
    if signals.ownerless_blocked_deps >= cfg.red_ownerless_blocked:
        red_reasons.append(f"{signals.ownerless_blocked_deps} blocked dependency(ies) with no owner")
    if abs(signals.scope_delta_pct) >= cfg.red_scope_delta_pct:
        red_reasons.append(f"scope moved {signals.scope_delta_pct:+.0f}% "
                           f"(>= {cfg.red_scope_delta_pct:.0f}%)")

    # ---- AMBER rules ----
    if signals.critical_path_slip_days >= cfg.amber_slip_days:
        amber_reasons.append(f"critical path slipped {signals.critical_path_slip_days}d")
    if signals.blocked_dependencies >= cfg.amber_blocked_deps:
        amber_reasons.append(f"{signals.blocked_dependencies} blocked dependency(ies)")
    if abs(signals.scope_delta_pct) >= cfg.amber_scope_delta_pct:
        amber_reasons.append(f"scope moved {signals.scope_delta_pct:+.0f}%")
    if signals.milestones_total > 0:
        miss_pct = 100.0 * (signals.milestones_total - signals.milestones_hit) / signals.milestones_total
        if miss_pct >= cfg.amber_milestone_miss_pct:
            amber_reasons.append(f"missed {miss_pct:.0f}% of milestones "
                                 f"({signals.milestones_hit}/{signals.milestones_total} hit)")

    if red_reasons:
        color: Color = "Red"
        reasons = red_reasons
    elif amber_reasons:
        color = "Amber"
        reasons = amber_reasons
    else:
        color = "Green"
        reasons = ["all signals within thresholds"]

    return Verdict(team=signals.team, color=color, reasons=reasons, signals=signals)


def evaluate_program(team_signals: list[TeamSignals], cfg: RuleConfig | None = None) -> ProgramRollup:
    """Roll up teams into a program verdict. Program color = worst team color."""
    if not team_signals:
        raise ValueError("no team signals provided")
    verdicts = [evaluate_team(s, cfg) for s in team_signals]
    verdicts.sort(key=lambda v: v.rank)  # Red first
    program_color: Color = verdicts[0].color  # worst, since sorted Red->Green
    return ProgramRollup(program_color=program_color, teams=verdicts)
