import numpy as np
import pandas as pd
from bot.forex.cost_model import CostModel
from bot.forex.backtest import simulate
from bot.forex.evaluate import exposure_adjusted_alpha, hold_long
from bot.forex.nullbench import (circular_shift_decisions, block_shuffle_decisions,
                                 null_distribution, percentile_rank, p_value, _draw_offset)

NO_COST = CostModel(0.0001, 0, 0, 21)        # bid==ask in _bars -> truly free


def _bars(mids):
    n = len(mids)
    return pd.DataFrame({
        "open_time": np.arange(n) * 14400000, "time": [f"t{i}" for i in range(n)],
        "bid_o": mids, "ask_o": mids, "bid_c": mids, "ask_c": mids,
        "bid_h": mids, "ask_h": mids, "bid_l": mids, "ask_l": mids,
        "mid_o": mids, "mid_c": mids, "mid_h": mids, "mid_l": mids,
        "volume": [1]*n, "complete": [True]*n})


def _bars_spread(mids, spread):
    n = len(mids); half = spread / 2.0
    return pd.DataFrame({
        "open_time": np.arange(n) * 14400000, "time": [f"t{i}" for i in range(n)],
        "bid_o": [m - half for m in mids], "ask_o": [m + half for m in mids],
        "bid_c": [m - half for m in mids], "ask_c": [m + half for m in mids],
        "bid_h": [m - half for m in mids], "ask_h": [m + half for m in mids],
        "bid_l": [m - half for m in mids], "ask_l": [m + half for m in mids],
        "mid_o": mids, "mid_c": mids, "mid_h": mids, "mid_l": mids,
        "volume": [1]*n, "complete": [True]*n})


# --- shuffles preserve the decision alphabet & multiset (exposure structure) ---

def test_circular_shift_preserves_multiset_and_values():
    d = np.array([1, 1, -1, 0, 1, 0, -1])
    s = circular_shift_decisions(d, 3)
    assert sorted(s.tolist()) == sorted(d.tolist())          # multiset preserved
    assert set(np.unique(s)).issubset({-1, 0, 1})            # alphabet preserved


def test_circular_shift_identity_offset_returns_original():
    d = np.array([1, 0, -1, 1])
    assert np.array_equal(circular_shift_decisions(d, 0), d)  # documents identity at offset 0 (excluded by _draw_offset)


def test_block_shuffle_preserves_multiset_and_can_change_timing():
    d = np.array([1, 1, 1, 1, -1, -1, -1, -1, 0, 0, 0, 0])    # clustered blocks
    changed = False
    for seed in range(10):
        out = block_shuffle_decisions(d, 4, np.random.default_rng(seed))
        assert sorted(out.tolist()) == sorted(d.tolist())     # exposure structure preserved
        assert set(np.unique(out)).issubset({-1, 0, 1})
        if not np.array_equal(out, d):
            changed = True
    assert changed                                            # timing is randomized across seeds


# --- rule 1: circular shift never reproduces the original timing (no identity sample) ---

def test_draw_offset_excludes_identity_and_stays_in_range():
    rng = np.random.default_rng(0)
    n, guard = 50, 2
    offs = [_draw_offset(n, guard, rng) for _ in range(2000)]
    assert all(1 <= o <= n - 1 for o in offs)                 # never 0 and never n (both == identity by wrap)
    assert 0 not in offs


# --- rule 2: deterministic with a seed ---

def test_deterministic_with_seed():
    bars = _bars(list(np.linspace(1.0, 1.4, 60)))
    d = (np.arange(60) % 3 - 1).astype(int)                   # values in {-1,0,1}
    a = null_distribution(bars, d, NO_COST, 1.0, 100.0, runs=50, method="circular_shift", seed=123, guard_frac=0.05)
    b = null_distribution(bars, d, NO_COST, 1.0, 100.0, runs=50, method="circular_shift", seed=123, guard_frac=0.05)
    assert a == b                                             # same seed -> identical report
    c = null_distribution(bars, d, NO_COST, 1.0, 100.0, runs=50, method="circular_shift", seed=999, guard_frac=0.05)
    assert abs(a["real_alpha"] - c["real_alpha"]) < 1e-12     # real_alpha is seed-independent


# --- rule: every null sample reruns simulate (no shortcut PnL path) ---

def test_circular_null_reruns_simulate(monkeypatch):
    import bot.forex.nullbench as nb
    calls = {"n": 0}
    real_sim = nb.simulate
    def counting_sim(*a, **k):
        calls["n"] += 1
        return real_sim(*a, **k)
    monkeypatch.setattr(nb, "simulate", counting_sim)
    bars = _bars(list(np.linspace(1.0, 1.4, 60)))
    d = np.ones(60, dtype=int)
    nb.null_distribution(bars, d, NO_COST, 1.0, 100.0, runs=25, method="circular_shift", seed=1, guard_frac=0.05)
    # nullbench.simulate is called once for real_alpha + once per run (hold_long uses evaluate's simulate)
    assert calls["n"] == 25 + 1


def test_block_shuffle_method_reruns_simulate(monkeypatch):
    import bot.forex.nullbench as nb
    calls = {"n": 0}
    real_sim = nb.simulate
    monkeypatch.setattr(nb, "simulate", lambda *a, **k: (calls.__setitem__("n", calls["n"] + 1), real_sim(*a, **k))[1])
    bars = _bars(list(np.linspace(1.0, 1.4, 60)))
    d = np.array(([1]*10 + [-1]*10 + [0]*10) * 2, dtype=int)
    res = nb.null_distribution(bars, d, NO_COST, 1.0, 100.0, runs=15, method="block_shuffle", seed=4, block_len=10, guard_frac=0.05)
    assert calls["n"] == 15 + 1
    assert res["method"] == "block_shuffle" and res["block_len"] == 10


def test_real_alpha_matches_engine_no_shortcut():
    # real_alpha must equal the engine's own output; a position*return shortcut would diverge
    bars = _bars(list(np.linspace(1.0, 1.4, 60)))
    d = (np.arange(60) % 3 - 1).astype(int)
    res = null_distribution(bars, d, NO_COST, 1.0, 100.0, runs=10, method="circular_shift", seed=3, guard_frac=0.05)
    s = simulate(bars, d, NO_COST, 1.0, 100.0)["summary"]
    hr = hold_long(bars, NO_COST, 100.0)["total_return"]
    expected = round(exposure_adjusted_alpha(s["total_return"], s["avg_net_exposure"], hr), 6)
    assert abs(res["real_alpha"] - expected) < 1e-9


# --- rule 4: null samples honor Task 7 engine conventions ---

def test_constant_decisions_make_every_null_identical_to_real():
    # circular-shifting a constant array yields the SAME array; only a true engine replay
    # (not a shortcut) makes every null alpha == real alpha.
    bars = _bars(list(np.linspace(1.0, 1.4, 60)))
    d = np.ones(60, dtype=int)
    res = null_distribution(bars, d, NO_COST, 1.0, 100.0, runs=50, method="circular_shift", seed=7, guard_frac=0.05)
    assert res["percentile_rank"] == 0.0                      # no null strictly below real
    assert abs(res["median"] - res["real_alpha"]) < 1e-9


def test_null_sample_honors_first_interval_flat_via_engine():
    bars = _bars([1.0, 2.0, 2.0, 2.0])                        # the only move is the FIRST interval
    shifted = circular_shift_decisions(np.array([1, 1, 1, 1]), 1)   # still all ones
    s = simulate(bars, shifted, NO_COST, 1.0, 100.0)["summary"]
    assert s["total_return"] == 0.0                           # first interval flat -> 1->2 move never earned


def test_null_sample_honors_final_forced_close_via_engine():
    bars = _bars_spread([1.0, 1.0, 1.0, 1.0], 0.0002)
    shifted = circular_shift_decisions(np.array([1, 1, 1, 1]), 2)   # still all ones
    cost = CostModel(0.0001, 0, 0, 21)
    half = 0.0001
    s = simulate(bars, shifted, cost, 1.0, 100.0)["summary"]
    assert abs(s["total_return"] - ((1 - half) ** 2 - 1.0)) < 1e-12  # entry + forced final close
    assert s["trade_count"] == 1


# --- rule: original decisions never mutated ---

def test_original_decisions_not_mutated():
    bars = _bars(list(np.linspace(1.0, 1.4, 60)))
    d = (np.arange(60) % 3 - 1).astype(int)
    d_before = d.copy()
    null_distribution(bars, d, NO_COST, 1.0, 100.0, runs=20, method="circular_shift", seed=2, guard_frac=0.05)
    assert np.array_equal(d, d_before)


# --- rule 5: percentile / p-value have a clear, tested direction ---

def test_percentile_and_pvalue_direction():
    dist = [0.0, 0.1, 0.2, 0.3, 0.4]
    # higher alpha is better -> higher percentile rank, lower (more significant) p-value
    assert percentile_rank(0.5, dist) == 100.0                # beats all
    assert percentile_rank(-0.1, dist) == 0.0                 # beats none
    assert abs(p_value(0.5, dist) - 1.0 / (len(dist) + 1)) < 1e-12      # most significant
    assert abs(p_value(-0.1, dist) - 1.0) < 1e-12             # least significant


def test_null_distribution_runs_and_reports():
    bars = _bars(list(np.linspace(1.0, 1.4, 80)))
    d = np.ones(80, dtype=int)
    res = null_distribution(bars, d, NO_COST, 1.0, 100.0, runs=200, method="circular_shift", seed=1, guard_frac=0.05)
    assert res["runs"] == 200
    assert 0.0 <= res["percentile_rank"] <= 100.0
    assert {"median", "p75", "p90", "p95", "real_alpha", "p_value"}.issubset(res)
