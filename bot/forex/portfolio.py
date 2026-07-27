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
spread, swap, rollover, or PnL -- it only weights already-tested sleeve outputs.

Task 8 adds the portfolio benchmark + alpha layer, built ONLY on `run_sleeve`,
`aggregate_portfolio`, and the reused `evaluate.exposure_adjusted_alpha`:
`portfolio_hold_basket` (equal-weight always-long HOLD basket = the costed beta
leg), `gross_matched_basket` (always-long at the bot's MEASURED gross fraction
G -- the drawdown-gate reference; f = G exactly, so G=0 gives a zero-notional
costless benchmark and small G is never inflated to 1.0; G validated in [0,1]),
`net_matched_basket` (DIAGNOSTIC-only constant net-exposure basket; net=0 gives
zero-notional/flat behavior, no 1.0 fallback), and
`portfolio_alpha_under` (bot vs hold-basket exposure-adjusted alpha). These are a
thin weighting shell: every fill/cost/PnL computation is delegated to the tested
engine through `run_sleeve`, and the sleeve fraction enters the engine exactly
once (it is never re-multiplied onto the aggregated returns)."""
from __future__ import annotations
from typing import Any, Dict
import numpy as np
import pandas as pd
from bot.forex.cost_model import CostModel
from bot.forex.backtest import simulate
from bot.forex.metrics import max_drawdown
from bot.forex.evaluate import exposure_adjusted_alpha

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

def _always_long_sleeve(bars, cost, f, eq):
    n = len(bars)
    return run_sleeve(bars, np.ones(n, dtype=int), cost, f, eq)

def portfolio_hold_basket(frames, cost_by_pair, weights=None, f: float = 1.0,
                          eq: float = 10000.0) -> Dict[str, Any]:
    """Equal-weight passive HOLD basket: every pair held always-long through the
    tested engine (via run_sleeve), then 1/N aggregated. Its portfolio_return is
    the costed basket hold_return -- the beta leg of exposure-adjusted alpha. Runs
    the SAME universe/window/costs as the bot; no direct price-return math."""
    sleeves = [_always_long_sleeve(frames[p], cost_by_pair[p], f, eq) for p in frames]
    return aggregate_portfolio(sleeves, weights, eq)

def gross_matched_basket(frames, cost_by_pair, G, weights=None,
                         eq: float = 10000.0) -> Dict[str, Any]:
    """Gross-matched passive basket -- the drawdown-GATE reference. Every pair held
    always-long at the common fraction f = the bot's MEASURED gross exposure G, then
    1/N aggregated, so the basket's own avg gross ~ G (apples-to-apples with the bot
    under the shared first-flat convention). G is used EXACTLY as measured: a
    zero-gross bot (G == 0) yields f = 0.0 -- a zero-notional, costless benchmark --
    and a small positive G is NEVER inflated to 1.0. G is validated finite and within
    [0, 1]. The fraction enters the engine ONCE (through run_sleeve) -- aggregated
    returns are not re-multiplied. (The reused evaluate.matched_gross helper still
    carries the old `or 1.0` fallback; unifying that is a deferred Task-11 decision.)"""
    g = float(G)
    if not np.isfinite(g) or g < 0.0 or g > 1.0:
        raise ValueError(f"gross_matched_basket: G must be finite in [0, 1], got {G!r}")
    sleeves = [_always_long_sleeve(frames[p], cost_by_pair[p], g, eq) for p in frames]
    return aggregate_portfolio(sleeves, weights, eq)

def net_matched_basket(frames, cost_by_pair, net, weights=None,
                       eq: float = 10000.0) -> Dict[str, Any]:
    """DIAGNOSTIC ONLY (NOT a gate): constant net-exposure passive basket -- hold
    sign(net) at fraction f = |measured net| per pair, 1/N aggregated, so its avg
    net exposure ~ net. The portfolio-level analogue of the per-pair net-matched
    passive; the gross-matched basket, not this, is the primary/gate benchmark. A
    zero measured net yields f = 0.0 -- deterministic zero-notional / flat behavior
    -- with NO 1.0 fallback. The fraction enters the engine once (via run_sleeve)."""
    n_net = float(net)
    side = int(np.sign(n_net)) or 1              # sign is 0 at net==0; f=0.0 makes it zero-notional regardless
    f = abs(n_net)
    sleeves = [run_sleeve(frames[p], np.full(len(frames[p]), side, dtype=int),
                          cost_by_pair[p], f, eq) for p in frames]
    return aggregate_portfolio(sleeves, weights, eq)

def portfolio_alpha_under(frames, decisions_by_pair, cost_by_pair, weights=None,
                          eq: float = 10000.0):
    """Portfolio exposure-adjusted alpha of the bot decisions vs the equal-weight
    hold basket. Bot sleeves run at engine f=1.0 (1/N dilution is by return
    averaging, not f); the hold basket is the costed beta leg. alpha is the reused
    evaluate.exposure_adjusted_alpha helper (NOT re-derived here). Returns
    (alpha, bot, hold) so callers can read the measured G = bot['avg_gross_exposure']."""
    sleeves = [run_sleeve(frames[p], decisions_by_pair[p], cost_by_pair[p], 1.0, eq)
               for p in frames]
    bot = aggregate_portfolio(sleeves, weights, eq)
    hold = portfolio_hold_basket(frames, cost_by_pair, weights, 1.0, eq)
    alpha = exposure_adjusted_alpha(bot["portfolio_return"], bot["avg_net_exposure"],
                                    hold["portfolio_return"])
    return float(alpha), bot, hold
