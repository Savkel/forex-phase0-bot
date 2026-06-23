import numpy as np
import pandas as pd
from bot.forex.cost_model import CostModel
from bot.forex.backtest import simulate
from bot.forex.indicators import compute_features, add_mid
from bot.forex.signals import candidate_decisions

NO_COST = CostModel(0.0001, 0.0, 0.0, 21)

def _bars(mids):
    n = len(mids)
    return add_mid(pd.DataFrame({
        "open_time": np.arange(n) * 14400000, "time": [f"t{i}" for i in range(n)],
        "bid_o": mids, "ask_o": mids, "bid_c": mids, "ask_c": mids,
        "bid_h": mids, "ask_h": mids, "bid_l": mids, "ask_l": mids,
        "volume": [1]*n, "complete": [True]*n}))

def test_decision_fills_at_next_open_never_same_bar():
    # the only jump is over interval [open1, open2]: mid_o[1]=1.0 -> mid_o[2]=2.0
    bars = _bars([1.0, 1.0, 2.0, 2.0])
    captured = simulate(bars, np.array([1, 1, 0, 0]), NO_COST, f=1.0, starting_equity=100.0)["summary"]["total_return"]
    assert abs(captured - 1.0) < 1e-9        # decision at close bar0 fills open1 -> captures jump
    missed = simulate(bars, np.array([0, 1, 1, 0]), NO_COST, f=1.0, starting_equity=100.0)["summary"]["total_return"]
    assert abs(missed - 0.0) < 1e-9          # decision at close bar1 fills open2 -> too late, jump missed

def test_first_interval_is_always_flat():
    bars = _bars([1.0, 2.0, 2.0])            # the only move is the first interval [open0,open1]
    res = simulate(bars, np.array([1, 1, 1]), NO_COST, f=1.0, starting_equity=100.0)["summary"]
    assert res["total_return"] == 0.0        # first interval flat -> 1->2 move never captured

def test_engine_equity_invariant_to_future_bar_mutation():
    bars = _bars([1.0, 1.1, 1.2, 1.3, 1.4])
    dec = np.array([1, 1, 1, 1, 1])
    base = simulate(bars, dec, NO_COST, f=1.0, starting_equity=100.0)["equity"]
    bars2 = bars.copy()
    for col in ("bid_o", "ask_o", "mid_o", "bid_c", "ask_c", "mid_c",
                "bid_h", "ask_h", "mid_h", "bid_l", "ask_l", "mid_l"):
        bars2.loc[len(bars2) - 1, col] = 1.35    # mutate ONLY the last bar (modest: keeps cagr finite on this tiny window)
    mut = simulate(bars2, dec, NO_COST, f=1.0, starting_equity=100.0)["equity"]
    assert np.allclose(base[:-1], mut[:-1])      # earlier opens computed before the last bar is used

def test_signal_is_invariant_to_future_mutation():
    closes = list(np.linspace(1.0, 1.5, 60))
    df = compute_features(_bars(closes), ["mom_20"])
    d_full = candidate_decisions(df, "mom_20").copy()
    closes2 = closes[:31] + [9.9]*(len(closes)-31)
    df2 = compute_features(_bars(closes2), ["mom_20"])
    d_mut = candidate_decisions(df2, "mom_20")
    assert np.array_equal(d_full[:31], d_mut[:31])
