"""Tests for the offline signal extraction + end-to-end offline pipeline."""

from statusforge.extract import extract_signals, LLMConfig, OFFLINE
from statusforge.engine import evaluate_team
from statusforge.narrate import narrate
from statusforge.dataset import load_gold
from statusforge.calibration import narrative_contradicts


def test_extract_pulls_p1_and_slip():
    s = extract_signals("T", "2 open P1s and slipped 6 days on the critical path")
    assert s.open_p1s == 2
    assert s.critical_path_slip_days == 6


def test_extract_ownerless_dep():
    s = extract_signals("T", "1 blocked dependency with no owner")
    assert s.blocked_dependencies == 1
    assert s.ownerless_blocked_deps == 1


def test_extract_scope_and_milestones():
    s = extract_signals("T", "scope +30%, 3 of 5 milestones hit")
    assert s.scope_delta_pct == 30
    assert s.milestones_total == 5 and s.milestones_hit == 3


def test_offline_config_is_not_live():
    assert OFFLINE.live is False
    assert LLMConfig(api_key="  ").live is False   # blank/whitespace = offline
    assert LLMConfig(api_key="sk-xyz").live is True


def test_gold_set_pipeline_is_faithful_and_reasonable():
    """End-to-end on the gold set (offline): narrative never contradicts the color,
    and engine agreement with human labels is high (the set was written to be
    unambiguous for the documented thresholds)."""
    gold = load_gold()
    agree = 0
    for row in gold:
        s = extract_signals(row["team"], row["text"])
        v = evaluate_team(s)
        v.narrative = narrate(v)
        assert not narrative_contradicts(v.color, v.narrative)  # faithfulness by construction
        if v.color == row["human_color"]:
            agree += 1
    # allow a couple of extraction misses but expect strong agreement
    assert agree >= len(gold) - 3
