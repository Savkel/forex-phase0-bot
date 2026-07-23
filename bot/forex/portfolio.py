"""Phase 1 per-pair sleeve execution (Task 6). Runs ONE pair through the
existing tested single-pair engine (`simulate`) UNCHANGED, then derives from its
output: per-interval returns (arithmetically, from the engine equity curve) and
the filled position path (from the engine's one-bar fill-lag convention:
decisions[j-1] is effective over interval j; interval 0 is flat). No portfolio
aggregation yet; no independent spread, swap, fill, forced-close, or
trade-accounting logic here.

The returned `pos` is the UNSCALED filled-position direction/state path, with
values 0, +1, or -1 only; it is NOT multiplied by `f`. Effective net and gross
exposure are obtained by applying the sleeve fraction `f` separately, e.g.
net = (pos * f).mean() and gross = (abs(pos) * f).mean() (`f` is returned
alongside `pos` for exactly this purpose)."""
from __future__ import annotations
from typing import Any, Dict
import numpy as np
import pandas as pd
from bot.forex.cost_model import CostModel
from bot.forex.backtest import simulate

def run_sleeve(bars: pd.DataFrame, decisions, cost: CostModel, f: float = 1.0,
               starting_equity: float = 10000.0) -> Dict[str, Any]:
    res = simulate(bars, decisions, cost, f, starting_equity)
    eq = np.asarray(res["equity"], dtype=float)              # length n
    dec = np.asarray(decisions, dtype=int)
    n = len(eq)
    ret = eq[1:] / eq[:-1] - 1.0                             # interval returns, length n-1
    pos = np.zeros(n - 1, dtype=float)                       # engine fill lag
    if n - 1 >= 1:
        pos[1:] = dec[:n - 2]                                # pos_j = decisions[j-1] for j=1..n-2; pos_0 = 0
    interval_time = bars["open_time"].to_numpy("int64")[:-1]
    return {"interval_time": interval_time, "ret": ret, "pos": pos,
            "f": float(f), "equity": eq, "summary": res["summary"]}
