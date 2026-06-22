import numpy as np
from bot.forex.metrics import max_drawdown, cagr, years_between

def test_max_drawdown_simple():
    assert abs(max_drawdown([100, 120, 60, 90]) - (60/120 - 1)) < 1e-12  # -0.5

def test_max_drawdown_sign_convention_negative_or_zero():
    # convention: drawdown is a NEGATIVE fraction (or 0), e.g. -0.25 for a 25% DD
    assert max_drawdown([100, 75]) == -0.25
    assert max_drawdown([100, 120, 60, 90]) <= 0.0

def test_max_drawdown_monotonic_is_zero():
    assert max_drawdown([100, 110, 120]) == 0.0

def test_max_drawdown_flat_curve_is_zero():
    assert max_drawdown([100, 100, 100]) == 0.0

def test_max_drawdown_empty_is_zero():
    assert max_drawdown([]) == 0.0

def test_cagr_doubles_in_one_year():
    assert abs(cagr(100, 200, 1.0) - 1.0) < 1e-9

def test_cagr_flat_curve_is_zero():
    assert cagr(100, 100, 1.0) == 0.0

def test_cagr_invalid_inputs_return_zero():
    assert cagr(0.0, 200.0, 1.0) == 0.0     # zero/invalid starting equity
    assert cagr(100.0, 0.0, 1.0) == 0.0     # non-positive end equity
    assert cagr(100.0, 200.0, 0.0) == 0.0   # non-positive years (degenerate/short period)

def test_years_between():
    yr = years_between(0, int(365.25 * 24 * 3600 * 1000))
    assert abs(yr - 1.0) < 1e-6

def test_years_between_short_interval_is_positive():
    # a sub-second interval clamps to a small positive number (never 0 or negative)
    assert years_between(0, 1000) > 0.0
