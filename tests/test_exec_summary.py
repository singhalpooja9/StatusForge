"""Quality-bar tests for the OFFLINE executive summary.

This is the PUBLIC DEFAULT most visitors see (no LLM key), so it must read like a
leader wrote it — flowing sentences, not an "At risk: …; Watch: …; On track: …"
label-run. These tests pin the properties that make it read well and stay honest:
  * BLUF: opens with the bold bottom line (color + driver).
  * No semicolon label-runs; reasons are joined in English ('A and B').
  * The user's context is woven in verbatim (never invented).
  * A team's Note is folded into its clause.
  * It closes with an explicit Ask.
  * It never contradicts the engine color (faithfulness).
"""

from statusforge.rulebook import load_rulebook
from statusforge.models import validate_signals
from statusforge.engine import evaluate_program
from statusforge.narrate import _exec_summary, _english_join
from statusforge.calibration import narrative_contradicts
from statusforge.extract import LLMConfig

RB = load_rulebook("program")
OFF = LLMConfig(api_key="")


def _roll(rows):
    return evaluate_program([(n, validate_signals(s, RB)) for n, s in rows], RB)


# The canonical scenario from the brief: Checkout+Billing red, Data amber, Identity green.
RED_ROWS = [
    ("Checkout", {"critical_issues": 2, "days_behind": 6, "blockers": 1, "percent_complete": 60}),
    ("Billing",  {"blockers": 3, "days_behind": 1, "critical_issues": 0, "percent_complete": 50}),
    ("Data",     {"days_behind": 2, "blockers": 0, "critical_issues": 0}),   # % Complete BLANK
    ("Identity", {"blockers": 0, "days_behind": 0, "critical_issues": 0, "percent_complete": 90}),
]
CTX = "Launching Payments v2 on Aug 15; slip risks Prime Day"
EXTRAS = {"Checkout": {"Notes": "two P1s block the release candidate"},
          "Billing":  {"Notes": "blockers on vendor API"},
          "Identity": {"Notes": "auth revamp shipped"}}


def test_english_join_reads_naturally():
    assert _english_join([]) == ""
    assert _english_join(["a"]) == "a"
    assert _english_join(["a", "b"]) == "a and b"
    assert _english_join(["a", "b", "c"]) == "a, b, and c"


def test_exec_summary_is_bluf_and_flowing():
    text, live = _exec_summary(_roll(RED_ROWS), OFF, context=CTX, extras=EXTRAS)
    assert live is False
    assert text.startswith("**The program is RED, driven by Checkout.**")
    # Not a label-run: the amateur "At risk: …; Watch: …; On track: …" is gone.
    for label in ("At risk:", "Watch:", "On track:"):
        assert label not in text
    # reasons flow in English, not semicolon-joined inside a team's clause.
    # (The only ';' allowed is inside the user's own context string, passed verbatim.)
    assert "2 critical issues open and 6 days behind schedule" in text
    body_wo_ctx = text.replace(CTX, "")
    assert "; " not in body_wo_ctx                # no semicolon reason-runs of our own


def test_exec_summary_weaves_context_and_notes():
    text, _ = _exec_summary(_roll(RED_ROWS), OFF, context=CTX, extras=EXTRAS)
    assert "Launching Payments v2 on Aug 15" in text        # user's stakes, verbatim
    assert "(two P1s block the release candidate)" in text  # driver's note, folded in
    assert text.rstrip().endswith("this week.")             # closes on the Ask
    assert "Ask: dedicated help to unblock Checkout" in text


def test_exec_summary_never_invents_impact_when_no_context():
    text, _ = _exec_summary(_roll(RED_ROWS), OFF, context="", extras=EXTRAS)
    # With no context, no stakes sentence is fabricated — the driver clause follows the BLUF.
    assert "Launching" not in text and "Prime Day" not in text
    assert "Checkout is the biggest risk" in text


def test_exec_summary_greens_fold_into_one_clause_not_a_label_line():
    text, _ = _exec_summary(_roll(RED_ROWS), OFF, context=CTX, extras=EXTRAS)
    assert "Meanwhile," in text
    assert "Identity is on track" in text        # green gets a clause, not its own label line


def test_all_green_says_it_once_no_redundant_meanwhile():
    rows = [("A", {"blockers": 0, "days_behind": 0, "critical_issues": 0, "percent_complete": 90}),
            ("B", {"blockers": 0, "days_behind": 0, "critical_issues": 0, "percent_complete": 80})]
    text, _ = _exec_summary(_roll(rows), OFF)
    assert text == "**The program is GREEN — all teams on track.**"
    assert "Meanwhile" not in text               # don't repeat "on track"


def test_amber_only_has_a_watch_ask():
    rows = [("A", {"days_behind": 2, "blockers": 0, "critical_issues": 0}),
            ("B", {"blockers": 0, "days_behind": 0, "critical_issues": 0, "percent_complete": 95})]
    text, _ = _exec_summary(_roll(rows), OFF, context="GA slips if this holds")
    assert text.startswith("**The program is AMBER, driven by A.**")
    assert "is the one to watch" in text
    assert "Ask: hold A on the weekly watch" in text


def test_exec_summary_bottom_line_matches_program_color():
    # The BLUF sentence must assert the program's own color (never a different tier).
    # NOTE: the faithfulness checker is for single-team narratives; a multi-team summary
    # legitimately names an on-track team inside a red program, so we assert on the
    # bold bottom line, which is the sentence that states the *program* status.
    for rows, ctx in [(RED_ROWS, CTX),
                      ([("A", {"days_behind": 2, "blockers": 0, "critical_issues": 0})], ""),
                      ([("A", {"blockers": 0, "days_behind": 0, "critical_issues": 0, "percent_complete": 90})], "")]:
        roll = _roll(rows)
        text, _ = _exec_summary(roll, OFF, context=ctx, extras=EXTRAS)
        bluf = text.split("**")[1]                     # the bold bottom line
        assert f"is {roll.program_color.upper()}" in bluf
        assert not narrative_contradicts(roll.program_color, bluf)
