"""Pre-registered Phase 1 mean-reversion candidates. Each returns a decision
array d[t] in {-1,0,+1} decided at bar t CLOSE: enter only from flat on an
extreme deviation (fade it); exit to flat on the side-specific reversion through
the mean OR after max_holding_bars; no direct flips; flat during warm-up. New for
Phase 1 — no Phase 0 signal logic."""
from __future__ import annotations
from typing import Callable
import numpy as np
import pandas as pd
from bot.forex.meanrev_indicators import zscore, wilder_rsi, bollinger

CANDIDATES = ["zscore_20_2.0", "rsi_14_30_70", "boll_20_2.0"]

def _run_state_machine(n_bars: int, entry: Callable[[int], int],
                       exit_: Callable[[int, int], bool], max_hold: int) -> np.ndarray:
    out = np.zeros(n_bars, dtype=int)
    pos = 0
    held = 0
    for i in range(n_bars):
        if pos == 0:
            e = entry(i)                     # +1/-1 to open, 0 = no entry (uses only info at bar i)
            if e != 0:
                pos = e
                held = 1
            out[i] = pos
        else:
            if exit_(i, pos) or held >= max_hold:
                pos = 0                       # go flat this bar; NO direct flip
                held = 0
                out[i] = 0
            else:
                held += 1
                out[i] = pos
    return out

def _zscore_candidate(df, n=20, k=2.0, max_hold=12) -> np.ndarray:
    z = zscore(df, n).to_numpy(float)
    def entry(i):
        if np.isnan(z[i]):
            return 0
        if z[i] >= k:
            return -1                        # above mean -> short (fade)
        if z[i] <= -k:
            return 1                         # below mean -> long (fade)
        return 0
    def exit_(i, side):
        if np.isnan(z[i]):
            return False
        return (z[i] <= 0.0) if side < 0 else (z[i] >= 0.0)   # revert through the mean
    return _run_state_machine(len(z), entry, exit_, max_hold)

def _rsi_candidate(df, n=14, low=30.0, high=70.0, neutral=50.0, max_hold=12) -> np.ndarray:
    r = wilder_rsi(df, n).to_numpy(float)
    def entry(i):
        if np.isnan(r[i]):
            return 0
        if r[i] <= low:
            return 1                         # oversold -> long
        if r[i] >= high:
            return -1                        # overbought -> short
        return 0
    def exit_(i, side):
        if np.isnan(r[i]):
            return False
        return (r[i] >= neutral) if side > 0 else (r[i] <= neutral)   # back to neutral
    return _run_state_machine(len(r), entry, exit_, max_hold)

def _boll_candidate(df, n=20, k=2.0, max_hold=12) -> np.ndarray:
    c = df["mid_c"].astype(float).to_numpy()
    mid, upper, lower = (s.to_numpy(float) for s in bollinger(df, n, k))
    def entry(i):
        if np.isnan(upper[i]):
            return 0
        if c[i] < lower[i]:
            return 1                         # below lower band -> long
        if c[i] > upper[i]:
            return -1                        # above upper band -> short
        return 0
    def exit_(i, side):
        if np.isnan(mid[i]):
            return False
        return (c[i] >= mid[i]) if side > 0 else (c[i] <= mid[i])     # back to mid-band
    return _run_state_machine(len(c), entry, exit_, max_hold)

def candidate_decisions(df: pd.DataFrame, name: str, max_hold: int = 12) -> np.ndarray:
    if name == "zscore_20_2.0":
        return _zscore_candidate(df, 20, 2.0, max_hold)
    if name == "rsi_14_30_70":
        return _rsi_candidate(df, 14, 30.0, 70.0, 50.0, max_hold)
    if name == "boll_20_2.0":
        return _boll_candidate(df, 20, 2.0, max_hold)
    raise ValueError(f"unknown candidate {name!r}; expected one of {CANDIDATES}")
