"""FX backtest engine. Look-ahead discipline (CLAUDE.md §1): a decision made at
bar t's CLOSE is FILLED at bar t+1's OPEN and earns the FORWARD interval only.
The position effective over interval [open j, open j+1] is decisions[j-1] (filled
at open j); the first interval [open 0, open 1] is flat because no decision
precedes bar 0. It is NOT applied to the already-finished [open(j-1), open j] move
(that would be look-ahead). Long fills/holds at ask, short at bid; equity
compounds open-to-open mid returns; spread is charged on the traded fraction at
each position change (half-spread per one-way fill, scaled by f) AND on the forced
liquidation of any position still open at the final bar; swap accrues per rollover
held. No leverage, no stops, no signal/indicator logic here."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List
import numpy as np
import pandas as pd
from bot.forex.cost_model import CostModel, spread_frac, swap_frac
from bot.forex.metrics import max_drawdown, cagr, years_between

@dataclass
class Trade:
    side: int
    entry_ts: str
    exit_ts: str
    entry_px: float
    exit_px: float
    bars_held: int
    ret: float

def _iso(ms: int) -> str:
    return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat(timespec="seconds")

def simulate(bars: pd.DataFrame, decisions: np.ndarray, cost: CostModel,
             f: float = 1.0, starting_equity: float = 10000.0) -> Dict[str, Any]:
    b = bars.reset_index(drop=True)
    n = len(b)
    if n < 3:
        raise RuntimeError("Not enough bars to backtest (need >= 3).")
    decisions = np.asarray(decisions, dtype=int)
    if len(decisions) != n:
        raise ValueError("decisions length must equal number of bars")

    mid_o = b["mid_o"].to_numpy(float)
    bid_o = b["bid_o"].to_numpy(float)
    ask_o = b["ask_o"].to_numpy(float)
    t_ms = b["open_time"].to_numpy("int64")

    equity = float(starting_equity)
    curve = [equity]                       # equity at each bar open (index 0..n-1)
    pos_path: List[int] = []               # position effective over interval j = [open j, open j+1]
    trades: List[Trade] = []
    prev_pos = 0
    open_trade = None                      # (side, entry_px, entry_ms, entry_bar)

    for j in range(n - 1):                 # interval j = [open j, open j+1]
        pos = int(decisions[j - 1]) if j >= 1 else 0   # FILL LAG: decided close j-1, filled open j; flat before first fill
        # --- spread on a position change, realized at THIS interval's open (bar j) ---
        if pos != prev_pos:
            # half-spread per one-way fill, scaled by f (a flip trades 2 units -> one full spread)
            spread_cost = abs(pos - prev_pos) * f * spread_frac(bid_o[j], ask_o[j], cost.spread_mult) / 2.0
            equity *= (1.0 - spread_cost)
            if open_trade is not None:                 # close the prior trade at open j
                side, e_px, e_ms, e_bar = open_trade
                x_px = bid_o[j] if side > 0 else ask_o[j]
                trades.append(Trade(side, _iso(e_ms), _iso(t_ms[j]), e_px, x_px,
                                    j - e_bar, side * (x_px / e_px - 1.0)))
                open_trade = None
            if pos != 0:                               # open the new trade at open j (long@ask, short@bid)
                e_px = ask_o[j] if pos > 0 else bid_o[j]
                open_trade = (pos, e_px, t_ms[j], j)
        # --- swap for holding `pos` over (open j, open j+1] ---
        if pos != 0:
            equity *= (1.0 - swap_frac(cost, pos, mid_o[j], t_ms[j], t_ms[j + 1]))
        # --- FORWARD open-to-open mid return earned by `pos` ---
        r = mid_o[j + 1] / mid_o[j] - 1.0
        equity *= (1.0 + pos * f * r)
        curve.append(equity)
        pos_path.append(pos)
        prev_pos = pos

    # force-close any position still open at the final bar's open. Returns mark to
    # mid, so an open position has paid only its entry half-spread; the liquidation
    # must pay one one-way half-spread (scaled by f) on the unwound notional, exactly
    # like an in-loop close. Otherwise any strategy/benchmark ending open is under-costed.
    if open_trade is not None:
        side, e_px, e_ms, e_bar = open_trade
        final_close_cost = abs(prev_pos) * f * spread_frac(bid_o[n - 1], ask_o[n - 1], cost.spread_mult) / 2.0
        equity *= (1.0 - final_close_cost)
        curve[-1] = equity                     # final-open equity reflects the liquidation half-spread
        x_px = bid_o[n - 1] if side > 0 else ask_o[n - 1]
        trades.append(Trade(side, _iso(e_ms), _iso(t_ms[n - 1]), e_px, x_px,
                            (n - 1) - e_bar, side * (x_px / e_px - 1.0)))

    eq = np.asarray(curve, dtype=float)
    pos_arr = np.asarray(pos_path, dtype=float)
    years = years_between(t_ms[0], t_ms[n - 1])
    total_return = eq[-1] / starting_equity - 1.0
    summary = {
        "total_return": float(total_return),
        "cagr": float(round(cagr(starting_equity, eq[-1], years), 6)),
        "max_drawdown": float(round(max_drawdown(eq), 6)),
        "avg_net_exposure": float(pos_arr.mean() * f) if pos_arr.size else 0.0,
        "avg_gross_exposure": float(np.abs(pos_arr).mean() * f) if pos_arr.size else 0.0,
        "time_in_market": float(round((pos_arr != 0).mean(), 6)) if pos_arr.size else 0.0,
        "trade_count": len(trades),
        "start": _iso(t_ms[0])[:10],
        "end": _iso(t_ms[n - 1])[:10],
    }
    return {"summary": summary, "equity": eq, "trades": trades}
