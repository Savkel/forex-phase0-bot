"""Task 10: portfolio null timing benchmark.

Primary null = per-pair INDEPENDENT circular shift of each pair's decision array
(deterministic seeded RNG, identity excluded by construction), re-run through
run_sleeve -> simulate and combined by aggregate_portfolio, scored with the
reused evaluate.exposure_adjusted_alpha vs the (constant) hold basket. Diagnostics
(non-gating): common shift across all pairs, and block-shuffle with a configured
block_len. Reuses the nullbench primitives; no return shifting, no post-hoc PnL/cost.
"""
import inspect
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from bot.forex.cost_model import CostModel
from bot.forex.nullbench import percentile_rank, p_value
from bot.forex.portfolio import (portfolio_null, portfolio_alpha_under,
                                 _shift_decisions, _draw_offset)
import bot.forex.portfolio as pf

NO_COST = CostModel(pip=0.0001, long_swap_pips=0.0, short_swap_pips=0.0, rollover_hour_utc=21)


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


def _osc(n):
    return list(1.0 + 0.01 * np.sin(np.arange(n)))


def _frames_dec(n=60):
    frames = {"A": _bars(_osc(n)), "B": _bars(_osc(n))}
    rng = np.random.default_rng(0)
    dec = {"A": rng.integers(-1, 2, n), "B": rng.integers(-1, 2, n)}
    return frames, dec


# ---- Plan tests (locked Task 10 spec) -------------------------------------------------

def test_null_is_deterministic_given_seed():
    frames, dec = _frames_dec()
    cbp = {"A": NO_COST, "B": NO_COST}
    a = portfolio_null(frames, dec, cbp, runs=50, seed=7)
    b = portfolio_null(frames, dec, cbp, runs=50, seed=7)
    assert a == b


def test_null_real_alpha_matches_direct_computation():
    frames, dec = _frames_dec()
    cbp = {"A": NO_COST, "B": NO_COST}
    nb = portfolio_null(frames, dec, cbp, runs=20, seed=1)
    direct, _, _ = portfolio_alpha_under(frames, dec, cbp)
    assert abs(nb["real_alpha"] - round(direct, 6)) < 1e-9


def test_null_reports_percentile_and_pvalue_in_range():
    frames, dec = _frames_dec()
    cbp = {"A": NO_COST, "B": NO_COST}
    nb = portfolio_null(frames, dec, cbp, runs=200, seed=3)
    assert 0.0 <= nb["percentile_rank"] <= 100.0
    assert 0.0 < nb["p_value"] <= 1.0
    assert nb["runs"] == 200


def test_common_shift_and_block_shuffle_methods_run():
    frames, dec = _frames_dec()
    cbp = {"A": NO_COST, "B": NO_COST}
    cs = portfolio_null(frames, dec, cbp, runs=30, seed=2, method="common_shift")
    bs = portfolio_null(frames, dec, cbp, runs=30, seed=2, method="block_shuffle", block_len=5)
    assert cs["method"] == "common_shift" and bs["method"] == "block_shuffle"


# ---- Additive hardening (each maps to a "tests must cover" bullet) ---------------------

def test_independent_shifts_differ_across_pairs():
    # identical decisions for A and B, but PRIMARY circular shift draws a SEPARATE
    # offset per pair -> the shifted arrays differ on (nearly) every run.
    n = 40
    arr = np.array([1, 0, -1, 0] * (n // 4))
    dec = {"A": arr.copy(), "B": arr.copy()}
    rngs = {"A": np.random.default_rng(11), "B": np.random.default_rng(22)}
    cr = np.random.default_rng(99)
    diffs = 0
    for _ in range(10):
        sh = _shift_decisions(dec, "circular_shift", rngs, cr, 0.02, None)
        if not np.array_equal(sh["A"], sh["B"]):
            diffs += 1
    assert diffs >= 8            # per-pair independence (offsets are drawn separately)


def test_common_shift_applies_same_offset_to_all_pairs():
    # contrast with the primary: the COMMON-shift diagnostic uses ONE offset for all
    # pairs -> identical decisions map to identical shifts.
    n = 40
    arr = np.array([1, 0, -1, 0] * (n // 4))
    dec = {"A": arr.copy(), "B": arr.copy()}
    sh = _shift_decisions(dec, "common_shift", {"A": None, "B": None},
                          np.random.default_rng(5), 0.02, None)
    assert np.array_equal(sh["A"], sh["B"])


def test_draw_offset_excludes_identity():
    rng = np.random.default_rng(0)
    for n in (5, 10, 40, 51):
        guard = max(1, int(0.02 * n))
        for _ in range(500):
            off = _draw_offset(n, guard, rng)
            assert 1 <= off <= n - 1        # never 0 and never n (both np.roll identities)


def test_different_seeds_give_different_distributions():
    frames, dec = _frames_dec()
    cbp = {"A": NO_COST, "B": NO_COST}
    a = portfolio_null(frames, dec, cbp, runs=80, seed=1)
    b = portfolio_null(frames, dec, cbp, runs=80, seed=2)
    assert a["real_alpha"] == b["real_alpha"]    # observed alpha is seed-independent
    assert a != b                                 # but the shuffled null distribution differs


def test_null_inherits_engine_costs_and_wednesday_swap():
    # the null re-runs each shifted pair through the ENGINE, so spread and swap
    # (incl. Wednesday x3, f-scaled per 94ded17) drag BOTH the observed alpha and the
    # whole null distribution -- proving no cost-free / return-shifting shortcut.
    n = 24
    mids = _osc(n)
    dec = {"A": np.array([1, 1, 0, -1, -1, 0] * (n // 6)),
           "B": np.array([1, 1, 0, -1, -1, 0] * (n // 6))}
    free = portfolio_null({"A": _bars(mids), "B": _bars(mids)}, dec,
                          {"A": NO_COST, "B": NO_COST}, runs=40, seed=5)
    spr = portfolio_null({"A": _bars(mids, spread=0.003), "B": _bars(mids, spread=0.003)}, dec,
                         {"A": NO_COST, "B": NO_COST}, runs=40, seed=5)
    assert spr["real_alpha"] != free["real_alpha"]     # spread bites the observed alpha
    assert spr["median"] != free["median"]             # ...and every null sample (engine-run)
    b0 = int(datetime(2024, 1, 3, 16, 0, tzinfo=timezone.utc).timestamp() * 1000)  # Wed 16:00
    ot = b0 + np.arange(n) * 14400000
    swap = CostModel(pip=0.0001, long_swap_pips=10.0, short_swap_pips=10.0, rollover_hour_utc=21)
    wed = portfolio_null({"A": _bars(mids, open_times=ot), "B": _bars(mids, open_times=ot)}, dec,
                         {"A": swap, "B": swap}, runs=40, seed=5)
    assert wed["median"] != free["median"]             # swap (Wednesday x3) inherited through the null


def test_block_shuffle_forwards_configured_block_len():
    # block_len >= n -> a single block -> identity permutation -> every null sample == real
    # (a hardcoded default of 10 would split n=40 into 4 blocks and NOT be degenerate).
    frames, dec = _frames_dec(40)
    cbp = {"A": NO_COST, "B": NO_COST}
    big = portfolio_null(frames, dec, cbp, runs=10, seed=1, method="block_shuffle", block_len=1000)
    assert big["p_value"] == 1.0 and big["percentile_rank"] == 0.0   # null degenerate to the real value
    small = portfolio_null(frames, dec, cbp, runs=30, seed=1, method="block_shuffle", block_len=2)
    assert big != small                                              # the configured block_len is honored


def test_inputs_are_not_mutated():
    frames, dec = _frames_dec(40)
    cbp = {"A": NO_COST, "B": NO_COST}
    dec_a0, dec_b0 = dec["A"].copy(), dec["B"].copy()
    mids_a0 = frames["A"]["mid_o"].to_numpy().copy()
    _ = portfolio_null(frames, dec, cbp, runs=25, seed=4)
    _ = portfolio_null(frames, dec, cbp, runs=25, seed=4, method="block_shuffle", block_len=3)
    assert np.array_equal(dec["A"], dec_a0) and np.array_equal(dec["B"], dec_b0)   # decisions untouched
    assert np.array_equal(frames["A"]["mid_o"].to_numpy(), mids_a0)                # bars untouched


def test_no_gate_runner_report_or_oanda_code():
    banned = ("phase1_acceptance", "run_phase1", "oanda", "fetch_candles",
              "verdict", "report_phase1", "acceptance_phase1", "to_markdown")
    for fn in (pf._draw_offset, pf._shift_decisions, pf.portfolio_null):
        src = inspect.getsource(fn)
        for term in banned:
            assert term not in src, f"{fn.__name__} must not reach into {term!r}"
