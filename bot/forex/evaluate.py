"""Evaluation: exposure-adjusted alpha + costed passive benchmarks + a
diagnostic segmented OOS view. Benchmarks run through the SAME engine as the bot
(constant/derived decision arrays) so costs (spread + final liquidation + swap)
apply identically and the passive long honors the engine's fill convention
(first interval flat, position from the second open, forced final close). Alpha
formula ported in structure from the crypto harness; no strategy logic here."""
from __future__ import annotations
from typing import Any, Dict
import numpy as np
import pandas as pd
from bot.forex.cost_model import CostModel
from bot.forex.backtest import simulate

def exposure_adjusted_alpha(bot_return: float, avg_net_exposure: float, hold_return: float) -> float:
    """alpha = bot_return - avg_net_exposure * hold_return. Strips passive beta:
    a flat book, or a position that merely rode the trend at its average net
    exposure, earns ~0 alpha. Explicit and deterministic — no hidden exposure
    assumption (the caller passes the MEASURED avg net exposure and the costed
    hold return)."""
    return float(bot_return) - float(avg_net_exposure) * float(hold_return)

def hold_long(bars: pd.DataFrame, cost: CostModel, starting_equity: float = 10000.0) -> Dict[str, Any]:
    """Always-long, f=1.0, THROUGH the engine (entry spread + swap + forced final
    liquidation applied). First interval is flat per the engine convention. This
    is the costed `hold_return` for alpha and the f=1.0 gross reference."""
    n = len(bars)
    return simulate(bars, np.ones(n, dtype=int), cost, 1.0, starting_equity)["summary"]

def matched_net(bars: pd.DataFrame, cost: CostModel, avg_net_exposure: float,
                starting_equity: float = 10000.0) -> Dict[str, Any]:
    """Constant net-exposure passive (costed): hold sign(avg_net) at fraction
    |avg_net|. Net-matched for alpha/beta removal."""
    n = len(bars)
    side = int(np.sign(avg_net_exposure)) or 1
    f = abs(float(avg_net_exposure))
    return simulate(bars, np.full(n, side, dtype=int), cost, f, starting_equity)["summary"]

def matched_gross(bars: pd.DataFrame, cost: CostModel, avg_gross_exposure: float,
                  starting_equity: float = 10000.0) -> Dict[str, Any]:
    """Gross-exposure-matched passive (costed): hold LONG at fraction f_gross =
    the bot's MEASURED avg gross exposure (capital-at-risk match for the
    equal-drawdown gate). f=1.0 is used ONLY as a degenerate fallback when the
    measured gross is ~0 — never silently hardcoded otherwise."""
    n = len(bars)
    f = abs(float(avg_gross_exposure)) or 1.0
    return simulate(bars, np.ones(n, dtype=int), cost, f, starting_equity)["summary"]

def passive_benchmarks(bars: pd.DataFrame, cost: CostModel,
                       starting_equity: float = 10000.0) -> Dict[str, Any]:
    """Diagnostic suite of costed passive benchmarks (all through the engine)."""
    n = len(bars)
    out = {"hold_long": hold_long(bars, cost, starting_equity)}
    out["fixed_50pct"] = simulate(bars, np.ones(n, dtype=int), cost, 0.5, starting_equity)["summary"]
    # MA(50) timing filter on mid close; decision uses shift(1) -> no look-ahead
    mid = bars["mid_c"].astype(float).reset_index(drop=True)
    ma = mid.rolling(50, min_periods=50).mean()
    in_mkt = (mid > ma).shift(1, fill_value=False).to_numpy().astype(int)
    out["ma_filter"] = simulate(bars, in_mkt, cost, 1.0, starting_equity)["summary"]
    return out

def segmented_evaluation(bars: pd.DataFrame, decisions: np.ndarray, cost: CostModel,
                         f: float, starting_equity: float, n_segments: int = 4) -> Dict[str, Any]:
    """DIAGNOSTIC ONLY (spans in-sample data). Replays the SAME fixed decisions on
    sequential independent windows and reports per-segment metrics. It selects
    nothing, tunes nothing, and emits no strategy decision — NOT a gate (spec
    §4). Inputs are never mutated."""
    b = bars.reset_index(drop=True)
    decisions = np.array(decisions, dtype=int, copy=True)   # defensive copy: never a view into the caller's array
    n = len(b)
    if n < n_segments * 3:
        n_segments = max(1, n // 3)
    seg_len = n // max(1, n_segments)
    segments = []
    for i in range(n_segments):
        lo = i * seg_len
        hi = n if i == n_segments - 1 else (i + 1) * seg_len
        sub = b.iloc[lo:hi].reset_index(drop=True)
        sub_dec = decisions[lo:hi]
        if len(sub) < 3:
            continue
        res = simulate(sub, sub_dec, cost, f, starting_equity)["summary"]
        hold = hold_long(sub, cost, starting_equity)["total_return"]
        segments.append({
            "segment": i + 1, "start": res["start"], "end": res["end"],
            "bot_return": res["total_return"], "hold_return": round(hold, 6),
            "avg_net_exposure": res["avg_net_exposure"],
            "exposure_adjusted_alpha": round(
                exposure_adjusted_alpha(res["total_return"], res["avg_net_exposure"], hold), 6),
            "max_drawdown": res["max_drawdown"], "trades": res["trade_count"],
        })
    xas = [s["exposure_adjusted_alpha"] for s in segments]
    return {
        "label": "DIAGNOSTIC ONLY — spans in-sample data; not a gate",
        "n_segments": len(segments), "segments": segments,
        "avg_exposure_adjusted_alpha": round(float(np.mean(xas)), 6) if xas else 0.0,
        "worst_exposure_adjusted_alpha": round(float(min(xas)), 6) if xas else 0.0,
    }
