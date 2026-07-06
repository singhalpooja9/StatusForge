"""Narrator: turn an engine Verdict into grounded prose.

The narrator is handed the color + the reasons the engine already computed; it may
only phrase them, never change them. A faithfulness check (calibration.py) verifies
the prose never claims a different health level.

Offline builds the narrative deterministically from the reasons (and is the silent
fallback when a live call fails). The real path asks an LLM to phrase those same
reasons, with the color pinned. On ANY real-call failure we fall back to offline —
so the demo never breaks on a rate-limit or outage.
"""

from __future__ import annotations

from .engine import Verdict, ProgramRollup
from .extract import LLMConfig, OFFLINE


def _mock_narrate(v: Verdict) -> str:
    lead = {"Red": "At risk", "Amber": "Watch", "Green": "On track"}[v.color]
    reasons = "; ".join(v.reasons)
    return f"{v.team}: {lead} ({v.color}). {reasons.capitalize()}."


_NARRATE_INSTRUCTIONS = (
    "You write one crisp status sentence for a program review. You are GIVEN the "
    "health color and the exact reasons a deterministic engine assigned it. Explain "
    "those reasons plainly. RULES: (1) never state or imply a different health level "
    "than the given color; (2) never introduce a metric not in the given reasons; "
    "(3) one or two sentences, factual, no hype.")


def _real_narrate(v: Verdict, cfg: LLMConfig) -> str:
    import litellm
    litellm.suppress_debug_info = True
    resp = litellm.completion(
        model=cfg.model, api_key=cfg.api_key,
        messages=[
            {"role": "system", "content": _NARRATE_INSTRUCTIONS},
            {"role": "user", "content": (
                f"TEAM: {v.team}\nCOLOR (fixed): {v.color}\n"
                f"REASONS (only use these): {v.reasons}")},
        ],
        temperature=0.2, max_tokens=120,
    )
    return resp["choices"][0]["message"]["content"].strip()


def narrate(v: Verdict, cfg: LLMConfig | None = None) -> tuple[str, bool]:
    """Return (narrative, used_live). Falls back to offline prose on any live failure."""
    cfg = cfg or OFFLINE
    if not cfg.live:
        return _mock_narrate(v), False
    try:
        return _real_narrate(v, cfg), True
    except Exception:
        return _mock_narrate(v), False   # silent fallback — demo never breaks


def narrate_rollup(roll: ProgramRollup, cfg: LLMConfig | None = None) -> ProgramRollup:
    """Attach narratives + a program summary. Sets roll.summary; leaves a flag on
    each verdict-less; caller can inspect if any live call fell back."""
    cfg = cfg or OFFLINE
    for v in roll.teams:
        v.narrative, _ = narrate(v, cfg)
    reds = [v.team for v in roll.teams if v.color == "Red"]
    ambers = [v.team for v in roll.teams if v.color == "Amber"]
    if reds:
        roll.summary = f"Program {roll.program_color}: {len(reds)} team(s) at risk — {', '.join(reds)}."
    elif ambers:
        roll.summary = f"Program {roll.program_color}: watch {', '.join(ambers)}."
    else:
        roll.summary = f"Program {roll.program_color}: all teams on track."
    return roll
