import copy
import numpy as np
import pandas as pd
import pytest
from bot.forex.oanda_data import parse_candles, cache_path, load_or_fetch, fetch_candles

# A captured-shape OANDA v20 candles payload (UNIX time format, BA price).
# Two complete candles + one still-forming (complete=False) candle that must be dropped.
PAYLOAD = {
    "instrument": "EUR_USD", "granularity": "H4",
    "candles": [
        {"time": "1700000000.000000000", "volume": 10, "complete": True,
         "bid": {"o": "1.0000", "h": "1.0010", "l": "0.9990", "c": "1.0005"},
         "ask": {"o": "1.0002", "h": "1.0012", "l": "0.9992", "c": "1.0007"}},
        {"time": "1700014400.000000000", "volume": 12, "complete": True,
         "bid": {"o": "1.0005", "h": "1.0020", "l": "1.0000", "c": "1.0015"},
         "ask": {"o": "1.0007", "h": "1.0022", "l": "1.0002", "c": "1.0017"}},
        {"time": "1700028800.000000000", "volume": 5, "complete": False,
         "bid": {"o": "1.0015", "h": "1.0030", "l": "1.0010", "c": "1.0025"},
         "ask": {"o": "1.0017", "h": "1.0032", "l": "1.0012", "c": "1.0027"}},
    ],
}


class _FakeResp:
    def __init__(self, payload): self._p = payload
    def raise_for_status(self): pass
    def json(self): return self._p

class _FakeSession:
    """Stand-in for requests.Session so fetch_candles runs fully offline."""
    def __init__(self, payload):
        self._p = payload; self.calls = 0; self.headers = {}
        self.last_params = None; self.params_log = []      # capture request params for assertions
    def get(self, url, params=None, timeout=None):
        self.calls += 1
        self.last_params = params
        self.params_log.append(params)
        return _FakeResp(self._p)


# --- parse_candles: drop incomplete, build bid/ask + mid, ascending, fail-deterministic ---

def test_parse_candles_drops_incomplete_candles():
    df = parse_candles(PAYLOAD)
    assert len(df) == 2                                  # complete==False candle dropped
    assert bool(df["complete"].all())


def test_parse_candles_builds_bid_ask_and_mid_correctly():
    df = parse_candles(PAYLOAD)
    assert df["bid_o"].iloc[0] == 1.0000 and df["ask_o"].iloc[0] == 1.0002
    assert df["ask_c"].iloc[1] == 1.0017
    # mid = (bid+ask)/2, derived consistently from bid/ask
    assert abs(df["mid_o"].iloc[0] - (1.0000 + 1.0002) / 2) < 1e-12
    assert abs(df["mid_c"].iloc[1] - (1.0015 + 1.0017) / 2) < 1e-12
    for col in ("open_time", "bid_o", "bid_h", "bid_l", "bid_c",
                "ask_o", "ask_h", "ask_l", "ask_c",
                "mid_o", "mid_h", "mid_l", "mid_c", "volume", "complete"):
        assert col in df.columns


def test_parse_candles_returns_ascending_time_order():
    p = copy.deepcopy(PAYLOAD)
    p["candles"] = [p["candles"][1], p["candles"][0], p["candles"][2]]   # shuffled input order
    df = parse_candles(p)
    assert list(df["open_time"]) == sorted(df["open_time"])
    assert df["open_time"].iloc[0] < df["open_time"].iloc[1]


def test_parse_candles_malformed_fields_fail_deterministically():
    missing_bid = copy.deepcopy(PAYLOAD)
    missing_bid["candles"] = [{"time": "1700000000.0", "volume": 1, "complete": True,
                               "ask": {"o": "1", "h": "1", "l": "1", "c": "1"}}]
    with pytest.raises(KeyError):
        parse_candles(missing_bid)
    bad_number = copy.deepcopy(PAYLOAD)
    bad_number["candles"][0]["bid"]["o"] = "not_a_number"
    with pytest.raises(ValueError):
        parse_candles(bad_number)


# --- cache_path is per variant / instrument / granularity / date range ---

def test_cache_path_changes_per_variant(tmp_path):
    base = {"cache_dir": str(tmp_path), "instrument": "EUR_USD", "granularity": "H4", "price": "BA"}
    p0 = cache_path(base)
    assert cache_path(dict(base, instrument="GBP_USD")) != p0
    assert cache_path(dict(base, granularity="H1")) != p0
    assert cache_path(dict(base, price="M")) != p0
    # date range participates in the key, and different ranges never collide
    r1 = cache_path(dict(base, **{"from": "2024-01-01", "to": "2024-06-01"}))
    r2 = cache_path(dict(base, **{"from": "2024-01-01", "to": "2024-12-01"}))
    assert r1 != p0 and r2 != p0 and r1 != r2


# --- load_or_fetch: cache hit avoids fetch; miss calls fetch_fn + writes CSV ---

def test_load_or_fetch_uses_cache_without_calling_fetch(tmp_path):
    cfg = {"cache_dir": str(tmp_path), "instrument": "EUR_USD", "granularity": "H4", "price": "BA"}
    calls = {"n": 0}
    def fake():
        calls["n"] += 1
        return parse_candles(PAYLOAD)
    df1 = load_or_fetch(cfg, fetch_fn=fake)              # miss -> fetch + cache
    df2 = load_or_fetch(cfg, fetch_fn=fake)              # hit -> no fetch
    assert calls["n"] == 1
    assert len(df1) == len(df2) == 2


def test_load_or_fetch_fetches_on_miss_and_writes_csv(tmp_path):
    cfg = {"cache_dir": str(tmp_path), "instrument": "EUR_USD", "granularity": "H4", "price": "BA"}
    assert not cache_path(cfg).exists()
    df = load_or_fetch(cfg, fetch_fn=lambda: parse_candles(PAYLOAD))
    assert cache_path(cfg).exists()                      # CSV written on miss
    assert len(df) == 2


def test_load_or_fetch_raises_when_no_cache_and_no_fetch(tmp_path):
    cfg = {"cache_dir": str(tmp_path), "instrument": "EUR_USD", "granularity": "H4", "price": "BA"}
    with pytest.raises(RuntimeError):
        load_or_fetch(cfg, fetch_fn=None)


def test_cache_roundtrip_preserves_columns_and_values(tmp_path):
    cfg = {"cache_dir": str(tmp_path), "instrument": "EUR_USD", "granularity": "H4", "price": "BA"}
    df1 = load_or_fetch(cfg, fetch_fn=lambda: parse_candles(PAYLOAD))    # miss -> writes
    def must_not_fetch():
        raise AssertionError("cache hit must not call fetch_fn")
    df2 = load_or_fetch(cfg, fetch_fn=must_not_fetch)    # hit -> read from CSV
    for col in ("open_time", "bid_o", "ask_c", "mid_o", "mid_c", "volume", "complete"):
        assert col in df2.columns
    assert list(df2["open_time"]) == list(df1["open_time"])
    assert np.allclose(df2["mid_c"].astype(float), df1["mid_c"].astype(float))
    assert df2["bid_o"].iloc[0] == df1["bid_o"].iloc[0]


# --- live fetch_candles: env-only creds, clear failure when missing, offline via injected session ---

def test_fetch_candles_requires_env_token_and_fails_clearly(monkeypatch):
    monkeypatch.delenv("OANDA_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="OANDA_API_TOKEN"):
        fetch_candles({"instrument": "EUR_USD", "granularity": "H4", "price": "BA"})


def test_fetch_candles_uses_injected_session_no_network(monkeypatch):
    monkeypatch.setenv("OANDA_API_TOKEN", "dummy-token-for-test-only")
    sess = _FakeSession(PAYLOAD)
    df = fetch_candles({"instrument": "EUR_USD", "granularity": "H4", "price": "BA"}, session=sess)
    assert sess.calls >= 1                               # used the injected session, not a real one
    assert len(df) == 2                                  # incomplete dropped
    assert list(df["open_time"]) == sorted(df["open_time"])


# --- B2: configured candle alignment is actually sent to OANDA (no silent no-op) ---

def test_fetch_candles_sends_configured_utc_alignment(monkeypatch):
    monkeypatch.setenv("OANDA_API_TOKEN", "dummy-token-for-test-only")
    sess = _FakeSession(PAYLOAD)
    fetch_candles({"instrument": "EUR_USD", "granularity": "H4", "price": "BA",
                   "alignment_hour_utc": 0}, session=sess)
    # every page request must carry the alignment contract, not just the first
    for p in sess.params_log:
        assert p["alignmentTimezone"] == "UTC"           # candles aligned to UTC per the config contract
        assert p["dailyAlignment"] == 0                  # = configured alignment_hour_utc


def test_fetch_candles_honors_nonzero_alignment_hour(monkeypatch):
    monkeypatch.setenv("OANDA_API_TOKEN", "dummy-token-for-test-only")
    sess = _FakeSession(PAYLOAD)
    fetch_candles({"instrument": "EUR_USD", "granularity": "D", "price": "BA",
                   "alignment_hour_utc": 17}, session=sess)
    assert sess.last_params["dailyAlignment"] == 17      # configured hour flows through to the request
    assert sess.last_params["alignmentTimezone"] == "UTC"
