"""Structural CFTC readiness only: never calculates FX returns or equity paths."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from bot.forex.tokyo_fix_baseline import matched_fraction
from bot.forex.tokyo_fix_readiness import IntegrityError

ROOT = Path(__file__).resolve().parents[2]
BASE = 'reports/forex/cftc_positioning/'
PRICE = 'reports/forex/tokyo_fix/readiness_20260924/USD_JPY_M15_BA_permitted.csv'
PRICE_SHA = 'bb0dd08f5657a0aa845131cecfd610de2a9cef79eac709c0b8c8fe83e43eca81'
SPEC = 'prereg/2026-10-30-cftc-positioning-exploratory-prereg-draft.md'
FREEZE = 'prereg/2026-10-30-cftc-positioning-exploratory-freeze.json'
L, U, STEP = 1388966400000, 1704499200000, 900000
NY = ZoneInfo('America/New_York')
FIRST, LAST = date(2014, 1, 20), date(2024, 1, 1)
BLACKOUTS = ((date(2018, 12, 22), date(2019, 3, 31)),
             (date(2023, 1, 31), date(2023, 3, 31)))
EXPECTED_GAPS = {'2016-12-26': 3, '2017-01-02': 3, '2019-11-04': 2,
                 '2019-12-23': 1, '2020-05-04': 1, '2020-08-31': 1, '2020-10-26': 1}
FIELDS = {'report_date_as_yyyy_mm_dd', 'cftc_contract_market_code',
          'market_and_exchange_names', 'open_interest_all',
          'lev_money_positions_long', 'lev_money_positions_short'}


def require(ok, message):
    if not ok:
        raise IntegrityError(message)


def sha(path):
    # Explicit callers only; never discover or open a full-cache source locator.
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+'\n')


def milliseconds(day, hour, minute):
    return int(datetime.combine(day, time(hour, minute), NY).timestamp()*1000)


def window(monday):
    require(monday.weekday() == 0, 'Decision must be Monday')
    decision = milliseconds(monday, 17, 0)
    entry = milliseconds(monday, 17, 15)
    end = milliseconds(monday+timedelta(days=1), 16, 45)
    require(L <= decision < entry < end < U, 'Window crosses research seal/envelope')
    require(end-entry == 94*STEP, 'Unexpected financing-day grid')
    return decision, entry, end


def integer(value):
    number = Decimal(str(value))
    require(number.is_finite() and number == number.to_integral_value(), 'Noninteger CFTC field')
    return int(number)


def reports(raw):
    require(isinstance(raw, list), 'CFTC response must be an array')
    out = {}
    previous = None
    for row in raw:
        require(set(row) == FIELDS, 'CFTC schema changed')
        d = datetime.fromisoformat(row['report_date_as_yyyy_mm_dd']).date()
        require(d.weekday() in (0, 1) and (previous is None or d > previous), 'CFTC duplicate/order/date')
        require(row['cftc_contract_market_code'] == '097741' and
                row['market_and_exchange_names'] == 'JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE',
                'Wrong CFTC contract/continuity')
        oi, long, short = (integer(row[k]) for k in
                          ('open_interest_all', 'lev_money_positions_long', 'lev_money_positions_short'))
        require(oi > 0 and 0 <= long <= oi and 0 <= short <= oi, 'Invalid positions/OI')
        out[d] = {'report_date': d.isoformat(), 'oi': oi, 'long': long, 'short': short,
                  'z': (long-short)/oi, 'signal': int(long > short)-int(long < short)}
        previous = d
    return out


def signal_for(monday, report_map):
    nominal = monday-timedelta(days=13)
    found = [d for d in (nominal, nominal-timedelta(days=1)) if d in report_map]
    require(len(found) == 1, 'Missing or ambiguous frozen reporting week')
    d = found[0]
    require((monday-d).days in (13, 14), 'Causal lag mismatch')
    return report_map[d]


def blackout(*dates):
    return any(a <= d <= b for d in dates for a, b in BLACKOUTS)


def build_mask(report_map, present, invalid=frozenset()):
    mask = []
    m = FIRST
    while m <= LAST:
        r = signal_for(m, report_map)
        decision, entry, end = window(m)
        excluded = blackout(date.fromisoformat(r['report_date']), m, m+timedelta(days=1))
        needed = set(range(entry, end+STEP, STEP))
        missing, bad = sorted(needed-present), sorted(needed.intersection(invalid))
        status = 'PUBLICATION_BLACKOUT' if excluded else ('INCOMPLETE' if missing or bad else 'SUPPORTED')
        mask.append(dict(r, monday=m.isoformat(), decision_ms=decision, entry_ms=entry,
                         exit_ms=end, lag_days=(m-date.fromisoformat(r['report_date'])).days,
                         status=status, missing=missing, invalid=bad))
        m += timedelta(days=7)
    require(len(report_map) == len(mask) == 520, 'Unused/missing report rows')
    return mask


def support_summary(mask, grid_count):
    kept = [r for r in mask if r['status'] == 'SUPPORTED']
    require(kept and grid_count > 1, 'Empty sample/grid')
    counts = Counter(r['signal'] for r in kept)
    runs, length, previous = [], 0, None
    for r in mask:
        current = r['signal'] if r['status'] == 'SUPPORTED' else None
        if current is None or current != previous:
            if length:
                runs.append(length)
            length = 0
        if current is not None:
            length += 1
        previous = current
    if length:
        runs.append(length)
    n = grid_count-1
    N = sum(r['signal']*94 for r in kept)/n
    G = sum(abs(r['signal'])*94 for r in kept)/n
    q = len(kept)*94/n
    return {'scheduled': len(mask), 'blackout': sum(r['status'] == 'PUBLICATION_BLACKOUT' for r in mask),
            'incomplete': sum(r['status'] == 'INCOMPLETE' for r in mask), 'supported': len(kept),
            'long': counts[1], 'short': counts[-1], 'neutral': counts[0],
            'sign_runs': len(runs), 'longest_run': max(runs), 'independent_weeks_claimed': False,
            'year_counts': dict(sorted(Counter(r['monday'][:4] for r in kept).items())),
            'N': N, 'G': G, 'q': q, 'f': matched_fraction(G, q), 'N_over_q': N/q,
            'intervals': n, 'incomplete_rate': 7/493}


def load_prices():
    """Validate only isolated prices; no returns, performance or price summaries."""
    path = ROOT / PRICE
    require(path.resolve() == ROOT.resolve()/PRICE and not path.is_symlink(), 'Unsafe price locator')
    require(sha(path) == PRICE_SHA, 'Isolated pre-seal price hash mismatch')
    df = pd.read_csv(path)
    expected = ['open_time', 'time', 'bid_o', 'bid_h', 'bid_l', 'bid_c', 'ask_o',
                'ask_h', 'ask_l', 'ask_c', 'volume', 'complete', 'mid_o', 'mid_h', 'mid_l', 'mid_c']
    require(list(df.columns) == expected and len(df) == 248784, 'Price schema/count mismatch')
    ts = df.open_time.to_numpy()
    require(np.issubdtype(ts.dtype, np.integer) and np.all(np.diff(ts) > 0) and
            np.all(ts % STEP == 0) and ts[0] >= L and ts[-1] < U, 'Global price timestamp/seal error')
    parsed = pd.to_datetime(df.time, utc=True).astype('int64').to_numpy()//1000000
    require(np.array_equal(ts, parsed), 'Inconsistent price time fields')
    valid = df.complete.eq(True).to_numpy()
    volume = df.volume.to_numpy(dtype=float)
    valid &= np.isfinite(volume) & (volume >= 0) & (volume == np.floor(volume))
    for side in ('bid', 'ask', 'mid'):
        o, h, lo, c = (df[f'{side}_{k}'].to_numpy(dtype=float) for k in ('o', 'h', 'l', 'c'))
        valid &= np.isfinite(o) & np.isfinite(h) & np.isfinite(lo) & np.isfinite(c)
        valid &= (lo > 0) & (lo <= o) & (lo <= c) & (h >= o) & (h >= c)
    for k in ('o', 'h', 'l', 'c'):
        valid &= df[f'bid_{k}'].to_numpy() <= df[f'ask_{k}'].to_numpy()
    return df, set(int(t) for t in ts[~valid])


def readiness():
    require(sha(ROOT/'CLAUDE.md') == 'e46730ea21f97b896ee646556b15c7ccffd0694a902176ef8f9c4a870459635f',
            'Constitution differs from approved snapshot')
    raw = json.loads((ROOT / BASE / 'inputs/tff_jpy_raw.json').read_text())
    meta = json.loads((ROOT / BASE / 'inputs/acquisition.json').read_text())
    require(meta['sha256'] == sha(ROOT / BASE / 'inputs/tff_jpy_raw.json'), 'Raw acquisition changed')
    mapping = reports(raw)
    df, invalid = load_prices()
    extraction = json.loads((ROOT/'reports/forex/tokyo_fix/readiness_20260924/input_binding.json').read_text())
    require(extraction['subset']['sha256'] == PRICE_SHA and extraction['subset']['row_count'] == len(df)
            and extraction['lower_inclusive'] == '2014-01-06T00:00:00Z'
            and extraction['upper_exclusive'] == '2024-01-06T00:00:00Z', 'Isolated extraction provenance mismatch')
    mask = build_mask(mapping, set(int(t) for t in df.open_time), invalid)
    summary = support_summary(mask, len(df))
    required = {'scheduled': 520, 'blackout': 27, 'incomplete': 7, 'supported': 486,
                'long': 110, 'short': 376, 'neutral': 0, 'sign_runs': 30, 'longest_run': 105, 'f': 1.0}
    require(all(summary[k] == v for k, v in required.items()), 'Frozen sample/sign/exposure mismatch')
    require(list(summary['year_counts'].values()) == [50,52,51,51,51,36,49,52,52,41,1], 'Year mask mismatch')
    require({r['monday']: len(r['missing']) for r in mask if r['status'] == 'INCOMPLETE'} == EXPECTED_GAPS,
            'Frozen complete-case dates changed')
    require(not any(r['invalid'] for r in mask if r['status'] != 'PUBLICATION_BLACKOUT'),
            'Unexpected invalid required quote')
    dates = sorted(mapping)
    summary['report_gaps_days'] = dict(sorted(Counter((b-a).days for a,b in zip(dates,dates[1:])).items()))
    summary['monday_reports'] = sum(d.weekday() == 0 for d in dates)
    require(summary['monday_reports'] == 5 and summary['report_gaps_days'] == {6:4,7:511,8:4},
            'Report continuity changed')
    return {'status': 'STRUCTURAL_READY_NO_ECONOMICS', 'economics_executed': False,
            'summary': summary, 'mask': mask, 'invalid_price_rows': len(invalid)}
