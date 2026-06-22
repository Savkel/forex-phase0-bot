"""Equity-curve metrics. Ported in structure from the crypto harness; no
strategy logic. drawdown <= 0; cagr/years are calendar-time based."""
from __future__ import annotations
from typing import Sequence
import numpy as np

def max_drawdown(equity: Sequence[float]) -> float:
    arr = np.asarray(list(equity), dtype=float)
    if arr.size == 0:
        return 0.0
    peak = np.maximum.accumulate(arr)
    dd = arr / peak - 1.0
    return float(dd.min())

def cagr(start: float, end: float, years: float) -> float:
    if start <= 0 or years <= 0 or end <= 0:
        return 0.0
    return float((end / start) ** (1.0 / years) - 1.0)

def years_between(t0_ms: int, t1_ms: int) -> float:
    return max(1e-9, (int(t1_ms) - int(t0_ms)) / 1000.0 / (365.25 * 24 * 3600))
