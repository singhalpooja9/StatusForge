"""Load the synthetic gold status sets (raw blurbs + human color labels).

Each domain pairs a rulebook with a gold set:
  software  -> rulebooks/software.yaml  + data/gold_statuses.jsonl
  marketing -> rulebooks/marketing.yaml + data/marketing_gold.jsonl
"""

from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# domain -> (rulebook name, gold file). Gold rows carry either free "text" (older
# domains, extraction-based) or a numeric "signals" dict (the simple grid domain).
DOMAINS = {
    "program":   ("program",   "program_gold.jsonl"),    # the simple default (numeric signals)
    "software":  ("software",  "gold_statuses.jsonl"),   # text-extraction domain
    "marketing": ("marketing", "marketing_gold.jsonl"),  # text-extraction domain
}


def load_gold(domain: str = "program") -> list[dict]:
    """Return list of gold rows for a domain (each has team, human_color, and either
    'text' or 'signals')."""
    _, fname = DOMAINS[domain]
    path = DATA_DIR / fname
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def rulebook_name(domain: str = "program") -> str:
    """The rulebook name for a domain (resolves to rulebooks/<name>.yaml)."""
    return DOMAINS[domain][0]
