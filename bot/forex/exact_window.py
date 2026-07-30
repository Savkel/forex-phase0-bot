"""Exact research-window + absolute split-boundary locking (M1+M2).

WHY this module exists, separately from `oanda_data` / `multipair_data`: on the legacy
path the research window and the train/holdout boundary are DERIVED from whatever data
happens to be cached — `common_window` takes min-of-max across pairs and
`split_common_window` cuts the loaded timeline at a ratio. One stale or short pair cache
therefore silently decides both, so refreshing a single pair re-splits the whole
experiment. That is unacceptable for a pre-registered experiment.

Here the window and the boundary are EXPLICIT INPUTS and everything else fails closed:

- cache identity carries every field that changes candle output (instrument, granularity,
  price, alignment hour, start_ms, end_ms), so two windows can never share a file;
- a cache that does not SPAN the locked window is rejected, never silently used;
- frames are trimmed to the inclusive [start_ms, end_ms] window, so bars outside it
  cannot change any result;
- the split cuts at the supplied absolute `boundary_ms`, which must itself be present in
  the shared timeline and strictly inside the window.

The legacy functions are untouched: Phase 0 and Phase 1 are closed and must keep
reproducing exactly. Nothing here fetches by itself — `fetch_fn` is always injected and
receives the locked range, so no network call can occur in tests.

Coverage rule (the one interpretation this module fixes): a frame covers the window when
`min(open_time) <= start_ms` and `max(open_time) >= end_ms`, with duplicate timestamps
rejected. That is what detects a stale or truncated cache. It deliberately does NOT demand
a bar at exactly each endpoint, because a per-pair frame may legitimately lack an
individual bar while the shared timeline (the union across pairs) still spans the window.

KNOWN LIMITATION: span coverage cannot detect a cache that is complete at both ends but
gutted in the middle. Detecting interior gaps requires an expected-bar-grid and a market
calendar, i.e. the bar-validity policy that is deliberately NOT part of this module. Until
that lands, an interior hole passes these checks.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from bot.forex.oanda_data import load_or_fetch  # noqa: F401  (legacy path, kept importable)


def _safe(s: Any) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "-", str(s))


def exact_cache_path(data_cfg: Dict[str, Any], *, start_ms: int, end_ms: int) -> Path:
    """Identity-keyed CSV path for one locked window.

    Every component that changes the candle payload is in the filename, so a different
    instrument, granularity, price side, candle ALIGNMENT, or window can never collide
    with this file. The `w` marker also keeps these files disjoint from legacy caches.
    """
    d = Path(data_cfg.get("cache_dir", "data/forex_ohlcv/"))
    parts = [
        data_cfg["instrument"],
        data_cfg["granularity"],
        data_cfg.get("price", "BA"),
        f"a{int(data_cfg.get('alignment_hour_utc', 0))}",
        f"w{int(start_ms)}-{int(end_ms)}",
    ]
    return d / (f"{'__'.join(_safe(p) for p in parts)}.csv")


def _validate_window(start_ms: int, end_ms: int) -> None:
    if int(start_ms) >= int(end_ms):
        raise ValueError(f"locked window invalid: start_ms {start_ms} >= end_ms {end_ms}")


def _assert_source_ok(frame: pd.DataFrame, label: str, start_ms: int, end_ms: int) -> None:
    """Fail closed on an unusable source: empty, stale/truncated/late-starting, or carrying
    duplicate bar timestamps. Duplicates are rejected rather than silently de-duplicated —
    they would make the set-based shared timeline disagree with the per-pair row counts and
    make row order depend on sort stability.
    """
    if frame is None or len(frame) == 0:
        raise ValueError(f"{label}: coverage check failed — frame is empty")
    lo, hi = int(frame["open_time"].min()), int(frame["open_time"].max())
    if lo > int(start_ms) or hi < int(end_ms):
        raise ValueError(
            f"{label}: coverage check failed — data spans [{lo}, {hi}] which does not "
            f"cover the locked window [{start_ms}, {end_ms}]; refusing a stale or "
            f"truncated source"
        )
    n_dup = int(frame["open_time"].duplicated().sum())
    if n_dup:
        raise ValueError(f"{label}: {n_dup} duplicate open_time value(s); refusing an "
                         f"ambiguous source rather than de-duplicating silently")


def _trim(frame: pd.DataFrame, start_ms: int, end_ms: int) -> pd.DataFrame:
    """Deterministic inclusive trim, sorted, index reset — bars outside cannot leak in."""
    w = frame[(frame["open_time"] >= int(start_ms)) & (frame["open_time"] <= int(end_ms))]
    return w.sort_values("open_time").reset_index(drop=True)


def load_exact_window(data_cfg: Dict[str, Any], *, start_ms: int, end_ms: int,
                      fetch_fn: Optional[Callable[[int, int], pd.DataFrame]] = None
                      ) -> pd.DataFrame:
    """Load one instrument for exactly [start_ms, end_ms] (inclusive), or raise.

    Cache hit: read the identity-keyed CSV. Cache miss: call `fetch_fn(start_ms, end_ms)`
    once — the locked range is PASSED to the fetcher, never assumed by it — and write the
    result under that identity. Either way the payload must span the window before it is
    trimmed and returned.
    """
    _validate_window(start_ms, end_ms)
    path = exact_cache_path(data_cfg, start_ms=start_ms, end_ms=end_ms)
    label = f"{data_cfg['instrument']} {data_cfg['granularity']} [{start_ms}, {end_ms}]"
    if path.exists():
        frame = pd.read_csv(path)
        _assert_source_ok(frame, f"{label} cache {path.name}", start_ms, end_ms)
        return _trim(frame, start_ms, end_ms)
    if fetch_fn is None:
        raise RuntimeError(f"No cache at {path} and no fetch_fn provided for {label}.")
    frame = fetch_fn(int(start_ms), int(end_ms))
    _assert_source_ok(frame, f"{label} fetch", start_ms, end_ms)
    windowed = _trim(frame, start_ms, end_ms)      # trim BEFORE writing: the identity-keyed
    path.parent.mkdir(parents=True, exist_ok=True)  # file must not over-claim its contents
    windowed.to_csv(path, index=False)
    return windowed


def load_universe_exact(data_cfg: Dict[str, Any], universe: List[str], *,
                        start_ms: int, end_ms: int,
                        fetch_fn_factory: Optional[
                            Callable[[str, Dict[str, Any], int, int], pd.DataFrame]] = None
                        ) -> Dict[str, pd.DataFrame]:
    """Every pair on the SAME locked window, keys in universe order (deterministic).

    Each pair gets its own identity-keyed cache (per-variant isolation, CLAUDE.md §6) and
    its own coverage check, so one lagging pair raises instead of shrinking the window.
    """
    _validate_window(start_ms, end_ms)
    out: Dict[str, pd.DataFrame] = {}
    for pair in universe:
        pcfg = dict(data_cfg)
        pcfg["instrument"] = pair
        fetch_fn = None
        if fetch_fn_factory is not None:
            fetch_fn = (lambda s, e, p=pair, c=pcfg: fetch_fn_factory(p, c, s, e))
        out[pair] = load_exact_window(pcfg, start_ms=start_ms, end_ms=end_ms, fetch_fn=fetch_fn)
    return out


def split_at_boundary(frames: Dict[str, pd.DataFrame], *, start_ms: int, end_ms: int,
                      boundary_ms: int) -> Dict[str, Any]:
    """Split a locked window at an ABSOLUTE pre-registered boundary.

    train = open_time < boundary_ms, holdout = open_time >= boundary_ms, both trimmed to
    the inclusive window first. Nothing is derived from a ratio or from how much data
    happens to be present, so adding bars outside the window — or refreshing one pair —
    cannot move the window, the boundary, or either side's length.

    Raises on: start >= end; a pair that does not span the window; a boundary at/below the
    window start, beyond the window end, or absent from the shared timeline; an empty side.
    """
    _validate_window(start_ms, end_ms)
    if len(frames) < 2:
        raise ValueError(f"split_at_boundary: need >= 2 pairs, got {len(frames)}")
    boundary_ms = int(boundary_ms)
    if not (int(start_ms) < boundary_ms <= int(end_ms)):
        raise ValueError(
            f"boundary_ms {boundary_ms} is outside the locked window "
            f"({start_ms}, {end_ms}]; it must leave a non-empty train and holdout side"
        )

    windowed: Dict[str, pd.DataFrame] = {}
    timeline: set = set()
    for pair, df in frames.items():
        _assert_source_ok(df, f"pair {pair!r}", start_ms, end_ms)
        w = _trim(df, start_ms, end_ms)
        if len(w) == 0:
            raise ValueError(f"pair {pair!r}: empty after trimming to the locked window")
        windowed[pair] = w
        timeline.update(int(x) for x in w["open_time"].to_numpy("int64"))

    tl = np.array(sorted(timeline), dtype="int64")
    if boundary_ms not in timeline:
        raise ValueError(
            f"boundary_ms {boundary_ms} is absent from the shared timeline of "
            f"{len(tl)} in-window bars; a locked boundary must be a real bar timestamp"
        )

    train: Dict[str, pd.DataFrame] = {}
    holdout: Dict[str, pd.DataFrame] = {}
    train_bars_by_pair: Dict[str, int] = {}
    holdout_bars_by_pair: Dict[str, int] = {}
    for pair, w in windowed.items():
        tr = w[w["open_time"] < boundary_ms].reset_index(drop=True)
        ho = w[w["open_time"] >= boundary_ms].reset_index(drop=True)
        if len(tr) == 0 or len(ho) == 0:
            raise ValueError(f"pair {pair!r}: empty train ({len(tr)}) or holdout "
                             f"({len(ho)}) side at locked boundary {boundary_ms}")
        train[pair] = tr
        holdout[pair] = ho
        train_bars_by_pair[pair] = int(len(tr))
        holdout_bars_by_pair[pair] = int(len(ho))

    meta = {
        "start_ms": int(start_ms), "end_ms": int(end_ms), "boundary_ms": boundary_ms,
        "boundary_source": "locked_absolute",
        "timeline_len": int(len(tl)),
        "train_len": int(int((tl < boundary_ms).sum())),
        "holdout_len": int(int((tl >= boundary_ms).sum())),
        "train_bars_by_pair": train_bars_by_pair,
        "holdout_bars_by_pair": holdout_bars_by_pair,
    }
    return {"train": train, "holdout": holdout, "meta": meta}
