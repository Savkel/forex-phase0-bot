import numpy as np
import pandas as pd
import pytest
from bot.forex.multipair_data import (
    load_universe, _pair_data_cfg,
    common_window, shared_timeline, split_common_window)

def _frame(start_ms, n):
    ot = np.arange(n, dtype="int64") * 14400000 + start_ms
    px = np.linspace(1.0, 1.1, n)
    return pd.DataFrame({
        "open_time": ot, "time": [f"t{i}" for i in range(n)],
        "bid_o": px, "bid_h": px, "bid_l": px, "bid_c": px,
        "ask_o": px + 0.0002, "ask_h": px + 0.0002, "ask_l": px + 0.0002, "ask_c": px + 0.0002,
        "volume": [1]*n, "complete": [True]*n})

def test_pair_data_cfg_sets_instrument_without_mutating_source():
    base = {"granularity": "H4", "cache_dir": "x/"}
    d = _pair_data_cfg(base, "EUR_USD")
    assert d["instrument"] == "EUR_USD" and "instrument" not in base

def test_load_universe_returns_deterministic_frame_per_pair_via_injected_fetch(tmp_path):
    calls = []
    def factory(pair, cfg):
        calls.append(pair)
        return _frame(0, 30)
    data_cfg = {"granularity": "H4", "price": "BA", "cache_dir": str(tmp_path) + "/"}
    universe = ["EUR_USD", "USD_JPY", "GBP_USD"]
    frames = load_universe(data_cfg, universe, fetch_fn_factory=factory)
    assert list(frames) == universe                  # deterministic, pair-keyed, in universe order
    assert sorted(calls) == sorted(universe)          # each pair fetched exactly once
    assert len(frames["EUR_USD"]) == 30

def test_each_pair_receives_correct_instrument_in_cfg(tmp_path):
    seen = {}
    def factory(pair, cfg):
        seen[pair] = cfg.get("instrument")
        return _frame(0, 30)
    data_cfg = {"granularity": "H4", "price": "BA", "cache_dir": str(tmp_path) + "/"}
    load_universe(data_cfg, ["EUR_USD", "USD_JPY"], fetch_fn_factory=factory)
    assert seen == {"EUR_USD": "EUR_USD", "USD_JPY": "USD_JPY"}

def test_load_universe_isolates_cache_per_pair(tmp_path):
    data_cfg = {"granularity": "H4", "price": "BA", "cache_dir": str(tmp_path) + "/"}
    load_universe(data_cfg, ["EUR_USD", "USD_JPY"],
                  fetch_fn_factory=lambda p, c: _frame(0, 30))
    written = sorted(x.name for x in tmp_path.glob("*.csv"))
    assert any("EUR_USD" in n for n in written)
    assert any("USD_JPY" in n for n in written)
    assert len(written) == 2                          # one isolated file per pair, none shared
    assert all(("EUR_USD" in n) or ("USD_JPY" in n) for n in written)

def test_missing_pair_data_fails_deterministically(tmp_path):
    # no cache file exists AND no fetch_fn -> the pair cannot be produced
    data_cfg = {"granularity": "H4", "price": "BA", "cache_dir": str(tmp_path) + "/"}
    with pytest.raises(RuntimeError):
        load_universe(data_cfg, ["EUR_USD"], fetch_fn_factory=None)

def test_empty_pair_data_fails_deterministically(tmp_path):
    data_cfg = {"granularity": "H4", "price": "BA", "cache_dir": str(tmp_path) + "/"}
    with pytest.raises(ValueError, match="EUR_USD"):
        load_universe(data_cfg, ["EUR_USD"], fetch_fn_factory=lambda p, c: _frame(0, 0))

# ---- Task 3: common calendar intersection + shared train/holdout split ----

def _frame_ts(times_ms):
    """Bars frame at explicit open_time stamps (for window/split tests)."""
    n = len(times_ms)
    px = np.linspace(1.0, 1.1, n) if n else np.array([])
    return pd.DataFrame({
        "open_time": np.asarray(times_ms, dtype="int64"),
        "time": [f"t{i}" for i in range(n)],
        "bid_o": px, "bid_h": px, "bid_l": px, "bid_c": px,
        "ask_o": px, "ask_h": px, "ask_l": px, "ask_c": px,
        "volume": [1]*n, "complete": [True]*n})

def test_common_window_is_max_start_min_end():
    a = _frame_ts([0, 10, 20, 30, 40])
    b = _frame_ts([10, 20, 30, 40, 50])
    start, end = common_window({"A": a, "B": b})
    assert start == 10 and end == 40

def test_shared_timeline_is_sorted_union_within_window():
    a = _frame_ts([10, 20, 30, 40])
    b = _frame_ts([10, 25, 30, 40])
    tl = shared_timeline({"A": a, "B": b}, 10, 40)
    assert tl.tolist() == [10, 20, 25, 30, 40]

def test_all_pairs_trimmed_to_common_shared_range():
    a = _frame_ts([0, 10, 20, 30, 40, 50])
    b = _frame_ts([20, 30, 40, 50, 60, 70])
    out = split_common_window({"A": a, "B": b}, holdout_frac=0.35)
    for p in ("A", "B"):
        allbars = pd.concat([out["train"][p], out["holdout"][p]])["open_time"]
        assert allbars.min() >= 20 and allbars.max() <= 50
    assert out["meta"]["start_ms"] == 20 and out["meta"]["end_ms"] == 50

def test_all_pairs_share_identical_train_and_holdout_ranges():
    a = _frame_ts(list(range(0, 100, 10)))
    b = _frame_ts(list(range(0, 100, 10)))
    out = split_common_window({"A": a, "B": b}, holdout_frac=0.3)
    ta, tb = out["train"]["A"]["open_time"], out["train"]["B"]["open_time"]
    ha, hb = out["holdout"]["A"]["open_time"], out["holdout"]["B"]["open_time"]
    assert ta.iloc[0] == tb.iloc[0] and ta.iloc[-1] == tb.iloc[-1]
    assert ha.iloc[0] == hb.iloc[0] and ha.iloc[-1] == hb.iloc[-1]

def test_split_uses_one_common_boundary_not_per_pair_fraction():
    a = _frame_ts(list(range(0, 100, 10)))
    b = _frame_ts([0, 30, 60, 90])
    out = split_common_window({"A": a, "B": b}, holdout_frac=0.3)
    bnd = out["meta"]["boundary_ms"]
    for p in ("A", "B"):
        assert (out["train"][p]["open_time"] < bnd).all()
        assert (out["holdout"][p]["open_time"] >= bnd).all()
    assert bnd == 70

def test_latest_fraction_is_holdout():
    f = _frame_ts(list(range(0, 100, 10)))
    out = split_common_window({"A": f, "B": f}, holdout_frac=0.3)
    assert out["meta"]["boundary_ms"] == 70
    assert out["holdout"]["A"]["open_time"].tolist() == [70, 80, 90]
    assert out["train"]["A"]["open_time"].tolist() == [0, 10, 20, 30, 40, 50, 60]

def test_default_holdout_frac_is_035():
    f = _frame_ts(list(range(0, 100, 5)))       # 20 bars
    out = split_common_window({"A": f, "B": f})  # no holdout_frac -> default 0.35
    assert out["meta"]["train_len"] == 13 and out["meta"]["holdout_len"] == 7

def test_split_is_deterministic_on_unsorted_input():
    ordered = list(range(0, 100, 10))
    shuffled = [50, 0, 90, 30, 70, 10, 80, 20, 60, 40]
    a_sorted = _frame_ts(ordered)
    a_shuf = _frame_ts(shuffled)
    out1 = split_common_window({"A": a_sorted, "B": a_sorted}, holdout_frac=0.3)
    out2 = split_common_window({"A": a_shuf, "B": a_shuf}, holdout_frac=0.3)
    assert out1["meta"] == out2["meta"]
    assert out2["train"]["A"]["open_time"].tolist() == [0, 10, 20, 30, 40, 50, 60]
    assert out2["holdout"]["A"]["open_time"].tolist() == [70, 80, 90]

def test_split_fails_on_no_calendar_overlap():
    a = _frame_ts([0, 10, 20, 30])
    b = _frame_ts([100, 110, 120, 130])
    with pytest.raises(ValueError, match="overlap"):
        split_common_window({"A": a, "B": b}, holdout_frac=0.3)

def test_split_fails_when_fewer_than_two_pairs():
    f = _frame_ts(list(range(0, 100, 10)))
    with pytest.raises(ValueError, match="2 pairs"):
        split_common_window({"A": f}, holdout_frac=0.3)

def test_split_fails_when_holdout_side_would_be_empty():
    f = _frame_ts(list(range(0, 100, 10)))
    with pytest.raises(ValueError, match="holdout side would be empty"):
        split_common_window({"A": f, "B": f}, holdout_frac=0.001)

def test_split_fails_when_train_side_would_be_empty():
    f = _frame_ts(list(range(0, 100, 10)))
    with pytest.raises(ValueError, match="train side would be empty"):
        split_common_window({"A": f, "B": f}, holdout_frac=0.999)

def test_split_meta_records_window_and_per_pair_bar_counts():
    a = _frame_ts(list(range(0, 100, 10)))
    b = _frame_ts([0, 10, 20, 30, 50, 60, 70, 80, 90])   # missing 40
    out = split_common_window({"A": a, "B": b}, holdout_frac=0.3)
    m = out["meta"]
    assert m["start_ms"] == 0 and m["end_ms"] == 90 and m["boundary_ms"] == 70
    assert m["train_bars_by_pair"]["A"] == 7 and m["holdout_bars_by_pair"]["A"] == 3
    assert m["train_bars_by_pair"]["B"] == 6 and m["holdout_bars_by_pair"]["B"] == 3
    for p in ("A", "B"):
        assert m["train_bars_by_pair"][p] == len(out["train"][p])
        assert m["holdout_bars_by_pair"][p] == len(out["holdout"][p])

def test_split_tolerates_a_missing_bar_in_one_pair():
    a = _frame_ts([0, 10, 20, 30, 40, 50, 60, 70, 80, 90])
    b = _frame_ts([0, 10, 20, 30, 50, 60, 70, 80, 90])   # missing 40
    out = split_common_window({"A": a, "B": b}, holdout_frac=0.3)
    bnd = out["meta"]["boundary_ms"]
    assert (out["holdout"]["B"]["open_time"] >= bnd).all()
    assert (out["train"]["B"]["open_time"] < bnd).all()
