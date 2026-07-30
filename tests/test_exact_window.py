"""M1+M2: exact research-window + absolute split-boundary locking.

These tests exist because the legacy path let a single stale cache silently decide the
common window AND the train/holdout boundary (B4). The locked path must be immune: the
window and boundary are explicit inputs, cache identity carries every field that changes
candle output, and a cache that does not span the locked window is rejected rather than
quietly used. No network: fetch is always injected.
"""
import pandas as pd
import pytest

from bot.forex.exact_window import (
    exact_cache_path,
    load_exact_window,
    load_universe_exact,
    split_at_boundary,
)
from bot.forex.oanda_data import cache_path as legacy_cache_path
from bot.forex.multipair_data import split_common_window

H4 = 4 * 3600 * 1000


def _bars(start_ms, n, step=H4):
    """Minimal engine-shaped frame: only open_time is load-bearing for windowing."""
    ts = [start_ms + i * step for i in range(n)]
    return pd.DataFrame({
        "open_time": ts,
        "mid_o": [1.0] * n,
        "volume": [100] * n,
    })


def _cfg(tmp_path, **over):
    cfg = {"instrument": "EUR_USD", "granularity": "H4", "price": "BA",
           "alignment_hour_utc": 0, "cache_dir": str(tmp_path)}
    cfg.update(over)
    return cfg


# --- cache identity -------------------------------------------------------------------

def test_cache_identity_includes_every_output_changing_field(tmp_path):
    base = dict(cfg=_cfg(tmp_path), start_ms=1000, end_ms=9000)
    p = exact_cache_path(base["cfg"], start_ms=1000, end_ms=9000)
    variants = {
        "same": exact_cache_path(_cfg(tmp_path), start_ms=1000, end_ms=9000),
        "instrument": exact_cache_path(_cfg(tmp_path, instrument="GBP_USD"), start_ms=1000, end_ms=9000),
        "granularity": exact_cache_path(_cfg(tmp_path, granularity="M15"), start_ms=1000, end_ms=9000),
        "price": exact_cache_path(_cfg(tmp_path, price="M"), start_ms=1000, end_ms=9000),
        "alignment": exact_cache_path(_cfg(tmp_path, alignment_hour_utc=21), start_ms=1000, end_ms=9000),
        "start": exact_cache_path(_cfg(tmp_path), start_ms=2000, end_ms=9000),
        "end": exact_cache_path(_cfg(tmp_path), start_ms=1000, end_ms=8000),
    }
    assert variants.pop("same") == p                      # deterministic for identical inputs
    for field, other in variants.items():
        assert other != p, f"cache identity ignores {field}"
    assert len(set(variants.values()) | {p}) == 7         # all distinct, no collisions

def test_exact_cache_path_is_disjoint_from_legacy_path(tmp_path):
    cfg = _cfg(tmp_path)
    assert exact_cache_path(cfg, start_ms=1000, end_ms=9000) != legacy_cache_path(cfg)


# --- fail-closed coverage -------------------------------------------------------------

def test_truncated_cache_is_rejected_not_silently_used(tmp_path):
    # This is the exact B4 failure mode: a cache ending before the locked end.
    cfg = _cfg(tmp_path)
    start, end = 0, 10 * H4
    _bars(start, 6).to_csv(exact_cache_path(cfg, start_ms=start, end_ms=end), index=False)
    with pytest.raises(ValueError, match="coverage"):
        load_exact_window(cfg, start_ms=start, end_ms=end)

def test_cache_starting_after_locked_start_is_rejected(tmp_path):
    cfg = _cfg(tmp_path)
    start, end = 0, 10 * H4
    _bars(2 * H4, 20).to_csv(exact_cache_path(cfg, start_ms=start, end_ms=end), index=False)
    with pytest.raises(ValueError, match="coverage"):
        load_exact_window(cfg, start_ms=start, end_ms=end)

def test_locked_range_is_passed_to_the_fetcher(tmp_path):
    cfg = _cfg(tmp_path)
    start, end = 4 * H4, 12 * H4
    seen = {}

    def fetch_fn(s, e):
        seen["range"] = (s, e)
        return _bars(0, 30)

    load_exact_window(cfg, start_ms=start, end_ms=end, fetch_fn=fetch_fn)
    assert seen["range"] == (start, end)
    assert exact_cache_path(cfg, start_ms=start, end_ms=end).exists()


# --- deterministic trimming -----------------------------------------------------------

def test_written_cache_contains_exactly_the_locked_window(tmp_path):
    # The filename claims a window, so the file must not over-claim: a wider fetch is
    # trimmed BEFORE it is written, otherwise the cache contents contradict its identity.
    cfg = _cfg(tmp_path)
    start, end = 5 * H4, 9 * H4
    load_exact_window(cfg, start_ms=start, end_ms=end, fetch_fn=lambda s, e: _bars(0, 40))
    on_disk = pd.read_csv(exact_cache_path(cfg, start_ms=start, end_ms=end))
    assert int(on_disk["open_time"].min()) == start
    assert int(on_disk["open_time"].max()) == end
    assert len(on_disk) == 5

def test_duplicate_bar_timestamps_are_rejected(tmp_path):
    # Duplicates would make the set-based timeline disagree with the per-pair row counts
    # and make row order sort-dependent. Fail closed rather than silently de-duplicate.
    cfg = _cfg(tmp_path)
    start, end = 0, 5 * H4
    dup = pd.concat([_bars(0, 6), _bars(2 * H4, 1)], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate"):
        load_exact_window(cfg, start_ms=start, end_ms=end, fetch_fn=lambda s, e: dup)
    with pytest.raises(ValueError, match="duplicate"):
        split_at_boundary({"EUR_USD": dup, "GBP_USD": _bars(0, 6)},
                          start_ms=start, end_ms=end, boundary_ms=3 * H4)

def test_cache_hit_path_also_trims_a_wider_file(tmp_path):
    # Guard for the read side: a wider file placed by hand must still yield the window.
    cfg = _cfg(tmp_path)
    start, end = 5 * H4, 9 * H4
    _bars(0, 40).to_csv(exact_cache_path(cfg, start_ms=start, end_ms=end), index=False)
    got = load_exact_window(cfg, start_ms=start, end_ms=end)
    assert list(got["open_time"]) == [start + i * H4 for i in range(5)]

def test_extra_bars_outside_the_window_are_trimmed_away(tmp_path):
    cfg = _cfg(tmp_path)
    start, end = 5 * H4, 9 * H4
    got = load_exact_window(cfg, start_ms=start, end_ms=end, fetch_fn=lambda s, e: _bars(0, 40))
    assert list(got["open_time"]) == [start + i * H4 for i in range(5)]   # inclusive both ends


# --- absolute boundary split ----------------------------------------------------------

def _universe(extra_for=None, extra_n=0):
    """Two pairs on a shared H4 grid; optionally extend ONE pair with later bars."""
    frames = {"EUR_USD": _bars(0, 20), "GBP_USD": _bars(0, 20)}
    if extra_for:
        frames[extra_for] = _bars(0, 20 + extra_n)
    return frames

def test_split_uses_the_supplied_absolute_boundary():
    frames = _universe()
    res = split_at_boundary(frames, start_ms=0, end_ms=19 * H4, boundary_ms=12 * H4)
    m = res["meta"]
    assert m["boundary_ms"] == 12 * H4
    assert m["train_len"] == 12 and m["holdout_len"] == 8
    for p in frames:
        assert int(res["train"][p]["open_time"].max()) == 11 * H4
        assert int(res["holdout"][p]["open_time"].min()) == 12 * H4

def test_extra_later_bars_cannot_move_window_boundary_or_counts():
    a = split_at_boundary(_universe(), start_ms=0, end_ms=19 * H4, boundary_ms=12 * H4)["meta"]
    b = split_at_boundary(_universe("EUR_USD", 50), start_ms=0, end_ms=19 * H4,
                          boundary_ms=12 * H4)["meta"]
    assert a == b, "refreshing one pair moved the locked split"

def test_refreshing_one_stale_pair_moves_the_legacy_split_but_never_the_locked_one():
    # Reproduces B4 in miniature: GBP_USD is stale (ends early), so under the legacy
    # ratio split it alone decides end_ms AND the boundary. Refreshing it moves both.
    stale = {"EUR_USD": _bars(0, 20), "GBP_USD": _bars(0, 14)}
    fresh = {"EUR_USD": _bars(0, 20), "GBP_USD": _bars(0, 20)}
    lo = split_common_window(stale, holdout_frac=0.35)["meta"]
    hi = split_common_window(fresh, holdout_frac=0.35)["meta"]
    assert lo["boundary_ms"] != hi["boundary_ms"]        # legacy: one stale cache moves the split
    assert lo["end_ms"] != hi["end_ms"]
    # Locked: the stale universe cannot silently shrink the window — it fails closed...
    with pytest.raises(ValueError, match="coverage"):
        split_at_boundary(stale, start_ms=0, end_ms=19 * H4, boundary_ms=12 * H4)
    # ...and the refreshed universe yields exactly the pre-registered split.
    m = split_at_boundary(fresh, start_ms=0, end_ms=19 * H4, boundary_ms=12 * H4)["meta"]
    assert (m["start_ms"], m["end_ms"], m["boundary_ms"]) == (0, 19 * H4, 12 * H4)
    assert m["train_len"] == 12 and m["holdout_len"] == 8

def test_boundary_outside_the_locked_window_is_rejected():
    frames = _universe()
    for bad in (0, 25 * H4):        # at/below start -> empty train; beyond end -> empty holdout
        with pytest.raises(ValueError, match="boundary"):
            split_at_boundary(frames, start_ms=0, end_ms=19 * H4, boundary_ms=bad)

def test_boundary_absent_from_the_shared_timeline_is_rejected():
    frames = _universe()
    with pytest.raises(ValueError, match="boundary"):
        split_at_boundary(frames, start_ms=0, end_ms=19 * H4, boundary_ms=12 * H4 + 1)

def test_start_not_before_end_is_rejected():
    frames = _universe()
    with pytest.raises(ValueError, match="window"):
        split_at_boundary(frames, start_ms=9 * H4, end_ms=9 * H4, boundary_ms=9 * H4)

def test_pair_missing_the_locked_window_is_rejected():
    frames = {"EUR_USD": _bars(0, 20), "GBP_USD": _bars(0, 8)}     # GBP ends early
    with pytest.raises(ValueError, match="coverage"):
        split_at_boundary(frames, start_ms=0, end_ms=19 * H4, boundary_ms=12 * H4)


# --- universe loader ------------------------------------------------------------------

def test_load_universe_exact_is_deterministic_and_range_locked(tmp_path):
    cfg = _cfg(tmp_path)
    start, end = 5 * H4, 15 * H4
    frames = load_universe_exact(cfg, ["EUR_USD", "GBP_USD"], start_ms=start, end_ms=end,
                                 fetch_fn_factory=lambda p, c, s, e: _bars(0, 40))
    assert list(frames) == ["EUR_USD", "GBP_USD"]
    for p, f in frames.items():
        assert int(f["open_time"].min()) == start and int(f["open_time"].max()) == end
    # per-pair isolation: each pair got its own identity-keyed cache file
    assert exact_cache_path(dict(cfg, instrument="GBP_USD"), start_ms=start, end_ms=end).exists()


# --- legacy must not change -----------------------------------------------------------

def test_legacy_paths_are_untouched(tmp_path):
    cfg = _cfg(tmp_path)
    assert legacy_cache_path(cfg).name == "EUR_USD__H4__BA.csv"     # still no range component
    m = split_common_window(_universe(), holdout_frac=0.35)["meta"]
    assert m["boundary_ms"] == 13 * H4                              # still ratio-derived
    assert m["train_len"] == 13 and m["holdout_len"] == 7
