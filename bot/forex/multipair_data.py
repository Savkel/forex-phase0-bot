"""Multi-pair data layer on top of the existing single-instrument data layer.
Covers: multi-pair data loading (reusing oanda_data.load_or_fetch per pair, with
cache already isolated per instrument, CLAUDE.md §6), common-calendar intersection
across the universe, and the shared train/holdout split at one common timestamp
boundary. No network in tests: inject fetch_fn_factory."""
from __future__ import annotations
from typing import Any, Callable, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from bot.forex.oanda_data import load_or_fetch

def _pair_data_cfg(data_cfg: Dict[str, Any], pair: str) -> Dict[str, Any]:
    """A per-pair copy of data_cfg with instrument=pair (the source is NOT mutated),
    so load_or_fetch keys its cache on this pair alone -> per-pair cache isolation."""
    d = dict(data_cfg)
    d["instrument"] = pair
    return d

def load_universe(data_cfg: Dict[str, Any], universe: List[str], *,
                  fetch_fn_factory: Optional[Callable[[str, Dict[str, Any]], pd.DataFrame]] = None
                  ) -> Dict[str, pd.DataFrame]:
    """Load every configured pair into a deterministic {pair -> bars DataFrame}
    mapping (keys in universe order), each via its own isolated cache path.
    Raises RuntimeError if a pair has neither a cache nor a fetch_fn (missing
    data), and ValueError if a pair loads but is empty (0 rows). Preserves the
    columns produced by the existing OANDA parser. fetch_fn_factory(pair, pair_cfg)
    -> DataFrame is injected in tests so no OANDA network call ever occurs; a real
    run wires it to oanda_data.fetch_candles."""
    out: Dict[str, pd.DataFrame] = {}
    for pair in universe:
        pcfg = _pair_data_cfg(data_cfg, pair)
        fetch_fn = None
        if fetch_fn_factory is not None:
            fetch_fn = (lambda p=pair, c=pcfg: fetch_fn_factory(p, c))
        frame = load_or_fetch(pcfg, fetch_fn=fetch_fn)
        if frame is None or len(frame) == 0:
            raise ValueError(f"pair {pair!r}: loaded data is empty (0 rows); refusing to proceed")
        out[pair] = frame
    return out

def common_window(frames: Dict[str, pd.DataFrame]) -> Tuple[int, int]:
    """Shared calendar range across all pairs: (max of per-pair earliest open_time,
    min of per-pair latest open_time). Uses min/max (not positional iloc) so it is
    correct even if a pair's frame is not pre-sorted."""
    if not frames:
        raise ValueError("common_window: no frames provided")
    starts = [int(df["open_time"].min()) for df in frames.values()]
    ends = [int(df["open_time"].max()) for df in frames.values()]
    return max(starts), min(ends)

def shared_timeline(frames: Dict[str, pd.DataFrame], start_ms: int, end_ms: int) -> np.ndarray:
    """Sorted union of every pair's bar timestamps that fall in [start_ms, end_ms]."""
    ts: set = set()
    for df in frames.values():
        ot = df["open_time"].to_numpy("int64")
        ts.update(int(x) for x in ot if start_ms <= x <= end_ms)
    return np.array(sorted(ts), dtype="int64")

def split_common_window(frames: Dict[str, pd.DataFrame], holdout_frac: float = 0.35) -> Dict[str, Any]:
    """Trim every pair to the shared calendar window and split it at ONE common
    timestamp boundary (spec §4): the boundary sits at the (1 - holdout_frac)
    position of the shared timeline (the sorted union of in-window bar timestamps),
    so every pair's holdout covers the SAME recent calendar period and a pair that
    is missing a bar is tolerated. train = bars with open_time < boundary; holdout =
    bars with open_time >= boundary. Each pair is sorted by open_time first, so the
    result is deterministic and independent of input row order. Fails clearly on:
    fewer than 2 pairs, no overlapping calendar range, a pair empty after the
    intersection, or an empty train/holdout side."""
    if len(frames) < 2:
        raise ValueError(f"split_common_window: need >= 2 pairs, got {len(frames)}")
    if not 0.0 < float(holdout_frac) < 1.0:
        raise ValueError("split_common_window: holdout_frac must be in (0, 1)")
    start_ms, end_ms = common_window(frames)
    if start_ms > end_ms:
        raise ValueError(f"split_common_window: no overlapping calendar range "
                         f"(shared start {start_ms} > shared end {end_ms})")
    tl = shared_timeline(frames, start_ms, end_ms)
    if len(tl) < 2:
        raise ValueError("split_common_window: shared timeline too short to split "
                         "(need >= 2 shared bars)")
    cut_idx = int(round(len(tl) * (1.0 - float(holdout_frac))))
    if cut_idx <= 0:
        raise ValueError(f"split_common_window: train side would be empty at "
                         f"holdout_frac={holdout_frac}")
    if cut_idx >= len(tl):
        raise ValueError(f"split_common_window: holdout side would be empty at "
                         f"holdout_frac={holdout_frac}")
    boundary_ms = int(tl[cut_idx])
    train: Dict[str, pd.DataFrame] = {}
    holdout: Dict[str, pd.DataFrame] = {}
    train_bars_by_pair: Dict[str, int] = {}
    holdout_bars_by_pair: Dict[str, int] = {}
    for pair, df in frames.items():
        w = df[(df["open_time"] >= start_ms) & (df["open_time"] <= end_ms)]
        w = w.sort_values("open_time").reset_index(drop=True)
        if len(w) == 0:
            raise ValueError(f"pair {pair!r}: empty after intersection to the shared window")
        tr = w[w["open_time"] < boundary_ms].reset_index(drop=True)
        ho = w[w["open_time"] >= boundary_ms].reset_index(drop=True)
        if len(tr) == 0 or len(ho) == 0:
            raise ValueError(f"pair {pair!r}: empty train ({len(tr)}) or holdout "
                             f"({len(ho)}) side at boundary {boundary_ms}")
        train[pair] = tr
        holdout[pair] = ho
        train_bars_by_pair[pair] = int(len(tr))
        holdout_bars_by_pair[pair] = int(len(ho))
    meta = {"start_ms": start_ms, "end_ms": end_ms, "boundary_ms": boundary_ms,
            "timeline_len": int(len(tl)), "train_len": int(cut_idx),
            "holdout_len": int(len(tl) - cut_idx),
            "train_bars_by_pair": train_bars_by_pair,
            "holdout_bars_by_pair": holdout_bars_by_pair}
    return {"train": train, "holdout": holdout, "meta": meta}
