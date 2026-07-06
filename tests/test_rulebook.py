"""Tests for rulebook loading + validation — the fail-closed governance guard."""

import pytest

from statusforge.rulebook import load_rulebook, RulebookError


def test_load_software_and_marketing():
    for name in ("software", "marketing"):
        rb = load_rulebook(name)
        assert rb.signals and rb.rules
        assert rb.domain


def test_rejects_unknown_signal_in_rule():
    spec = {"domain": "X", "signals": [{"name": "a"}],
            "rules": [{"color": "Red", "signal": "NOPE", "op": ">=", "value": 1, "reason": "r"}]}
    with pytest.raises(RulebookError):
        load_rulebook(spec)


def test_rejects_unknown_operator():
    spec = {"domain": "X", "signals": [{"name": "a"}],
            "rules": [{"color": "Red", "signal": "a", "op": "PWN", "value": 1, "reason": "r"}]}
    with pytest.raises(RulebookError):
        load_rulebook(spec)


def test_rejects_bad_color():
    spec = {"domain": "X", "signals": [{"name": "a"}],
            "rules": [{"color": "Purple", "signal": "a", "op": ">=", "value": 1, "reason": "r"}]}
    with pytest.raises(RulebookError):
        load_rulebook(spec)


def test_rejects_non_numeric_value():
    spec = {"domain": "X", "signals": [{"name": "a"}],
            "rules": [{"color": "Red", "signal": "a", "op": ">=", "value": "lots", "reason": "r"}]}
    with pytest.raises(RulebookError):
        load_rulebook(spec)


def test_rejects_no_signals_or_rules():
    with pytest.raises(RulebookError):
        load_rulebook({"domain": "X", "signals": [], "rules": []})


def test_operator_whitelist_only():
    from statusforge.rulebook import OPERATORS
    assert set(OPERATORS) == {">=", "<=", ">", "<", "==", "abs>=", "abs<="}
