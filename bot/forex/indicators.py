"""Pure feature functions over a bid/ask candle frame. No look-ahead: every
value at row t uses only rows <= t (Donchian uses strictly < t)."""
from __future__ import annotations
from typing import List, Tuple
import pandas as pd

def add_mid(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in ("o", "h", "l", "c"):
        out[f"mid_{c}"] = (out[f"bid_{c}"].astype(float) + out[f"ask_{c}"].astype(float)) / 2.0
    return out

def nbar_return(df: pd.DataFrame, n: int) -> pd.Series:
    m = df["mid_c"].astype(float)
    return m / m.shift(n) - 1.0

def donchian(df: pd.DataFrame, n: int) -> Tuple[pd.Series, pd.Series]:
    # channel over the PRIOR n bars (shift 1 excludes the current bar)
    hi = df["mid_h"].astype(float).rolling(window=n, min_periods=n).max().shift(1)
    lo = df["mid_l"].astype(float).rolling(window=n, min_periods=n).min().shift(1)
    return hi, lo

_FAMILIES = ("mom", "donchian")

def _parse_candidate(name: str) -> Tuple[str, int]:
    """Parse a candidate name into (family, lookback). Raises a clear ValueError
    on any unknown/malformed name — compute_features never silently ignores a
    name it does not recognize. (The exact pre-registered set {mom_20, mom_50,
    donchian_50} is enforced separately at config-validation time.)"""
    parts = str(name).split("_")
    if len(parts) == 2 and parts[0] in _FAMILIES and parts[1].isdigit() and int(parts[1]) > 0:
        return parts[0], int(parts[1])
    raise ValueError(f"unknown candidate name {name!r}; expected 'mom_<n>' or 'donchian_<n>'")

def compute_features(df: pd.DataFrame, candidates: List[str]) -> pd.DataFrame:
    """Feature assembler ONLY: for each candidate name, add the matching
    indicator columns. No signals, decisions, scoring, ranking, selection, or
    long/short/flat logic; no future bars (Donchian uses prior-window shift(1))."""
    out = df if "mid_c" in df.columns else add_mid(df)
    out = out.copy()
    for name in candidates:
        family, n = _parse_candidate(name)
        if family == "mom":
            out[f"mom_{n}"] = nbar_return(out, n)
        else:  # "donchian"
            hi, lo = donchian(out, n)
            out[f"dc_hi_{n}"] = hi
            out[f"dc_lo_{n}"] = lo
    return out
