import numpy as np
import pandas as pd
from datetime import datetime, timezone
from bot.forex.cost_model import CostModel
from bot.forex.backtest import simulate

def _bars(mids, spread=0.0):
    n = len(mids)
    half = spread / 2.0
    return pd.DataFrame({
        "open_time": np.arange(n) * 14400000, "time": [f"t{i}" for i in range(n)],
        "bid_o": [m - half for m in mids], "ask_o": [m + half for m in mids],
        "bid_c": [m - half for m in mids], "ask_c": [m + half for m in mids],
        "bid_h": [m - half for m in mids], "ask_h": [m + half for m in mids],
        "bid_l": [m - half for m in mids], "ask_l": [m + half for m in mids],
        "mid_o": mids, "mid_c": mids, "mid_h": mids, "mid_l": mids,
        "volume": [1]*n, "complete": [True]*n})

def _ms(y, m, d, h):
    return int(datetime(y, m, d, h, tzinfo=timezone.utc).timestamp() * 1000)

def _bars_at(times_ms, mids, spread=0.0):
    n = len(mids); half = spread / 2.0
    return pd.DataFrame({
        "open_time": list(times_ms), "time": [f"t{i}" for i in range(n)],
        "bid_o": [m - half for m in mids], "ask_o": [m + half for m in mids],
        "bid_c": [m - half for m in mids], "ask_c": [m + half for m in mids],
        "bid_h": [m - half for m in mids], "ask_h": [m + half for m in mids],
        "bid_l": [m - half for m in mids], "ask_l": [m + half for m in mids],
        "mid_o": mids, "mid_c": mids, "mid_h": mids, "mid_l": mids,
        "volume": [1]*n, "complete": [True]*n})

NO_COST = CostModel(pip=0.0001, long_swap_pips=0.0, short_swap_pips=0.0, rollover_hour_utc=21)

def test_long_position_takes_effect_at_next_open():
    bars = _bars([1.0, 1.1, 1.21], spread=0.0)
    res = simulate(bars, np.array([1, 1, 1]), NO_COST, f=1.0, starting_equity=100.0)["summary"]
    # decisions[0] (close bar0) fills at open1: interval [open0,open1] is FLAT, only 1.1->1.21 (+10%) captured
    assert abs(res["total_return"] - 0.1) < 1e-9
    assert abs(res["avg_net_exposure"] - 0.5) < 1e-9        # flat over interval 0, long over interval 1

def test_short_profits_when_price_falls():
    bars = _bars([1.0, 0.9, 0.81], spread=0.0)
    res = simulate(bars, np.array([-1, -1, -1]), NO_COST, f=1.0, starting_equity=100.0)["summary"]
    assert res["total_return"] > 0
    assert abs(res["avg_net_exposure"] + 0.5) < 1e-9

def test_spread_applied_on_position_change_only():
    flat = _bars([1.0, 1.0, 1.0], spread=0.0002)            # flat price -> only spread can move equity
    held_flat = simulate(flat, np.array([0, 0, 0]), NO_COST, f=1.0, starting_equity=100.0)["summary"]
    assert held_flat["total_return"] == 0.0                 # never traded -> no spread
    entered = simulate(flat, np.array([1, 1, 1]), NO_COST, f=1.0, starting_equity=100.0)["summary"]
    assert entered["total_return"] < 0.0                    # one entry fill pays spread
    assert entered["trade_count"] >= 1

def test_spread_cost_per_fill_convention():
    bars = _bars([1.0, 1.0, 1.0, 1.0, 1.0], spread=0.0002)  # flat price; spread_frac=0.0002, mid=1.0
    half = 0.0002 / 2.0                                     # half-spread per one-way fill (f=1)
    rt = simulate(bars, np.array([1, 0, 0, 0, 0]), NO_COST, f=1.0, starting_equity=100.0)["summary"]
    assert abs(rt["total_return"] - ((1 - half) ** 2 - 1.0)) < 1e-12          # entry + exit = one full spread
    flip = simulate(bars, np.array([1, -1, -1, 0, 0]), NO_COST, f=1.0, starting_equity=100.0)["summary"]
    # the trailing 0s fill too late (fill-lag) to flatten in-window, so the short is open at the last bar:
    # entry(half) + flip(full) + forced final exit(half)
    assert abs(flip["total_return"] - ((1 - half) * (1 - 2 * half) * (1 - half) - 1.0)) < 1e-12

def test_open_position_at_final_bar_pays_liquidation_half_spread():
    bars = _bars([1.0, 1.0, 1.0, 1.0], spread=0.0002)       # flat price -> only spread moves equity
    half = 0.0002 / 2.0                                     # half-spread per one-way fill (f=1)
    res = simulate(bars, np.array([1, 1, 1, 1]), NO_COST, f=1.0, starting_equity=100.0)
    s = res["summary"]
    # long opens at open1 (entry half) and is force-closed at the final open (exit half) = one full spread
    assert abs(s["total_return"] - ((1 - half) ** 2 - 1.0)) < 1e-12
    assert s["trade_count"] == 1
    tr = res["trades"][0]
    assert tr.side == 1
    assert tr.bars_held == 2                                # opened bar1, closed at the final bar (bar3)
    assert abs(tr.exit_px - bars["bid_o"].iloc[-1]) < 1e-12 # long liquidates at the final bar's bid
    # equity[-1] reflects BOTH the entry and the forced liquidation half-spread
    assert abs(res["equity"][-1] - 100.0 * (1 - half) ** 2) < 1e-9
    assert res["equity"][-1] < res["equity"][-2]            # the final close cost lowers last-open equity

def test_spread_cost_scales_with_f():
    bars = _bars([1.0, 1.0, 1.0, 1.0, 1.0], spread=0.0002)
    full = simulate(bars, np.array([1, 0, 0, 0, 0]), NO_COST, f=1.0, starting_equity=100.0)["summary"]["total_return"]
    half = simulate(bars, np.array([1, 0, 0, 0, 0]), NO_COST, f=0.5, starting_equity=100.0)["summary"]["total_return"]
    assert full < half < 0.0       # smaller f -> proportionally smaller spread cost (the *f fix)

def test_swap_flows_through_engine_with_wednesday_triple():
    cost = CostModel(pip=0.0001, long_swap_pips=10.0, short_swap_pips=10.0, rollover_hour_utc=21)
    mids = [1.0, 1.0, 1.0]                                  # flat price so only swap moves equity
    wed = _bars_at([_ms(2026,6,3,16), _ms(2026,6,3,20), _ms(2026,6,4,0)], mids)   # interval1 crosses Wed 21:00 (x3)
    thu = _bars_at([_ms(2026,6,4,16), _ms(2026,6,4,20), _ms(2026,6,5,0)], mids)   # interval1 crosses Thu 21:00 (x1)
    rw = simulate(wed, np.array([1, 1, 1]), cost, f=1.0, starting_equity=100.0)["summary"]["total_return"]
    rt = simulate(thu, np.array([1, 1, 1]), cost, f=1.0, starting_equity=100.0)["summary"]["total_return"]
    assert rw < 0 and rt < 0
    assert abs(rw - 3.0 * rt) < 1e-9                        # Wednesday rollover counts x3 through the engine

def test_exposure_uses_filled_positions_not_raw_decisions():
    bars = _bars([1.0, 1.0, 1.0, 1.0], spread=0.0)
    res = simulate(bars, np.array([1, 1, 1, 1]), NO_COST, f=1.0, starting_equity=100.0)["summary"]
    # filled positions over intervals j=0..2 are [0,1,1] (first interval flat); mean 2/3, NOT raw mean 1.0
    assert abs(res["avg_net_exposure"] - 2.0/3.0) < 1e-9
    assert abs(res["avg_gross_exposure"] - 2.0/3.0) < 1e-9

def test_summary_has_required_metrics():
    bars = _bars([1.0, 1.1, 1.05, 1.2], spread=0.0001)
    res = simulate(bars, np.array([1, -1, 1, 1]), NO_COST, f=1.0, starting_equity=100.0)
    s = res["summary"]
    for k in ("total_return", "max_drawdown", "cagr", "avg_net_exposure", "avg_gross_exposure", "trade_count"):
        assert k in s
    assert isinstance(s["trade_count"], int)
    assert s["max_drawdown"] <= 0.0
    assert len(res["equity"]) == len(bars)
