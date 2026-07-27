"""Task 9: relative-to-base portfolio cost-stress sweep.

Scales ONLY the supplied base cost models' spread_mult / swap_mult (via
dataclasses.replace, relative to the configured base) and re-runs the SAME
bot-vs-hold alpha path (portfolio_alpha_under -> run_sleeve -> simulate ->
aggregate_portfolio) under each scenario. Identical non-cost inputs in every
scenario; base cost objects are never mutated; no post-hoc cost/PnL arithmetic.
"""
import inspect
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from bot.forex.cost_model import CostModel, swap_frac
from bot.forex.portfolio import (portfolio_cost_stress, _scale_costs,
                                 portfolio_alpha_under, run_sleeve)
import bot.forex.portfolio as pf

BASE = CostModel(pip=0.0001, long_swap_pips=0.5, short_swap_pips=0.5,
                 rollover_hour_utc=21, spread_mult=1.0, swap_mult=1.0)


def _bars(mids, spread=0.0, open_times=None):
    n = len(mids); half = spread / 2.0
    ot = np.arange(n) * 14400000 if open_times is None else np.asarray(open_times, "int64")
    m = list(mids)
    return pd.DataFrame({
        "open_time": ot, "time": [f"t{i}" for i in range(n)],
        "bid_o": [x-half for x in m], "ask_o": [x+half for x in m],
        "bid_c": [x-half for x in m], "ask_c": [x+half for x in m],
        "bid_h": [x-half for x in m], "ask_h": [x+half for x in m],
        "bid_l": [x-half for x in m], "ask_l": [x+half for x in m],
        "mid_o": m, "mid_c": m, "mid_h": m, "mid_l": m,
        "volume": [1]*n, "complete": [True]*n})


# ---- Plan tests (locked Task 9 spec) --------------------------------------------------

def test_scale_costs_is_relative_to_base():
    base = {"A": CostModel(pip=0.0001, spread_mult=2.0, swap_mult=1.0)}
    scaled = _scale_costs(base, 1.5, 2.0)
    assert scaled["A"].spread_mult == 3.0      # 2.0 * 1.5, relative to base
    assert scaled["A"].swap_mult == 2.0        # 1.0 * 2.0


def test_stress_returns_four_cells_and_combined_is_worst_or_equal():
    mids = [1.0, 1.01, 1.0, 1.01, 1.0, 1.01, 1.0]
    frames = {"A": _bars(mids, 0.0004), "B": _bars(mids, 0.0004)}
    cbp = {"A": BASE, "B": BASE}
    dec = {"A": np.array([1, 0, 1, 0, 1, 0, 0]), "B": np.array([1, 0, 1, 0, 1, 0, 0])}
    sweep = portfolio_cost_stress(frames, dec, cbp, spread_mult=1.5, swap_mult=2.0)
    assert set(sweep) == {"base", "spread", "swap", "combined"}
    assert sweep["combined"] <= sweep["base"] + 1e-12    # more cost -> not higher alpha
    assert sweep["spread"] <= sweep["base"] + 1e-12
    assert sweep["swap"] <= sweep["base"] + 1e-12


# ---- Additive hardening (each maps to a "tests must prove" bullet) ---------------------

def test_base_cell_reproduces_unstressed_alpha():
    # base cell = (x1.0, x1.0) -> identical costs -> identical alpha to a direct call
    mids = [1.0, 1.01, 1.0, 1.01, 1.0, 1.01, 1.0]
    frames = {"A": _bars(mids, 0.0004), "B": _bars(mids, 0.0004)}
    cbp = {"A": BASE, "B": BASE}
    dec = {"A": np.array([1, 0, 1, 0, 1, 0, 0]), "B": np.array([1, 0, 1, 0, 1, 0, 0])}
    sweep = portfolio_cost_stress(frames, dec, cbp, 1.5, 2.0)
    direct, _, _ = portfolio_alpha_under(frames, dec, cbp)
    assert sweep["base"] == round(float(direct), 6)


def test_spread_and_swap_cells_change_only_their_field():
    base = {"A": CostModel(pip=0.0001, long_swap_pips=0.5, short_swap_pips=0.5,
                           rollover_hour_utc=21, spread_mult=1.0, swap_mult=1.0)}
    spread_only = _scale_costs(base, 1.5, 1.0)["A"]        # spread scenario
    swap_only = _scale_costs(base, 1.0, 2.0)["A"]          # swap scenario
    assert spread_only.spread_mult == 1.5 and spread_only.swap_mult == 1.0
    assert swap_only.spread_mult == 1.0 and swap_only.swap_mult == 2.0
    # pip sizes, swap pips, and rollover timing preserved in BOTH scenarios
    for s in (spread_only, swap_only):
        assert s.pip == 0.0001
        assert s.long_swap_pips == 0.5 and s.short_swap_pips == 0.5
        assert s.rollover_hour_utc == 21


def test_combined_applies_both_multipliers_once():
    base = {"A": CostModel(pip=0.0001, spread_mult=1.0, swap_mult=1.0)}
    c = _scale_costs(base, 1.5, 2.0)["A"]
    assert c.spread_mult == 1.5        # applied once, not 1.5**2
    assert c.swap_mult == 2.0          # applied once, not 2.0**2


def test_base_cost_objects_are_not_mutated():
    base_a = CostModel(pip=0.0001, long_swap_pips=0.5, short_swap_pips=0.5,
                       rollover_hour_utc=21, spread_mult=1.0, swap_mult=1.0)
    base_b = CostModel(pip=0.0001, long_swap_pips=0.5, short_swap_pips=0.5,
                       rollover_hour_utc=21, spread_mult=1.0, swap_mult=1.0)
    snapshot = (repr(base_a), repr(base_b))
    frames = {"A": _bars([1.0, 1.01, 1.0, 1.01, 1.0], 0.0004),
              "B": _bars([1.0, 1.01, 1.0, 1.01, 1.0], 0.0004)}
    dec = {"A": np.array([1, 0, 1, 0, 0]), "B": np.array([1, 0, 1, 0, 0])}
    _ = portfolio_cost_stress(frames, dec, {"A": base_a, "B": base_b}, 1.5, 2.0)
    assert (repr(base_a), repr(base_b)) == snapshot        # supplied objects untouched
    assert base_a.spread_mult == 1.0 and base_a.swap_mult == 1.0


def test_wednesday_x3_and_f_scaled_swap_inherited_through_stress_cost():
    # (a) the SWAP-scaled cost model doubles per-night swap AND preserves Wednesday x3,
    #     for BOTH long and short sides (swap_mult scales both).
    base = CostModel(pip=0.0001, long_swap_pips=10.0, short_swap_pips=10.0, rollover_hour_utc=21)
    swap2 = _scale_costs({"A": base}, 1.0, 2.0)["A"]
    wed = int(datetime(2024, 1, 3, 20, 0, tzinfo=timezone.utc).timestamp() * 1000)  # Wed, pre-21:00
    wed_n = wed + 14400000                                                          # crosses Wed 21:00
    thu = int(datetime(2024, 1, 4, 20, 0, tzinfo=timezone.utc).timestamp() * 1000)  # Thu, pre-21:00
    thu_n = thu + 14400000                                                          # crosses Thu 21:00
    for side in (1, -1):                                                            # long AND short
        assert abs(swap_frac(swap2, side, 1.0, wed, wed_n)
                   - 2.0 * swap_frac(base, side, 1.0, wed, wed_n)) < 1e-15          # doubled
        assert abs(swap_frac(swap2, side, 1.0, wed, wed_n)
                   - 3.0 * swap_frac(swap2, side, 1.0, thu, thu_n)) < 1e-15         # Wed x3 preserved
    # (b) f-scaling (94ded17) inherited: the SAME scaled cost, run through run_sleeve,
    #     pays exactly half the swap at f=0.5 (flat mids + zero spread -> swap is the only drag).
    b0 = int(datetime(2024, 1, 3, 16, 0, tzinfo=timezone.utc).timestamp() * 1000)   # Wed 16:00
    ot = b0 + np.arange(9) * 14400000
    bars = _bars([1.0] * 9, open_times=ot)
    full = run_sleeve(bars, np.ones(9, int), swap2, 1.0)["ret"]
    half = run_sleeve(bars, np.ones(9, int), swap2, 0.5)["ret"]
    assert abs(full[1] - (-0.006)) < 1e-12                 # interval 1 crosses Wed 21:00: 2*0.001*3
    assert np.allclose(half, 0.5 * full)                   # f-scaled swap inherited through stressed cost


def test_all_scenarios_use_identical_non_cost_inputs(monkeypatch):
    frames = {"A": _bars([1.0, 1.01, 1.0], 0.0004), "B": _bars([1.0, 1.01, 1.0], 0.0004)}
    dec = {"A": np.array([1, 0, 0]), "B": np.array([1, 0, 0])}
    weights = [0.5, 0.5]
    calls = []
    def _recorder(f_, d_, c_, w_=None, e_=10000.0):
        calls.append((f_, d_, c_, w_, e_))
        return 0.0, {"avg_gross_exposure": 0.0}, {}
    monkeypatch.setattr(pf, "portfolio_alpha_under", _recorder)
    pf.portfolio_cost_stress(frames, dec, {"A": BASE, "B": BASE}, 1.5, 2.0,
                             weights=weights, eq=5000.0)
    assert len(calls) == 4
    for f_, d_, c_, w_, e_ in calls:
        assert f_ is frames            # SAME frames object every scenario
        assert d_ is dec               # SAME decisions object
        assert w_ is weights           # SAME weights
        assert e_ == 5000.0            # SAME starting equity
    labels = ("base", "spread", "swap", "combined")
    muls = {labels[i]: (calls[i][2]["A"].spread_mult, calls[i][2]["A"].swap_mult)
            for i in range(4)}
    assert muls == {"base": (1.0, 1.0), "spread": (1.5, 1.0),
                    "swap": (1.0, 2.0), "combined": (1.5, 2.0)}   # only costs differ


def test_combined_stress_alpha_is_deterministic():
    mids = [1.0, 1.01, 1.0, 1.01, 1.0, 1.01, 1.0]
    frames = {"A": _bars(mids, 0.0004), "B": _bars(mids, 0.0004)}
    dec = {"A": np.array([1, 0, 1, 0, 1, 0, 0]), "B": np.array([1, 0, 1, 0, 1, 0, 0])}
    cbp = {"A": BASE, "B": BASE}
    s1 = portfolio_cost_stress(frames, dec, cbp, 1.5, 2.0)
    s2 = portfolio_cost_stress(frames, dec, cbp, 1.5, 2.0)
    assert s1 == s2                    # bit-identical across runs
    assert isinstance(s1["combined"], float)


def test_no_post_hoc_cost_or_pnl_arithmetic_in_stress_layer():
    banned = ("cumprod", "mid_o", "ask_o", "bid_o", "swap_frac", "spread_frac",
              "Trade", "simulate", "1.0 +", "* r")
    for fn in (pf._scale_costs, pf.portfolio_cost_stress):
        src = inspect.getsource(fn)
        for term in banned:
            assert term not in src, f"{fn.__name__} must delegate, found {term!r}"
