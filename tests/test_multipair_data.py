import numpy as np
import pandas as pd
import pytest
from bot.forex.multipair_data import load_universe, _pair_data_cfg

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
