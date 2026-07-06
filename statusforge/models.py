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

    - a signal that is MISSING (absent, None, or blank string) means "not provided":
      it is OMITTED from the result, NOT defaulted to 0. The engine then skips every
      rule on that signal, so a blank "% Complete" cell can never fire "only 0%
      complete" or push a team to Amber. (A genuinely typed 0 is kept and fires.)
    - values that are present must be numeric
    - negatives rejected unless the signal sets allow_negative
    - unknown keys are dropped (with the rulebook as the source of truth)
    Returns a clean {name: float} dict of ONLY the provided signals.
    """
    out: dict[str, float] = {}
    for sig in rulebook.signals:
        if sig.name not in raw:
            continue
        v = raw[sig.name]
        if v is None or (isinstance(v, str) and not v.strip()):
            continue                      # blank cell -> "not provided", not 0
        try:
            v = float(v)
        except (TypeError, ValueError):
            raise ValueError(f"signal {sig.name!r} must be numeric, got {v!r}")
        if v < 0 and not sig.allow_negative:
            raise ValueError(f"signal {sig.name!r} cannot be negative")
        out[sig.name] = v
    return out
