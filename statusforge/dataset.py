"""Load the synthetic gold status sets (raw blurbs + human color labels).

Each domain pairs a rulebook with a gold set:
  software  -> rulebooks/software.yaml  + data/gold_statuses.jsonl
  marketing -> rulebooks/marketing.yaml + data/marketing_gold.jsonl
"""

from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

DOMAINS = {
    "software":  ("software",  "gold_statuses.jsonl"),
    "marketing": ("marketing", "marketing_gold.jsonl"),
}


def load_gold(domain: str = "software") -> list[dict]:
    """Return list of {team, text, human_color} for a domain."""
    _, fname = DOMAINS[domain]
    path = DATA_DIR / fname
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def rulebook_name(domain: str = "software") -> str:
    """The rulebook name for a domain (resolves to rulebooks/<name>.yaml)."""
    return DOMAINS[domain][0]
