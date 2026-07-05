"""Tests for the deterministic RAG-color engine — the must-be-correct core.

Hand-worked cases a reviewer can verify by eye. The engine is pure, so these
fully pin its behavior with no mocking.
"""

import pytest

from statusforge.models import TeamSignals
from statusforge.engine import evaluate_team, evaluate_program, RuleConfig


def sig(**kw) -> TeamSignals:
    base = dict(team="T")
    base.update(kw)
    return TeamSignals(**base)


def test_all_clear_is_green():
    v = evaluate_team(sig(milestones_total=4, milestones_hit=4))
    assert v.color == "Green"


def test_open_p1_forces_red():
    v = evaluate_team(sig(open_p1s=1))
    assert v.color == "Red"
    assert any("P1" in r for r in v.reasons)


def test_ownerless_blocked_dep_forces_red():
    v = evaluate_team(sig(blocked_dependencies=1, ownerless_blocked_deps=1))
    assert v.color == "Red"
    assert any("no owner" in r for r in v.reasons)


def test_big_slip_is_red_small_slip_is_amber():
    assert evaluate_team(sig(critical_path_slip_days=5)).color == "Red"
    assert evaluate_team(sig(critical_path_slip_days=2)).color == "Amber"
    assert evaluate_team(sig(critical_path_slip_days=1)).color == "Green"


def test_scope_delta_thresholds():
    assert evaluate_team(sig(scope_delta_pct=30)).color == "Red"
    assert evaluate_team(sig(scope_delta_pct=-30)).color == "Red"   # cuts count too (abs)
    assert evaluate_team(sig(scope_delta_pct=12)).color == "Amber"


def test_owned_blocked_dep_is_amber_not_red():
    # a blocked dep WITH an owner is amber; ownerless is red
    v = evaluate_team(sig(blocked_dependencies=2, ownerless_blocked_deps=0))
    assert v.color == "Amber"


def test_milestone_miss_is_amber():
    v = evaluate_team(sig(milestones_total=5, milestones_hit=3))  # 40% missed
    assert v.color == "Amber"


def test_red_precedence_over_amber():
    # both a red and amber condition present -> Red, and red reasons reported
    v = evaluate_team(sig(open_p1s=1, blocked_dependencies=3))
    assert v.color == "Red"


def test_program_color_is_worst_team():
    teams = [
        sig(team="A", milestones_total=2, milestones_hit=2),  # Green
        sig(team="B", critical_path_slip_days=2),             # Amber
        sig(team="C", open_p1s=2),                            # Red
    ]
    roll = evaluate_program(teams)
    assert roll.program_color == "Red"
    assert roll.teams[0].team == "C"   # Red sorted first


def test_program_green_when_all_green():
    teams = [sig(team="A"), sig(team="B", milestones_total=3, milestones_hit=3)]
    assert evaluate_program(teams).program_color == "Green"


def test_milestone_invariant_rejected():
    with pytest.raises(ValueError):
        sig(milestones_total=2, milestones_hit=5)


def test_empty_program_raises():
    with pytest.raises(ValueError):
        evaluate_program([])


def test_thresholds_are_tunable():
    strict = RuleConfig(red_slip_days=1)
    assert evaluate_team(sig(critical_path_slip_days=1), strict).color == "Red"
