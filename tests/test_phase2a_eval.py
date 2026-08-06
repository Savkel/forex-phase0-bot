"""Phase 2A evaluation framework: null, benchmark, gates, selection.

Everything here pins the LOCKED spec. The null permutes a day-level object that is either
`NO_TRADE` or `(entry offset, direction)` — no-trade days participate, otherwise the null
would quietly compare a fully-invested strategy against a fully-invested shadow and lose
the timing question it exists to ask. Permutation is within same-ISO-weekday days,
independent per pair, and only a globally unchanged mapping is redrawn. On the target day
entry and stop are rebuilt from that day's own prices; no source stop distance travels.

The benchmark is candidate-specific and session-matched: always long, same eligible
pair-days, same schedule, same bid/ask, slippage and no-overnight rule. If exact
volatility matching needs k>10, or either volatility is zero, the gate is UNDEFINED and
FAILS — it is never capped and called matched.
"""
import numpy as np
import pandas as pd
import pytest

from bot.forex.market_grid import expected_grid
from bot.forex.phase2a import SPECS, run_candidate, session_bounds
from bot.forex.phase2a_eval import (
    NULL_RUNS,
    NULL_SEED,
    ConfirmationLocked,
    evaluate_candidate,
    measure_candidate,
    open_confirmation,
    permute_objects,
    run_null,
    select_candidate,
    session_matched_benchmark,
    stress_frames,
    volatility_scale,
)

M15 = 900_000
SPEC = SPECS["c2_london_orb"]


def _ms(s):
    return int(pd.Timestamp(s, tz="UTC").value // 10 ** 6)


SPAN = (_ms("2026-06-07T00:00:00"), _ms("2026-06-27T00:00:00"))     # three quiet weeks


def _frame(spread=0.0002, mid=1.0):
    ts = [int(t) for t in expected_grid(*SPAN)]
    h = spread / 2
    return pd.DataFrame({
        "open_time": ts,
        "bid_o": [mid - h] * len(ts), "bid_h": [mid - h] * len(ts),
        "bid_l": [mid - h] * len(ts), "bid_c": [mid - h] * len(ts),
        "ask_o": [mid + h] * len(ts), "ask_h": [mid + h] * len(ts),
        "ask_l": [mid + h] * len(ts), "ask_c": [mid + h] * len(ts),
        "volume": [100] * len(ts), "complete": [True] * len(ts),
    })


def _set(df, ms, *, o, h, l, c, spread=0.0002):
    half = spread / 2
    i = df.index[df["open_time"] == ms]
    for name, v in (("o", o), ("h", h), ("l", l), ("c", c)):
        df.loc[i, f"bid_{name}"] = v - half
        df.loc[i, f"ask_{name}"] = v + half
    return df


def _breakouts(days, *, px=1.02):
    """Flat weeks with a breakout on the named days, and a DAY-SPECIFIC exit price.

    The distinct exit prices matter: with a perfectly flat frame every permutation would
    yield the same return and a broken null would look deterministic for the wrong reason.
    """
    df = _frame()
    for k, d in enumerate(pd.bdate_range("2026-06-08", "2026-06-26")):
        b = session_bounds(SPEC, d)
        lvl = 1.0 + 0.001 * (k + 1)
        # A range with real width, so the stop is not sitting on top of the entry price.
        _set(df, b["range_start_ms"], o=1.0, h=1.005, l=0.995, c=1.0)
        _set(df, b["exit_ms"], o=lvl, h=lvl, l=lvl, c=lvl)
    for d in days:
        b = session_bounds(SPEC, pd.Timestamp(d))
        _set(df, b["entry_start_ms"], o=1.0, h=max(px, 1.0), l=min(px, 1.0), c=px)
    return df


EXP = expected_grid(*SPAN)


# --- permutation --------------------------------------------------------------------

def _objects():
    # Two pairs, six days: Mondays and Tuesdays, some trading and some not.
    days = [pd.Timestamp(d) for d in ("2026-06-08", "2026-06-15", "2026-06-22",
                                      "2026-06-09", "2026-06-16", "2026-06-23")]
    return {
        "EUR_USD": {days[0]: (0, 1), days[1]: None, days[2]: (2, -1),
                    days[3]: None, days[4]: (1, 1), days[5]: None},
        "GBP_USD": {days[0]: None, days[1]: (3, -1), days[2]: None,
                    days[3]: (1, 1), days[4]: None, days[5]: (0, -1)},
    }


def test_no_trade_days_take_part_in_the_permutation():
    obj = _objects()
    out = permute_objects(obj, np.random.default_rng(1))
    for pair in obj:
        assert sorted(map(str, out[pair])) == sorted(map(str, obj[pair]))
        # the multiset of objects is preserved, including the NO_TRADE entries
        assert sum(1 for v in out[pair].values() if v is None) == \
            sum(1 for v in obj[pair].values() if v is None)
    moved = any(out[p][d] != obj[p][d] for p in obj for d in obj[p])
    assert moved, "nothing moved at all"

def test_objects_only_move_between_days_of_the_same_weekday():
    obj = _objects()
    for seed in range(20):
        out = permute_objects(obj, np.random.default_rng(seed))
        for pair in obj:
            for wd in (0, 1):
                src = {d: v for d, v in obj[pair].items() if d.weekday() == wd}
                dst = {d: v for d, v in out[pair].items() if d.weekday() == wd}
                assert sorted(map(str, src.values())) == sorted(map(str, dst.values()))

def test_pairs_are_permuted_independently():
    # Both pairs start from the IDENTICAL object map, so under a single shared
    # permutation their outputs would be identical on every draw.
    obj = _objects()
    same = {"EUR_USD": dict(obj["EUR_USD"]), "GBP_USD": dict(obj["EUR_USD"])}
    differed = False
    for seed in range(30):
        out = permute_objects(same, np.random.default_rng(seed))
        if any(out["EUR_USD"][d] != out["GBP_USD"][d] for d in same["EUR_USD"]):
            differed = True
            break
    assert differed, "pairs appear to share one permutation"

def test_a_globally_unchanged_mapping_is_redrawn():
    single = {"EUR_USD": {pd.Timestamp("2026-06-08"): (0, 1)}}   # only one arrangement
    with pytest.raises(ValueError, match="unchanged"):
        permute_objects(single, np.random.default_rng(0))


# --- null ------------------------------------------------------------------------------

def test_the_null_is_deterministic_for_a_fixed_seed():
    frames = {"EUR_USD": _breakouts(["2026-06-08", "2026-06-15"]),
              "GBP_USD": _breakouts(["2026-06-09", "2026-06-16"])}
    kw = dict(spec=SPEC, expected=EXP, runs=8, seed=NULL_SEED)
    a = run_null(frames, **kw)
    b = run_null(frames, **kw)
    assert a["alphas"] == b["alphas"]
    assert a["percentile_rank"] == b["percentile_rank"]
    assert len(a["alphas"]) == 8
    assert run_null(frames, spec=SPEC, expected=EXP, runs=8, seed=NULL_SEED + 1)["alphas"] \
        != a["alphas"]

def test_the_locked_null_constants_are_frozen():
    assert (NULL_RUNS, NULL_SEED) == (1000, 20260806)


# --- benchmark -------------------------------------------------------------------------

def test_the_benchmark_is_always_long_on_the_same_schedule_and_pays_the_same_costs():
    df = _breakouts(["2026-06-08"])
    bench = session_matched_benchmark(df, SPEC, pair="EUR_USD", expected=EXP)
    day = [t for t in bench if t["trading_day"] == "2026-06-08"][0]
    b = session_bounds(SPEC, pd.Timestamp("2026-06-08"))
    assert day["direction"] == 1
    assert day["entry_ms"] == b["entry_start_ms"] + M15     # first permitted fill open
    assert day["exit_ms"] == b["exit_ms"] and day["exit_reason"] == "scheduled"
    slipped = session_matched_benchmark(df, SPEC, pair="EUR_USD", expected=EXP,
                                        pip=0.0001, slippage_pips=0.5)
    s = [t for t in slipped if t["trading_day"] == "2026-06-08"][0]
    assert s["entry_px"] > day["entry_px"] and s["exit_px"] < day["exit_px"]

def test_the_benchmark_covers_every_eligible_day_not_only_traded_days():
    df = _breakouts(["2026-06-08"])
    strat = run_candidate(df, SPEC, pair="EUR_USD", expected=EXP)
    bench = session_matched_benchmark(df, SPEC, pair="EUR_USD", expected=EXP)
    assert len(bench) > len(strat)

def test_zero_volatility_or_an_extreme_scale_makes_the_benchmark_gate_fail():
    flat = np.zeros(10)
    assert volatility_scale(np.array([0.1, -0.1] * 5), flat)["status"] == "UNDEFINED"
    assert volatility_scale(flat, np.array([0.1, -0.1] * 5))["status"] == "UNDEFINED"
    big = volatility_scale(np.array([1.0, -1.0] * 5), np.array([0.01, -0.01] * 5))
    assert big["status"] == "UNDEFINED" and big["k"] > 10          # never capped
    ok = volatility_scale(np.array([0.02, -0.02] * 5), np.array([0.01, -0.01] * 5))
    assert ok["status"] == "OK" and ok["k"] == pytest.approx(2.0)


# --- gates and selection ---------------------------------------------------------------

def _result(**over):
    base = {"name": "c2_london_orb", "alpha": 0.05, "null_percentile": 95.0,
            "stressed_alpha": 0.01, "positive_pairs": 4, "worst_pair_alpha": -0.05,
            "participation": {"EUR_USD": 0.2}, "trades_per_pair": {"EUR_USD": 100},
            "active_month_ratio": {"EUR_USD": 0.9}, "benchmark_status": "OK",
            "n_trades": 100}
    base.update(over)
    return base

def test_every_gate_is_anded_so_one_failure_blocks_the_candidate():
    assert evaluate_candidate(_result())["eligible"] is True
    for bad in ({"alpha": -0.001}, {"null_percentile": 89.9}, {"stressed_alpha": 0.0},
                {"positive_pairs": 2}, {"worst_pair_alpha": -0.11},
                {"participation": {"EUR_USD": 0.07}}, {"trades_per_pair": {"EUR_USD": 39}},
                {"active_month_ratio": {"EUR_USD": 0.69}},
                {"benchmark_status": "UNDEFINED"}):
        r = evaluate_candidate(_result(**bad))
        assert r["eligible"] is False and r["failed"], bad

def test_selection_is_deterministic_on_alpha_then_trades_then_listed_order():
    a = _result(name="c1_asia_london", alpha=0.05, n_trades=120)
    b = _result(name="c2_london_orb", alpha=0.05, n_trades=100)
    c = _result(name="c3_london_ny", alpha=0.05, n_trades=100)
    assert select_candidate([a, b, c])["selected"] == "c2_london_orb"   # fewer trades
    assert select_candidate([b, c])["selected"] == "c2_london_orb"      # listed order
    hi = _result(name="c3_london_ny", alpha=0.06, n_trades=999)
    assert select_candidate([a, b, hi])["selected"] == "c3_london_ny"   # alpha first

def test_no_eligible_candidate_kills_the_family():
    out = select_candidate([_result(alpha=-0.01), _result(name="c1_asia_london", alpha=-0.2)])
    assert out["selected"] is None and out["verdict"] == "FAMILY_KILLED"

def test_exactly_one_candidate_is_frozen_for_confirmation():
    out = select_candidate([_result(name="c1_asia_london", alpha=0.02),
                            _result(name="c2_london_orb", alpha=0.05)])
    assert out["selected"] == "c2_london_orb" and out["verdict"] == "PROCEED"
    assert len(out["frozen"]) == 1


def test_measure_candidate_wires_the_volatility_scale_into_alpha():
    frames = {"EUR_USD": _breakouts(["2026-06-08", "2026-06-15"]),
              "GBP_USD": _breakouts(["2026-06-09", "2026-06-16"])}
    m = measure_candidate(frames, SPEC, expected=EXP, null_percentile=95.0)
    assert m["benchmark_status"] == "OK" and m["k"] > 0
    assert set(m["per_pair_alpha"]) == {"EUR_USD", "GBP_USD"}
    assert m["n_trades"] == sum(m["trades_per_pair"].values()) == 4
    assert 0.0 < m["participation"]["EUR_USD"] <= 1.0

def test_a_zero_volatility_benchmark_propagates_to_the_gate():
    flat = {"EUR_USD": _frame(), "GBP_USD": _frame()}          # identical every day
    m = measure_candidate(flat, SPEC, expected=EXP, null_percentile=95.0)
    assert m["benchmark_status"] == "UNDEFINED"
    assert evaluate_candidate(m)["eligible"] is False
    assert "benchmark_undefined" in evaluate_candidate(m)["failed"]

def test_the_locked_stress_cell_doubles_the_spread_without_moving_the_mid():
    frames = {"EUR_USD": _breakouts(["2026-06-08"])}
    st = stress_frames(frames, 2.0)
    a, b = frames["EUR_USD"], st["EUR_USD"]
    for f in ("o", "h", "l", "c"):
        assert np.allclose((b[f"bid_{f}"] + b[f"ask_{f}"]) / 2,
                           (a[f"bid_{f}"] + a[f"ask_{f}"]) / 2)     # mid untouched
        assert np.allclose(b[f"ask_{f}"] - b[f"bid_{f}"],
                           2 * (a[f"ask_{f}"] - a[f"bid_{f}"]))     # spread doubled

def test_the_stress_cell_makes_the_same_trade_strictly_more_expensive():
    # The mid is untouched, so the signal is identical; only execution gets worse. Note
    # the PORTFOLIO stressed alpha need not fall, because the benchmark is stressed too.
    df = _breakouts(["2026-06-08"])
    base = run_candidate(df, SPEC, pair="EUR_USD", expected=EXP)[0]
    hard = run_candidate(stress_frames({"EUR_USD": df}, 2.0)["EUR_USD"], SPEC,
                         pair="EUR_USD", expected=EXP, pip=0.0001, slippage_pips=0.5)[0]
    assert base["signal_ms"] == hard["signal_ms"]
    assert base["exit_reason"] == hard["exit_reason"] == "scheduled"
    assert hard["entry_px"] > base["entry_px"] and hard["exit_px"] < base["exit_px"]


# --- confirmation stays shut -----------------------------------------------------------

def test_confirmation_cannot_be_opened_without_a_frozen_selection():
    with pytest.raises(ConfirmationLocked):
        open_confirmation(None)
    with pytest.raises(ConfirmationLocked):
        open_confirmation({"selected": None, "verdict": "FAMILY_KILLED", "frozen": []})

def test_confirmation_opens_only_once_a_single_candidate_is_frozen():
    out = select_candidate([_result(name="c2_london_orb", alpha=0.05)])
    assert open_confirmation(out) == "c2_london_orb"
    with pytest.raises(ConfirmationLocked):
        open_confirmation({**out, "frozen": ["c1_asia_london", "c2_london_orb"]})

def test_a_hand_assembled_verdict_cannot_open_confirmation():
    # The door re-derives eligibility from the stored measurements; a dict that merely
    # SAYS "PROCEED" for a candidate failing every gate must not be believed.
    forged = {"selected": "c2_london_orb", "verdict": "PROCEED",
              "frozen": ["c2_london_orb"],
              "candidates": [_result(name="c2_london_orb", alpha=-0.5,
                                     null_percentile=1.0, stressed_alpha=-0.9)]}
    with pytest.raises(ConfirmationLocked, match="recheck"):
        open_confirmation(forged)
    with pytest.raises(ConfirmationLocked, match="no measurement record"):
        open_confirmation({**forged, "candidates": []})
