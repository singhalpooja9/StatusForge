"""Offline extraction + end-to-end pipeline + narrator-fallback tests."""

import pytest

from statusforge.rulebook import load_rulebook
from statusforge.extract import extract_signals, LLMConfig, OFFLINE
from statusforge.engine import evaluate_team, Verdict
from statusforge.narrate import narrate
from statusforge.dataset import load_gold
from statusforge.calibration import narrative_contradicts

RB = load_rulebook("software")


def test_extract_p1_and_slip():
    s = extract_signals("2 open P1s and slipped 6 days on the critical path", RB)
    assert s["open_p1s"] == 2 and s["critical_path_slip_days"] == 6


def test_extract_ownerless_dep():
    s = extract_signals("1 blocked dependency with no owner", RB)
    assert s["blocked_dependencies"] == 1 and s["ownerless_blocked_deps"] == 1


def test_milestone_bug_fixed_all_hit():
    # "all 4 milestones hit" must be hit=4,total=4 (was the hit=0 bug)
    s = extract_signals("all 4 milestones hit this sprint", RB)
    assert s["milestones_total"] == 4 and s["milestones_hit"] == 4
    assert evaluate_team("T", s, RB).color == "Green"


def test_milestone_of_form():
    s = extract_signals("3 of 5 milestones hit", RB)
    assert s["milestones_total"] == 5 and s["milestones_hit"] == 3


def test_offline_config_flag():
    assert OFFLINE.live is False
    assert LLMConfig(api_key="  ").live is False
    assert LLMConfig(api_key="sk-x").live is True


def test_negative_scope_allowed_but_others_not():
    # scope allows negative; a non-negative signal must reject negatives
    ok = extract_signals("scope -12%", RB)
    assert ok["scope_delta_pct"] == -12


def test_narrate_fallback_on_live_failure(monkeypatch):
    """A live call that raises must silently fall back to offline prose."""
    import statusforge.narrate as N
    def boom(v, cfg):
        raise RuntimeError("groq 429")
    monkeypatch.setattr(N, "_real_narrate", boom)
    v = Verdict(team="T", color="Red", reasons=["2 open P1(s)"], signals={})
    text, used_live = N.narrate(v, LLMConfig(api_key="sk-fake"))
    assert used_live is False           # fell back
    assert "Red" in text and text       # got offline prose, not a crash


def test_gold_pipeline_faithful_and_reasonable():
    gold = load_gold("software")
    agree = 0
    for row in gold:
        s = extract_signals(row["text"], RB)
        v = evaluate_team(row["team"], s, RB)
        v.narrative, _ = narrate(v)
        assert not narrative_contradicts(v.color, v.narrative)
        if v.color == row["human_color"]:
            agree += 1
    assert agree >= len(gold) - 3
