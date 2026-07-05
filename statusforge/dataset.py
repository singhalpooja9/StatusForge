"""Load the synthetic gold status set (raw blurbs + human color labels)."""

from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_gold(path: Path | None = None) -> list[dict]:
    """Return list of {team, text, human_color}."""
    path = path or DATA_DIR / "gold_statuses.jsonl"
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out
