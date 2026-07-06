"""Signal extraction: raw team status text -> validated signal dict.

Two paths, same validated output:
  * offline heuristic (default / no key / CI): deterministic regex/keyword reader.
    Transparent and reproducible — but a demo prop; a human should confirm the
    numbers in the UI (that's what the editable table is for).
  * real LLM via LiteLLM: fills the rulebook's signal names as JSON.

Either way the result is validated against the rulebook and fed to the pure engine
— the LLM never sets the color, only proposes numbers a human can override.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .rulebook import Rulebook
from .models import validate_signals


@dataclass
class LLMConfig:
    """How to run the LLM narrator/extractor. api_key is passed PER CALL to LiteLLM,
    never written to os.environ (Streamlit shares one process across visitors)."""
    model: str = "groq/llama-3.3-70b-versatile"
    api_key: str = ""

    @property
    def live(self) -> bool:
        return bool(self.api_key and self.api_key.strip())


OFFLINE = LLMConfig(api_key="")


# --------------------------------------------------------------- offline read ---
def _first_int(pattern: str, text: str, default=None):
    """First integer captured by `pattern`, or `default` (None = "not found") if no
    match. Returning None — not 0 — lets the caller OMIT a signal the text never
    mentioned, so a missing value never masquerades as a real 0 downstream."""
    m = re.search(pattern, text, re.IGNORECASE)
    return int(m.group(1)) if m else default


# Known software-domain signals get targeted regexes. For an arbitrary rulebook
# signal we look for "<n> <signal words>" as a generic fallback.
def _offline_extract(text: str, rb: Rulebook) -> dict:
    t = text.lower()
    raw: dict[str, float] = {}

    def has(sig: str) -> bool:
        return sig in rb.signal_names

    if has("critical_path_slip_days"):
        slip = _first_int(r"slip(?:ped|page)?[^0-9]{0,12}(\d+)\s*day", t) \
            or _first_int(r"(\d+)\s*day[s]?\s*(?:behind|late|slip)", t) \
            or _first_int(r"behind[^0-9]{0,8}(\d+)\s*day", t)
        raw["critical_path_slip_days"] = slip
    if has("open_p1s"):
        raw["open_p1s"] = _first_int(r"(\d+)\s*(?:open\s*)?p1", t) or _first_int(r"(\d+)\s*sev[- ]?1", t)
    if has("blocked_dependencies"):
        raw["blocked_dependencies"] = _first_int(r"(\d+)\s*blocked", t)
    if has("ownerless_blocked_deps"):
        raw["ownerless_blocked_deps"] = (
            1 if ("no owner" in t or "unowned" in t or "ownerless" in t)
            else _first_int(r"(\d+)\s*(?:unowned|ownerless)", t))
    if has("scope_delta_pct"):
        ms = re.search(r"scope[^0-9+-]{0,16}([+-]?\d+)\s*%", t)
        if ms:
            raw["scope_delta_pct"] = float(ms.group(1))   # else: omit (not provided)
    if has("milestones_total") or has("milestones_hit"):
        raw.update(_extract_of_pair(t, "milestone", "milestones_total", "milestones_hit"))

    # ---- marketing-domain signals (offline reader also handles this second domain) ----
    if has("legal_approvals_pending"):
        raw["legal_approvals_pending"] = _first_int(r"(\d+)\s*(?:legal|brand)?\s*approval", t)
    if has("channels_blocked"):
        raw["channels_blocked"] = _first_int(r"(\d+)\s*(?:launch\s*)?channel[s]?\s*blocked", t) \
            or _first_int(r"(\d+)\s*blocked\s*channel", t)
    if has("budget_overrun_pct"):
        mo = re.search(r"budget\s*(\d+)\s*%\s*over", t)
        mu = re.search(r"budget\s*(\d+)\s*%\s*under", t)
        if mo:
            raw["budget_overrun_pct"] = float(mo.group(1))
        elif mu:
            raw["budget_overrun_pct"] = -float(mu.group(1))   # else: omit (not provided)
    if has("assets_total") or has("assets_ready"):
        pair = _extract_of_pair(t, "asset", "assets_total", "assets_ready")
        # "9 of 30 assets NOT ready" means ready = total - 9
        mneg = re.search(r"(\d+)\s*(?:of|/)\s*(\d+)\s*(?:creative\s*)?assets?\s*not\s*ready", t)
        if mneg:
            not_ready, total = int(mneg.group(1)), int(mneg.group(2))
            pair = {"assets_total": total, "assets_ready": total - not_ready}
        raw.update(pair)
    if has("days_to_launch"):
        raw["days_to_launch"] = _first_int(r"(\d+)\s*days?\s*(?:to|out|until|before)", t)

    # generic fallback for any other declared signal: "<n> <first word of name>".
    # If the text never mentions it, leave it OUT (don't write 0) so validate_signals
    # treats it as "not provided" and the engine skips its rules.
    for sig in rb.signals:
        if sig.name in raw:
            continue
        word = sig.name.split("_")[0]
        found = _first_int(rf"(\d+)\s*{re.escape(word)}", t)
        if found is not None:
            raw[sig.name] = found
    return {k: v for k, v in raw.items() if v is not None}


def _extract_of_pair(t: str, noun: str, total_key: str, hit_key: str) -> dict:
    """'3 of 5 <noun>s' -> {total:5,hit:3}; 'all 4 <noun>s' -> {total:4,hit:4}.
    Returns {} when the text never mentions <noun> — so the pair stays "not provided"
    (the derived rule needs BOTH operands and is skipped) rather than a phantom 0."""
    m = re.search(rf"(\d+)\s*(?:of|/)\s*(\d+)\s*(?:creative\s*)?{noun}", t)
    if m:
        hit, total = int(m.group(1)), int(m.group(2))
    else:
        total = _first_int(rf"(?:all\s*)?(\d+)\s*(?:creative\s*)?{noun}", t)
        if total is None:
            return {}
        hit = total if ("all" in t and noun in t) else 0
    return {total_key: total, hit_key: min(hit, total) if total else hit}


# --------------------------------------------------------------- real read -----
def _extract_instructions(rb: Rulebook) -> str:
    fields = ", ".join(s.name for s in rb.signals)
    return (
        f"Extract program-health SIGNALS from a team's status update for the domain "
        f"'{rb.domain}'. Return ONLY JSON with numeric values for these fields: {fields}. "
        f"OMIT any field the update does not state — do NOT guess and do NOT fill 0 for a "
        f"missing value (0 is a real measurement, not 'unknown'). Do NOT judge health or "
        f"assign any color — only pull the numbers that are actually stated.")


def _real_extract(text: str, rb: Rulebook, cfg: LLMConfig) -> dict:
    import litellm
    litellm.suppress_debug_info = True
    resp = litellm.completion(
        model=cfg.model, api_key=cfg.api_key,
        messages=[
            {"role": "system", "content": _extract_instructions(rb)},
            {"role": "user", "content": text},
        ],
        temperature=0, max_tokens=300,
        response_format={"type": "json_object"},
    )
    return _loads(resp["choices"][0]["message"]["content"])


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


def extract_signals(text: str, rulebook: Rulebook, cfg: LLMConfig | None = None) -> dict[str, float]:
    """Raw status text -> validated signal dict for the rulebook. LLM never sets color.

    Note: extraction stays deterministic (offline) unless cfg.live AND you opt in;
    the app keeps extraction offline even with the shared key so colors stay reproducible."""
    cfg = cfg or OFFLINE
    raw = _real_extract(text, rulebook, cfg) if cfg.live else _offline_extract(text, rulebook)
    return validate_signals(raw, rulebook)
