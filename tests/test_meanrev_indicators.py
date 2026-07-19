import numpy as np
import pandas as pd
from bot.forex.indicators import add_mid
from bot.forex.meanrev_indicators import zscore, wilder_rsi, bollinger

def _bars(closes):
    n = len(closes)
    return add_mid(pd.DataFrame({
        "open_time": np.arange(n) * 14400000, "time": [f"t{i}" for i in range(n)],
        "bid_o": closes, "bid_h": closes, "bid_l": closes, "bid_c": closes,
        "ask_o": closes, "ask_h": closes, "ask_l": closes, "ask_c": closes,
        "volume": [1]*n, "complete": [True]*n}))

# ---- z-score ----
def test_zscore_warmup_is_nan_then_matches_hand_value():
    df = _bars([1, 2, 3, 4, 5, 6])           # mid == close (bid==ask)
    z = zscore(df, 3)
    assert np.isnan(z.iloc[0]) and np.isnan(z.iloc[1])       # warm-up
    # window [4,5,6] mean=5 popstd=sqrt(2/3); z at idx5 = (6-5)/sqrt(2/3)
    assert abs(z.iloc[5] - (1.0 / np.sqrt(2.0/3.0))) < 1e-9

def test_zscore_zero_std_is_nan():
    df = _bars([2.0, 2.0, 2.0, 2.0])
    z = zscore(df, 3)
    assert np.isnan(z.iloc[3])               # flat window -> std 0 -> NaN, no misleading signal

# ---- Wilder RSI ----
def test_wilder_rsi_all_gains_is_100():
    df = _bars([1, 2, 3, 4, 5, 6, 7, 8])
    r = wilder_rsi(df, 3)
    assert np.isnan(r.iloc[2])               # RSI defined from index n=3
    assert abs(r.iloc[3] - 100.0) < 1e-9     # no losses -> 100
    assert abs(r.iloc[-1] - 100.0) < 1e-9

def test_wilder_rsi_all_losses_is_zero():
    df = _bars([8, 7, 6, 5, 4, 3, 2, 1])
    r = wilder_rsi(df, 3)
    assert abs(r.iloc[3] - 0.0) < 1e-9       # no gains -> 0
    assert abs(r.iloc[-1] - 0.0) < 1e-9

def test_wilder_rsi_flat_series_is_nan():
    df = _bars([5, 5, 5, 5, 5, 5])
    r = wilder_rsi(df, 3)
    assert np.isnan(r.iloc[3]) and np.isnan(r.iloc[-1])     # flat -> RSI undefined -> NaN, no spurious extreme

def test_wilder_rsi_hand_computed_small_series():
    # deltas: +1,+1,-2,+1 ; n=2 seed over first 2 deltas: avg_gain=1, avg_loss=0 -> rsi[2]=100
    # idx3 delta -2: avg_gain=(1*1+0)/2=0.5, avg_loss=(0*1+2)/2=1.0 -> rs=0.5 -> rsi=100-100/1.5
    df = _bars([10, 11, 12, 10, 11])
    r = wilder_rsi(df, 2)
    assert abs(r.iloc[2] - 100.0) < 1e-9
    assert abs(r.iloc[3] - (100.0 - 100.0/1.5)) < 1e-9

# ---- Bollinger ----
def test_bollinger_bands_are_sma_plus_minus_k_std():
    df = _bars([1, 2, 3, 4, 5])
    mid, up, lo = bollinger(df, 3, 2.0)
    # window [3,4,5] mean=4 popstd=sqrt(2/3)
    assert abs(mid.iloc[4] - 4.0) < 1e-9
    assert abs(up.iloc[4] - (4.0 + 2.0*np.sqrt(2.0/3.0))) < 1e-9
    assert abs(lo.iloc[4] - (4.0 - 2.0*np.sqrt(2.0/3.0))) < 1e-9

def test_bollinger_zero_std_bands_are_nan_mid_defined():
    df = _bars([2.0, 2.0, 2.0, 2.0])
    mid, up, lo = bollinger(df, 3, 2.0)
    assert abs(mid.iloc[3] - 2.0) < 1e-9     # mean is defined on a flat window
    assert np.isnan(up.iloc[3]) and np.isnan(lo.iloc[3])   # zero-variance bands -> NaN, no breakout signal

# ---- causality (all three) ----
def test_indicators_no_lookahead_on_future_mutation():
    closes = list(np.linspace(1.0, 2.0, 40))
    base = _bars(closes)
    z0 = zscore(base, 20).to_numpy()
    r0 = wilder_rsi(base, 14).to_numpy()
    m0, u0, l0 = (s.to_numpy() for s in bollinger(base, 20, 2.0))
    closes2 = closes[:25] + [9.9]*(len(closes)-25)           # mutate bars after idx 24
    mut = _bars(closes2)
    z1 = zscore(mut, 20).to_numpy()
    r1 = wilder_rsi(mut, 14).to_numpy()
    m1, u1, l1 = (s.to_numpy() for s in bollinger(mut, 20, 2.0))
    assert np.allclose(z0[:25], z1[:25], equal_nan=True)
    assert np.allclose(r0[:25], r1[:25], equal_nan=True)
    assert np.allclose(m0[:25], m1[:25], equal_nan=True)
    assert np.allclose(u0[:25], u1[:25], equal_nan=True)
    assert np.allclose(l0[:25], l1[:25], equal_nan=True)

# ---- hygiene / scope ----
def test_indicators_do_not_mutate_input():
    df = _bars(list(np.linspace(1.0, 2.0, 30)))
    snap = df.copy(deep=True)
    _ = zscore(df, 20); _ = wilder_rsi(df, 14); _ = bollinger(df, 20, 2.0)
    assert df.equals(snap)                   # no in-place mutation of the caller's frame

def test_indicator_outputs_have_explicit_stable_names():
    df = _bars([1, 2, 3, 4, 5, 6])
    assert zscore(df, 3).name == "zscore"
    assert wilder_rsi(df, 3).name == "rsi"
    mid, up, lo = bollinger(df, 3, 2.0)
    assert (mid.name, up.name, lo.name) == ("bb_mid", "bb_upper", "bb_lower")

def test_module_emits_no_strategy_decisions():
    import bot.forex.meanrev_indicators as mi
    public = {nm for nm in dir(mi) if not nm.startswith("_")}
    for forbidden in ("candidate_decisions", "signal", "decisions", "enter",
                      "exit", "run_state_machine", "CANDIDATES"):
        assert forbidden not in public       # indicators only, no signal/decision surface
    z = zscore(_bars(list(np.linspace(1, 2, 30))), 20).dropna()
    assert not set(np.unique(z.to_numpy())).issubset({-1.0, 0.0, 1.0})  # continuous feature, not decisions
