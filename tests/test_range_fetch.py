"""Range-locked OANDA fetching: pagination that cannot silently truncate history.

The legacy fetcher pages backward with `to`/`count` and stops on `len(page) < 4999`,
which conflates "end of history" with "a page that happened to be short" (a gap, a
low-liquidity stretch, or incomplete candles being dropped). A locked research window
cannot tolerate that: a silently short fetch would be written into an identity-keyed cache
and then look authoritative. These tests pin the termination and duplicate rules.

No network anywhere: every request goes through an injected session stub.
"""
import pandas as pd
import pytest

from bot.forex.range_fetch import fetch_range, make_range_fetch_fn
from bot.forex.exact_window import exact_cache_path, load_exact_window
from bot.forex.oanda_data import fetch_candles

H4 = 4 * 3600 * 1000
T0 = 1_600_000_000_000 - (1_600_000_000_000 % H4)      # H4-aligned base


def _c(ms, *, complete=True, px=1.0):
    s = f"{px:.5f}"
    return {"time": f"{ms / 1000:.6f}", "complete": complete, "volume": 10,
            "bid": {"o": s, "h": s, "l": s, "c": s},
            "ask": {"o": s, "h": s, "l": s, "c": s}}


def _series(n, *, start=T0, incomplete_at=(), px=1.0, step=H4):
    return [_c(start + i * step, complete=(i not in incomplete_at), px=px) for i in range(n)]


class _Resp:
    def __init__(self, payload): self._p = payload
    def raise_for_status(self): pass
    def json(self): return self._p


class _RangeSession:
    """Serves the newest `count` candles below the requested `to`.

    `to` is EXCLUSIVE, which is what the live v20 endpoint was measured to do: a request
    with `to` = a bar's timestamp returns bars strictly older than it, so consecutive
    pages abut instead of overlapping. `inclusive_to=True` models the opposite convention
    so the duplicate-collapsing path stays exercised.

    `short_calls` forces an artificially short page (without ending history) so the
    fetcher cannot use page length as a termination signal.
    """
    def __init__(self, candles, *, short_calls=(), oldest_first=False, empty=False,
                 overshoot=False, inclusive_to=False):
        self.all = sorted(candles, key=lambda c: float(c["time"]))
        self.short_calls = set(short_calls)
        self.oldest_first = oldest_first      # simulate a server anchoring at the oldest bar
        self.empty = empty
        self.overshoot = overshoot            # simulate a server ignoring the `to` bound
        self.inclusive_to = inclusive_to
        self.calls = 0
        self.headers = {}
        self.params_log = []
        self.returned = []                    # raw candle times served, per page

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        self.params_log.append(params)
        # The legacy pager sends neither `from` nor (on its first call) `to`; tolerate that
        # so this stub can serve both clients without changing either one's contract.
        def _bound(key, default):
            raw = params.get(key)
            try:
                return float(raw)
            except (TypeError, ValueError):
                return default
        lo, hi = _bound("from", float("-inf")), _bound("to", float("inf"))
        if self.empty:
            self.returned.append([])
            return _Resp({"candles": []})
        if self.overshoot:
            hi = float("inf")                 # ignores the requested upper bound
        below = (lambda t: t <= hi) if self.inclusive_to else (lambda t: t < hi)
        sel = [c for c in self.all if lo <= float(c["time"]) and below(float(c["time"]))]
        n = int(params.get("count", 5000))
        sel = sel[:n] if self.oldest_first else sel[-n:]
        if self.calls in self.short_calls:
            sel = sel[-2:] if len(sel) > 2 else sel
        self.returned.append([int(round(float(c["time"]) * 1000)) for c in sel])
        return _Resp({"candles": sel})


@pytest.fixture(autouse=True)
def _token(monkeypatch):
    monkeypatch.setenv("OANDA_API_TOKEN", "dummy-token-for-test-only")


def _cfg(**over):
    cfg = {"instrument": "EUR_USD", "granularity": "H4", "price": "BA", "alignment_hour_utc": 0}
    cfg.update(over)
    return cfg


# --- pagination termination -----------------------------------------------------------

def test_multiple_backward_pages_reach_the_locked_start():
    sess = _RangeSession(_series(12))
    df = fetch_range(_cfg(), start_ms=T0, end_ms=T0 + 11 * H4, session=sess, page_size=5)
    assert sess.calls >= 3                                   # 12 candles / 5 per page
    assert list(df["open_time"]) == [T0 + i * H4 for i in range(12)]

def test_a_short_intermediate_page_does_not_end_pagination():
    # Page 2 comes back short. Under the legacy `len(page) < count` rule this would stop
    # and silently return a truncated history.
    sess = _RangeSession(_series(12), short_calls=(2,))
    df = fetch_range(_cfg(), start_ms=T0, end_ms=T0 + 11 * H4, session=sess, page_size=5)
    assert len(df) == 12
    assert int(df["open_time"].min()) == T0

def test_incomplete_candles_do_not_stop_pagination_or_truncate():
    # Candles 4..7 are still forming: they are dropped from the DATA but must still drive
    # the paging cursor, otherwise a fully-incomplete page looks like the end of history.
    sess = _RangeSession(_series(12, incomplete_at=(4, 5, 6, 7)))
    df = fetch_range(_cfg(), start_ms=T0, end_ms=T0 + 11 * H4, session=sess, page_size=4)
    assert int(df["open_time"].min()) == T0                  # reached the locked start
    assert len(df) == 8                                      # four incomplete dropped
    assert all(bool(x) for x in df["complete"])

def test_history_ending_after_requested_start_fails_closed():
    sess = _RangeSession(_series(6, start=T0 + 6 * H4))       # nothing before T0+6*H4
    with pytest.raises(ValueError, match="coverage"):
        fetch_range(_cfg(), start_ms=T0, end_ms=T0 + 11 * H4, session=sess, page_size=4)


def test_a_server_anchored_at_the_oldest_candle_fails_closed_not_silently_short():
    # If the live API anchors a `from`-bearing request at the OLDEST candle instead of the
    # newest, page 1 already satisfies "start reached" while covering only the old end of
    # the window. That must raise, never return a series truncated at the recent end.
    sess = _RangeSession(_series(40), oldest_first=True)
    with pytest.raises(ValueError, match="coverage"):
        fetch_range(_cfg(), start_ms=T0, end_ms=T0 + 39 * H4, session=sess, page_size=5)

def test_an_immediately_empty_response_fails_closed():
    sess = _RangeSession(_series(12), empty=True)
    with pytest.raises(ValueError, match="coverage"):
        fetch_range(_cfg(), start_ms=T0, end_ms=T0 + 11 * H4, session=sess, page_size=5)


# --- duplicate / ordering rules -------------------------------------------------------

def test_identical_page_boundary_overlap_is_deduplicated():
    # Under an INCLUSIVE-`to` server each page repeats the previous cursor bar. The live
    # endpoint is exclusive, but the collapsing path must stay correct: a repeat whose
    # values all match is a paging artifact, not data.
    sess = _RangeSession(_series(12), inclusive_to=True)
    df = fetch_range(_cfg(), start_ms=T0, end_ms=T0 + 11 * H4, session=sess, page_size=5)
    assert sess.calls >= 3
    assert not df["open_time"].duplicated().any()            # overlap collapsed
    assert len(df) == 12

def test_conflicting_duplicate_timestamps_fail_closed():
    # Same timestamp, different price: not a page-boundary artifact — a data conflict.
    bad = _series(12) + [_c(T0 + 5 * H4, px=1.5)]
    sess = _RangeSession(bad)
    with pytest.raises(ValueError, match="conflict"):
        fetch_range(_cfg(), start_ms=T0, end_ms=T0 + 11 * H4, session=sess, page_size=5)

def test_result_is_sorted_and_trimmed_inclusively():
    sess = _RangeSession(_series(20))
    lo, hi = T0 + 5 * H4, T0 + 12 * H4
    df = fetch_range(_cfg(), start_ms=lo, end_ms=hi, session=sess, page_size=4)
    assert list(df["open_time"]) == sorted(df["open_time"])
    assert int(df["open_time"].min()) == lo and int(df["open_time"].max()) == hi
    assert len(df) == 8                                      # inclusive on both ends


# --- request carries only the locked range -------------------------------------------

def test_no_request_combines_count_with_both_from_and_to():
    # OANDA v20 rejects/reinterprets `count` alongside both `from` and `to`. Backward
    # paging must therefore be `to` + `count` only; `start_ms` stays a LOCAL bound used
    # for stopping, coverage validation and trimming — it is never sent.
    sess = _RangeSession(_series(12))
    fetch_range(_cfg(), start_ms=T0, end_ms=T0 + 11 * H4, session=sess, page_size=5)
    assert sess.params_log
    for p in sess.params_log:
        assert "from" not in p
        assert not ("count" in p and "from" in p and "to" in p)

def test_every_paginated_request_carries_to_and_count_and_the_alignment_contract():
    sess = _RangeSession(_series(12))
    hi = T0 + 11 * H4
    fetch_range(_cfg(alignment_hour_utc=0), start_ms=T0, end_ms=hi, session=sess, page_size=5)
    for p in sess.params_log:
        assert "to" in p and "count" in p
        assert p["count"] == 5
        # `to` is exclusive, so page 1 asks one bar above the locked end and no higher.
        assert float(p["to"]) * 1000 <= hi + H4
        assert p["alignmentTimezone"] == "UTC" and p["dailyAlignment"] == 0
        assert p["granularity"] == "H4" and p["price"] == "BA"

def test_cursor_moves_strictly_backward_across_pages():
    sess = _RangeSession(_series(20))
    fetch_range(_cfg(), start_ms=T0, end_ms=T0 + 19 * H4, session=sess, page_size=4)
    tos = [float(p["to"]) for p in sess.params_log]
    assert len(tos) >= 3
    assert all(b < a for a, b in zip(tos, tos[1:])), f"cursor did not move strictly back: {tos}"

def test_a_page_returning_candles_above_the_cursor_fails_closed():
    # A server that ignores `to` would otherwise drag the cursor above the locked end on
    # page 1, where the forward-move guard is not yet armed.
    sess = _RangeSession(_series(20), overshoot=True)
    with pytest.raises(ValueError, match="above the requested"):
        fetch_range(_cfg(), start_ms=T0 + 2 * H4, end_ms=T0 + 10 * H4, session=sess, page_size=4)

# --- exclusive `to` semantics (measured against the live endpoint) --------------------

def test_the_candle_at_the_locked_end_is_returned_under_an_exclusive_to_server():
    # Measured live: `to` excludes the bar at that timestamp. Asking with `to = end_ms`
    # would therefore silently drop the final bar of a locked window.
    sess = _RangeSession(_series(12))
    hi = T0 + 11 * H4
    df = fetch_range(_cfg(), start_ms=T0, end_ms=hi, session=sess, page_size=5)
    assert int(df["open_time"].max()) == hi
    assert len(df) == 12

def test_first_request_asks_one_granularity_step_above_the_locked_end():
    sess = _RangeSession(_series(12))
    hi = T0 + 11 * H4
    fetch_range(_cfg(), start_ms=T0, end_ms=hi, session=sess, page_size=5)
    assert int(round(float(sess.params_log[0]["to"]) * 1000)) == hi + H4

def test_later_requests_ask_at_the_previous_pages_earliest_raw_timestamp():
    sess = _RangeSession(_series(20, incomplete_at=(3, 4)))
    fetch_range(_cfg(), start_ms=T0, end_ms=T0 + 19 * H4, session=sess, page_size=6)
    assert len(sess.params_log) >= 3
    for i in range(1, len(sess.params_log)):
        asked = int(round(float(sess.params_log[i]["to"]) * 1000))
        assert asked == min(sess.returned[i - 1]), f"page {i + 1} did not resume at the cursor"

def test_pages_abut_without_gaps_or_duplication():
    sess = _RangeSession(_series(20))
    df = fetch_range(_cfg(), start_ms=T0, end_ms=T0 + 19 * H4, session=sess, page_size=6)
    served = [t for page in sess.returned for t in page]
    assert len(served) == len(set(served)), "pages overlapped under exclusive `to`"
    assert list(df["open_time"]) == [T0 + i * H4 for i in range(20)]   # no gap either

def test_step_is_derived_from_granularity_not_hardcoded():
    step = 15 * 60 * 1000
    sess = _RangeSession(_series(8, step=step))
    hi = T0 + 7 * step
    fetch_range(_cfg(granularity="M15"), start_ms=T0, end_ms=hi, session=sess, page_size=4)
    assert int(round(float(sess.params_log[0]["to"]) * 1000)) == hi + step

def test_a_variable_duration_granularity_fails_closed_before_any_request():
    for bad in ("M", "W", "H5", ""):
        sess = _RangeSession(_series(12))
        with pytest.raises(ValueError, match="granularity"):
            fetch_range(_cfg(granularity=bad), start_ms=T0, end_ms=T0 + 11 * H4,
                        session=sess, page_size=5)
        assert sess.calls == 0, f"{bad!r} reached the network before being rejected"


def test_history_ending_before_the_locked_end_fails_closed():
    sess = _RangeSession(_series(12))                        # newest bar is T0 + 11*H4
    with pytest.raises(ValueError, match="coverage"):
        fetch_range(_cfg(), start_ms=T0, end_ms=T0 + 20 * H4, session=sess, page_size=5)


# --- adapter into the locked loader ---------------------------------------------------

def test_adapter_feeds_load_exact_window(tmp_path):
    sess = _RangeSession(_series(20))
    cfg = _cfg(cache_dir=str(tmp_path))
    lo, hi = T0 + 2 * H4, T0 + 15 * H4
    fn = make_range_fetch_fn(cfg, session=sess, page_size=6)
    got = load_exact_window(cfg, start_ms=lo, end_ms=hi, fetch_fn=fn)
    assert int(got["open_time"].min()) == lo and int(got["open_time"].max()) == hi
    assert exact_cache_path(cfg, start_ms=lo, end_ms=hi).exists()

def test_exact_window_cache_hit_performs_no_fetch(tmp_path):
    sess = _RangeSession(_series(20))
    cfg = _cfg(cache_dir=str(tmp_path))
    lo, hi = T0 + 2 * H4, T0 + 15 * H4
    fn = make_range_fetch_fn(cfg, session=sess, page_size=6)
    load_exact_window(cfg, start_ms=lo, end_ms=hi, fetch_fn=fn)
    before = sess.calls
    again = load_exact_window(cfg, start_ms=lo, end_ms=hi, fetch_fn=fn)
    assert sess.calls == before                              # served from cache, no request
    assert len(again) > 0


# --- legacy must not change -----------------------------------------------------------

def test_legacy_fetch_candles_is_unchanged():
    # The legacy pager still uses to/count and never sends `from`; Phase 0/1 depend on it.
    sess = _RangeSession(_series(3))
    fetch_candles({"instrument": "EUR_USD", "granularity": "H4", "price": "BA"}, session=sess)
    assert sess.params_log, "legacy fetcher made no request"
    for p in sess.params_log:
        assert "from" not in p
        assert p["count"] == 5000
