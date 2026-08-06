"""Phase 2A core: session/liquidity breakout mechanics for the locked M15 family.

Scope is deliberately narrow — sessions, eligibility, signals and execution. Nulls,
benchmarks, validation gates and any confirmation access are NOT here.

The locked rules this module implements, verbatim:

- Sessions resolve in each venue's OWN timezone on the trading day's calendar date. A week
  where US and EU DST disagree is handled by resolving each venue independently; there is
  no reconciliation and no fixed UTC offset anywhere.
- A pair-day is eligible only when EVERY expected M15 bar from the range start through the
  candidate's SCHEDULED EXIT bar is present. The 16:45 ET flat-by is an emergency
  invariant, not an extra data requirement, so bars after the scheduled exit are not
  required. The mask comes from the frozen expected grid, before any signal is computed.
- Signal on a bar's close, fill at the NEXT bar's open: buy at ask, sell at bid.
- One trade per pair/day/candidate. No re-entry.
- Per-bar exit precedence: scheduled exit or emergency flat AT THE OPEN first; else a
  gap-through stop at the executable open; else an intrabar stop at the stop price. After
  an open-time exit the bar's high and low are never inspected — that ordering is what
  keeps a same-bar stop from being invented after the position is already closed.

Ranges and signal comparisons use mid prices; execution uses bid/ask. Slippage is a fixed
adverse amount per side, applied only through the pre-registered stress cell.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from bot.forex.market_grid import M15_MS, _trading_day

_FLAT_TZ = "America/New_York"
_FLAT_TIME = time(16, 45)          # emergency invariant, always before the 17:00 rollover


@dataclass(frozen=True)
class SessionSpec:
    """One candidate's session geometry. Times are LOCAL to their own venue."""
    name: str
    range_tz: str
    range_start: time
    range_end: time                                   # exclusive
    entry_start: Tuple[Tuple[str, time], ...]         # entry opens at the LATEST of these
    entry_last_close: Tuple[str, time]                # last permitted SIGNAL close
    exit_at: Tuple[str, time]                         # scheduled exit bar open


SPECS: Dict[str, SessionSpec] = {
    "c1_asia_london": SessionSpec(
        name="c1_asia_london",
        range_tz="Asia/Tokyo", range_start=time(9, 0), range_end=time(15, 0),
        entry_start=(("Europe/London", time(8, 0)),),
        entry_last_close=("Europe/London", time(12, 0)),
        exit_at=("Europe/London", time(16, 30)),
    ),
    "c2_london_orb": SessionSpec(
        name="c2_london_orb",
        range_tz="Europe/London", range_start=time(8, 0), range_end=time(9, 0),
        entry_start=(("Europe/London", time(9, 0)),),
        entry_last_close=("Europe/London", time(12, 0)),
        exit_at=("Europe/London", time(16, 30)),
    ),
    "c3_london_ny": SessionSpec(
        name="c3_london_ny",
        range_tz="Europe/London", range_start=time(8, 0), range_end=time(12, 0),
        entry_start=(("Europe/London", time(12, 0)), ("America/New_York", time(8, 0))),
        entry_last_close=("America/New_York", time(15, 0)),
        exit_at=("America/New_York", time(16, 0)),
    ),
}


def _local_ms(tz: str, day: Any, t: time) -> int:
    """A local wall-clock time on the trading day's calendar date, as UTC ms."""
    d = pd.Timestamp(day).date()
    return int(datetime.combine(d, t, tzinfo=ZoneInfo(tz)).timestamp() * 1000)


def session_bounds(spec: SessionSpec, trading_day: Any) -> Dict[str, int]:
    """Resolve one candidate's windows for one trading day, each venue in its own tz."""
    range_start = _local_ms(spec.range_tz, trading_day, spec.range_start)
    range_end = _local_ms(spec.range_tz, trading_day, spec.range_end)
    entry_start = max(_local_ms(tz, trading_day, t) for tz, t in spec.entry_start)
    entry_start = max(entry_start, range_end)          # never before the range completes
    last_close = _local_ms(*(spec.entry_last_close[0], trading_day, spec.entry_last_close[1]))
    exit_ms = _local_ms(spec.exit_at[0], trading_day, spec.exit_at[1])
    return {
        "range_start_ms": range_start,
        "range_end_ms": range_end,
        "entry_start_ms": entry_start,
        # the last bar whose CLOSE is still inside the entry window
        "last_signal_open_ms": last_close - M15_MS,
        "exit_ms": exit_ms,
        "flat_ms": _local_ms(_FLAT_TZ, trading_day, _FLAT_TIME),
    }


def _required_slots(spec: SessionSpec, day: Any, expected: np.ndarray) -> np.ndarray:
    b = session_bounds(spec, day)
    return expected[(expected >= b["range_start_ms"]) & (expected <= b["exit_ms"])]


def _trading_days(observed: Iterable[int]) -> List[pd.Timestamp]:
    """Distinct trading-day labels as tz-naive midnight Timestamps (the ET calendar date),
    so a day is comparable regardless of which timezone produced it."""
    ts = sorted(int(x) for x in observed)
    if not ts:
        return []
    return sorted({pd.Timestamp(x).tz_localize(None).normalize() for x in _trading_day(ts)})


def eligible_days(df: pd.DataFrame, spec: SessionSpec, expected: np.ndarray) -> List[Any]:
    """Trading days whose every required bar is present. Nothing is imputed."""
    observed = set(int(x) for x in df["open_time"].to_numpy("int64"))
    exp = np.asarray(expected, dtype="int64")
    if not len(exp):
        return []
    exp_set, exp_lo, exp_hi = set(int(x) for x in exp), int(exp.min()), int(exp.max())
    out: List[Any] = []
    for day in _trading_days(observed):
        b = session_bounds(spec, day)
        # The required span must lie inside the grid's OWN coverage, or "every required
        # bar is present" would be satisfied vacuously by a grid that stops short.
        if b["range_start_ms"] < exp_lo or b["exit_ms"] > exp_hi:
            continue
        # The scheduled-exit bar is the exit mechanism. If it is not an expected slot the
        # day has no way to close on time, and the exit loop would otherwise take the next
        # available bar — the next trading day's — and carry the position overnight.
        if b["exit_ms"] not in exp_set or b["exit_ms"] not in observed:
            continue
        need = _required_slots(spec, day, exp)
        if len(need) and all(int(t) in observed for t in need):
            out.append(day)
    return out


def _mid(row: pd.Series, field: str) -> float:
    return (float(row[f"bid_{field}"]) + float(row[f"ask_{field}"])) / 2.0


def range_extremes(bars: pd.DataFrame, b: Dict[str, int]) -> Optional[Tuple[float, float]]:
    """Mid high/low of the candidate's range window, or None when it is empty."""
    rng = bars[(bars["open_time"] >= b["range_start_ms"])
               & (bars["open_time"] < b["range_end_ms"])]
    if rng.empty:
        return None
    return (float(((rng["bid_h"] + rng["ask_h"]) / 2.0).max()),
            float(((rng["bid_l"] + rng["ask_l"]) / 2.0).min()))


def execute_signal(bars: pd.DataFrame, idx: Dict[int, int], b: Dict[str, int], *,
                   spec: SessionSpec, pair: str, day: Any, signal_ms: int, direction: int,
                   stop_px: Optional[float], slip: float,
                   range_high: Optional[float] = None,
                   range_low: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """Fill one signal and carry it to its exit. THE single execution path.

    The strategy, the null and the session-matched benchmark all route through here, so
    fills, spread, slippage, exit precedence and the no-overnight rule cannot drift apart
    between them. `stop_px=None` means no stop at all (the always-long benchmark).
    """
    fill_i = idx[int(signal_ms)] + 1
    if fill_i >= len(bars):
        return None
    fill = bars.iloc[fill_i]
    if int(fill["open_time"]) >= b["exit_ms"]:                 # no room to hold the trade
        return None
    entry_px = (float(fill["ask_o"]) + slip) if direction == 1 \
        else (float(fill["bid_o"]) - slip)
    trade: Dict[str, Any] = {
        "pair": pair, "candidate": spec.name,
        "trading_day": str(pd.Timestamp(day).date()),
        "signal_ms": int(signal_ms), "entry_ms": int(fill["open_time"]),
        "direction": int(direction), "entry_px": entry_px, "stop_px": stop_px,
        "range_high": range_high, "range_low": range_low,
    }

    first = idx[trade["entry_ms"]]
    for i in range(first, len(bars)):
        bar = bars.iloc[i]
        t = int(bar["open_time"])
        # The ENTRY bar is already live from its open, so its low/high are in scope — but
        # its open IS the fill, so the open-time and gap-through branches cannot apply.
        if i == first:
            if stop_px is not None:
                if direction == 1 and float(bar["bid_l"]) <= stop_px:
                    trade.update(exit_ms=t, exit_px=stop_px - slip, exit_reason="stop")
                    break
                if direction == -1 and float(bar["ask_h"]) >= stop_px:
                    trade.update(exit_ms=t, exit_px=stop_px + slip, exit_reason="stop")
                    break
            continue
        # 1. an open-time exit wins outright; the bar's high/low are NOT consulted.
        if t >= b["exit_ms"] or t >= b["flat_ms"]:
            px = (float(bar["bid_o"]) - slip) if direction == 1 \
                else (float(bar["ask_o"]) + slip)
            trade.update(exit_ms=t, exit_px=px,
                         exit_reason="scheduled" if t >= b["exit_ms"] else "flat_by")
            break
        if stop_px is None:
            continue
        # 2. a gap-through stop fills at the executable open, which is worse.
        if direction == 1 and float(bar["bid_o"]) <= stop_px:
            trade.update(exit_ms=t, exit_px=float(bar["bid_o"]) - slip,
                         exit_reason="gap_stop")
            break
        if direction == -1 and float(bar["ask_o"]) >= stop_px:
            trade.update(exit_ms=t, exit_px=float(bar["ask_o"]) + slip,
                         exit_reason="gap_stop")
            break
        # 3. otherwise an intrabar stop: long on the BID low, short on the ASK high.
        if direction == 1 and float(bar["bid_l"]) <= stop_px:
            trade.update(exit_ms=t, exit_px=stop_px - slip, exit_reason="stop")
            break
        if direction == -1 and float(bar["ask_h"]) >= stop_px:
            trade.update(exit_ms=t, exit_px=stop_px + slip, exit_reason="stop")
            break
    return trade if "exit_ms" in trade else None                # never leave one open


def run_candidate(df: pd.DataFrame, spec: SessionSpec, *, pair: str,
                  expected: np.ndarray, pip: float = 0.0001,
                  slippage_pips: float = 0.0) -> List[Dict[str, Any]]:
    """Signals and fills for one pair, one candidate. Returns trades; measures nothing."""
    slip = float(slippage_pips) * float(pip)
    bars = df.sort_values("open_time").reset_index(drop=True)
    idx = {int(t): i for i, t in enumerate(bars["open_time"].to_numpy("int64"))}
    trades: List[Dict[str, Any]] = []

    for day in eligible_days(bars, spec, expected):
        b = session_bounds(spec, day)
        extremes = range_extremes(bars, b)
        if extremes is None:
            continue
        hi, lo = extremes

        window = bars[(bars["open_time"] >= b["entry_start_ms"])
                      & (bars["open_time"] <= b["last_signal_open_ms"])]
        for _, row in window.iterrows():                       # ONE trade per pair-day
            close = _mid(row, "c")
            direction = 1 if close > hi else (-1 if close < lo else 0)
            if direction == 0:
                continue
            trade = execute_signal(bars, idx, b, spec=spec, pair=pair, day=day,
                                   signal_ms=int(row["open_time"]), direction=direction,
                                   stop_px=lo if direction == 1 else hi, slip=slip,
                                   range_high=hi, range_low=lo)
            if trade is not None:
                trades.append(trade)
            break                                              # no re-entry either way
    return trades


def _ts_keys(trades: Iterable[Dict[str, Any]]) -> set:
    return {(t["pair"], int(t["entry_ms"]), int(t["direction"])) for t in trades}


def _day_keys(trades: Iterable[Dict[str, Any]]) -> set:
    return {(t["pair"], t["trading_day"], int(t["direction"])) for t in trades}


def _jaccard(a: set, b: set) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def jaccard_timestamp(a, b) -> float:
    """Overlap on `(pair, entry timestamp, direction)`."""
    return _jaccard(_ts_keys(a), _ts_keys(b))


def jaccard_pair_day(a, b) -> float:
    """Overlap on `(pair, trading day, direction)` — a one-bar shift cannot evade it."""
    return _jaccard(_day_keys(a), _day_keys(b))
