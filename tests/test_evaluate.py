import numpy as np
import pandas as pd
from bot.forex.cost_model import CostModel
from bot.forex.backtest import simulate
from bot.forex.evaluate import (exposure_adjusted_alpha, hold_long, matched_net,
                                matched_gross, passive_benchmarks, segmented_evaluation)

NO_COST = CostModel(0.0001, 0, 0, 21)        # bid==ask in _bars -> truly free


def _bars(mids):
    n = len(mids)
    return pd.DataFrame({
        "open_time": np.arange(n) * 14400000, "time": [f"t{i}" for i in range(n)],
        "bid_o": mids, "ask_o": mids, "bid_c": mids, "ask_c": mids,
        "bid_h": mids, "ask_h": mids, "bid_l": mids, "ask_l": mids,
        "mid_o": mids, "mid_c": mids, "mid_h": mids, "mid_l": mids,
        "volume": [1]*n, "complete": [True]*n})


def _bars_spread(mids, spread):
    n = len(mids); half = spread / 2.0
    return pd.DataFrame({
        "open_time": np.arange(n) * 14400000, "time": [f"t{i}" for i in range(n)],
        "bid_o": [m - half for m in mids], "ask_o": [m + half for m in mids],
        "bid_c": [m - half for m in mids], "ask_c": [m + half for m in mids],
        "bid_h": [m - half for m in mids], "ask_h": [m + half for m in mids],
        "bid_l": [m - half for m in mids], "ask_l": [m + half for m in mids],
        "mid_o": mids, "mid_c": mids, "mid_h": mids, "mid_l": mids,
        "volume": [1]*n, "complete": [True]*n})


# --- exposure_adjusted_alpha: explicit, deterministic, beta-removing ---

def test_alpha_is_zero_when_strategy_equals_matching_benchmark():
    # alpha = bot_return - avg_net_exposure * hold_return
    assert abs(exposure_adjusted_alpha(0.0, 0.0, 0.5)) < 1e-12        # flat book earns no alpha
    assert abs(exposure_adjusted_alpha(0.5, 1.0, 0.5)) < 1e-12        # full-long book that just rode hold
    assert abs(exposure_adjusted_alpha(-0.25, -0.5, 0.5)) < 1e-12     # half-short book matching its beta


def test_alpha_is_positive_when_strategy_outperforms_matching_benchmark():
    assert exposure_adjusted_alpha(0.6, 1.0, 0.5) > 0                 # long beat its beta
    assert exposure_adjusted_alpha(0.2, -1.0, -0.1) > 0               # short profited as hold fell


# --- costed passive long: same fill convention as the engine ---

def test_hold_long_uses_engine_fill_convention_first_interval_flat():
    bars = _bars([1.0, 1.1, 1.21])
    h = hold_long(bars, NO_COST, 100.0)
    # first interval [open0,open1] is FLAT (no decision precedes bar 0); hold earns 1.1 -> 1.21 only
    assert abs(h["total_return"] - (1.21 / 1.1 - 1.0)) < 1e-9
    assert abs(h["total_return"] - 0.10) < 1e-9


def test_costed_benchmark_pays_spread_and_final_liquidation_via_simulate():
    bars = _bars_spread([1.0, 1.0, 1.0, 1.0], spread=0.0002)          # flat price isolates cost
    cost = CostModel(0.0001, 0, 0, 21)                               # spread_mult=1.0 default
    half = 0.0002 / 2.0
    h = hold_long(bars, cost, 100.0)
    # always-long enters at open1 (entry half-spread) and is force-closed at the final open (exit half)
    assert abs(h["total_return"] - ((1 - half) ** 2 - 1.0)) < 1e-12
    assert h["trade_count"] == 1                                     # one round-trip, force-closed at the end


def test_costed_benchmark_is_not_free():
    # the SAME bars, costed vs uncosted ONLY via the cost model -> the benchmark pays through simulate
    bars = _bars_spread(list(np.linspace(1.0, 1.3, 30)), spread=0.0004)
    free = hold_long(bars, CostModel(0.0001, 0, 0, 21, spread_mult=0.0), 100.0)["total_return"]
    costed = hold_long(bars, CostModel(0.0001, 0, 0, 21, spread_mult=1.0), 100.0)["total_return"]
    assert costed < free                                            # a costed strategy must not be compared to a free benchmark


# --- gross-matched passive: MEASURED gross exposure, the drawdown reference ---

def test_matched_gross_uses_measured_avg_gross_exposure():
    bars = _bars([1.0, 1.1, 1.21])
    full = matched_gross(bars, NO_COST, 1.0, 100.0)
    half = matched_gross(bars, NO_COST, 0.5, 100.0)
    assert abs(full["total_return"] - (1.21 / 1.1 - 1.0)) < 1e-9    # f_gross=1.0 -> full move (first interval flat)
    assert 0 < half["total_return"] < full["total_return"]          # smaller measured gross -> smaller move
    # degenerate fallback only: f_gross == 0 falls back to 1.0 (never silently hardcoded otherwise)
    assert abs(matched_gross(bars, NO_COST, 0.0, 100.0)["total_return"] - full["total_return"]) < 1e-9


def test_matched_gross_is_the_drawdown_reference_scaling_with_exposure():
    bars = _bars([1.0, 1.1, 1.2, 1.0, 0.9])                          # rise then fall -> a real drawdown
    dd_full = matched_gross(bars, NO_COST, 1.0, 100.0)["max_drawdown"]
    dd_half = matched_gross(bars, NO_COST, 0.5, 100.0)["max_drawdown"]
    assert dd_full <= 0.0 and dd_half <= 0.0                         # drawdowns are <= 0
    assert dd_full < dd_half                                         # larger gross exposure -> deeper DD reference


def test_matched_net_holds_signed_net_exposure():
    bars = _bars([1.0, 0.9, 0.81])                                   # falling price
    short = matched_net(bars, NO_COST, -0.5, 100.0)                 # net short -> profits as price falls
    assert short["total_return"] > 0


# --- diagnostic suite (costed) ---

def test_passive_benchmarks_suite_runs_through_engine():
    bars = _bars(list(np.linspace(1.0, 1.3, 60)))
    out = passive_benchmarks(bars, NO_COST, 100.0)
    assert {"hold_long", "fixed_50pct", "ma_filter"}.issubset(out)
    for k in ("hold_long", "fixed_50pct", "ma_filter"):
        assert "total_return" in out[k] and "max_drawdown" in out[k]


# --- B1: MA-filter uses the SAME single-lag convention as any decision array (no double-lag) ---

def _ma_crossover_bars():
    # rise then fall so the price crosses its own MA(50) after the 50-bar warm-up; this makes the
    # single-lag and double-lag equity curves materially different, so the test can distinguish them.
    up = np.linspace(1.00, 1.30, 70)
    down = np.linspace(1.30, 1.05, 40)
    return _bars(list(np.concatenate([up, down])))


def test_ma_filter_uses_single_engine_lag_not_double_lag():
    bars = _ma_crossover_bars()
    mid = bars["mid_c"].astype(float).reset_index(drop=True)
    ma = mid.rolling(50, min_periods=50).mean()
    raw = (mid > ma).to_numpy().astype(int)                              # decision known at bar CLOSE, no pre-shift
    shifted = (mid > ma).shift(1, fill_value=False).to_numpy().astype(int)

    single_lag = simulate(bars, raw, NO_COST, 1.0, 100.0)["summary"]      # engine fills at next open => ONE lag
    double_lag = simulate(bars, shifted, NO_COST, 1.0, 100.0)["summary"]  # pre-shift + engine fill => TWO lags
    assert abs(single_lag["total_return"] - double_lag["total_return"]) > 1e-9   # data truly distinguishes them

    ma_filter = passive_benchmarks(bars, NO_COST, 100.0)["ma_filter"]
    # the diagnostic must equal the SINGLE-lag path (like every normal decision array), not the double-lag one
    assert abs(ma_filter["total_return"] - single_lag["total_return"]) < 1e-12
    assert abs(ma_filter["max_drawdown"] - single_lag["max_drawdown"]) < 1e-12
    assert abs(ma_filter["total_return"] - double_lag["total_return"]) > 1e-9    # NOT double-lagged


def test_ma_filter_remains_diagnostic_only():
    out = passive_benchmarks(_ma_crossover_bars(), NO_COST, 100.0)
    # passive_benchmarks emits ONLY costed benchmark summaries — no gate/verdict/selection surface,
    # so the MA filter can never feed acceptance or the runner gate.
    assert set(out.keys()) == {"hold_long", "fixed_50pct", "ma_filter"}
    for forbidden in ("verdict", "overall", "acceptance", "selected", "selection", "gate", "passed"):
        assert forbidden not in out
    assert "total_return" in out["ma_filter"] and "max_drawdown" in out["ma_filter"]


# --- segmented evaluation: DIAGNOSTIC ONLY, never selects/tunes ---

def test_segmented_returns_segments_and_is_diagnostic_only():
    bars = _bars(list(np.linspace(1.0, 1.5, 40)))
    seg = segmented_evaluation(bars, np.ones(40, dtype=int), NO_COST, 1.0, 100.0, n_segments=4)
    assert seg["n_segments"] >= 1 and "segments" in seg
    assert "DIAGNOSTIC" in seg["label"].upper()
    # it must not select, tune, or emit any strategy decision
    for forbidden in ("selected", "selection", "verdict", "best", "winner"):
        assert forbidden not in seg


def test_segmented_does_not_mutate_inputs_or_change_strategy_output():
    bars = _bars(list(np.linspace(1.0, 1.5, 40)))
    dec = np.ones(40, dtype=int)
    bars_before = bars.copy(deep=True)
    dec_before = dec.copy()
    segmented_evaluation(bars, dec, NO_COST, 1.0, 100.0, n_segments=4)
    assert bars.equals(bars_before)                                 # input bars untouched
    assert np.array_equal(dec, dec_before)                          # input decisions untouched
