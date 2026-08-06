"""M3: the expected intraday market grid and the fail-closed data validator.

The grid is anchored in `America/New_York`, not UTC: the FX week runs Sunday 17:00 ET
(inclusive) to Friday 17:00 ET (exclusive), which is 22:00Z..22:00Z in winter and
21:00Z..21:00Z in summer. A UTC-anchored grid would therefore mislabel one hour of every
DST-shifted week as a gap — a measured M15 probe showed exactly that. Every timestamp here
is a fixed literal so the tests pin the real calendar, not a re-derivation of it.

Nothing in this module fetches; frames are constructed in-test.
"""
import pandas as pd
import pytest

from bot.forex.market_grid import (
    GridValidationError,
    expected_grid,
    first_expected_ms,
    last_expected_ms,
    segment_of,
    validate_universe,
)

M15 = 900_000
PAIRS = ["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD"]


def _ms(s):
    return int(pd.Timestamp(s, tz="UTC").value // 10 ** 6)


def _iso(ms):
    return pd.Timestamp(ms, unit="ms", tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


# One winter week and one summer week, weekend-boundary to weekend-boundary.
WIN = (_ms("2014-01-04T00:00:00"), _ms("2014-01-11T00:00:00"))
SUM = (_ms("2021-06-05T00:00:00"), _ms("2021-06-12T00:00:00"))

SEGMENTS = {
    "development": (_ms("2014-01-04T00:00:00"), _ms("2021-07-03T00:00:00")),
    "validation": (_ms("2021-07-03T00:00:00"), _ms("2024-01-06T00:00:00")),
    "confirmation": (_ms("2024-01-06T00:00:00"), _ms("2026-06-27T00:00:00")),
}


def _frame(ts, *, volume=100, complete=True, price=1.0):
    ts = list(ts)
    n = len(ts)
    return pd.DataFrame({
        "open_time": ts,
        "volume": [volume] * n if not isinstance(volume, list) else volume,
        "complete": [complete] * n if not isinstance(complete, list) else complete,
        "bid_c": [price] * n if not isinstance(price, list) else price,
        "ask_c": [price] * n if not isinstance(price, list) else price,
    })


def _universe(ts, **over):
    return {p: _frame(ts, **over) for p in PAIRS}


# --- the grid itself ------------------------------------------------------------------

def test_winter_week_opens_at_2200z_and_closes_at_2145z():
    g = expected_grid(*WIN)
    assert _iso(g[0]) == "2014-01-05T22:00:00Z"       # Sunday 17:00 EST
    assert _iso(g[-1]) == "2014-01-10T21:45:00Z"      # last bar before Friday 17:00 EST
    assert len(g) == 480                               # 120 hours of M15

def test_summer_week_opens_at_2100z_and_closes_at_2045z():
    g = expected_grid(*SUM)
    assert _iso(g[0]) == "2021-06-06T21:00:00Z"       # Sunday 17:00 EDT
    assert _iso(g[-1]) == "2021-06-11T20:45:00Z"
    assert len(g) == 480                               # same bar count, shifted one hour

def test_the_dst_transition_week_shifts_the_utc_open_by_one_hour():
    # Spring forward lands Sunday 2021-03-14 02:00 ET, inside the closed weekend gap, so
    # the offset is constant WITHIN each week and only changes BETWEEN them.
    before = expected_grid(_ms("2021-03-06T00:00:00"), _ms("2021-03-13T00:00:00"))
    after = expected_grid(_ms("2021-03-13T00:00:00"), _ms("2021-03-20T00:00:00"))
    assert _iso(before[0]) == "2021-03-07T22:00:00Z"   # still EST
    assert _iso(after[0]) == "2021-03-14T21:00:00Z"    # EDT
    assert len(before) == len(after) == 480

def test_the_fall_back_week_keeps_the_same_bar_count_despite_the_repeated_et_hour():
    # 2021-11-07 02:00 ET occurs twice. It sits inside the closed weekend gap, so the
    # week must still be exactly 480 bars and must open at 22:00Z (back on EST).
    g = expected_grid(_ms("2021-11-06T00:00:00"), _ms("2021-11-13T00:00:00"))
    assert _iso(g[0]) == "2021-11-07T22:00:00Z"
    assert _iso(g[-1]) == "2021-11-12T21:45:00Z"
    assert len(g) == 480

def test_saturday_and_pre_open_sunday_slots_are_not_grid_members():
    g = set(expected_grid(*WIN))
    for absent in ("2014-01-04T12:00:00", "2014-01-05T12:00:00", "2014-01-05T21:45:00",
                   "2014-01-10T22:00:00"):
        assert _ms(absent) not in g, f"{absent} must not be an expected slot"

def test_a_weekend_only_interval_has_no_expected_bars():
    assert len(expected_grid(_ms("2014-01-04T00:00:00"), _ms("2014-01-05T22:00:00"))) == 0

def test_first_and_last_expected_derive_the_inclusive_candle_range():
    # The research interval is a half-open weekend-to-weekend span; the FETCH needs the
    # inclusive first/last real candle inside it.
    assert _iso(first_expected_ms(*WIN)) == "2014-01-05T22:00:00Z"
    assert _iso(last_expected_ms(*WIN)) == "2014-01-10T21:45:00Z"

def test_grid_is_strictly_increasing_and_on_the_m15_lattice():
    g = expected_grid(*SUM)
    assert all(b - a == M15 for a, b in zip(g, g[1:]))


# --- half-open segment membership -----------------------------------------------------

def test_segment_boundaries_are_half_open_with_no_overlap():
    assert segment_of(_ms("2021-07-02T20:00:00"), SEGMENTS) == "development"
    assert segment_of(_ms("2021-07-03T00:00:00"), SEGMENTS) == "validation"
    assert segment_of(_ms("2024-01-05T20:00:00"), SEGMENTS) == "validation"
    assert segment_of(_ms("2024-01-06T00:00:00"), SEGMENTS) == "confirmation"
    assert segment_of(_ms("2026-06-27T00:00:00"), SEGMENTS) is None   # end is exclusive
    assert segment_of(_ms("2014-01-03T00:00:00"), SEGMENTS) is None


# --- validator: fail-closed rules -----------------------------------------------------

def test_a_complete_universe_validates_and_reports_expected_equals_observed():
    g = expected_grid(*WIN)
    rep = validate_universe(_universe(g), start_ms=WIN[0], end_ms=WIN[1], segments=SEGMENTS)
    assert rep["expected_bars"] == 480
    for p in PAIRS:
        assert rep["pairs"][p]["observed"] == 480
        assert rep["pairs"][p]["first"] == int(g[0]) and rep["pairs"][p]["last"] == int(g[-1])
    assert rep["all_pair_gaps"] == [] and rep["subset_gaps"] == []

def test_a_slot_missing_from_every_pair_is_listed_not_classified_and_not_fatal():
    # Frozen policy: a missing bar invalidates the affected opportunity, it does not
    # invalidate the dataset. Dataset readiness is decided by thresholds, below.
    g = list(expected_grid(*WIN))
    hole = g[100]
    rep = validate_universe(_universe([t for t in g if t != hole]),
                            start_ms=WIN[0], end_ms=WIN[1], segments=SEGMENTS)
    assert rep["all_pair_gaps"] == [hole]
    assert rep["readiness"]["verdict"] == "READY"
    assert "holiday" not in str(rep).lower(), "missing slots must not be auto-classified"

def test_a_slot_missing_from_only_some_pairs_is_recorded_with_the_pairs_named():
    g = list(expected_grid(*WIN))
    hole = g[200]
    frames = _universe(g)
    frames["USD_JPY"] = _frame([t for t in g if t != hole])
    rep = validate_universe(frames, start_ms=WIN[0], end_ms=WIN[1], segments=SEGMENTS)
    assert rep["all_pair_gaps"] == []
    assert rep["subset_gaps"] == [{"open_time": hole, "missing": ["USD_JPY"]}]
    assert rep["readiness"]["verdict"] == "READY"


# --- frozen gap policy: boundary rows and threshold verdicts ---------------------------

def test_friday_1700_et_rows_are_excluded_and_logged_not_treated_as_off_grid():
    # Measured: 35 such rows exist across the four pairs, always at :00, volume 1-3.
    # They are boundary artifacts of an exclusive week close, not tradeable bars.
    g = list(expected_grid(*WIN))
    frames = _universe(g)
    frames["USD_JPY"] = _frame(g + [_ms("2014-01-10T22:00:00")])      # Friday 17:00 EST
    rep = validate_universe(frames, start_ms=WIN[0], end_ms=WIN[1], segments=SEGMENTS)
    assert rep["pairs"]["USD_JPY"]["boundary_rows_excluded"] == 1
    assert rep["pairs"]["USD_JPY"]["off_grid"] == 0
    assert rep["readiness"]["verdict"] == "READY"

def test_coverage_below_the_floor_blocks_readiness():
    g = list(expected_grid(*WIN))
    drop = set(g[10:16])                                  # 6/480 = 1.25% from EVERY pair
    rep = validate_universe(_universe([t for t in g if t not in drop]),
                            start_ms=WIN[0], end_ms=WIN[1], segments=SEGMENTS)
    assert rep["readiness"]["verdict"] == "BLOCKED"
    assert any("coverage" in f for f in rep["readiness"]["failed"])
    assert rep["coverage"]["EUR_USD"]["development"] == pytest.approx(474 / 480)
    assert rep["coverage"]["EUR_USD"]["validation"] is None      # no expected bars there

def test_subset_gap_rate_above_the_ceiling_blocks_readiness():
    g = list(expected_grid(*WIN))
    frames = _universe(g)
    frames["AUD_USD"] = _frame([t for t in g if t not in (g[5], g[300])])   # 0.42% > 0.25%
    rep = validate_universe(frames, start_ms=WIN[0], end_ms=WIN[1], segments=SEGMENTS)
    assert rep["readiness"]["verdict"] == "BLOCKED"
    assert any("subset_gap_rate" in f for f in rep["readiness"]["failed"])

def test_an_all_pair_run_longer_than_288_bars_blocks_readiness():
    g = list(expected_grid(*WIN))
    drop = set(g[50:350])                                  # 300 contiguous, all pairs
    rep = validate_universe(_universe([t for t in g if t not in drop]),
                            start_ms=WIN[0], end_ms=WIN[1], segments=SEGMENTS)
    assert rep["longest_all_pair_run"] == 300
    assert any("all_pair_run" in f for f in rep["readiness"]["failed"])

def test_a_subset_run_longer_than_32_bars_blocks_readiness():
    g = list(expected_grid(*WIN))
    frames = _universe(g)
    frames["GBP_USD"] = _frame([t for t in g if t not in set(g[100:140])])   # 40 contiguous
    rep = validate_universe(frames, start_ms=WIN[0], end_ms=WIN[1], segments=SEGMENTS)
    assert rep["longest_subset_run"] == 40
    assert any("subset_run" in f for f in rep["readiness"]["failed"])

def test_a_pair_day_losing_more_than_ten_percent_of_its_bars_is_marked_invalid():
    g = list(expected_grid(*WIN))
    day = [t for t in g if _iso(t).startswith("2014-01-07")]
    frames = _universe(g)
    frames["EUR_USD"] = _frame([t for t in g if t not in set(day[:20])])   # >10% of that day
    rep = validate_universe(frames, start_ms=WIN[0], end_ms=WIN[1], segments=SEGMENTS)
    assert rep["invalid_pair_days"]["EUR_USD"]["development"] == 1
    assert rep["invalid_pair_days"]["USD_JPY"]["development"] == 0

def test_a_fully_covered_universe_is_ready_and_publishes_its_thresholds():
    g = expected_grid(*WIN)
    rep = validate_universe(_universe(g), start_ms=WIN[0], end_ms=WIN[1], segments=SEGMENTS)
    assert rep["readiness"] == {"verdict": "READY", "failed": []}
    assert rep["thresholds"] == {"min_coverage": 0.99, "max_subset_gap_rate": 0.0025,
                                 "max_all_pair_run": 288, "max_subset_run": 32,
                                 "max_pair_day_missing": 0.10}

def test_an_off_grid_timestamp_fails():
    g = list(expected_grid(*WIN))
    frames = _universe(g)
    frames["EUR_USD"] = _frame(g + [_ms("2014-01-11T12:00:00")])     # a Saturday bar
    with pytest.raises(GridValidationError, match="off-grid"):
        validate_universe(frames, start_ms=WIN[0], end_ms=WIN[1], segments=SEGMENTS)

def test_zero_volume_fails_and_low_positive_volume_is_recorded_only():
    g = list(expected_grid(*WIN))
    vols = [100] * len(g); vols[5] = 0
    frames = _universe(g); frames["AUD_USD"] = _frame(g, volume=vols)
    with pytest.raises(GridValidationError, match="zero volume"):
        validate_universe(frames, start_ms=WIN[0], end_ms=WIN[1], segments=SEGMENTS)

    vols = [100] * len(g); vols[5] = 2; vols[6] = 1
    frames = _universe(g); frames["AUD_USD"] = _frame(g, volume=vols)
    rep = validate_universe(frames, start_ms=WIN[0], end_ms=WIN[1], segments=SEGMENTS)
    assert rep["pairs"]["AUD_USD"]["low_volume"] == 2
    assert rep["pairs"]["AUD_USD"]["observed"] == 480               # kept, not dropped

def test_incomplete_candles_are_excluded_before_coverage_is_judged():
    g = list(expected_grid(*WIN))
    comp = [True] * len(g); comp[7] = False
    frames = _universe(g); frames["GBP_USD"] = _frame(g, complete=comp)
    # dropping the incomplete bar leaves a subset gap: excluded, then judged.
    rep = validate_universe(frames, start_ms=WIN[0], end_ms=WIN[1], segments=SEGMENTS)
    assert rep["subset_gaps"] == [{"open_time": g[7], "missing": ["GBP_USD"]}]
    assert rep["pairs"]["GBP_USD"]["incomplete_excluded"] == 1

def test_identical_duplicates_collapse_and_conflicting_duplicates_fail():
    g = list(expected_grid(*WIN))
    frames = _universe(g)
    frames["EUR_USD"] = pd.concat([_frame(g), _frame([g[3]])], ignore_index=True)
    rep = validate_universe(frames, start_ms=WIN[0], end_ms=WIN[1], segments=SEGMENTS)
    assert rep["pairs"]["EUR_USD"]["identical_duplicates"] == 1
    assert rep["pairs"]["EUR_USD"]["observed"] == 480

    frames["EUR_USD"] = pd.concat([_frame(g), _frame([g[3]], price=9.9)], ignore_index=True)
    with pytest.raises(GridValidationError, match="conflicting"):
        validate_universe(frames, start_ms=WIN[0], end_ms=WIN[1], segments=SEGMENTS)

def test_a_frame_without_the_columns_the_gates_need_fails_closed():
    # A fail-closed validator must not fail OPEN when the evidence is absent: a frame with
    # no `volume` column would otherwise sail past the zero-volume gate unchecked.
    g = list(expected_grid(*WIN))
    for missing in ("volume", "complete"):
        frames = _universe(g)
        frames["EUR_USD"] = _frame(g).drop(columns=[missing])
        with pytest.raises(GridValidationError, match=missing):
            validate_universe(frames, start_ms=WIN[0], end_ms=WIN[1], segments=SEGMENTS)

def test_unsorted_input_is_rejected_not_silently_sorted():
    g = list(expected_grid(*WIN))
    frames = _universe(g)
    frames["USD_JPY"] = _frame(g[::-1])
    with pytest.raises(GridValidationError, match="increasing"):
        validate_universe(frames, start_ms=WIN[0], end_ms=WIN[1], segments=SEGMENTS)


# --- provenance -----------------------------------------------------------------------

def test_trading_days_are_counted_per_segment():
    g = expected_grid(*WIN)
    rep = validate_universe(_universe(g), start_ms=WIN[0], end_ms=WIN[1], segments=SEGMENTS)
    # Sunday 17:00 ET opens the Monday trading day, so a full week is 5 trading days.
    assert rep["trading_days"]["development"] == 5
    assert rep["trading_days"]["validation"] == 0
    assert rep["trading_days"]["confirmation"] == 0

def test_provenance_hash_is_deterministic_and_content_sensitive():
    g = list(expected_grid(*WIN))
    a = validate_universe(_universe(g), start_ms=WIN[0], end_ms=WIN[1], segments=SEGMENTS)
    b = validate_universe(_universe(g), start_ms=WIN[0], end_ms=WIN[1], segments=SEGMENTS)
    assert a["content_hash"] == b["content_hash"] and len(a["content_hash"]) == 64

    vols = [100] * len(g); vols[5] = 2
    frames = _universe(g); frames["AUD_USD"] = _frame(g, volume=vols)
    c = validate_universe(frames, start_ms=WIN[0], end_ms=WIN[1], segments=SEGMENTS)
    assert c["content_hash"] != a["content_hash"]


# --- integration / legacy -------------------------------------------------------------

def test_validator_accepts_frames_loaded_through_load_exact_window(tmp_path):
    from bot.forex.exact_window import load_exact_window
    g = list(expected_grid(*WIN))
    cfg = {"instrument": "EUR_USD", "granularity": "M15", "price": "BA",
           "alignment_hour_utc": 0, "cache_dir": str(tmp_path)}
    lo, hi = int(g[0]), int(g[-1])
    frames = {p: load_exact_window(dict(cfg, instrument=p), start_ms=lo, end_ms=hi,
                                   fetch_fn=lambda s, e: _frame(g)) for p in PAIRS}
    rep = validate_universe(frames, start_ms=WIN[0], end_ms=WIN[1], segments=SEGMENTS)
    assert rep["expected_bars"] == 480 and rep["all_pair_gaps"] == []

def test_legacy_h4_paths_are_untouched():
    from bot.forex.oanda_data import cache_path
    from bot.forex.multipair_data import split_common_window
    assert cache_path({"instrument": "EUR_USD", "granularity": "H4", "price": "BA"}).name \
        == "EUR_USD__H4__BA.csv"
    assert callable(split_common_window)
