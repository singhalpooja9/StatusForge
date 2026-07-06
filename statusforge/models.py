"""Signal validation, spec-driven from a rulebook.

Instead of a hardcoded TeamSignals class, we build a validator from the rulebook's
declared signals. This keeps validation strict (unknown fields rejected, negatives
only where allowed) while letting a different rulebook define a different domain's
signals — the governance property (color is a pure function of validated numbers)
is unchanged.
"""

from __future__ import annotations

from .rulebook import Rulebook


def validate_signals(raw: dict, rulebook: Rulebook) -> dict[str, float]:
    """Coerce + validate a raw signal dict against the rulebook's declared signals.

    - every declared signal defaults to 0 if missing
    - values must be numeric
    - negatives rejected unless the signal sets allow_negative
    - unknown keys are dropped (with the rulebook as the source of truth)
    Returns a clean {name: float} dict the engine can consume.
    """
    out: dict[str, float] = {}
    for sig in rulebook.signals:
        v = raw.get(sig.name, 0)
        try:
            v = float(v)
        except (TypeError, ValueError):
            raise ValueError(f"signal {sig.name!r} must be numeric, got {v!r}")
        if v < 0 and not sig.allow_negative:
            raise ValueError(f"signal {sig.name!r} cannot be negative")
        out[sig.name] = v
    return out
