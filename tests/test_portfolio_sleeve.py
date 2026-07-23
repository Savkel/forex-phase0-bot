import inspect
import numpy as np
import pandas as pd
from bot.forex.cost_model import CostModel
from bot.forex.backtest import simulate
from bot.forex.portfolio import run_sleeve

NO_COST = CostModel(pip=0.0001, long_swap_pips=0.0, short_swap_pips=0.0, rollover_hour_utc=21)
# Real spread + nonzero swap so parity covers the spread, swap and Wednesday x3 paths.
COSTLY = CostModel(pip=0.0001, long_swap_pips=2.0, short_swap_pips=2.0, rollover_hour_utc=21)
N_PAIRS = 7

def _bars(mids, spread=0.0, start="2024-01-01 00:00", step_h=4):
    """H4 bars on real UTC timestamps so the swap / Wednesday-x3 logic is exercised."""
    n = len(mids); half = spread / 2.0
    idx = pd.date_range(start, periods=n, freq=f"{step_h}h", tz="UTC")
    open_ms = np.array([int(ts.value) // 1_000_000 for ts in idx], dtype="int64")
    return pd.DataFrame({
        "open_time": open_ms, "time": [ts.isoformat() for ts in idx],
        "bid_o": [m-half for m in mids], "ask_o": [m+half for m in mids],
        "bid_c": [m-half for m in mids], "ask_c": [m+half for m in mids],
        "bid_h": [m-half for m in mids], "ask_h": [m+half for m in mids],
        "bid_l": [m-half for m in mids], "ask_l": [m+half for m in mids],
        "mid_o": mids, "mid_c": mids, "mid_h": mids, "mid_l": mids,
        "volume": [1]*n, "complete": [True]*n})

def _wed_bars(mids, spread=0.0002):
    """Interval 1 = [open1, open2] straddles a Wednesday 21:00 UTC rollover (2024-01-03 is a
    Wednesday): open1 = Wed 20:00, open2 = Thu 00:00. A position held from interval 1 on is
    charged the Wednesday x3 swap by the engine; the sleeve must inherit it, not re-derive it."""
    return _bars(mids, spread=spread, start="2024-01-03 16:00", step_h=4)

def test_sleeve_shapes_and_interval_times():
    bars = _bars([1.0, 1.1, 1.21, 1.3])
    s = run_sleeve(bars, np.array([1, 1, 1, 1]), NO_COST, f=1.0, starting_equity=100.0)
    n = len(bars)
    assert len(s["ret"]) == n-1 and len(s["pos"]) == n-1 and len(s["interval_time"]) == n-1
    assert s["interval_time"].tolist() == bars["open_time"].to_numpy()[:-1].tolist()

def test_sleeve_position_uses_engine_fill_lag():
    bars = _bars([1.0, 1.1, 1.21])
    s = run_sleeve(bars, np.array([1, 1, 1]), NO_COST, f=1.0, starting_equity=100.0)
    # interval 0 flat (no decision precedes bar 0), interval 1 = decisions[0] = 1
    assert s["pos"].tolist() == [0.0, 1.0]

# Redline item 1: exact summary parity at f=1.0.
def test_sleeve_summary_matches_engine_at_f1():
    bars = _wed_bars([1.0, 1.1, 1.05, 1.2, 1.15, 1.18])
    dec = np.array([1, 1, 1, 1, 1, 1])   # held to the last bar -> forced final close
    s = run_sleeve(bars, dec, COSTLY, f=1.0, starting_equity=100.0)
    summ = simulate(bars, dec, COSTLY, f=1.0, starting_equity=100.0)["summary"]
    for k in ("total_return", "max_drawdown", "trade_count",
              "avg_net_exposure", "avg_gross_exposure"):
        assert s["summary"][k] == summ[k]

# Redline item 2: f = 1/N scales net AND gross exactly by 1/N vs the engine at f=1.0.
def test_sleeve_scales_exposure_at_f_1_over_n():
    bars = _bars([1.0, 1.02, 1.01, 1.03, 1.0, 1.04])
    dec = np.array([1, 1, 1, -1, 1, 1])    # NON-zero net: filled path [0,1,1,1,-1] -> net 0.4, gross 0.8
    base = simulate(bars, dec, NO_COST, f=1.0, starting_equity=100.0)["summary"]
    # degeneracy guards: net must be non-zero AND distinct from gross, so the two
    # scaling assertions below are independent proofs (neither is trivially 0 == 0)
    assert base["avg_net_exposure"] != 0.0
    assert base["avg_net_exposure"] != base["avg_gross_exposure"]
    s = run_sleeve(bars, dec, NO_COST, f=1.0 / N_PAIRS, starting_equity=100.0)
    assert s["f"] == 1.0 / N_PAIRS
    got_gross = float((np.abs(s["pos"]) * s["f"]).mean())
    got_net = float((s["pos"] * s["f"]).mean())
    assert got_net != 0.0 and got_net != got_gross
    assert abs(got_gross - base["avg_gross_exposure"] / N_PAIRS) < 1e-12
    assert abs(got_net - base["avg_net_exposure"] / N_PAIRS) < 1e-12
    # the sleeve's own engine summary agrees: net AND gross each scale by exactly 1/N
    assert abs(s["summary"]["avg_net_exposure"] - base["avg_net_exposure"] / N_PAIRS) < 1e-12
    assert abs(s["summary"]["avg_gross_exposure"] - base["avg_gross_exposure"] / N_PAIRS) < 1e-12

# Redline item 3: no independent same-bar PnL shortcut -> reconstruction rebuilds the engine path.
def test_sleeve_no_same_bar_pnl_shortcut():
    bars = _wed_bars([1.0, 1.1, 1.05, 1.2, 1.15, 1.18])
    dec = np.array([1, -1, 1, -1, 1, 1])
    res = simulate(bars, dec, COSTLY, f=1.0, starting_equity=100.0)
    s = run_sleeve(bars, dec, COSTLY, f=1.0, starting_equity=100.0)
    # the sleeve equity IS the engine equity (delegation, not a re-implementation)
    assert np.array_equal(s["equity"], res["equity"])
    # reconstructed returns rebuild that path at EVERY bar, not just the endpoint
    rebuilt = 100.0 * np.cumprod(1.0 + s["ret"])
    assert np.allclose(rebuilt, res["equity"][1:])
    # a naive same-bar pos*mid shortcut WOULD diverge here (costs are live) -> the test has teeth
    mid = bars["mid_o"].to_numpy(float)
    naive = 100.0 * np.cumprod(1.0 + s["pos"] * (mid[1:] / mid[:-1] - 1.0))
    assert not np.allclose(naive, res["equity"][1:])

# Redline item 4: forced final close + spread + swap + Wednesday x3 all flow through the sleeve.
def test_sleeve_preserves_forced_close_and_wed_swap():
    bars = _wed_bars([1.0, 1.0, 1.0, 1.0, 1.0])   # flat mids -> only spread+swap move equity
    dec = np.array([1, 1, 1, 1, 1])               # long held across Wed 21:00 and to the last bar
    res = simulate(bars, dec, COSTLY, f=1.0, starting_equity=100.0)
    s = run_sleeve(bars, dec, COSTLY, f=1.0, starting_equity=100.0)
    # forced final close is counted (a position is open at the last bar)
    assert s["summary"]["trade_count"] == res["summary"]["trade_count"] >= 1
    # equity identical -> spread, swap and the Wednesday x3 rollover are inherited, not re-derived
    assert np.array_equal(s["equity"], res["equity"])
    # and the swap/spread actually moved equity on flat mids, so the path is genuinely exercised
    assert s["summary"]["total_return"] < 0.0

# Explicit sleeve swap-vs-f parity after engine fix 94ded17: the sleeve inherits the
# f-scaled swap (and Wednesday x3) from simulate() and performs NO swap arithmetic itself.
def test_sleeve_swap_scales_with_f_and_preserves_wed_x3():
    swap_only = CostModel(pip=0.0001, long_swap_pips=10.0, short_swap_pips=10.0, rollover_hour_utc=21)
    # flat mids + zero spread -> ONLY swap can move equity. Opens run Wed 2024-01-03 16:00
    # UTC -> Fri 00:00 in 4h steps: interval 1 [Wed 20:00, Thu 00:00] crosses Wed 21:00
    # (x3); interval 7 [Thu 20:00, Fri 00:00] crosses Thu 21:00 (x1); no other held
    # interval crosses a rollover. Identical bars and decisions at both fractions.
    bars = _bars([1.0] * 9, spread=0.0, start="2024-01-03 16:00")
    dec = np.array([1] * 9)                                  # long held throughout
    full = run_sleeve(bars, dec, swap_only, f=1.0, starting_equity=100.0)
    half = run_sleeve(bars, dec, swap_only, f=0.5, starting_equity=100.0)
    # sleeve equity IS the engine equity at BOTH fractions (delegation, not recomputation)
    assert np.array_equal(full["equity"], simulate(bars, dec, swap_only, f=1.0, starting_equity=100.0)["equity"])
    assert np.array_equal(half["equity"], simulate(bars, dec, swap_only, f=0.5, starting_equity=100.0)["equity"])
    # per_night = 10 * 0.0001 / 1.0 = 0.001: Wed x3 -> -0.003 at f=1.0; Thu x1 -> -0.001
    assert abs(full["ret"][1] - (-0.003)) < 1e-12            # Wednesday x3 at f=1.0
    assert abs(half["ret"][1] - (-0.0015)) < 1e-12           # f=0.5 pays exactly HALF the Wed swap
    assert abs(half["ret"][1] - 0.5 * full["ret"][1]) < 1e-12
    assert abs(full["ret"][7] - (-0.001)) < 1e-12            # Thursday x1 at f=1.0
    assert abs(half["ret"][7] - 0.5 * full["ret"][7]) < 1e-12  # x1 rollover halves too
    assert abs(full["ret"][1] - 3.0 * full["ret"][7]) < 1e-12  # Wed x3 vs Thu x1, same run
    assert abs(half["ret"][1] - 3.0 * half["ret"][7]) < 1e-12  # ...x3 preserved after f-scaling
    # no swap where no rollover is crossed (flat mids, zero spread -> exactly zero return)
    for j in (0, 2, 3, 4, 5, 6):
        assert full["ret"][j] == 0.0 and half["ret"][j] == 0.0
    # run_sleeve contains NO swap/rollover arithmetic of its own: every drag asserted
    # above reached the sleeve exclusively through simulate().
    src = inspect.getsource(run_sleeve)
    assert "swap" not in src and "rollover" not in src
