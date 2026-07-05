"""Narrator: turn an engine Verdict into grounded prose.

The narrator writes the human-readable status line, but it is handed the color and
the reasons the engine already computed — it may only explain them, never change
them. A faithfulness check (see calibration.py) verifies the prose never claims a
health tier different from the engine's, and never cites a number the engine
didn't produce.

Offline mock builds the narrative deterministically from the reasons; the real
path asks an LLM to phrase those same reasons, with the color pinned.
"""

from __future__ import annotations

from .models import Verdict, ProgramRollup
from .extract import LLMConfig, OFFLINE  # shared LLM config (session api_key, no env)


# ---------------------------------------------------------------- mock narrate --
def _mock_narrate(v: Verdict) -> str:
    lead = {"Red": "At risk", "Amber": "Watch", "Green": "On track"}[v.color]
    reasons = "; ".join(v.reasons)
    return f"{v.team}: {lead} ({v.color}). {reasons.capitalize()}."


# ---------------------------------------------------------------- real narrate --
_NARRATE_INSTRUCTIONS = (
    "You write one crisp status sentence for a program review. You are GIVEN the "
    "health color and the exact reasons it was assigned by a deterministic engine. "
    "Explain those reasons in plain language. RULES: (1) never state or imply a "
    "different health level than the given color; (2) never introduce a metric or "
    "number that isn't in the given reasons; (3) one or two sentences, factual, no "
    "hype."
)


def _real_narrate(v: Verdict, cfg: LLMConfig) -> str:
    import litellm
    litellm.suppress_debug_info = True  # never log payloads/keys
    resp = litellm.completion(
        model=cfg.model,
        api_key=cfg.api_key,   # per-call; NEVER via os.environ
        messages=[
            {"role": "system", "content": _NARRATE_INSTRUCTIONS},
            {"role": "user", "content": (
                f"TEAM: {v.team}\nCOLOR (fixed): {v.color}\n"
                f"REASONS (only use these): {v.reasons}")},
        ],
        temperature=0.2,
    )
    return resp["choices"][0]["message"]["content"].strip()


def narrate(v: Verdict, cfg: LLMConfig | None = None) -> str:
    cfg = cfg or OFFLINE
    if not cfg.live:
        return _mock_narrate(v)
    return _real_narrate(v, cfg)


def narrate_rollup(roll: ProgramRollup, cfg: LLMConfig | None = None) -> ProgramRollup:
    """Attach narratives to every team and a one-line program summary."""
    cfg = cfg or OFFLINE
    for v in roll.teams:
        v.narrative = narrate(v, cfg)
    reds = [v.team for v in roll.teams if v.color == "Red"]
    ambers = [v.team for v in roll.teams if v.color == "Amber"]
    if reds:
        roll.summary = f"Program {roll.program_color}: {len(reds)} team(s) at risk — {', '.join(reds)}."
    elif ambers:
        roll.summary = f"Program {roll.program_color}: watch {', '.join(ambers)}."
    else:
        roll.summary = f"Program {roll.program_color}: all teams on track."
    return roll
