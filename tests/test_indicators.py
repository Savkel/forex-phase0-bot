import numpy as np
import pandas as pd
import pytest
from bot.forex.indicators import add_mid, nbar_return, donchian, compute_features

def _bars(closes):
    n = len(closes)
    return pd.DataFrame({
        "open_time": np.arange(n) * 14400000,
        "time": [f"t{i}" for i in range(n)],
        "bid_o": closes, "bid_h": closes, "bid_l": closes, "bid_c": closes,
        "ask_o": [c + 0.0002 for c in closes], "ask_h": [c + 0.0002 for c in closes],
        "ask_l": [c + 0.0002 for c in closes], "ask_c": [c + 0.0002 for c in closes],
        "volume": [1] * n, "complete": [True] * n,
    })

def test_add_mid_is_average_of_bid_ask():
    df = add_mid(_bars([1.0, 1.0]))
    assert abs(df["mid_c"].iloc[0] - 1.0001) < 1e-9

def test_nbar_return_sign():
    df = add_mid(_bars([1.0, 1.1, 1.2, 1.1]))
    r = nbar_return(df, 1)
    assert np.isnan(r.iloc[0])
    assert r.iloc[1] > 0 and r.iloc[3] < 0

def test_donchian_uses_prior_bars_only():
    # current bar's own high must not be in its channel (no self-reference)
    df = add_mid(_bars([1.0, 1.0, 1.0, 2.0]))
    up, lo = donchian(df, 2)
    # at idx 3, channel = max/min of mid over idx 1..2 (=1.0001), not incl idx 3
    assert abs(up.iloc[3] - 1.0001) < 1e-9
    assert np.isnan(up.iloc[1])  # not enough prior bars

def test_compute_features_adds_expected_columns():
    df = compute_features(add_mid(_bars([1.0] * 60)), ["mom_20", "donchian_50"])
    assert "mom_20" in df and "dc_hi_50" in df and "dc_lo_50" in df

def test_compute_features_adds_only_requested_columns():
    df = compute_features(add_mid(_bars([1.0] * 60)), ["mom_20"])
    assert "mom_20" in df.columns
    assert "mom_50" not in df.columns                      # not requested
    assert "dc_hi_50" not in df.columns and "dc_lo_50" not in df.columns

def test_compute_features_rejects_unknown_candidate():
    df = add_mid(_bars([1.0] * 10))
    with pytest.raises(ValueError, match="rsi_14"):
        compute_features(df, ["rsi_14"])
    with pytest.raises(ValueError):
        compute_features(df, ["mom_abc"])
