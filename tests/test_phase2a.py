"""Phase 2A: session/liquidity breakout mechanics.

These tests pin the LOCKED spec, not a strategy opinion: session windows resolved in each
venue's own timezone (so a week where US and EU DST disagree is handled without
reconciliation), eligibility that demands every bar from range start through the scheduled
exit, next-open bid/ask fills, and a strict per-bar exit precedence — scheduled exit or
emergency flat at the open first, then a gap-through stop at the executable open, then an
intrabar stop. After an open-time exit the bar's high and low must never be consulted.

No performance is measured anywhere here; only mechanics.
"""
import numpy as np
import pandas as pd
import pytest

from bot.forex.market_grid import expected_grid
from bot.forex.phase2a import (
    SPECS,
    eligible_days,
    jaccard_pair_day,
    jaccard_timestamp,
    run_candidate,
    session_bounds,
)

M15 = 900_000
PIP = 0.0001


def _ms(s):
    return int(pd.Timestamp(s, tz="UTC").value // 10 ** 6)


def _iso(ms):
    return pd.Timestamp(int(ms), unit="ms", tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def _frame(lo, hi, *, spread=0.0002, mid=1.0):
    """Flat M15 bars over the expected grid of [lo, hi), bid/ask around a constant mid."""
    ts = [int(t) for t in expected_grid(lo, hi)]
    half = spread / 2
    return pd.DataFrame({
        "open_time": ts,
        "bid_o": [mid - half] * len(ts), "bid_h": [mid - half] * len(ts),
        "bid_l": [mid - half] * len(ts), "bid_c": [mid - half] * len(ts),
        "ask_o": [mid + half] * len(ts), "ask_h": [mid + half] * len(ts),
        "ask_l": [mid + half] * len(ts), "ask_c": [mid + half] * len(ts),
        "volume": [100] * len(ts), "complete": [True] * len(ts),
    })


def _set(df, ms, *, o=None, h=None, l=None, c=None, spread=0.0002):
    """Overwrite one bar's mid OHLC, keeping the bid/ask spread symmetric."""
    half = spread / 2
    i = df.index[df["open_time"] == ms]
    assert len(i) == 1, f"no bar at {_iso(ms)}"
    for name, v in (("o", o), ("h", h), ("l", l), ("c", c)):
        if v is None:
            continue
        df.loc[i, f"bid_{name}"] = v - half
        df.loc[i, f"ask_{name}"] = v + half
    return df


# A quiet summer week (both venues on DST) and the March week where the US has already
# sprung forward but the EU has not.
SUMMER = (_ms("2026-06-07T00:00:00"), _ms("2026-06-13T00:00:00"))
MISMATCH = (_ms("2026-03-08T00:00:00"), _ms("2026-03-14T00:00:00"))
WINTER = (_ms("2026-01-11T00:00:00"), _ms("2026-01-17T00:00:00"))

SUMMER_DAY = pd.Timestamp("2026-06-09").to_datetime64()      # Tuesday
MISMATCH_DAY = pd.Timestamp("2026-03-10").to_datetime64()
WINTER_DAY = pd.Timestamp("2026-01-13").to_datetime64()


# --- session windows ------------------------------------------------------------------

def test_c1_range_is_tokyo_0900_inclusive_to_1500_exclusive():
    b = session_bounds(SPECS["c1_asia_london"], SUMMER_DAY)
    assert _iso(b["range_start_ms"]) == "2026-06-09T00:00:00Z"     # 09:00 JST
    assert _iso(b["range_end_ms"]) == "2026-06-09T06:00:00Z"       # 15:00 JST, exclusive
    assert (b["range_end_ms"] - b["range_start_ms"]) // M15 == 24

def test_c1_entry_window_runs_from_london_open_to_the_last_signal_close():
    b = session_bounds(SPECS["c1_asia_london"], SUMMER_DAY)
    assert _iso(b["entry_start_ms"]) == "2026-06-09T07:00:00Z"     # 08:00 BST
    assert _iso(b["last_signal_open_ms"]) == "2026-06-09T10:45:00Z"  # closes 12:00 BST
    assert _iso(b["exit_ms"]) == "2026-06-09T15:30:00Z"            # 16:30 BST

def test_c2_range_is_the_first_london_hour_and_the_first_signal_closes_at_0915():
    b = session_bounds(SPECS["c2_london_orb"], SUMMER_DAY)
    assert (b["range_end_ms"] - b["range_start_ms"]) // M15 == 4
    assert b["entry_start_ms"] == b["range_end_ms"]                # 09:00 London
    assert _iso(b["entry_start_ms"] + M15) == "2026-06-09T08:15:00Z"

def test_c3_entry_starts_at_the_later_of_london_1200_and_new_york_0800():
    # Summer: both on DST -> 12:00 UTC. Winter: both standard -> 13:00 UTC. Mismatch week:
    # US on EDT, EU still on GMT -> both land on 12:00 UTC. Each venue is resolved in its
    # own timezone; there is no reconciliation.
    assert _iso(session_bounds(SPECS["c3_london_ny"], SUMMER_DAY)["entry_start_ms"]) \
        == "2026-06-09T12:00:00Z"
    assert _iso(session_bounds(SPECS["c3_london_ny"], WINTER_DAY)["entry_start_ms"]) \
        == "2026-01-13T13:00:00Z"
    assert _iso(session_bounds(SPECS["c3_london_ny"], MISMATCH_DAY)["entry_start_ms"]) \
        == "2026-03-10T12:00:00Z"

def test_c3_scheduled_exit_is_1600_new_york_and_precedes_the_emergency_flat():
    b = session_bounds(SPECS["c3_london_ny"], SUMMER_DAY)
    assert _iso(b["exit_ms"]) == "2026-06-09T20:00:00Z"            # 16:00 EDT
    assert b["exit_ms"] < b["flat_ms"]                             # 16:45 ET invariant


# --- eligibility ----------------------------------------------------------------------

def test_a_missing_bar_inside_the_required_span_invalidates_the_day():
    spec = SPECS["c2_london_orb"]
    df = _frame(*SUMMER)
    b = session_bounds(spec, SUMMER_DAY)
    exp = expected_grid(*SUMMER)
    assert SUMMER_DAY in eligible_days(df, spec, exp)
    holed = df[df["open_time"] != b["range_start_ms"] + 2 * M15]
    assert SUMMER_DAY not in eligible_days(holed, spec, exp)

def test_a_missing_bar_after_the_scheduled_exit_does_not_invalidate_the_day():
    # 16:45 ET is an emergency invariant, not an extra data requirement.
    spec = SPECS["c2_london_orb"]
    df = _frame(*SUMMER)
    b = session_bounds(spec, SUMMER_DAY)
    exp = expected_grid(*SUMMER)
    holed = df[df["open_time"] != b["exit_ms"] + 4 * M15]
    assert SUMMER_DAY in eligible_days(holed, spec, exp)


# --- entry / execution ----------------------------------------------------------------

def _breakout_day(spec, day, span, *, direction="long", offset=0):
    """Flat range, then a decisive close beyond it inside the entry window."""
    df = _frame(*span)
    b = session_bounds(spec, day)
    sig = b["entry_start_ms"] + offset * M15
    px = 1.02 if direction == "long" else 0.98
    _set(df, sig, o=1.0, h=max(px, 1.0), l=min(px, 1.0), c=px)
    return df, b, sig

def test_entry_fills_at_the_next_bar_open_on_the_correct_side():
    spec = SPECS["c2_london_orb"]
    df, b, sig = _breakout_day(spec, SUMMER_DAY, SUMMER)
    t = run_candidate(df, spec, pair="EUR_USD", expected=expected_grid(*SUMMER))
    assert len(t) == 1
    assert t[0]["signal_ms"] == sig and t[0]["entry_ms"] == sig + M15
    assert t[0]["direction"] == 1
    assert t[0]["entry_px"] == pytest.approx(1.0 + 0.0001)          # ask open

def test_a_short_signal_fills_at_the_bid_open():
    spec = SPECS["c2_london_orb"]
    df, b, sig = _breakout_day(spec, SUMMER_DAY, SUMMER, direction="short")
    t = run_candidate(df, spec, pair="EUR_USD", expected=expected_grid(*SUMMER))
    assert t[0]["direction"] == -1
    assert t[0]["entry_px"] == pytest.approx(1.0 - 0.0001)          # bid open

def test_a_signal_before_the_entry_window_is_ignored():
    spec = SPECS["c2_london_orb"]
    df = _frame(*SUMMER)
    b = session_bounds(spec, SUMMER_DAY)
    _set(df, b["range_start_ms"] + M15, o=1.0, h=1.02, l=1.0, c=1.02)   # inside the range
    assert run_candidate(df, spec, pair="EUR_USD", expected=expected_grid(*SUMMER)) == []

def test_a_signal_after_the_last_allowed_close_is_ignored():
    spec = SPECS["c2_london_orb"]
    df = _frame(*SUMMER)
    b = session_bounds(spec, SUMMER_DAY)
    _set(df, b["last_signal_open_ms"] + M15, o=1.0, h=1.02, l=1.0, c=1.02)
    assert run_candidate(df, spec, pair="EUR_USD", expected=expected_grid(*SUMMER)) == []

def test_only_one_trade_per_pair_day_and_no_re_entry():
    spec = SPECS["c2_london_orb"]
    df, b, sig = _breakout_day(spec, SUMMER_DAY, SUMMER)
    _set(df, sig + 4 * M15, o=1.0, h=1.03, l=1.0, c=1.03)           # a second breakout
    t = run_candidate(df, spec, pair="EUR_USD", expected=expected_grid(*SUMMER))
    assert len(t) == 1


# --- exits ----------------------------------------------------------------------------

def test_a_long_stop_is_triggered_by_the_bid_low_and_fills_at_the_stop():
    spec = SPECS["c2_london_orb"]
    df = _frame(*SUMMER)
    b = session_bounds(spec, SUMMER_DAY)
    _set(df, b["range_start_ms"], o=1.0, h=1.0, l=0.99, c=1.0)      # range low 0.99
    sig = b["entry_start_ms"]
    _set(df, sig, o=1.0, h=1.02, l=1.0, c=1.02)
    _set(df, sig + 2 * M15, o=1.0, h=1.0, l=0.98, c=0.99)           # bid low pierces 0.99
    t = run_candidate(df, spec, pair="EUR_USD", expected=expected_grid(*SUMMER))[0]
    assert t["exit_reason"] == "stop"
    assert t["exit_ms"] == sig + 2 * M15
    assert t["exit_px"] == pytest.approx(0.99)

def test_a_short_stop_is_triggered_by_the_ask_high():
    spec = SPECS["c2_london_orb"]
    df = _frame(*SUMMER)
    b = session_bounds(spec, SUMMER_DAY)
    _set(df, b["range_start_ms"], o=1.0, h=1.01, l=1.0, c=1.0)      # range high 1.01
    sig = b["entry_start_ms"]
    _set(df, sig, o=1.0, h=1.0, l=0.98, c=0.98)
    _set(df, sig + 2 * M15, o=1.0, h=1.02, l=1.0, c=1.01)
    t = run_candidate(df, spec, pair="EUR_USD", expected=expected_grid(*SUMMER))[0]
    assert t["exit_reason"] == "stop" and t["exit_px"] == pytest.approx(1.01)

def test_a_gap_through_stop_fills_at_the_worse_executable_open():
    spec = SPECS["c2_london_orb"]
    df = _frame(*SUMMER)
    b = session_bounds(spec, SUMMER_DAY)
    _set(df, b["range_start_ms"], o=1.0, h=1.0, l=0.99, c=1.0)
    sig = b["entry_start_ms"]
    _set(df, sig, o=1.0, h=1.02, l=1.0, c=1.02)
    _set(df, sig + 2 * M15, o=0.95, h=0.96, l=0.94, c=0.95)         # opens below the stop
    t = run_candidate(df, spec, pair="EUR_USD", expected=expected_grid(*SUMMER))[0]
    assert t["exit_reason"] == "gap_stop"
    assert t["exit_px"] == pytest.approx(0.95 - 0.0001)             # bid open, worse

def test_the_scheduled_exit_open_wins_over_a_stop_inside_that_same_bar():
    # Precedence: an open-time exit is taken first and the bar's high/low are never read.
    spec = SPECS["c2_london_orb"]
    df = _frame(*SUMMER)
    b = session_bounds(spec, SUMMER_DAY)
    _set(df, b["range_start_ms"], o=1.0, h=1.0, l=0.99, c=1.0)
    sig = b["entry_start_ms"]
    _set(df, sig, o=1.0, h=1.02, l=1.0, c=1.02)
    _set(df, b["exit_ms"], o=1.0, h=1.0, l=0.90, c=0.95)            # would have stopped out
    t = run_candidate(df, spec, pair="EUR_USD", expected=expected_grid(*SUMMER))[0]
    assert t["exit_reason"] == "scheduled"
    assert t["exit_ms"] == b["exit_ms"]
    assert t["exit_px"] == pytest.approx(1.0 - 0.0001)              # the OPEN, not the stop

def test_no_position_is_ever_carried_past_the_scheduled_exit_or_overnight():
    spec = SPECS["c1_asia_london"]
    df, b, sig = _breakout_day(spec, SUMMER_DAY, SUMMER)
    t = run_candidate(df, spec, pair="EUR_USD", expected=expected_grid(*SUMMER))[0]
    assert t["exit_ms"] <= b["exit_ms"] < b["flat_ms"]

def test_slippage_is_applied_adversely_on_both_sides():
    spec = SPECS["c2_london_orb"]
    df, b, sig = _breakout_day(spec, SUMMER_DAY, SUMMER)
    base = run_candidate(df, spec, pair="EUR_USD", expected=expected_grid(*SUMMER))[0]
    slip = run_candidate(df, spec, pair="EUR_USD", expected=expected_grid(*SUMMER),
                         pip=PIP, slippage_pips=0.5)[0]
    assert slip["entry_px"] > base["entry_px"]                      # buy worse
    assert slip["exit_px"] < base["exit_px"]                        # sell worse


def test_a_stop_pierced_inside_the_entry_bar_itself_closes_the_trade():
    # The position is live from the entry bar's OPEN, so that bar's low is in scope. A scan
    # starting one bar later would carry a stopped-out position to the scheduled exit.
    spec = SPECS["c2_london_orb"]
    df = _frame(*SUMMER)
    b = session_bounds(spec, SUMMER_DAY)
    _set(df, b["range_start_ms"], o=1.0, h=1.0, l=0.99, c=1.0)      # range low 0.99
    sig = b["entry_start_ms"]
    _set(df, sig, o=1.0, h=1.02, l=1.0, c=1.02)
    _set(df, sig + M15, o=1.0, h=1.0, l=0.97, c=0.98)               # entry bar pierces it
    t = run_candidate(df, spec, pair="EUR_USD", expected=expected_grid(*SUMMER))[0]
    assert t["exit_ms"] == sig + M15 and t["exit_reason"] == "stop"

def test_a_day_whose_scheduled_exit_slot_is_not_an_expected_bar_is_not_eligible():
    # Without this the exit loop would take the next bar at or after the exit time — the
    # NEXT TRADING DAY's — and stamp it "scheduled", carrying a position overnight.
    spec = SPECS["c2_london_orb"]
    df = _frame(*SUMMER)
    b = session_bounds(spec, SUMMER_DAY)
    exp = np.array([t for t in expected_grid(*SUMMER) if t != b["exit_ms"]], dtype="int64")
    assert SUMMER_DAY not in eligible_days(df, spec, exp)
    assert all(t["trading_day"] != str(pd.Timestamp(SUMMER_DAY).date())
               for t in run_candidate(df, spec, pair="EUR_USD", expected=exp))

def test_a_day_reaching_outside_the_expected_grids_own_span_is_not_eligible():
    spec = SPECS["c2_london_orb"]
    df = _frame(*SUMMER)
    b = session_bounds(spec, SUMMER_DAY)
    exp = np.array([t for t in expected_grid(*SUMMER) if t > b["range_start_ms"]],
                   dtype="int64")
    assert SUMMER_DAY not in eligible_days(df, spec, exp)

def test_every_candidate_schedules_its_exit_before_the_emergency_flat():
    # The 16:45 ET flat-by is an unreachable invariant under these three specs, in every
    # DST regime. Pinning that is what makes "no overnight position" structural.
    for name, spec in SPECS.items():
        for day in (SUMMER_DAY, WINTER_DAY, MISMATCH_DAY):
            b = session_bounds(spec, day)
            assert b["exit_ms"] < b["flat_ms"], (name, day)


# --- overlap measures -----------------------------------------------------------------

def test_both_locked_jaccard_measures_are_computed():
    a = [{"pair": "EUR_USD", "entry_ms": 1000, "direction": 1, "trading_day": "2026-06-09"},
         {"pair": "EUR_USD", "entry_ms": 2000, "direction": -1, "trading_day": "2026-06-10"}]
    b = [{"pair": "EUR_USD", "entry_ms": 1000, "direction": 1, "trading_day": "2026-06-09"}]
    assert jaccard_timestamp(a, b) == pytest.approx(0.5)
    assert jaccard_pair_day(a, b) == pytest.approx(0.5)

def test_a_one_bar_shift_in_REAL_trades_evades_only_the_timestamp_measure():
    # Both trade sets come out of the engine, not out of hand-written dicts: the same
    # pair-day and direction, entered one bar apart.
    spec = SPECS["c2_london_orb"]
    exp = expected_grid(*SUMMER)
    a_df, _, _ = _breakout_day(spec, SUMMER_DAY, SUMMER, offset=0)
    b_df, _, _ = _breakout_day(spec, SUMMER_DAY, SUMMER, offset=1)
    A = run_candidate(a_df, spec, pair="EUR_USD", expected=exp)
    B = run_candidate(b_df, spec, pair="EUR_USD", expected=exp)
    assert len(A) == len(B) == 1
    assert A[0]["entry_ms"] + M15 == B[0]["entry_ms"]
    assert A[0]["trading_day"] == B[0]["trading_day"]
    assert jaccard_timestamp(A, B) == 0.0
    assert jaccard_pair_day(A, B) == pytest.approx(1.0)
