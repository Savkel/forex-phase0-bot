"""Randomized/null timing benchmark (spec §6.2). Shuffles the candidate's
DECISION series and re-runs the SAME Task 7 engine on it, so the null shares the
bot's exposure + turnover but destroys its timing. Execution-faithful: every null
sample is `simulate(bars, shuffled_decisions, cost, f, eq)` — never a same-bar
position*return shortcut — so the null inherits the engine's fill lag, first
flat interval, spread, swap, and forced final close.

Reporting convention (no hidden assumptions):
- The metric is exposure-adjusted alpha; HIGHER is better.
- `percentile_rank` = % of null alphas STRICTLY BELOW the real alpha (0..100);
  higher rank = the real timing beats more scrambles = stronger.
- `p_value` is one-sided: (1 + #{null >= real}) / (1 + runs); SMALLER is more
  significant. Both add-one terms keep the real sample in its own reference set.
"""
from __future__ import annotations
from typing import Any, Dict, List, Sequence
import numpy as np
import pandas as pd
from bot.forex.cost_model import CostModel
from bot.forex.backtest import simulate
from bot.forex.evaluate import exposure_adjusted_alpha, hold_long

def circular_shift_decisions(d: np.ndarray, offset: int) -> np.ndarray:
    """Roll the decision series by `offset` (a new array; the input is not
    mutated). offset 0 (or a multiple of len) is the identity — `_draw_offset`
    never selects it, so the original timing is never used as a null sample."""
    return np.roll(np.asarray(d, dtype=int), int(offset))

def block_shuffle_decisions(d: np.ndarray, block_len: int, rng: np.random.Generator) -> np.ndarray:
    """Partition the decisions into contiguous blocks and permute the block order.
    This preserves the decision multiset (and so the exposure structure) and keeps
    intra-block clusters intact while randomizing WHEN those clusters occur. New
    array; the input is not mutated."""
    d = np.asarray(d, dtype=int)
    block_len = max(1, int(block_len))
    blocks = [d[i:i + block_len] for i in range(0, len(d), block_len)]
    order = rng.permutation(len(blocks))
    return np.concatenate([blocks[i] for i in order])[:len(d)]

def _draw_offset(n: int, guard: int, rng: np.random.Generator) -> int:
    """Draw a circular-shift offset in [1, n-1] — never 0 and never n (both of
    which `np.roll` maps to the identity), so the original timing is excluded from
    the null. `guard` keeps the shift away from the array ends; it is clamped so a
    valid offset always exists for n >= 2."""
    low = max(1, int(guard))                       # >= 1 => identity (offset 0) excluded
    high = max(low + 1, n - int(guard))            # exclusive upper bound; ensure a nonempty range
    high = min(high, n)                            # offset == n would also be the identity
    return int(rng.integers(low, high))

def percentile_rank(value: float, dist: Sequence[float]) -> float:
    """% of `dist` strictly below `value` (higher = better)."""
    arr = np.asarray(list(dist), dtype=float)
    if arr.size == 0:
        return 0.0
    return float(round(100.0 * np.mean(arr < value), 4))

def p_value(value: float, dist: Sequence[float]) -> float:
    """One-sided null p-value: (1 + #{dist >= value}) / (1 + N). Smaller = more
    significant. The add-one terms include the real sample in its reference set."""
    arr = np.asarray(list(dist), dtype=float)
    return float((1 + int(np.sum(arr >= value))) / (1 + arr.size))

def _alpha_of(bars: pd.DataFrame, decisions: np.ndarray, cost: CostModel,
              f: float, eq: float, hold_return: float) -> float:
    """Exposure-adjusted alpha of a decision array, computed THROUGH the engine."""
    res = simulate(bars, decisions, cost, f, eq)["summary"]
    return exposure_adjusted_alpha(res["total_return"], res["avg_net_exposure"], hold_return)

def null_distribution(bars: pd.DataFrame, decisions: np.ndarray, cost: CostModel,
                      f: float, starting_equity: float, *, runs: int = 1000,
                      method: str = "circular_shift", seed: int = 12345,
                      guard_frac: float = 0.02, block_len: int | None = None) -> Dict[str, Any]:
    """Build the null timing distribution. Deterministic given `seed`. The real
    decisions are copied up front and never mutated; each null sample re-runs the
    engine on a freshly shuffled/shifted copy."""
    decisions = np.array(decisions, dtype=int, copy=True)   # defensive copy: original never mutated
    n = len(decisions)
    rng = np.random.default_rng(seed)
    hold_return = hold_long(bars, cost, starting_equity)["total_return"]
    real_alpha = _alpha_of(bars, decisions, cost, f, starting_equity, hold_return)

    guard = max(1, int(guard_frac * n))
    if block_len is None:
        # default block = median run-length of constant stretches (fallback 10)
        run_lengths: List[int] = []
        cur = 1
        for i in range(1, n):
            if decisions[i] == decisions[i - 1]:
                cur += 1
            else:
                run_lengths.append(cur); cur = 1
        run_lengths.append(cur)
        block_len = int(np.median(run_lengths)) if run_lengths else 10

    null_alphas: List[float] = []
    for _ in range(int(runs)):
        if method == "block_shuffle":
            shuffled = block_shuffle_decisions(decisions, block_len, rng)
        else:
            shuffled = circular_shift_decisions(decisions, _draw_offset(n, guard, rng))
        null_alphas.append(_alpha_of(bars, shuffled, cost, f, starting_equity, hold_return))

    arr = np.asarray(null_alphas, dtype=float)
    return {
        "method": method, "runs": int(runs), "block_len": int(block_len),
        "real_alpha": float(round(real_alpha, 6)),
        "median": float(round(np.percentile(arr, 50), 6)),
        "p75": float(round(np.percentile(arr, 75), 6)),
        "p90": float(round(np.percentile(arr, 90), 6)),
        "p95": float(round(np.percentile(arr, 95), 6)),
        "percentile_rank": percentile_rank(real_alpha, arr),
        "p_value": float(round(p_value(real_alpha, arr), 6)),
    }
