"""Range-locked OANDA candle fetching for pre-registered research windows (M1 follow-up).

The legacy `oanda_data.fetch_candles` pages backward with `to`/`count` and stops when a
page comes back with fewer than 4999 rows. That rule conflates three different things:
end of history, a genuine gap in the series, and a page whose candles were dropped for
being incomplete. For an ad-hoc pull that is merely untidy; for a locked window it is
dangerous, because the short result would be written into an identity-keyed cache and
thereafter look authoritative.

This module is a SEPARATE path. `oanda_data.fetch_candles` is untouched so Phase 0 and
Phase 1 keep reproducing exactly.

Request contract (backward paging), per the documented OANDA v20 candle endpoint and one
supervised live probe against it:
    `count` may not be combined with both `from` and `to`, so a page sends `to` (the
    current cursor) + `count`, never `from`. Each request also carries `granularity`,
    `price`, `alignmentTimezone=UTC` and `dailyAlignment`.

    `to` is EXCLUSIVE — measured, not assumed: a request with `to` set to a bar's own
    timestamp returns bars strictly older than it. Two consequences drive the cursor:
      - the locked window is inclusive at both ends, so the FIRST request asks
        `end_ms + one granularity step`. Asking at `end_ms` itself never returns that
        bar, which the end-coverage check below then rejects — the fetch fails, loudly,
        rather than returning a series short of its locked end;
      - later requests ask at the previous page's earliest RAW timestamp, and pages
        therefore ABUT rather than overlap — no bar is repeated and none is skipped.
    That is why an unsupported or variable-duration granularity is rejected up front
    instead of approximated: without a fixed step the end bar cannot be requested.

    `start_ms` is a LOCAL lower bound only. It never appears in a request; it governs when
    paging stops, whether coverage is sufficient, and where the assembled series is
    trimmed. A page may legitimately return candles older than `start_ms` — those are
    trimmed away, not treated as an error.

Termination (page LENGTH is never a stop signal):
    - stop with success once a page's earliest RAW candle is at or before `start_ms`;
    - an empty page means history genuinely ended: if `start_ms` was not reached, fail
      closed rather than return a short series;
    - a page that does not move the cursor backward is a protocol/no-progress error;
    - a hard page cap bounds the loop.

The cursor is driven by RAW candle times, including still-forming candles that
`parse_candles` drops. Otherwise a page consisting only of incomplete candles would parse
to nothing and be mistaken for the end of history.

Duplicates: under the measured exclusive-`to` contract pages abut, so there is normally
nothing to collapse. The rule is kept anyway — it costs nothing and covers an inclusive
server or a contract change: rows repeating a timestamp are collapsed only when every
value matches; a timestamp carrying conflicting values is a data conflict and raises.

NOT in scope (deliberately, see the M3 decision): any expected-bar calendar or
bar-validity filtering. Interior gaps are still invisible here.
"""
from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from bot.forex.oanda_data import PRACTICE_HOST, _to_ms, parse_candles

_PAGE_CAP = 2000

# Bar duration per granularity, needed because `to` is EXCLUSIVE: reaching an inclusive
# locked end means asking one bar above it. Only FIXED-duration granularities are listed.
# `W` (calendar-aligned weekly) and `M` (monthly, 28-31 days) have no constant step, so
# they are absent and rejected rather than approximated.
_GRANULARITY_MS = {
    "S5": 5_000, "S10": 10_000, "S15": 15_000, "S30": 30_000,
    "M1": 60_000, "M2": 120_000, "M4": 240_000, "M5": 300_000,
    "M10": 600_000, "M15": 900_000, "M30": 1_800_000,
    "H1": 3_600_000, "H2": 7_200_000, "H3": 10_800_000, "H4": 14_400_000,
    "H6": 21_600_000, "H8": 28_800_000, "H12": 43_200_000,
    "D": 86_400_000,
}


def _granularity_step_ms(granularity: Any) -> int:
    """One bar duration in ms, or raise. Never guesses an unlisted granularity."""
    step = _GRANULARITY_MS.get(str(granularity))
    if step is None:
        raise ValueError(
            f"granularity {granularity!r} has no fixed bar duration; range fetching needs "
            f"one to convert the inclusive locked end into an exclusive `to`. Supported: "
            f"{', '.join(sorted(_GRANULARITY_MS))}"
        )
    return step


def _params(data_cfg: Dict[str, Any], to_ms: int, count: int) -> Dict[str, Any]:
    """Request params for one backward page: `to` + `count`, never `from`.

    OANDA v20 does not accept `count` together with both `from` and `to`, so the locked
    start is NOT a request parameter. It stays local, governing when paging stops, whether
    coverage is sufficient, and where the result is trimmed. `to` is UNIX seconds, matching
    the `Accept-Datetime-Format: UNIX` header the session is configured with.
    """
    return {
        "granularity": data_cfg["granularity"],
        "price": data_cfg.get("price", "BA"),
        "count": int(count),
        "alignmentTimezone": "UTC",
        "dailyAlignment": int(data_cfg.get("alignment_hour_utc", 0)),
        "to": f"{to_ms / 1000:.6f}",
    }


def _dedupe_or_raise(df: pd.DataFrame, label: str) -> pd.DataFrame:
    """Collapse page-boundary repeats; raise if one timestamp carries conflicting values."""
    if df.empty:
        return df
    dup_ts = df["open_time"][df["open_time"].duplicated()].unique()
    if len(dup_ts):
        cols = [c for c in df.columns if c != "time"]        # `time` is derived from open_time
        for ts in dup_ts:
            rows = df.loc[df["open_time"] == ts, cols].drop_duplicates()
            if len(rows) > 1:
                raise ValueError(
                    f"{label}: conflicting duplicate candles at open_time {int(ts)} "
                    f"({len(rows)} distinct value sets); refusing to guess which is real"
                )
        df = df.drop_duplicates(subset="open_time", keep="first")
    return df


def fetch_range(data_cfg: Dict[str, Any], *, start_ms: int, end_ms: int,
                token: Optional[str] = None, session: Any = None,
                page_size: int = 5000) -> pd.DataFrame:
    """Fetch complete candles for exactly [start_ms, end_ms] (inclusive), or raise.

    Returns a sorted, de-duplicated, strictly increasing frame trimmed to the window.
    Never returns a short series silently: not reaching `start_ms` is an error.
    """
    start_ms, end_ms = int(start_ms), int(end_ms)
    if start_ms >= end_ms:
        raise ValueError(f"locked window invalid: start_ms {start_ms} >= end_ms {end_ms}")
    step = _granularity_step_ms(data_cfg["granularity"])    # before any network call
    token = token or os.environ.get("OANDA_API_TOKEN")
    if not token:
        raise RuntimeError("OANDA_API_TOKEN not set; provide it via the environment (never hardcode).")

    sess = session
    if sess is None:
        import requests                                      # imported only for a real fetch
        sess = requests.Session()
    sess.headers.update({"Authorization": f"Bearer {token}",
                         "Accept-Datetime-Format": "UNIX"})

    inst = data_cfg["instrument"]
    label = f"{inst} {data_cfg['granularity']} [{start_ms}, {end_ms}]"
    url = f"{PRACTICE_HOST}/v3/instruments/{inst}/candles"

    frames: List[pd.DataFrame] = []
    cursor = end_ms + step        # `to` is exclusive: ask one bar above the inclusive end
    reached_start = False
    prev_earliest: Optional[int] = None
    raw_newest: Optional[int] = None      # newest RAW candle seen across all pages

    for _ in range(_PAGE_CAP):
        resp = sess.get(url, params=_params(data_cfg, cursor, page_size), timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        raw = payload.get("candles", [])
        if not raw:
            break                                            # history genuinely ended here
        # Cursor comes from RAW times so a page of only-incomplete candles still advances.
        raw_times = [_to_ms(c["time"]) for c in raw]
        earliest = min(raw_times)
        newest = max(raw_times)
        if newest > cursor:
            raise ValueError(f"{label}: page returned a candle at {newest}, above the "
                             f"requested `to` cursor {cursor}; refusing an out-of-range "
                             f"response")
        raw_newest = newest if raw_newest is None else max(raw_newest, newest)
        parsed = parse_candles(payload)
        if len(parsed):                  # an all-incomplete page parses empty; don't concat it
            frames.append(parsed)
        if earliest <= start_ms:
            reached_start = True
            break
        if prev_earliest is not None:
            if earliest > prev_earliest:
                raise ValueError(f"{label}: pagination moved FORWARD at cursor {cursor} "
                                 f"(earliest {earliest} > previous {prev_earliest}); "
                                 f"refusing an inconsistent response")
            if earliest == prev_earliest:
                break        # cursor cannot move back further: history is exhausted here
        prev_earliest = earliest
        cursor = earliest                                    # inclusive: boundary candle repeats
    else:
        raise ValueError(f"{label}: exceeded the {_PAGE_CAP}-page cap before reaching the "
                         f"locked start; refusing a partial history")

    if not reached_start:
        raise ValueError(
            f"{label}: coverage check failed — available history begins after the locked "
            f"start; refusing a truncated series"
        )
    # Both ends must have been paged over. The start side is `reached_start`; the end side
    # guards against a server that anchors a `from`-bearing request at the OLDEST candle,
    # which would satisfy `reached_start` on page 1 while covering only the old end of the
    # window. Checked on RAW times so a still-forming final candle is not mistaken for a
    # short fetch; completeness coverage is the loader's job, not the pager's.
    if raw_newest is None or raw_newest < end_ms:
        raise ValueError(
            f"{label}: coverage check failed — paging reached only {raw_newest}, short of "
            f"the locked end {end_ms}; the server may not honour this paging contract"
        )

    df = pd.concat(frames, ignore_index=True) if frames else parse_candles({"candles": []})
    df = df.sort_values("open_time").reset_index(drop=True)
    df = _dedupe_or_raise(df, label)
    df = df[(df["open_time"] >= start_ms) & (df["open_time"] <= end_ms)]
    df = df.sort_values("open_time").reset_index(drop=True)
    if not df["open_time"].is_monotonic_increasing or df["open_time"].duplicated().any():
        raise ValueError(f"{label}: timestamps are not strictly increasing after merge")
    return df


def make_range_fetch_fn(data_cfg: Dict[str, Any], *, token: Optional[str] = None,
                        session: Any = None, page_size: int = 5000
                        ) -> Callable[[int, int], pd.DataFrame]:
    """Adapter matching `exact_window.load_exact_window`'s `fetch_fn(start_ms, end_ms)`.

    Pure plumbing: the locked range still comes from the caller, and nothing about the
    scientific semantics of the loader changes.
    """
    def _fn(start_ms: int, end_ms: int) -> pd.DataFrame:
        return fetch_range(data_cfg, start_ms=start_ms, end_ms=end_ms,
                           token=token, session=session, page_size=page_size)
    return _fn


def make_range_fetch_factory(*, token: Optional[str] = None, session: Any = None,
                             page_size: int = 5000
                             ) -> Callable[[str, Dict[str, Any], int, int], pd.DataFrame]:
    """Adapter matching `exact_window.load_universe_exact`'s `fetch_fn_factory`."""
    def _factory(pair: str, pair_cfg: Dict[str, Any], start_ms: int, end_ms: int) -> pd.DataFrame:
        return fetch_range(pair_cfg, start_ms=start_ms, end_ms=end_ms,
                           token=token, session=session, page_size=page_size)
    return _factory
