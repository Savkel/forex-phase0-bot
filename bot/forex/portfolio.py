"""Phase 1 per-pair sleeve execution (Task 6). Runs ONE pair through the
existing tested single-pair engine (`simulate`) UNCHANGED, then derives from its
output: per-interval returns (arithmetically, from the engine equity curve) and
the filled position path (from the engine's one-bar fill-lag convention:
decisions[j-1] is effective over interval j; interval 0 is flat). No independent
spread, swap, fill, forced-close, or trade-accounting logic here.

The returned `pos` is the UNSCALED filled-position direction/state path, with
values 0, +1, or -1 only; it is NOT multiplied by `f`. Effective net and gross
exposure are obtained by applying the sleeve fraction `f` separately, e.g.
net = (pos * f).mean() and gross = (abs(pos) * f).mean() (`f` is returned
alongside `pos` for exactly this purpose).

Task 7 adds `aggregate_portfolio`: a FIXED 1/N combination of tested `run_sleeve`
outputs (spec §7). It aligns sleeves on the sorted UNION of interval_time (a pair
with no bar that interval contributes ret=0, pos=0), forms the portfolio interval
return R[t] = Sum_i w_i * ret_i[t] with w_i = 1/N by default, and builds equity
ONLY from those aggregated returns (equity[0]=E0; equity[t+1]=equity[t]*(1+R[t])).
Net = Sum_i w_i * pos_i[t] * f_i and gross = Sum_i w_i * |pos_i[t]| * f_i fold in
each sleeve's own `f`. The denominator is the fixed universe size N: flat pairs
keep their 1/N allocation (contributing zero), weights are never renormalized over
active pairs, and the 1/N weight is applied exactly once. It re-derives NO fills,
spread, swap, rollover, or PnL -- it only weights already-tested sleeve outputs."""
from __future__ import annotations
from typing import Any, Dict
import numpy as np
import pandas as pd
from bot.forex.cost_model import CostModel
from bot.forex.backtest import simulate
from bot.forex.metrics import max_drawdown

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

def aggregate_portfolio(sleeves, weights=None, starting_equity: float = 10000.0) -> Dict[str, Any]:
    """Fixed 1/N portfolio aggregation of tested `run_sleeve` outputs (spec §7).
    Union-aligns sleeves on interval_time (missing interval -> ret=0, pos=0);
    R[t]=Sum w_i*ret_i[t]; equity from R only; net/gross fold in each sleeve's f.
    Fixed denominator N (no active-pair renormalization; 1/N applied once). No
    execution/PnL/cost logic here -- it only weights already-tested sleeve outputs."""
    if not sleeves:
        raise ValueError("aggregate_portfolio: need at least one sleeve")
    N = len(sleeves)
    if weights is None:
        weights = [1.0 / N] * N
    if len(weights) != N:
        raise ValueError("weights length must match number of sleeves")
    for s in sleeves:                                          # reject upstream corruption early
        if not np.all(np.isfinite(np.asarray(s["ret"], dtype=float))):
            raise ValueError("aggregate_portfolio: non-finite interval return in a sleeve")
    tl_set: set = set()
    for s in sleeves:
        tl_set.update(int(t) for t in s["interval_time"].tolist())
    tl = np.array(sorted(tl_set), dtype="int64")
    T = len(tl)
    idx = {int(t): i for i, t in enumerate(tl)}
    R = np.zeros(T); net = np.zeros(T); gross = np.zeros(T)
    for s, w in zip(sleeves, weights):
        r = np.zeros(T); p = np.zeros(T)
        f = float(s["f"])
        for t, rv, pv in zip(s["interval_time"].tolist(), s["ret"].tolist(), s["pos"].tolist()):
            k = idx[int(t)]
            r[k] = rv; p[k] = pv
        R += w * r
        net += w * p * f
        gross += w * np.abs(p) * f
    eq = np.concatenate([[starting_equity], starting_equity * np.cumprod(1.0 + R)]) if T \
        else np.array([starting_equity], dtype=float)
    return {"timeline": tl, "equity": eq,
            "portfolio_return": float(eq[-1] / starting_equity - 1.0),
            "max_drawdown": float(max_drawdown(eq)),
            "avg_net_exposure": float(net.mean()) if T else 0.0,
            "avg_gross_exposure": float(gross.mean()) if T else 0.0,
            "interval_return": R, "net": net, "gross": gross}
