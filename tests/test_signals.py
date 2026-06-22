import numpy as np
import pandas as pd
from bot.forex.indicators import add_mid, compute_features
from bot.forex.signals import candidate_decisions, CANDIDATES

def _bars(closes):
    n = len(closes)
    return add_mid(pd.DataFrame({
        "open_time": np.arange(n) * 14400000, "time": [f"t{i}" for i in range(n)],
        "bid_o": closes, "bid_h": closes, "bid_l": closes, "bid_c": closes,
        "ask_o": closes, "ask_h": closes, "ask_l": closes, "ask_c": closes,
        "volume": [1]*n, "complete": [True]*n}))

def test_momentum_sign_and_warmup_flat():
    closes = [1.0]*1 + list(np.linspace(1.0, 1.5, 30)) + list(np.linspace(1.5, 1.2, 30))
    df = compute_features(_bars(closes), ["mom_20"])
    d = candidate_decisions(df, "mom_20")
    assert d[:20].tolist() == [0]*20          # warm-up flat
    assert d[25] == 1                          # rising -> long
    assert d[-1] == -1                         # falling -> short

def test_momentum_holds_prior_on_zero_return():
    closes = [1.0, 1.1, 1.2, 1.2, 1.2]  # flat after rise
    df = compute_features(_bars(closes), ["mom_20"])  # n>len -> all warmup; use mom small via direct
    # use N=2 path through helper by faking column
    df["mom_2"] = df["mid_c"] / df["mid_c"].shift(2) - 1.0
    d = candidate_decisions(df, "mom_2")
    # idx2: r>0 long; idx3: r>0 long; idx4: r==0 -> hold prior (long)
    assert d[2] == 1 and d[4] == 1

def test_donchian_breakout_holds_until_opposite():
    closes = [1.0]*55 + [1.05] + [1.04]*5 + [0.90]
    df = compute_features(_bars(closes), ["donchian_50"])
    d = candidate_decisions(df, "donchian_50")
    assert d[55] == 1            # upper breakout
    assert d[57] == 1            # holds long (no opposite break)
    assert d[-1] == -1           # lower breakout flips short

def test_candidates_constant_is_correct():
    assert CANDIDATES == ["mom_20", "mom_50", "donchian_50"]
