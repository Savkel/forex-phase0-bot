"""FX cost model: empirical bid/ask spread + per-night swap (Wed x3). Rebuilt
for FX; the perp funding model is NOT ported (CLAUDE.md Reuse policy)."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List

@dataclass
class CostModel:
    pip: float = 0.0001
    long_swap_pips: float = 0.0      # cost in pips/night when long (positive = cost)
    short_swap_pips: float = 0.0     # cost in pips/night when short
    rollover_hour_utc: int = 21
    spread_mult: float = 1.0
    swap_mult: float = 1.0

def spread_frac(bid_o: float, ask_o: float, spread_mult: float = 1.0) -> float:
    """Return the FULL bid/ask spread (ask - bid) as a fraction of mid, widened by
    spread_mult. This is the per-unit cost of a full entry+exit round-trip, NOT the
    cost of a single fill. The engine charges HALF of this value per one-way fill, so:
    a round-trip (entry then exit) pays ~one full spread; a flip pays ~one full spread
    because it is two one-way fills (close + open). Math unchanged."""
    mid = (bid_o + ask_o) / 2.0
    if mid <= 0:
        return 0.0
    return (ask_o - bid_o) / mid * float(spread_mult)

def rollovers_in(t0_ms: int, t1_ms: int, rollover_hour_utc: int) -> List[datetime]:
    """Rollover instants (HH:00 UTC) strictly after t0 and at/<= t1, on BUSINESS DAYS ONLY
    (Mon-Fri). Saturday and Sunday instants are never charged: no value date rolls over a
    weekend, which is precisely why `swap_frac` weights the Wednesday rollover x3. Charging
    Sat/Sun as well would double-count the weekend the x3 already covers. No holiday
    calendar is applied. Interval semantics (t0, t1] are unchanged."""
    t0 = datetime.fromtimestamp(t0_ms / 1000, tz=timezone.utc)
    t1 = datetime.fromtimestamp(t1_ms / 1000, tz=timezone.utc)
    out: List[datetime] = []
    day = t0.replace(hour=rollover_hour_utc, minute=0, second=0, microsecond=0)
    if day <= t0:
        day += timedelta(days=1)
    while day <= t1:
        if day.weekday() < 5:                # 0-4 == Mon-Fri; skip Sat (5) and Sun (6)
            out.append(day)
        day += timedelta(days=1)
    return out

def swap_frac(cost: CostModel, side: int, mid: float, t0_ms: int, t1_ms: int) -> float:
    """Cost fraction (>=0 = drag) for holding `side` over (t0, t1]. Each rollover
    crossed charges swap_pips * pip / mid * swap_mult; Wednesday rollover x3
    (weekend value date). Rollovers are business-day only (see `rollovers_in`), so a
    continuously held position pays 7.0 weighted units per normal week (4 x1 + Wed x3).
    Long and short differ only in `pips`; the counting is identical."""
    if side == 0 or mid <= 0:
        return 0.0
    pips = cost.long_swap_pips if side > 0 else cost.short_swap_pips
    per_night = pips * cost.pip / mid * cost.swap_mult
    total = 0.0
    for r in rollovers_in(t0_ms, t1_ms, cost.rollover_hour_utc):
        total += per_night * (3.0 if r.weekday() == 2 else 1.0)  # weekday 2 == Wednesday
    return total
