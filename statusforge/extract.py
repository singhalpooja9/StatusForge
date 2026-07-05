"""Signal extraction: raw team status text -> typed TeamSignals.

Two paths, same typed output:
  * offline MOCK (default / no API key / CI): deterministic regex + keyword rules
    that pull numbers out of a status blurb. Transparent and reproducible.
  * real LLM via LiteLLM: asks the model to fill the TeamSignals schema as JSON.

Either way the result is a strict TeamSignals object the deterministic engine
consumes — the LLM never sees or sets the RAG color, only proposes the numbers,
which a human can inspect and override in the UI.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .models import TeamSignals


@dataclass
class LLMConfig:
    """How to run the LLM narrator/extractor.

    api_key is the VISITOR'S session key (or the owner's), passed per-call to
    LiteLLM — never written to the environment. If api_key is empty, everything
    runs on the deterministic offline path (the health color never needs an LLM).
    """
    model: str = "groq/llama-3.3-70b-versatile"
    api_key: str = ""

    @property
    def live(self) -> bool:
        """True only when we have a key to make a real call."""
        return bool(self.api_key and self.api_key.strip())


# The offline default: no key, deterministic mock everywhere.
OFFLINE = LLMConfig(api_key="")


# --------------------------------------------------------------- mock extract ---
def _first_int(pattern: str, text: str, default: int = 0) -> int:
    m = re.search(pattern, text, re.IGNORECASE)
    return int(m.group(1)) if m else default


def _mock_extract(team: str, text: str) -> TeamSignals:
    """Deterministic keyword/regex extraction. Not clever — reproducible."""
    t = text.lower()
    slip = _first_int(r"slip(?:ped|page)?[^0-9]{0,12}(\d+)\s*day", t)
    if not slip:
        slip = _first_int(r"(\d+)\s*day[s]?\s*(?:behind|late|slip)", t)
    p1s = _first_int(r"(\d+)\s*(?:open\s*)?p1", t) or _first_int(r"(\d+)\s*sev[- ]?1", t)
    blocked = _first_int(r"(\d+)\s*blocked", t)
    ownerless = 0
    if "no owner" in t or "unowned" in t or "ownerless" in t:
        ownerless = max(1, _first_int(r"(\d+)\s*(?:unowned|ownerless)", t))
    scope = 0.0
    ms = re.search(r"scope[^0-9+-]{0,16}([+-]?\d+)\s*%", t)
    if ms:
        scope = float(ms.group(1))
    total = _first_int(r"(\d+)\s*milestone", t)
    hit = _first_int(r"(\d+)\s*(?:of|/)\s*\d+\s*milestone", t)
    if total and hit > total:
        hit = total
    return TeamSignals(
        team=team, critical_path_slip_days=slip, open_p1s=p1s,
        blocked_dependencies=blocked, ownerless_blocked_deps=min(ownerless, blocked or ownerless),
        scope_delta_pct=scope, milestones_total=total, milestones_hit=hit)


# --------------------------------------------------------------- real extract ---
_EXTRACT_INSTRUCTIONS = (
    "Extract program-health SIGNALS from a team's status update. Return ONLY JSON "
    "with integer/number fields: critical_path_slip_days, open_p1s, "
    "blocked_dependencies, ownerless_blocked_deps, scope_delta_pct, "
    "milestones_total, milestones_hit. Use 0 when unstated. Do NOT judge health or "
    "assign any color — only pull the numbers."
)


def _real_extract(team: str, text: str, cfg: LLMConfig) -> TeamSignals:
    import litellm  # lazy import; offline path needs no dependency
    litellm.suppress_debug_info = True  # never print payloads/keys to logs
    resp = litellm.completion(
        model=cfg.model,
        api_key=cfg.api_key,   # per-call; NEVER via os.environ (shared-process leak)
        messages=[
            {"role": "system", "content": _EXTRACT_INSTRUCTIONS},
            {"role": "user", "content": f"TEAM: {team}\nSTATUS:\n{text}"},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    raw = _loads(resp["choices"][0]["message"]["content"])
    raw["team"] = team
    return TeamSignals(**raw)


def _loads(content: str) -> dict:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```[a-z]*\n?|\n?```$", "", content).strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", content, re.DOTALL)
        if not m:
            raise
        return json.loads(m.group(0))


def extract_signals(team: str, text: str, cfg: LLMConfig | None = None) -> TeamSignals:
    """Raw status text -> typed TeamSignals. Offline mock unless cfg has a key.
    The LLM never sets the RAG color — only proposes numbers a human can override."""
    cfg = cfg or OFFLINE
    if not cfg.live:
        return _mock_extract(team, text)
    return _real_extract(team, text, cfg)
