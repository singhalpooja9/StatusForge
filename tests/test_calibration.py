"""Tests for the 3-class ordinal calibration math + narrative faithfulness."""

import pytest

from statusforge.calibration import (
    confusion_3x3, quadratic_weighted_kappa, wilson_interval,
    calibrate_colors, narrative_contradicts, faithfulness_rate,
)


def test_perfect_agreement():
    y = ["Green", "Amber", "Red", "Green", "Red"]
    r = calibrate_colors(y, y)
    assert r.exact_agreement == 1.0
    assert r.quadratic_kappa == 1.0
    assert r.danger_rate == 0.0


def test_quadratic_kappa_penalizes_distant_errors_more():
    y_true = ["Green", "Red", "Green", "Red"]
    near = ["Green", "Amber", "Green", "Amber"]   # Red->Amber (distance 1)
    far = ["Green", "Green", "Green", "Green"]     # Red->Green (distance 2)
    k_near = quadratic_weighted_kappa(y_true, near)
    k_far = quadratic_weighted_kappa(y_true, far)
    assert k_near > k_far  # distant miss punished harder


def test_danger_rate_counts_only_under_called_red():
    # 2 truly-Red: one called Green (danger), one called Red (fine)
    y_true = ["Red", "Red", "Green"]
    y_pred = ["Green", "Red", "Green"]
    r = calibrate_colors(y_true, y_pred)
    assert r.n_true_red == 2
    assert r.danger_rate == pytest.approx(0.5)


def test_over_calling_is_not_danger():
    # calling a Green team Red is cautious, NOT a danger-rate hit
    y_true = ["Green", "Green"]
    y_pred = ["Red", "Amber"]
    r = calibrate_colors(y_true, y_pred)
    assert r.danger_rate == 0.0  # no true-Red teams under-called


def test_confusion_shape():
    m = confusion_3x3(["Green", "Red"], ["Green", "Amber"])
    assert len(m) == 3 and all(len(r) == 3 for r in m)
    assert m[0][0] == 1  # true Green, pred Green
    assert m[2][1] == 1  # true Red, pred Amber


def test_wilson_bounds():
    lo, hi = wilson_interval(1, 4)
    assert 0.0 <= lo < hi <= 1.0


def test_narrative_contradiction_detection():
    # engine says Red but prose says "on track" -> contradiction
    assert narrative_contradicts("Red", "Checkout: on track, all good") is True
    # engine Red, prose says at risk -> consistent
    assert narrative_contradicts("Red", "Checkout: at risk, 2 P1s open") is False
    # neutral prose -> not a contradiction
    assert narrative_contradicts("Amber", "Checkout: 2 blocked deps this week") is False


def test_faithfulness_rate():
    colors = ["Red", "Green"]
    good = ["at risk: P1 open", "on track, milestones hit"]
    bad = ["on track, no issues", "on track, milestones hit"]  # first contradicts Red
    assert faithfulness_rate(colors, good) == 1.0
    assert faithfulness_rate(colors, bad) == pytest.approx(0.5)


def test_length_mismatch_raises():
    with pytest.raises(ValueError):
        confusion_3x3(["Green"], ["Green", "Red"])
