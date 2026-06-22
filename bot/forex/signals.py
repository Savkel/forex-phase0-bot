"""Pre-registered Phase 0 candidate signals. Each returns a decision array
d[t] in {-1,0,+1} decided at bar t CLOSE. 0 occurs only during warm-up; after
that the candidates are always-in (hold prior on no fresh signal)."""
from __future__ import annotations
import numpy as np
import pandas as pd

CANDIDATES = ["mom_20", "mom_50", "donchian_50"]

def _hold_prior(raw: np.ndarray) -> np.ndarray:
    """raw uses np.nan for 'no decision yet' and 0 for 'hold prior'. Resolve to
    {-1,0,+1}: carry the last non-zero decision forward; leading region stays 0."""
    out = np.zeros(len(raw), dtype=int)
    cur = 0
    for i, v in enumerate(raw):
        if np.isnan(v):
            out[i] = 0
            cur = 0
        elif v == 0:
            out[i] = cur          # hold prior
        else:
            cur = int(np.sign(v))
            out[i] = cur
    return out

def _momentum(df: pd.DataFrame, n: int) -> np.ndarray:
    r = df[f"mom_{n}"].to_numpy(dtype=float)
    raw = np.where(np.isnan(r), np.nan, np.sign(r))  # +1/-1, 0 where r==0 -> hold prior
    return _hold_prior(raw)

def _donchian(df: pd.DataFrame, n: int) -> np.ndarray:
    close = df["mid_c"].to_numpy(dtype=float)
    hi = df[f"dc_hi_{n}"].to_numpy(dtype=float)
    lo = df[f"dc_lo_{n}"].to_numpy(dtype=float)
    raw = np.full(len(close), np.nan)
    for i in range(len(close)):
        if np.isnan(hi[i]) or np.isnan(lo[i]):
            raw[i] = np.nan
        elif close[i] > hi[i]:
            raw[i] = 1.0
        elif close[i] < lo[i]:
            raw[i] = -1.0
        else:
            raw[i] = 0.0          # inside channel -> hold prior
    return _hold_prior(raw)

def candidate_decisions(df: pd.DataFrame, name: str) -> np.ndarray:
    n = int(name.split("_")[1])
    if name.startswith("mom_"):
        return _momentum(df, n)
    if name.startswith("donchian_"):
        return _donchian(df, n)
    raise ValueError(f"unknown candidate {name!r}")
