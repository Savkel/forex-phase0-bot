"""Frozen Tokyo pre-economics input checks. No returns or trading calculations.

Never pass the full M15 cache to a dataframe, hash, or buffered reader. Only
extract_permitted may open it, via an unbuffered timestamp-first byte stream.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import platform
import re
import subprocess
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import BinaryIO
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
L = 1388966400000  # 2014-01-06T00:00:00Z
U = 1704499200000  # 2024-01-06T00:00:00Z, EXCLUSIVE
STEP = 900000
SOURCE = 'data/forex_ohlcv/phase2_m15/USD_JPY__M15__BA__a0__w1388959200000-1782506700000.csv'
PREREG = 'prereg/2026-09-23-tokyo-fix-baseline-prereg-draft.md'
CALENDAR = 'data/japan_calendar/tokyo_eligible_days_20140106_20240105.csv'
PROVENANCE = 'reports/forex/phase2_m15_provenance.json'
CLAUDE_SHA = 'e46730ea21f97b896ee646556b15c7ccffd0694a902176ef8f9c4a870459635f'
REQUIRED = ('open_time', 'time', 'bid_o', 'bid_h', 'bid_l', 'bid_c',
            'ask_o', 'ask_h', 'ask_l', 'ask_c', 'volume', 'complete')
OPTIONAL = ('mid_o', 'mid_h', 'mid_l', 'mid_c')
UTC = timezone.utc
TOKYO = ZoneInfo('Asia/Tokyo')
NY = ZoneInfo('America/New_York')


class IntegrityError(ValueError):
    pass


def digest(path: Path) -> str:
    # Explicit guard prevents accidental full-cache hashing.
    if path.resolve() == (ROOT / SOURCE).resolve():
        raise IntegrityError('Whole-cache hashing prohibited')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc_ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def iso(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, UTC).isoformat().replace('+00:00', 'Z')


def scheduled_windows(day: date) -> dict[str, tuple[int, int]]:
    def tokyo(h: int, m: int) -> int:
        return utc_ms(datetime.combine(day, time(h, m), TOKYO))
    previous = datetime.combine(day - timedelta(days=1), time(17), NY)
    current = datetime.combine(day, time(17), NY)
    return {
        'primary': (tokyo(9, 0), tokyo(9, 45)),
        'early': (tokyo(7, 30), tokyo(8, 15)),
        'late': (tokyo(10, 30), tokyo(11, 15)),
        'passive': (utc_ms(previous) + STEP, utc_ms(current) - STEP),
    }


def calendar_dates() -> dict:
    rows = list(csv.DictReader((ROOT / CALENDAR).open(encoding='utf-8', newline='')))
    expected = date(2014, 1, 6)
    included, excluded = [], []
    eligible_count = 0
    for row in rows:
        day = date.fromisoformat(row['jst_date'])
        if day != expected or row['eligible'] not in ('true', 'false'):
            raise IntegrityError('Calendar ordering or boolean mismatch')
        expected += timedelta(days=1)
        if row['eligible'] != 'true':
            continue
        eligible_count += 1
        windows = scheduled_windows(day)
        if not all(L <= a - STEP <= a <= b < U
                   for name, (a, b) in windows.items() if name != 'passive'):
            excluded.append({'jst_date': day.isoformat(), 'reason': 'BOUNDARY_OUTSIDE_ENVELOPE'})
            continue
        a, b = windows['passive']
        if not L <= a <= b < U:
            raise IntegrityError('Passive window outside envelope')
        included.append(day.isoformat())
    if (len(rows), eligible_count, len(included), expected) != (3652, 2446, 2445, date(2024, 1, 6)):
        raise IntegrityError('Frozen calendar counts disagree')
    if excluded != [{'jst_date': '2014-01-06', 'reason': 'BOUNDARY_OUTSIDE_ENVELOPE'}]:
        raise IntegrityError('Boundary exclusion mismatch')
    return {'eligible_dates': included, 'boundary_exclusions': excluded,
            'calendar_rows': len(rows), 'calendar_eligible_count': eligible_count}


def verify_bindings() -> dict:
    text = (ROOT / PREREG).read_text(encoding='utf-8')
    bindings = dict(re.findall(r'\| `([^`]+)`[^|]*\| `([a-f0-9]{64})` \|', text))
    if len(bindings) != 10:
        raise IntegrityError('Unexpected artifact binding set')
    for name, expected in bindings.items():
        if digest(ROOT / name) != expected:
            raise IntegrityError('Artifact binding mismatch: ' + name)
    if digest(ROOT / 'CLAUDE.md') != CLAUDE_SHA:
        raise IntegrityError('Constitution binding mismatch')
    return bindings


def _through(stream: BinaryIO, delimiter: bytes, limit: int) -> bytes:
    """No read request exceeds one byte: cannot prefetch across a seal."""
    out = bytearray()
    while len(out) < limit:
        ch = stream.read(1)
        if not ch:
            if not out:
                return b''
            raise IntegrityError('Unterminated field/row')
        out.extend(ch)
        if ch == delimiter:
            return bytes(out)
        if delimiter == b',' and ch in (b'\n', b'\r'):
            raise IntegrityError('Malformed timestamp field')
    raise IntegrityError('Unexpectedly long field/row')


def extract_stream(stream: BinaryIO, output: BinaryIO, lower: int = L, upper: int = U) -> dict:
    header = _through(stream, b'\n', 4096)
    try:
        columns = header.decode('utf-8').strip('\r\n').split(',')
    except UnicodeDecodeError as exc:
        raise IntegrityError('Invalid header') from exc
    if (not columns or columns[0] != 'open_time' or len(columns) != len(set(columns))
            or not set(REQUIRED) <= set(columns) or not set(columns) <= set(REQUIRED + OPTIONAL)):
        raise IntegrityError('Unexpected M15 schema')
    output.write(header)
    sha = hashlib.sha256(header)
    size, count, first, last, previous, sentinel = len(header), 0, None, None, None, None
    while True:
        prefix = _through(stream, b',', 32)
        if not prefix:
            break
        if not re.fullmatch(rb'[0-9]+,', prefix):
            raise IntegrityError('Malformed timestamp')
        stamp = int(prefix[:-1])
        if previous is not None and stamp <= previous:
            raise IntegrityError('Non-increasing timestamp prefix')
        previous = stamp
        if stamp >= upper:
            sentinel = stamp
            break  # crucial: no byte of this row's remaining fields is requested
        rest = _through(stream, b'\n', 4096)
        if not rest:
            raise IntegrityError('Missing permitted row remainder')
        if stamp < lower:
            continue  # do not interpret/hash discarded price fields
        row = prefix + rest
        output.write(row)
        sha.update(row)
        size += len(row)
        count += 1
        if first is None:
            first = stamp
        last = stamp
    if count == 0:
        raise IntegrityError('Empty permitted subset')
    return {'header': columns, 'sha256': sha.hexdigest(), 'byte_count': size,
            'row_count': count, 'first_ms': first, 'last_ms': last,
            'stop_timestamp_ms': sentinel, 'stop_condition': 'TIMESTAMP_BOUNDARY' if sentinel is not None else 'EOF'}


def extract_permitted(destination: Path) -> dict:
    # xb refuses any overwrite. Source is never buffered, mapped or hashed.
    with (ROOT / SOURCE).open('rb', buffering=0) as source, destination.open('xb') as target:
        return extract_stream(source, target)


def support_check(stamps: set[int], dates: list[str]) -> dict:
    missing = []
    for label in dates:
        for role, (entry, end) in scheduled_windows(date.fromisoformat(label)).items():
            # Decision bar is checked separately; passive entry is pre-scheduled too.
            if entry - STEP not in stamps:
                missing.append({'jst_date': label, 'role': role, 'kind': 'DECISION_BAR', 'timestamp': iso(entry - STEP)})
            for stamp in range(entry, end + STEP, STEP):
                if stamp not in stamps:
                    kind = 'ENTRY' if stamp == entry else 'EXIT' if stamp == end else 'INTERMEDIATE'
                    missing.append({'jst_date': label, 'role': role, 'kind': kind, 'timestamp': iso(stamp)})
    return {'support_ready': not missing, 'missing_count': len(missing), 'missing': missing}


def read_subset_timestamps(path: Path) -> set[int]:
    """Only the isolated permitted subset is allowed here; no price arithmetic."""
    if path.resolve() == (ROOT / SOURCE).resolve():
        raise IntegrityError('Full cache prohibited')
    stamps = set()
    previous = None
    with path.open(encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            stamp = int(row['open_time'])
            if not L <= stamp < U or stamp % STEP or (previous is not None and stamp <= previous):
                raise IntegrityError('Subset timestamp integrity')
            parsed = datetime.fromisoformat(row['time'].replace('Z', '+00:00'))
            if parsed.utcoffset() != timedelta(0) or utc_ms(parsed) != stamp:
                raise IntegrityError('Time fields disagree')
            previous = stamp
            stamps.add(stamp)
    return stamps


def write_json_new(path: Path, data: dict) -> None:
    with path.open('x', encoding='utf-8', newline='\n') as output:
        output.write(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + '\n')


def main() -> int:
    bindings = verify_bindings()
    dates = calendar_dates()
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    frozen = [PREREG, 'RESEARCH_HANDOFF.md', 'governance/2026-09-24-intraday-passive-benchmark-amendment.md',
              'provenance/tokyo_v20_daily_research_venue.md']
    if subprocess.check_output(['git', 'diff', 'HEAD', '--', *frozen], cwd=ROOT):
        raise IntegrityError('Freeze documents modified')
    report = ROOT / 'reports/forex/tokyo_fix/readiness_20260924'
    report.mkdir(parents=True, exist_ok=False)
    subset = report / 'USD_JPY_M15_BA_permitted.csv'
    date_path = report / 'boundary_dates.json'
    write_json_new(date_path, dates)
    extracted = extract_permitted(subset)
    if digest(subset) != extracted['sha256']:
        raise IntegrityError('Subset byte/hash parity failed')
    manifest = {
        'source_locator_only': SOURCE, 'provenance_sha256': bindings[PROVENANCE],
        'instrument': 'USD_JPY', 'timeframe': 'M15', 'price': 'BA',
        'lower_inclusive': iso(L), 'upper_exclusive': iso(U), 'timestamp_units': 'epoch_milliseconds',
        'subset_path': str(subset.relative_to(ROOT)), 'subset': extracted,
        'extractor_sha256': digest(Path(__file__)), 'freeze_commit': commit,
        'extractor_status': 'post-freeze uncommitted implementation',
        'python': platform.python_version(), 'tzdata': importlib.metadata.version('tzdata'),
        'prereg_sha256': digest(ROOT / PREREG), 'bindings': bindings,
        'boundary_dates_path': str(date_path.relative_to(ROOT)), 'boundary_dates_sha256': digest(date_path),
        'account_mode': 'UNKNOWN', 'research_venue_convention': 'OANDA_V20_DAILY_1700_America_New_York',
        'economics_executed': False,
    }
    write_json_new(report / 'input_binding.json', manifest)
    stamps = read_subset_timestamps(subset)
    result = support_check(stamps, dates['eligible_dates'])
    result.update({'input_binding_sha256': digest(report / 'input_binding.json'),
                   'status': 'SUPPORT_PASS_NOT_FULL_READINESS' if result['support_ready'] else 'BLOCKED_MISSING_REQUIRED_TIMESTAMPS',
                   'economics_executed': False, 'prices_validated': False,
                   'remaining_checks': 'quote integrity, ledger, bootstrap, causality and full readiness remain pending'})
    write_json_new(report / 'timestamp_support.json', result)
    print(json.dumps({k: result[k] for k in ('status', 'missing_count', 'economics_executed')}))
    return 0 if result['support_ready'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
