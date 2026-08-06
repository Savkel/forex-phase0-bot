"""M3: the expected intraday market grid, a fail-closed validator, and provenance.

WHY New York and not UTC. The FX week runs Sunday 17:00 ET to Friday 17:00 ET. In UTC
that is 22:00Z..22:00Z under EST and 21:00Z..21:00Z under EDT, so a UTC-anchored grid
mislabels one hour of every DST-shifted week as missing data. A supervised M15 probe
measured exactly that: the winter week opened 22:00Z and the summer week 21:00Z. The
grid is therefore generated in `America/New_York` via `zoneinfo`, with no fixed-offset
assumption anywhere. US DST switches at Sunday 02:00 ET, inside the closed weekend gap,
so the offset is constant WITHIN any trading week and changes only between weeks.

WHY fail closed. Phase 1's window and split were decided by whatever happened to be
cached. Here every deviation from the expected grid is an error that names itself:
an off-grid bar, a slot missing from one pair, a slot missing from all pairs, a zero
volume, a conflicting duplicate. Nothing is imputed, forward-filled, repaired, or
explained away — in particular a slot absent from every pair is REPORTED, never
auto-classified as a holiday. Classification is a later, human, pre-registered step.

The research interval is half-open, `[start_ms, end_ms)`, and its boundaries sit inside
the weekend gap where no candle exists. `first_expected_ms`/`last_expected_ms` convert
that interval into the inclusive first/last real candle, which is what a range fetch
needs; the interval semantics themselves are never weakened to accommodate a fetcher.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

_ET = ZoneInfo("America/New_York")
M15_MS = 900_000

WEEK_OPEN_HOUR_ET = 17        # Sunday 17:00 ET, inclusive
WEEK_CLOSE_HOUR_ET = 17       # Friday 17:00 ET, exclusive
LOW_VOLUME_MAX = 2            # provenance only; never a rejection criterion

# Frozen gap policy. A missing bar invalidates the affected pair/session opportunity, not
# the dataset; dataset readiness is decided by these pre-registered limits alone. Each was
# set from measured data quality over 2014-2026, never from returns: worst observed pair
# coverage 99.26%, worst subset-gap rate 0.046%, longest all-pair run 110 bars (a year-end
# closure), longest subset run 23 bars. The all-pair limit passes a three-day closure and
# fails an unexplained longer outage; the subset limit is one session, beyond which a pair
# silently loses a whole session while the others trade and cross-sectional comparability
# breaks.
THRESHOLDS = {
    "min_coverage": 0.99,
    "max_subset_gap_rate": 0.0025,
    "max_all_pair_run": 288,        # 72 hours of M15
    "max_subset_run": 32,           # 8 hours of M15
    "max_pair_day_missing": 0.10,
}


class GridValidationError(ValueError):
    """Raised on any validity breach. Carries the partial provenance report."""

    def __init__(self, message: str, report: Dict[str, Any]):
        super().__init__(message)
        self.report = report


def expected_grid(start_ms: int, end_ms: int, *, step_ms: int = M15_MS) -> np.ndarray:
    """Every expected bar timestamp in the half-open interval `[start_ms, end_ms)`.

    A slot is expected when its New York wall time falls in Sunday 17:00 ET (inclusive)
    .. Friday 17:00 ET (exclusive). Saturday is never expected, nor is Sunday before the
    open.
    """
    start_ms, end_ms = int(start_ms), int(end_ms)
    if start_ms >= end_ms:
        raise ValueError(f"interval invalid: start_ms {start_ms} >= end_ms {end_ms}")
    idx = pd.date_range(pd.Timestamp(start_ms, unit="ms", tz="UTC"),
                        pd.Timestamp(end_ms, unit="ms", tz="UTC"),
                        freq=pd.Timedelta(milliseconds=step_ms), inclusive="left")
    et = idx.tz_convert(_ET)
    wd, hh = et.weekday, et.hour
    in_week = (((wd == 6) & (hh >= WEEK_OPEN_HOUR_ET))      # Sunday from the open
               | (wd <= 3)                                   # Monday .. Thursday
               | ((wd == 4) & (hh < WEEK_CLOSE_HOUR_ET)))    # Friday up to the close
    return (idx[in_week].astype("int64") // 10 ** 6).to_numpy()


def first_expected_ms(start_ms: int, end_ms: int, *, step_ms: int = M15_MS) -> int:
    g = expected_grid(start_ms, end_ms, step_ms=step_ms)
    if not len(g):
        raise ValueError(f"no expected bars in [{start_ms}, {end_ms})")
    return int(g[0])


def last_expected_ms(start_ms: int, end_ms: int, *, step_ms: int = M15_MS) -> int:
    g = expected_grid(start_ms, end_ms, step_ms=step_ms)
    if not len(g):
        raise ValueError(f"no expected bars in [{start_ms}, {end_ms})")
    return int(g[-1])


def segment_of(ts_ms: int, segments: Dict[str, Tuple[int, int]]) -> Optional[str]:
    """Half-open membership: `lo <= ts < hi`. A boundary belongs to the LATER segment,
    so no candle can ever fall in two segments."""
    ts = int(ts_ms)
    for name, (lo, hi) in segments.items():
        if int(lo) <= ts < int(hi):
            return name
    return None


def _trading_day(ts_ms: Iterable[int]) -> np.ndarray:
    """ET calendar date of the trading day a bar belongs to.

    The day opens at 17:00 ET, so shifting +7h maps an open to 00:00 of the day it
    starts: Sunday 17:00 ET is the Monday trading day.
    """
    et = pd.DatetimeIndex(pd.to_datetime(list(ts_ms), unit="ms", utc=True)).tz_convert(_ET)
    return (et + pd.Timedelta(hours=24 - WEEK_OPEN_HOUR_ET)).normalize().to_numpy()


def _longest_run(missing: Iterable[int], pos: Dict[int, int]) -> int:
    """Longest contiguous stretch of MISSING expected slots, measured in grid positions
    so a weekend never counts as part of a gap."""
    idx = sorted(pos[int(t)] for t in missing)
    if not idx:
        return 0
    best = run = 1
    for a, b in zip(idx, idx[1:]):
        run = run + 1 if b == a + 1 else 1
        best = max(best, run)
    return best


def _clean_pair(pair: str, df: pd.DataFrame, errors: List[str]) -> Tuple[pd.DataFrame, int, int]:
    """Exclude incomplete bars, collapse identical duplicates, then check ordering.

    Returns the cleaned frame plus the incomplete and identical-duplicate counts. Order
    matters: a conflicting duplicate must be named as a conflict, not as disordering.
    """
    n_incomplete = 0
    if "complete" in df.columns:
        keep = df["complete"].astype(bool)
        n_incomplete = int((~keep).sum())
        df = df[keep]
    df = df.reset_index(drop=True)

    n_identical = 0
    dups = df["open_time"][df["open_time"].duplicated()].unique()
    if len(dups):
        cols = [c for c in df.columns if c != "time"]     # `time` is derived from open_time
        for ts in dups:
            rows = df.loc[df["open_time"] == ts, cols].drop_duplicates()
            if len(rows) > 1:
                errors.append(f"{pair}: conflicting duplicate candles at open_time "
                              f"{int(ts)} ({len(rows)} distinct value sets)")
        n_identical = int(df["open_time"].duplicated().sum())
        df = df.drop_duplicates(subset="open_time", keep="first")

    if not df["open_time"].is_monotonic_increasing:
        errors.append(f"{pair}: open_time is not strictly increasing; refusing to sort "
                      f"an out-of-order source")
    return df, n_incomplete, n_identical


def validate_universe(frames: Dict[str, pd.DataFrame], *, start_ms: int, end_ms: int,
                      segments: Dict[str, Tuple[int, int]],
                      step_ms: int = M15_MS) -> Dict[str, Any]:
    """Validate a universe against the expected grid, or raise `GridValidationError`.

    Every breach is collected before raising, so one run reports every problem instead of
    only the first. The returned (or attached) dict is the provenance record.
    """
    start_ms, end_ms = int(start_ms), int(end_ms)
    grid = expected_grid(start_ms, end_ms, step_ms=step_ms)
    grid_set = set(int(x) for x in grid)
    errors: List[str] = []

    report: Dict[str, Any] = {
        "start_ms": start_ms, "end_ms": end_ms, "step_ms": int(step_ms),
        "grid_timezone": "America/New_York",
        "week": "Sunday 17:00 ET inclusive .. Friday 17:00 ET exclusive",
        "expected_bars": len(grid_set),
        "pairs": {}, "all_pair_gaps": [], "subset_gaps": [], "trading_days": {},
    }

    observed: Dict[str, set] = {}
    for pair in sorted(frames):
        # A fail-closed validator must not fail OPEN when the evidence is missing: without
        # `volume` the zero-volume gate, and without `complete` the exclusion rule, would
        # silently pass everything.
        absent = [c for c in ("open_time", "volume", "complete")
                  if c not in frames[pair].columns]
        if absent:
            errors.append(f"{pair}: required column(s) {', '.join(absent)} absent; "
                          f"cannot validate what is not present")
            report["pairs"][pair] = {"observed": None, "missing_columns": absent}
            observed[pair] = set()
            continue
        df, n_incomplete, n_identical = _clean_pair(pair, frames[pair], errors)

        # Friday 17:00 ET rows: the venue occasionally emits one bar on the exclusive week
        # close (measured: 35 rows, always at :00, volume 1-3 against a session median in
        # the thousands). They are boundary artifacts, excluded and logged — never
        # off-grid failures, and never imputed into the series.
        et = pd.DatetimeIndex(pd.to_datetime(df["open_time"], unit="ms", utc=True)).tz_convert(_ET)
        boundary = (et.weekday == 4) & (et.hour == WEEK_CLOSE_HOUR_ET) & (et.minute == 0)
        n_boundary = int(boundary.sum())
        if n_boundary:
            df = df[~np.asarray(boundary)].reset_index(drop=True)

        ts = [int(x) for x in df["open_time"].to_numpy("int64")]
        observed[pair] = set(ts)

        vols = df["volume"].to_numpy() if "volume" in df.columns else np.array([])
        n_zero = int((vols == 0).sum()) if len(vols) else 0
        if n_zero:
            errors.append(f"{pair}: {n_zero} candle(s) with zero volume")
        n_low = int(((vols > 0) & (vols <= LOW_VOLUME_MAX)).sum()) if len(vols) else 0

        off_grid = sorted(observed[pair] - grid_set)
        if off_grid:
            errors.append(f"{pair}: {len(off_grid)} off-grid timestamp(s), first "
                          f"{off_grid[0]}")

        report["pairs"][pair] = {
            "observed": len(observed[pair]),
            "first": min(ts) if ts else None,
            "last": max(ts) if ts else None,
            "incomplete_excluded": n_incomplete,
            "identical_duplicates": n_identical,
            "low_volume": n_low,
            "zero_volume": n_zero,
            "off_grid": len(off_grid),
            "missing": len(grid_set - observed[pair]),
            "boundary_rows_excluded": n_boundary,
        }

    union = set().union(*observed.values()) if observed else set()
    inter = set.intersection(*observed.values()) if observed else set()

    # Gaps are RECORDED, never repaired and never classified. Under the frozen policy a
    # missing bar invalidates only the affected pair/session opportunity; whether the
    # DATASET is usable is decided by the thresholds below, not by any single hole.
    all_pair = sorted(grid_set - union)
    report["all_pair_gaps"] = all_pair
    subset = sorted((grid_set & union) - inter)
    report["subset_gaps"] = [
        {"open_time": t, "missing": sorted(p for p in observed if t not in observed[p])}
        for t in subset
    ]

    pos = {int(t): i for i, t in enumerate(int(x) for x in grid)}
    report["longest_all_pair_run"] = _longest_run(all_pair, pos)
    report["longest_subset_run"] = max(
        (_longest_run([t for t in subset if t not in observed[p]], pos) for p in observed),
        default=0)

    exp_seg: Dict[str, set] = {name: set() for name in segments}
    for t in grid_set:
        seg = segment_of(t, segments)
        if seg is not None:
            exp_seg[seg].add(t)
    day_of = dict(zip(sorted(grid_set), _trading_day(sorted(grid_set)))) if grid_set else {}

    coverage: Dict[str, Dict[str, Any]] = {}
    subset_rate: Dict[str, Dict[str, Any]] = {}
    invalid_days: Dict[str, Dict[str, int]] = {}
    failed: List[str] = []
    for pair, obs in observed.items():
        coverage[pair], subset_rate[pair], invalid_days[pair] = {}, {}, {}
        for name, exp in exp_seg.items():
            if not exp:
                coverage[pair][name] = subset_rate[pair][name] = None
                invalid_days[pair][name] = 0
                continue
            cov = len(obs & exp) / len(exp)
            rate = len([t for t in subset if t in exp and t not in obs]) / len(exp)
            coverage[pair][name] = cov
            subset_rate[pair][name] = rate
            if cov < THRESHOLDS["min_coverage"]:
                failed.append(f"coverage:{pair}:{name}={cov:.5f}<{THRESHOLDS['min_coverage']}")
            if rate > THRESHOLDS["max_subset_gap_rate"]:
                failed.append(f"subset_gap_rate:{pair}:{name}={rate:.5f}>"
                              f"{THRESHOLDS['max_subset_gap_rate']}")
            per_day_exp: Dict[Any, int] = {}
            per_day_missing: Dict[Any, int] = {}
            for t in exp:
                day = day_of[t]
                per_day_exp[day] = per_day_exp.get(day, 0) + 1
                if t not in obs:
                    per_day_missing[day] = per_day_missing.get(day, 0) + 1
            invalid_days[pair][name] = sum(
                1 for day, miss in per_day_missing.items()
                if miss / per_day_exp[day] > THRESHOLDS["max_pair_day_missing"])
    if report["longest_all_pair_run"] > THRESHOLDS["max_all_pair_run"]:
        failed.append(f"all_pair_run={report['longest_all_pair_run']}>"
                      f"{THRESHOLDS['max_all_pair_run']}")
    if report["longest_subset_run"] > THRESHOLDS["max_subset_run"]:
        failed.append(f"subset_run={report['longest_subset_run']}>"
                      f"{THRESHOLDS['max_subset_run']}")

    report["coverage"] = coverage
    report["subset_gap_rate"] = subset_rate
    report["invalid_pair_days"] = invalid_days
    report["thresholds"] = dict(THRESHOLDS)
    report["readiness"] = {"verdict": "BLOCKED" if failed else "READY",
                           "failed": sorted(failed)}

    valid = sorted(inter & grid_set)
    days = _trading_day(valid) if valid else np.array([], dtype="datetime64[ns]")
    counts = {name: set() for name in segments}
    for ts, day in zip(valid, days):
        seg = segment_of(ts, segments)
        if seg is not None:
            counts[seg].add(day)
    report["trading_days"] = {name: len(v) for name, v in counts.items()}

    report["errors"] = errors
    report["content_hash"] = hashlib.sha256(
        json.dumps({k: v for k, v in report.items() if k != "content_hash"},
                   sort_keys=True, default=str).encode()
    ).hexdigest()

    if errors:
        raise GridValidationError("; ".join(errors), report)
    return report
