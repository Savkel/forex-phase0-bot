"""Task 8: portfolio exposure-adjusted alpha + costed passive baskets.

The benchmark layer is a THIN weighting shell over the tested engine: every
passive decision (always-long hold, gross-matched-at-G, net-matched diagnostic)
runs through `run_sleeve` -> `simulate` and is 1/N combined by `aggregate_portfolio`.
No direct price-return math, no re-derivation of fills / spread / swap / PnL here.
"""
import inspect
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from bot.forex.cost_model import CostModel
from bot.forex.metrics import max_drawdown
from bot.forex.evaluate import exposure_adjusted_alpha
from bot.forex.portfolio import (run_sleeve, aggregate_portfolio,
                                 portfolio_hold_basket, gross_matched_basket,
                                 net_matched_basket, portfolio_alpha_under)

NO_COST = CostModel(pip=0.0001, long_swap_pips=0.0, short_swap_pips=0.0, rollover_hour_utc=21)


def _bars(mids, spread=0.0, open_times=None):
    """Bars with mid == bid == ask by default (zero empirical spread). `spread`
    opens a symmetric bid/ask gap; `open_times` overrides the H4 grid (for the
    Wednesday-rollover swap test)."""
    n = len(mids)
    half = spread / 2.0
    ot = np.arange(n) * 14400000 if open_times is None else np.asarray(open_times, dtype="int64")
    m = list(mids)
    return pd.DataFrame({
        "open_time": ot, "time": [f"t{i}" for i in range(n)],
        "bid_o": [x - half for x in m], "ask_o": [x + half for x in m],
        "bid_c": [x - half for x in m], "ask_c": [x + half for x in m],
        "bid_h": [x - half for x in m], "ask_h": [x + half for x in m],
        "bid_l": [x - half for x in m], "ask_l": [x + half for x in m],
        "mid_o": m, "mid_c": m, "mid_h": m, "mid_l": m,
        "volume": [1] * n, "complete": [True] * n})


def _rising(n, step=0.01):
    return list(1.0 + step * np.arange(n))


# ---- Plan tests (verbatim from the approved Task 8 spec) ------------------------------

def test_hold_basket_return_is_positive_on_rising_pairs():
    frames = {"A": _bars(_rising(6)), "B": _bars(_rising(6))}
    cbp = {"A": NO_COST, "B": NO_COST}
    hold = portfolio_hold_basket(frames, cbp)
    assert hold["portfolio_return"] > 0.0


def test_alpha_zero_for_a_flat_book():
    frames = {"A": _bars(_rising(6)), "B": _bars(_rising(6))}
    cbp = {"A": NO_COST, "B": NO_COST}
    dec = {"A": np.zeros(6, int), "B": np.zeros(6, int)}     # never trade
    alpha, bot, hold = portfolio_alpha_under(frames, dec, cbp)
    assert abs(alpha) < 1e-9                                 # flat -> ~0 alpha
    assert bot["avg_net_exposure"] == 0.0


def test_gross_matched_basket_measures_G():
    frames = {"A": _bars(_rising(40)), "B": _bars(_rising(40))}
    cbp = {"A": NO_COST, "B": NO_COST}
    G = 0.3
    gm = gross_matched_basket(frames, cbp, G)
    # always-long at f=G, 1/N weighted -> avg gross ~ G*(T-1)/T (shared first-flat convention)
    assert abs(gm["avg_gross_exposure"] - G) < 0.02


def test_gross_matched_scales_linearly_with_G():
    frames = {"A": _bars(_rising(40))}
    cbp = {"A": NO_COST}
    g1 = gross_matched_basket(frames, cbp, 0.2)["avg_gross_exposure"]
    g2 = gross_matched_basket(frames, cbp, 0.4)["avg_gross_exposure"]
    assert abs(g2 - 2.0 * g1) < 1e-6


def test_gross_matched_zero_G_is_zero_notional_and_costless():
    # a genuinely zero-gross bot (never trades) -> measured G == 0. Feeding that G
    # back must produce a ZERO-NOTIONAL, COSTLESS benchmark (f=0.0, not the old 1.0
    # fallback): zero return, zero exposure, and -- despite a real spread+swap being
    # configured -- no cost leaks through (f=0 zeroes every cost term in the engine).
    swap = CostModel(pip=0.0001, long_swap_pips=10.0, short_swap_pips=10.0, rollover_hour_utc=21)
    frames = {"A": _bars(_rising(12), spread=0.002), "B": _bars(_rising(12), spread=0.002)}
    cbp = {"A": swap, "B": swap}
    dec = {"A": np.zeros(12, int), "B": np.zeros(12, int)}   # zero-gross bot
    _, bot, _ = portfolio_alpha_under(frames, dec, cbp)
    G = bot["avg_gross_exposure"]
    assert G == 0.0                                          # measured, not assumed
    gm = gross_matched_basket(frames, cbp, G)               # G == 0.0 -> f = 0.0
    assert gm["avg_gross_exposure"] == 0.0                  # zero exposure
    assert gm["avg_net_exposure"] == 0.0
    assert gm["portfolio_return"] == 0.0                    # zero return AND no cost leaked
    assert np.all(gm["interval_return"] == 0.0)


def test_small_positive_G_passed_unchanged_not_replaced_by_one():
    # a small MEASURED G must reach the engine UNCHANGED -- emphatically not inflated
    # to the old 1.0 degenerate fallback.
    frames = {"A": _bars(_rising(40)), "B": _bars(_rising(40))}
    cbp = {"A": NO_COST, "B": NO_COST}
    G = 0.05
    gm = gross_matched_basket(frames, cbp, G)
    assert abs(gm["avg_gross_exposure"] - G) < 0.01        # realized gross tracks the small G*(T-1)/T
    assert gm["avg_gross_exposure"] < 0.1                  # NOT the ~1.0 hardcode
    manual = aggregate_portfolio([                          # hand-rebuild at f=G matches exactly
        run_sleeve(frames["A"], np.ones(40, int), NO_COST, G),
        run_sleeve(frames["B"], np.ones(40, int), NO_COST, G)])
    assert np.allclose(gm["equity"], manual["equity"])


def test_zero_net_diagnostic_is_zero_notional():
    # zero measured net -> deterministic ZERO-NOTIONAL / flat diagnostic (f=0.0, no
    # 1.0 fallback): no exposure, no return, no cost even with spread+swap configured.
    swap = CostModel(pip=0.0001, long_swap_pips=10.0, short_swap_pips=10.0, rollover_hour_utc=21)
    frames = {"A": _bars(_rising(20), spread=0.002), "B": _bars(_rising(20), spread=0.002)}
    cbp = {"A": swap, "B": swap}
    nm0 = net_matched_basket(frames, cbp, 0.0)
    assert nm0["avg_net_exposure"] == 0.0
    assert nm0["avg_gross_exposure"] == 0.0
    assert nm0["portfolio_return"] == 0.0
    nm0b = net_matched_basket(frames, cbp, 0.0)             # deterministic
    assert nm0b["portfolio_return"] == nm0["portfolio_return"]


def test_gross_matched_is_primary_net_matched_is_diagnostic():
    # the primary/gate benchmark is gross-matched; net-matched stays NON-GATING.
    # The contract is encoded in the docstrings and in the baskets being distinct.
    import bot.forex.portfolio as pf
    gm_doc = pf.gross_matched_basket.__doc__.lower()
    nm_doc = pf.net_matched_basket.__doc__.lower()
    assert "gate" in gm_doc                                 # gross-matched = the (drawdown) gate reference
    assert "diagnostic" in nm_doc and "not a gate" in nm_doc  # net-matched = non-gating diagnostic
    frames = {"A": _bars(_rising(40))}
    cbp = {"A": NO_COST}
    gm = gross_matched_basket(frames, cbp, 0.4)            # holds LONG at G
    nm = net_matched_basket(frames, cbp, -0.4)            # honors sign(net) at |net|
    assert gm["avg_net_exposure"] > 0.0 and nm["avg_net_exposure"] < 0.0   # genuinely different baskets


def test_alpha_matches_manual_formula():
    frames = {"A": _bars(_rising(30))}
    cbp = {"A": NO_COST}
    dec = {"A": np.ones(30, int)}                           # always long
    alpha, bot, hold = portfolio_alpha_under(frames, dec, cbp)
    manual = bot["portfolio_return"] - bot["avg_net_exposure"] * hold["portfolio_return"]
    assert abs(alpha - manual) < 1e-12


# ---- Additive hardening (each maps to a "tests must prove" bullet) --------------------

def test_metrics_and_alpha_reuse_existing_helpers():
    # a peaked path so max_drawdown is genuinely negative (not a trivial 0 match)
    mids = [1.00, 1.02, 1.05, 1.03, 1.00, 0.98, 0.97]
    frames = {"A": _bars(mids)}
    cbp = {"A": NO_COST}
    dec = {"A": np.ones(len(mids), int)}
    alpha, bot, hold = portfolio_alpha_under(frames, dec, cbp)
    assert bot["max_drawdown"] < 0.0                                    # real drawdown
    # portfolio max_drawdown is the Phase-0 metrics helper on the aggregated equity
    assert abs(bot["max_drawdown"] - max_drawdown(bot["equity"])) < 1e-12
    # alpha is exactly the reused exposure_adjusted_alpha helper, not a re-derivation
    assert abs(alpha - exposure_adjusted_alpha(
        bot["portfolio_return"], bot["avg_net_exposure"], hold["portfolio_return"])) < 1e-12


def test_G_is_measured_from_bot_not_hardcoded():
    # a partially-invested book -> measured gross strictly between 0 and 1 (not the 1.0 hardcode)
    dec_arr = np.tile([1, 1, 0, 0], 10)                                 # length 40, ~half invested
    frames = {"A": _bars(_rising(40)), "B": _bars(_rising(40))}
    cbp = {"A": NO_COST, "B": NO_COST}
    dec = {"A": dec_arr, "B": dec_arr}
    alpha, bot, hold = portfolio_alpha_under(frames, dec, cbp)
    G = bot["avg_gross_exposure"]
    assert 0.0 < G < 0.9                                                # a real measured gross
    gm = gross_matched_basket(frames, cbp, G)                          # feed the MEASURED G back
    assert abs(gm["avg_gross_exposure"] - G) < 0.03                    # basket realizes requested G
    assert gm["avg_gross_exposure"] < 0.9                              # not the hardcoded 1.0 basket


def test_benchmark_window_matches_bot():
    frames = {"A": _bars(_rising(20)), "B": _bars(_rising(20))}
    cbp = {"A": NO_COST, "B": NO_COST}
    dec = {"A": np.ones(20, int), "B": np.ones(20, int)}
    _, bot, hold = portfolio_alpha_under(frames, dec, cbp)
    # identical aggregated timeline for bot, hold basket, and gross-matched basket
    assert np.array_equal(bot["timeline"], hold["timeline"])
    gm = gross_matched_basket(frames, cbp, 0.5)
    assert np.array_equal(gm["timeline"], bot["timeline"])
    assert len(bot["timeline"]) == 19                                   # 20 bars -> 19 intervals


def test_hold_basket_applies_costs_through_engine():
    # a bid/ask gap must drag the costed benchmark vs the zero-spread bars -> proves it
    # runs through the engine (spread charged), NOT a direct mid-price return calc.
    mids = _rising(8)
    r_free = portfolio_hold_basket({"A": _bars(mids)}, {"A": NO_COST})["portfolio_return"]
    r_wide = portfolio_hold_basket({"A": _bars(mids, spread=0.002)}, {"A": NO_COST})["portfolio_return"]
    assert r_wide < r_free


def test_f_equals_G_passed_to_engine_and_no_double_scaling():
    frames = {"A": _bars(_rising(20)), "B": _bars(_rising(20))}
    cbp = {"A": NO_COST, "B": NO_COST}
    G = 0.3
    gm = gross_matched_basket(frames, cbp, G)
    # hand-rebuild the basket: each pair always-long at f=G, 1/N aggregated
    manual = aggregate_portfolio([
        run_sleeve(frames["A"], np.ones(20, int), NO_COST, G),
        run_sleeve(frames["B"], np.ones(20, int), NO_COST, G)])
    assert np.allclose(gm["equity"], manual["equity"])                 # f=G actually reached the engine
    assert np.allclose(gm["interval_return"], manual["interval_return"])
    # no double scaling: interval returns are LINEAR in G (applied once), not quadratic (G**2)
    gm2 = gross_matched_basket(frames, cbp, 2 * G)
    assert np.allclose(gm2["interval_return"], 2.0 * gm["interval_return"])
    assert not np.allclose(gm2["interval_return"], 4.0 * gm["interval_return"])


def test_swap_fix_94ded17_inherited_through_basket():
    base = int(datetime(2024, 1, 3, 16, 0, tzinfo=timezone.utc).timestamp() * 1000)  # Wed 16:00 UTC
    ot = base + np.arange(9) * 14400000
    bars = _bars([1.0] * 9, open_times=ot)                             # flat mids, zero spread
    cost = CostModel(pip=0.0001, long_swap_pips=10.0, short_swap_pips=10.0, rollover_hour_utc=21)
    frames = {"A": bars}
    cbp = {"A": cost}
    Rf = gross_matched_basket(frames, cbp, 1.0)["interval_return"]
    Rh = gross_matched_basket(frames, cbp, 0.5)["interval_return"]
    # flat mids + zero spread -> the ONLY drag is the f-scaled swap. per_night = 10*0.0001/1 = 0.001.
    # interval 1 crosses Wed 21:00 (x3 -> 0.003); interval 7 crosses Thu 21:00 (x1 -> 0.001).
    assert abs(Rf[1] - (-0.003)) < 1e-12 and abs(Rf[7] - (-0.001)) < 1e-12   # Wednesday x3 preserved
    assert abs(Rf[1] / Rf[7] - 3.0) < 1e-9
    # 94ded17: the funding drag scales with f -> exactly half at f=0.5 (pre-fix it was f-independent)
    assert np.allclose(Rh, 0.5 * Rf)
    assert abs(Rh[1] - (-0.0015)) < 1e-12


def test_zero_gross_and_invalid_inputs_are_deterministic():
    frames = {"A": _bars(_rising(10))}
    cbp = {"A": NO_COST}
    a = gross_matched_basket(frames, cbp, 0.0)["avg_gross_exposure"]
    b = gross_matched_basket(frames, cbp, 0.0)["avg_gross_exposure"]
    assert a == b == 0.0                                               # zero-gross -> f=0.0 (no 1.0 fallback)
    with pytest.raises(ValueError):                                    # empty universe -> deterministic raise
        gross_matched_basket({}, {}, 0.3)
    with pytest.raises(ValueError):
        portfolio_hold_basket({}, {})
    for bad in (1.5, -0.1, float("nan"), float("inf")):               # G must be finite in [0, 1]
        with pytest.raises(ValueError):
            gross_matched_basket(frames, cbp, bad)


def test_benchmark_layer_has_no_execution_reimplementation():
    import bot.forex.portfolio as pf
    banned = ("spread", "swap", "rollover", "ask_o", "bid_o", "mid_o", "Trade", "simulate", "cumprod")
    for fn in (pf._always_long_sleeve, pf.portfolio_hold_basket, pf.gross_matched_basket,
               pf.net_matched_basket, pf.portfolio_alpha_under):
        src = inspect.getsource(fn)
        for term in banned:
            assert term not in src, f"{fn.__name__} must delegate to run_sleeve, found {term!r}"


def test_net_matched_basket_is_diagnostic_and_measures_net():
    frames = {"A": _bars(_rising(40)), "B": _bars(_rising(40))}
    cbp = {"A": NO_COST, "B": NO_COST}
    nm = net_matched_basket(frames, cbp, 0.3)                          # long side
    assert abs(nm["avg_net_exposure"] - 0.3) < 0.02
    assert abs(nm["avg_gross_exposure"] - 0.3) < 0.02
    nm_s = net_matched_basket(frames, cbp, -0.3)                       # short side
    assert abs(nm_s["avg_net_exposure"] + 0.3) < 0.02                  # net is negative, magnitude ~0.3
    assert abs(nm_s["avg_gross_exposure"] - 0.3) < 0.02               # gross stays positive ~0.3
    nm0 = net_matched_basket(frames, cbp, 0.0)                         # degenerate -> f=0.0 zero-notional
    assert nm0["avg_gross_exposure"] == 0.0                            # no 1.0 fallback
