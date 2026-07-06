"""Regression tests for the "blank cell = not provided, not 0" contract.

The bug: an unfilled signal cell defaulted to 0, and 0 fired rules — so a team that
never entered "% Complete" showed "only 0% complete" and got pushed to Amber. A
missing signal must be OMITTED end-to-end (validate -> engine -> every output), while
a genuinely-typed 0 must still be present and still fire.
"""

from statusforge.rulebook import load_rulebook
from statusforge.models import validate_signals
from statusforge.engine import evaluate_team, _fmt
from statusforge.extract import extract_signals

RB = load_rulebook("program")


# ---------------------------------------------------------------- validate_signals ---
def test_missing_signal_is_omitted_not_zeroed():
    sig = validate_signals({"blockers": 0, "days_behind": 0, "critical_issues": 0}, RB)
    assert "percent_complete" not in sig          # not provided -> absent, not 0.0
    assert sig == {"blockers": 0.0, "days_behind": 0.0, "critical_issues": 0.0}


def test_blank_and_none_cells_are_omitted():
    sig = validate_signals({"percent_complete": "", "days_behind": None, "blockers": 2}, RB)
    assert sig == {"blockers": 2.0}               # blank str + None both dropped


def test_typed_zero_is_kept():
    # An explicitly-entered 0% must survive and fire the "<=20" amber rule.
    sig = validate_signals({"percent_complete": 0, "days_behind": 0,
                            "blockers": 0, "critical_issues": 0}, RB)
    assert sig["percent_complete"] == 0.0
    assert evaluate_team("T", sig, RB).color == "Amber"


# --------------------------------------------------------------------------- engine ---
def test_engine_skips_rule_for_missing_signal():
    # Clean team, % Complete never provided -> Green, and NO "0% complete" reason.
    v = evaluate_team("Data", {"blockers": 0, "days_behind": 0, "critical_issues": 0}, RB)
    assert v.color == "Green"
    assert not any("complete" in r.lower() for r in v.reasons)


def test_missing_percent_does_not_add_reason_to_amber_team():
    # 2 days behind (Amber) with % Complete missing: the ONLY reason is the slip.
    v = evaluate_team("Data", {"days_behind": 2, "blockers": 0, "critical_issues": 0}, RB)
    assert v.color == "Amber"
    assert v.reasons == ["2 days behind"]         # no phantom "only 0% complete"


def test_typed_low_percent_still_fires():
    v = evaluate_team("T", {"percent_complete": 5, "days_behind": 0,
                            "blockers": 0, "critical_issues": 0}, RB)
    assert v.color == "Amber"
    assert any("5% complete" in r for r in v.reasons)


# ----------------------------------------------------------------------- extraction ---
def test_offline_extract_omits_unmentioned_signals():
    # Free text mentions only a slip; % Complete etc. must NOT appear as 0.
    sig = extract_signals("2 days behind schedule this week", RB)
    assert "percent_complete" not in sig
    assert sig.get("days_behind") == 2.0
    assert evaluate_team("Data", sig, RB).reasons == ["2 days behind"]


# --------------------------------------------------------------------- pluralization ---
def test_pluralization_singular_and_plural():
    assert _fmt("{n} critical issue(s) open", n=1) == "1 critical issue open"
    assert _fmt("{n} critical issue(s) open", n=2) == "2 critical issues open"
    assert _fmt("{n} blocker(s)", n=1) == "1 blocker"


def test_pluralization_alnum_stem_and_ies():
    # digit-terminated stem (P1) and y->ies plural must both resolve.
    assert _fmt("{n} open P1(s)", n=1) == "1 open P1"
    assert _fmt("{n} open P1(s)", n=2) == "2 open P1s"
    assert _fmt("{n} blocked dependency(ies)", n=1) == "1 blocked dependency"
    assert _fmt("{n} blocked dependency(ies)", n=2) == "2 blocked dependencies"
