"""Mean-reversion features over a mid-price candle frame. No look-ahead: every
value at row t uses only rows <= t (trailing rolling windows / causal Wilder
recursion). Population std (ddof=0). These are pure INDICATORS — they emit numeric
features only, never trading decisions (no enter/exit/state-machine logic; that is
Task 5). New for Phase 1; no Phase 0 signal logic reused. Degenerate windows are
handled so they never emit a misleading finite signal: a zero-variance z-score is
NaN, a flat-series RSI is NaN, and zero-variance Bollinger bands are NaN."""
from __future__ import annotations
from typing import Tuple
import numpy as np
import pandas as pd

def zscore(df: pd.DataFrame, n: int) -> pd.Series:
    """(mid_c - SMA_n) / STD_n over a trailing n-row window (rows <= t only),
    population std (ddof=0). NaN during warm-up (< n rows) and where STD_n == 0 (a
    flat window), so a zero-variance window never emits a misleading finite z."""
    m = df["mid_c"].astype(float)
    mean = m.rolling(window=n, min_periods=n).mean()
    std = m.rolling(window=n, min_periods=n).std(ddof=0)
    z = (m - mean) / std
    return z.where(std > 0).rename("zscore")

def wilder_rsi(df: pd.DataFrame, n: int) -> pd.Series:
    """Canonical Wilder RSI: seed = SMA of the first n deltas (RSI defined from
    index n), then Wilder recursive smoothing. Causal (row t uses deltas <= t).
    all-gains window -> 100; all-losses -> 0; a genuinely flat window (no gains and
    no losses) -> NaN (RSI undefined; emit no signal rather than a spurious extreme)."""
    c = df["mid_c"].astype(float).to_numpy()
    m = len(c)
    rsi = np.full(m, np.nan)
    if m < n + 1:
        return pd.Series(rsi, index=df.index, name="rsi")
    delta = np.diff(c)                            # length m-1; delta[i-1] = c[i]-c[i-1]
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    def _rsi(ag: float, al: float) -> float:
        if ag == 0.0 and al == 0.0:
            return np.nan                         # flat: RSI undefined, no signal
        if al == 0.0:
            return 100.0                          # only gains
        rs = ag / al
        return 100.0 - 100.0 / (1.0 + rs)         # al > 0 (ag == 0 -> 0.0)
    avg_gain = gain[:n].mean()                    # seed = SMA of first n deltas -> RSI at index n
    avg_loss = loss[:n].mean()
    rsi[n] = _rsi(avg_gain, avg_loss)
    for i in range(n + 1, m):
        avg_gain = (avg_gain * (n - 1) + gain[i - 1]) / n     # uses only delta up to bar i
        avg_loss = (avg_loss * (n - 1) + loss[i - 1]) / n
        rsi[i] = _rsi(avg_gain, avg_loss)
    return pd.Series(rsi, index=df.index, name="rsi")

def bollinger(df: pd.DataFrame, n: int, k: float) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Bollinger bands over a trailing n-row window (rows <= t only), population std
    (ddof=0): mid = SMA_n, upper = mid + k*STD_n, lower = mid - k*STD_n. NaN during
    warm-up. On a zero-variance window (STD_n == 0) the bands are NaN (mid, the mean,
    stays defined), so a flat window never emits a breakout signal."""
    m = df["mid_c"].astype(float)
    mid = m.rolling(window=n, min_periods=n).mean().rename("bb_mid")
    std = m.rolling(window=n, min_periods=n).std(ddof=0)
    upper = (mid + float(k) * std).where(std > 0).rename("bb_upper")
    lower = (mid - float(k) * std).where(std > 0).rename("bb_lower")
    return mid, upper, lower
