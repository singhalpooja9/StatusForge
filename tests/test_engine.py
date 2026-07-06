"""Tests for the rulebook interpreter engine — the must-be-correct core.

The engine is a pure function of (signals, rulebook); these pin its behavior on the
software rulebook with hand-worked cases.
"""

import pytest

from statusforge.rulebook import load_rulebook
from statusforge.engine import evaluate_team, evaluate_program

RB = load_rulebook("software")


def color(sig: dict) -> str:
    return evaluate_team("T", sig, RB).color


def test_all_clear_is_green():
    assert color({"milestones_total": 4, "milestones_hit": 4}) == "Green"


def test_open_p1_forces_red():
    v = evaluate_team("T", {"open_p1s": 1}, RB)
    assert v.color == "Red"
    assert any("P1" in r for r in v.reasons)


def test_ownerless_blocked_dep_forces_red():
    assert color({"blocked_dependencies": 1, "ownerless_blocked_deps": 1}) == "Red"


def test_slip_thresholds():
    assert color({"critical_path_slip_days": 5}) == "Red"
    assert color({"critical_path_slip_days": 2}) == "Amber"
    assert color({"critical_path_slip_days": 1}) == "Green"


def test_scope_delta_abs():
    assert color({"scope_delta_pct": 30}) == "Red"
    assert color({"scope_delta_pct": -30}) == "Red"   # abs>= catches cuts too
    assert color({"scope_delta_pct": 12}) == "Amber"


def test_owned_blocked_dep_is_amber():
    assert color({"blocked_dependencies": 2, "ownerless_blocked_deps": 0}) == "Amber"


def test_milestone_miss_derived_rule():
    assert color({"milestones_total": 5, "milestones_hit": 3}) == "Amber"   # 40% missed
    assert color({"milestones_total": 5, "milestones_hit": 5}) == "Green"   # 0% missed


def test_red_precedence_over_amber():
    assert color({"open_p1s": 1, "blocked_dependencies": 3}) == "Red"


def test_program_color_is_worst_team():
    teams = [
        ("A", {"milestones_total": 2, "milestones_hit": 2}),  # Green
        ("B", {"critical_path_slip_days": 2}),                # Amber
        ("C", {"open_p1s": 2}),                               # Red
    ]
    roll = evaluate_program(teams, RB)
    assert roll.program_color == "Red"
    assert roll.teams[0].team == "C"  # Red first


def test_program_green_when_all_green():
    teams = [("A", {}), ("B", {"milestones_total": 3, "milestones_hit": 3})]
    assert evaluate_program(teams, RB).program_color == "Green"


def test_empty_program_raises():
    with pytest.raises(ValueError):
        evaluate_program([], RB)


def test_marketing_rulebook_is_domain_independent():
    """Same engine, different rulebook -> a non-software domain grades correctly."""
    mk = load_rulebook("marketing")
    # 1 legal approval pending -> Red per marketing rules
    assert evaluate_team("Brand", {"legal_approvals_pending": 1}, mk).color == "Red"
    # all assets ready, nothing blocked -> Green
    assert evaluate_team("Web", {"assets_total": 10, "assets_ready": 10}, mk).color == "Green"
    # 1 channel blocked -> Amber
    assert evaluate_team("Email", {"channels_blocked": 1}, mk).color == "Amber"
