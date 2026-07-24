import inspect
import numpy as np
import pytest
from bot.forex.portfolio import aggregate_portfolio

def _sleeve(times, ret, pos, f=1.0):
    return {"interval_time": np.asarray(times, dtype="int64"),
            "ret": np.asarray(ret, float), "pos": np.asarray(pos, float), "f": f,
            "equity": None, "summary": None}

# ---- Plan tests (verbatim from the approved Task 7 spec) ------------------------------

def test_equal_weight_return_is_mean_of_sleeve_returns():
    a = _sleeve([0, 1, 2], [0.10, 0.00, -0.10], [0, 1, 1])
    b = _sleeve([0, 1, 2], [0.00, 0.20, 0.00], [0, 1, 0])
    agg = aggregate_portfolio([a, b], starting_equity=100.0)
    # R = [(0.10+0)/2, (0+0.20)/2, (-0.10+0)/2] = [0.05, 0.10, -0.05]
    assert np.allclose(agg["interval_return"], [0.05, 0.10, -0.05])
    exp = 100.0 * np.prod(1.0 + np.array([0.05, 0.10, -0.05]))
    assert abs(agg["equity"][-1] - exp) < 1e-9

def test_gross_is_fraction_of_active_pairs_over_N():
    # both pairs long over interval 1 -> gross = (1/2)(1) + (1/2)(1) = 1.0 ; interval 2 one active -> 0.5
    a = _sleeve([0, 1, 2], [0, 0, 0], [0, 1, 1])
    b = _sleeve([0, 1, 2], [0, 0, 0], [0, 1, 0])
    agg = aggregate_portfolio([a, b])
    assert np.allclose(agg["gross"], [0.0, 1.0, 0.5])
    assert abs(agg["avg_gross_exposure"] - (0.0 + 1.0 + 0.5) / 3.0) < 1e-9

def test_net_signs_and_cancellation():
    a = _sleeve([0, 1], [0, 0], [0, 1])          # long
    b = _sleeve([0, 1], [0, 0], [0, -1])         # short -> net cancels, gross stays
    agg = aggregate_portfolio([a, b])
    assert np.allclose(agg["net"], [0.0, 0.0])
    assert np.allclose(agg["gross"], [0.0, 1.0])

def test_all_flat_portfolio_is_zero_return_and_exposure():
    a = _sleeve([0, 1, 2], [0, 0, 0], [0, 0, 0])
    agg = aggregate_portfolio([a], starting_equity=100.0)
    assert agg["portfolio_return"] == 0.0
    assert agg["avg_gross_exposure"] == 0.0 and agg["max_drawdown"] == 0.0

def test_union_timeline_zero_fills_missing_intervals():
    a = _sleeve([0, 1, 2], [0.0, 0.10, 0.0], [0, 1, 0])
    b = _sleeve([0, 2],    [0.0, 0.20],      [0, 1])       # missing interval at t=1
    agg = aggregate_portfolio([a, b])
    assert agg["timeline"].tolist() == [0, 1, 2]
    # t=1: only A active -> R=(0.10+0)/2=0.05, gross=0.5 ; t=2: only B -> R=(0+0.20)/2=0.10
    assert np.allclose(agg["interval_return"], [0.0, 0.05, 0.10])
    assert np.allclose(agg["gross"], [0.0, 0.5, 0.5])

def test_f_scales_exposure_in_aggregation():
    a = _sleeve([0, 1], [0, 0], [0, 1], f=0.5)
    agg = aggregate_portfolio([a])                # single sleeve, weight 1.0
    assert np.allclose(agg["gross"], [0.0, 0.5])  # |pos|*f = 0.5

# ---- Additive hardening (compatible with the union + fold-f contract) -----------------

def test_flat_pairs_keep_1_over_N_allocation_no_renormalization():
    # N=4: one active long (ret 0.40) + three flat pairs. The active pair keeps its FIXED
    # 1/4 weight; flat pairs are NOT dropped and the denominator stays N=4 (no renorm over
    # active pairs). Portfolio return = 0.40/4 = 0.10, NOT the full 0.40; gross = 1/4 = 0.25.
    active = _sleeve([0, 1], [0.0, 0.40], [0, 1])
    flat = lambda: _sleeve([0, 1], [0.0, 0.0], [0, 0])
    agg = aggregate_portfolio([active, flat(), flat(), flat()], starting_equity=100.0)
    assert np.allclose(agg["interval_return"], [0.0, 0.10])       # 0.40/4, not 0.40 and not renormalized
    assert np.allclose(agg["gross"], [0.0, 0.25]) and np.allclose(agg["net"], [0.0, 0.25])
    assert abs(agg["equity"][-1] - 110.0) < 1e-9                  # 100 * 1.10

def test_no_double_scaling_return_divided_by_N_exactly_once():
    # Single active sleeve among N=5: portfolio interval return = 0.40/5 = 0.08 (divided by
    # N ONCE), never 0.40/25. And a sleeve's f scales EXPOSURE only, never the return.
    active = _sleeve([0, 1], [0.0, 0.40], [0, 1], f=0.5)
    flat = lambda: _sleeve([0, 1], [0.0, 0.0], [0, 0])
    agg = aggregate_portfolio([active, flat(), flat(), flat(), flat()])
    assert np.allclose(agg["interval_return"], [0.0, 0.08])       # 0.40/5 exactly once (not /25)
    assert np.allclose(agg["gross"], [0.0, 0.5 * 1.0 / 5])        # |pos|*f*w = 1*0.5*(1/5) = 0.10
    # f does NOT touch the return path: single sleeve, weight 1.0, f=0.5 -> return is the raw 0.40
    solo = aggregate_portfolio([_sleeve([0, 1], [0.0, 0.40], [0, 1], f=0.5)])
    assert np.allclose(solo["interval_return"], [0.0, 0.40])      # f left the return untouched
    assert np.allclose(solo["gross"], [0.0, 0.5])                 # ...and scaled exposure exactly once

def test_net_and_gross_bounds_on_nondegenerate_mixed_path():
    # mixed long/short so net != gross and neither assertion is degenerate
    a = _sleeve([0, 1, 2], [0, 0, 0], [0, 1, 1])
    b = _sleeve([0, 1, 2], [0, 0, 0], [0, -1, 1])
    agg = aggregate_portfolio([a, b])
    assert np.allclose(agg["net"], [0.0, 0.0, 1.0])              # interval1 cancels, interval2 aligns
    assert np.allclose(agg["gross"], [0.0, 1.0, 1.0])
    assert agg["gross"].max() <= 1.0 + 1e-12
    assert agg["net"].min() >= -1.0 - 1e-12 and agg["net"].max() <= 1.0 + 1e-12
    # non-degenerate: net and gross genuinely differ on interval 1 (0.0 vs 1.0)
    assert not np.allclose(agg["net"], agg["gross"])

def test_reject_non_finite_interval_returns():
    good = _sleeve([0, 1], [0.0, 0.0], [0, 1])
    with pytest.raises(ValueError):
        aggregate_portfolio([_sleeve([0, 1], [0.0, np.nan], [0, 1])])
    with pytest.raises(ValueError):
        aggregate_portfolio([good, _sleeve([0, 1], [0.0, np.inf], [0, 1])])

def test_determinism_under_insertion_order():
    a = _sleeve([0, 1, 2], [0.10, 0.00, -0.10], [0, 1, 1])
    b = _sleeve([0, 1, 2], [0.00, 0.20, 0.00], [0, 1, 0])
    ab = aggregate_portfolio([a, b], starting_equity=100.0)
    ba = aggregate_portfolio([b, a], starting_equity=100.0)      # reversed insertion order, equal weights
    assert np.array_equal(ab["timeline"], ba["timeline"])
    assert np.allclose(ab["interval_return"], ba["interval_return"])
    assert np.allclose(ab["net"], ba["net"]) and np.allclose(ab["gross"], ba["gross"])
    assert np.allclose(ab["equity"], ba["equity"])
    assert ab["portfolio_return"] == ba["portfolio_return"]

def test_empty_sleeves_raises():
    with pytest.raises(ValueError):
        aggregate_portfolio([])

def test_weights_length_must_match_sleeves():
    a = _sleeve([0, 1], [0, 0], [0, 1])
    b = _sleeve([0, 1], [0, 0], [0, 1])
    with pytest.raises(ValueError):
        aggregate_portfolio([a, b], weights=[1.0])

def test_no_execution_logic_in_aggregator():
    # the aggregator must NOT re-derive fills/PnL/costs; it only weights tested sleeve outputs
    src = inspect.getsource(aggregate_portfolio)
    for banned in ("simulate", "spread", "swap", "rollover", "Trade", "ask_o", "bid_o"):
        assert banned not in src
