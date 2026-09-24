"""USER-RUN ONLY: bounded OANDA repair; no strategy/economics and no full-cache access.

Run from the repo: python -m scripts.repair_tokyo_m15_gaps --execute-authorized-repair
Authentication is read only inside main from the user's OANDA_API_TOKEN environment.
No dotenv loading, account endpoints, redirects, retries, date overrides or gap filling.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = Path('reports/forex/tokyo_fix/readiness_20260924')
OUTPUT = Path('data/forex_ohlcv/tokyo_fix_gap_repair')
ENDPOINT = 'https://api-fxpractice.oanda.com/v3/instruments/USD_JPY/candles'
LOWER, UPPER, STEP = 1388966400000, 1704499200000, 900000
PREREG = 'prereg/2026-09-23-tokyo-fix-baseline-prereg-draft.md'
PINNED = {
    PREREG: '38fe09cde8f98f0b8dab159f4d9acb9c3bb0a493b2951b04510f1eafb3328f4b',
    str(EVIDENCE / 'input_binding.json'): 'a6d03ceb111ec97e1ba432c90996b9c14f4a530db67c1497b949072fe84950f0',
    str(EVIDENCE / 'timestamp_support.json'): '2aad53f7c367c760a29208d582c5172d9fa76efedcb919de9f5078896cfcc378',
    str(EVIDENCE / 'USD_JPY_M15_BA_permitted.csv'): 'bb0dd08f5657a0aa845131cecfd610de2a9cef79eac709c0b8c8fe83e43eca81',
}
COLUMNS = ['open_time', 'time', 'bid_o', 'bid_h', 'bid_l', 'bid_c',
           'ask_o', 'ask_h', 'ask_l', 'ask_c', 'volume', 'complete',
           'mid_o', 'mid_h', 'mid_l', 'mid_c']


class RepairError(Exception):
    """Only fixed, non-secret error codes may be passed to this exception."""


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stamp(text: str) -> int:
    # Reject nonzero nanoseconds rather than silently truncating to microseconds.
    if not isinstance(text, str) or not re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:00(?:\.0{1,9})?(?:Z|\+00:00)', text):
        raise RepairError('INVALID_CANDLE_TIMESTAMP')
    try:
        value = int(datetime.fromisoformat(text.replace('Z', '+00:00')).timestamp()) * 1000
    except ValueError:
        raise RepairError('INVALID_CANDLE_TIMESTAMP') from None
    if value % STEP or not LOWER <= value < UPPER:
        raise RepairError('TIMESTAMP_OUTSIDE_APPROVED_GRID')
    return value


def iso(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_json(path: Path, value: dict | list) -> None:
    data = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()
    # Only files inside this new attempt directory are updated; inputs are never written.
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('xb') as output:
        output.write(data)
    temporary.replace(path)


def groups(targets: list[int]) -> list[list[int]]:
    if not targets or targets != sorted(set(targets)):
        raise RepairError('INVALID_TARGET_ORDER')
    result: list[list[int]] = []
    for value in targets:
        if value % STEP or not LOWER <= value < UPPER:
            raise RepairError('TARGET_OUTSIDE_ENVELOPE')
        if not result or value != result[-1][-1] + STEP or len(result[-1]) == 5000:
            result.append([])
        result[-1].append(value)
    return result


def params_for(targets: list[int]) -> dict:
    if len(groups(targets)) != 1:
        raise RepairError('REQUEST_SPANS_UNAPPROVED_TIMESTAMPS')
    # End inside the last requested candle: never fetch the next observed/sealed bar.
    return {'price': 'BA', 'granularity': 'M15', 'from': iso(targets[0]),
            'to': iso(targets[-1] + STEP - 1), 'includeFirst': 'true', 'smooth': 'false',
            'alignmentTimezone': 'UTC', 'dailyAlignment': 0}


@dataclass
class Inputs:
    subset: Path
    subset_sha256: str
    targets: list[int]
    roles: dict[int, list[dict]]
    provenance: dict


def read_original(path: Path) -> tuple[bytes, list[tuple[int, bytes]]]:
    """This accepts only the isolated permitted input selected by preflight."""
    with path.open('rb') as source:
        header = source.readline()
        if header.decode('utf-8').rstrip('\r\n').split(',') != COLUMNS:
            raise RepairError('INPUT_SCHEMA_MISMATCH')
        rows = []
        previous = None
        for raw in source:
            prefix, delimiter, _ = raw.partition(b',')
            if not delimiter or not prefix.isdigit() or not raw.endswith(b'\n'):
                raise RepairError('INPUT_ROW_MALFORMED')
            value = int(prefix)
            if not LOWER <= value < UPPER or value % STEP or (previous is not None and value <= previous):
                raise RepairError('INPUT_TIMESTAMP_INTEGRITY')
            previous = value
            rows.append((value, raw))
    return header, rows


def preflight() -> Inputs:
    for name, expected in PINNED.items():
        if sha((ROOT / name).read_bytes()) != expected:
            raise RepairError('FROZEN_INPUT_HASH_MISMATCH')
    manifest = json.loads((ROOT / EVIDENCE / 'input_binding.json').read_text())
    report = json.loads((ROOT / EVIDENCE / 'timestamp_support.json').read_text())
    if report['input_binding_sha256'] != PINNED[str(EVIDENCE / 'input_binding.json')]:
        raise RepairError('REPORT_BINDING_MISMATCH')
    for name, expected in manifest['bindings'].items():
        # These are pinned metadata/calendar artifacts, never the full cache.
        if Path(name).is_absolute() or '..' in Path(name).parts or 'forex_ohlcv' in Path(name).parts:
            raise RepairError('UNEXPECTED_BINDING_PATH')
        if sha((ROOT / name).read_bytes()) != expected:
            raise RepairError('ARTIFACT_HASH_MISMATCH')
    if sha((ROOT / 'CLAUDE.md').read_bytes()) != 'e46730ea21f97b896ee646556b15c7ccffd0694a902176ef8f9c4a870459635f':
        raise RepairError('CONSTITUTION_HASH_MISMATCH')
    roles: dict[int, list[dict]] = {}
    for item in report['missing']:
        roles.setdefault(stamp(item['timestamp']), []).append(item)
    targets = sorted(roles)
    if len(targets) != 983 or len(report['missing']) != 1147 or len({x['jst_date'] for x in report['missing']}) != 44:
        raise RepairError('FROZEN_REPAIR_LIST_MISMATCH')
    subset = ROOT / EVIDENCE / 'USD_JPY_M15_BA_permitted.csv'
    header, rows = read_original(subset)
    if len(rows) != 248784 or set(targets).intersection(t for t, _ in rows):
        raise RepairError('TARGET_IS_NOT_A_MISSING_TIMESTAMP')
    if sha(header + b''.join(row for _, row in rows)) != manifest['subset']['sha256']:
        raise RepairError('INPUT_BYTE_PARITY_MISMATCH')
    groups(targets)
    return Inputs(subset, manifest['subset']['sha256'], targets, roles,
                  {'pinned_inputs': PINNED, 'artifact_bindings': manifest['bindings'],
                   'freeze_commit': manifest['freeze_commit'], 'original_cache_opened': False})


def response_candles(body: bytes, requested: list[int]) -> dict[int, dict]:
    try:
        data = json.loads(body)
    except (ValueError, UnicodeError):
        raise RepairError('INVALID_JSON_RESPONSE') from None
    if not isinstance(data, dict) or set(data) != {'instrument', 'granularity', 'candles'}:
        raise RepairError('UNEXPECTED_RESPONSE_SCHEMA')
    if data['instrument'] != 'USD_JPY' or data['granularity'] != 'M15' or not isinstance(data['candles'], list):
        raise RepairError('RESPONSE_IDENTITY_MISMATCH')
    allowed = set(requested)
    found = {}
    for candle in data['candles']:
        if not isinstance(candle, dict):
            raise RepairError('INVALID_CANDLE_SCHEMA')
        value = stamp(candle.get('time'))  # timestamp guard BEFORE accessing quote values
        if value not in allowed or value in found:
            raise RepairError('UNREQUESTED_OR_DUPLICATE_CANDLE')
        if set(candle) != {'time', 'bid', 'ask', 'volume', 'complete'}:
            raise RepairError('INVALID_CANDLE_SCHEMA')
        found[value] = candle
    return found


def candle_row(value: int, candle: dict, newline: str) -> bytes:
    if candle['complete'] is not True:
        raise RepairError('INCOMPLETE_CANDLE')
    if type(candle['volume']) is not int or candle['volume'] < 0:
        raise RepairError('INVALID_VOLUME')
    quotes = {}
    for side in ('bid', 'ask'):
        if not isinstance(candle[side], dict) or set(candle[side]) != set('ohlc'):
            raise RepairError('INVALID_QUOTES')
        for part in 'ohlc':
            text = candle[side][part]
            if not isinstance(text, str) or not re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', text) or len(text) > 24:
                raise RepairError('INVALID_QUOTES')
            try:
                number = Decimal(text)
            except InvalidOperation:
                raise RepairError('INVALID_QUOTES') from None
            if not number.is_finite() or number <= 0:
                raise RepairError('INVALID_QUOTES')
            quotes[side, part] = number
        if not (quotes[side, 'l'] <= min(quotes[side, 'o'], quotes[side, 'c'])
                <= max(quotes[side, 'o'], quotes[side, 'c']) <= quotes[side, 'h']):
            raise RepairError('INVALID_OHLC')
    if any(quotes['ask', p] < quotes['bid', p] for p in 'ohlc'):
        raise RepairError('CROSSED_QUOTES')
    values = [str(value), datetime.fromtimestamp(value / 1000, timezone.utc).isoformat(timespec='seconds')]
    values += [candle[side][p] for side in ('bid', 'ask') for p in 'ohlc']
    values += [str(candle['volume']), 'True']
    # Existing cache schema has derived mid columns. These are same-bar arithmetic
    # views of authoritative BA observations, never interpolated/synthetic candles.
    values += [str((quotes['bid', p] + quotes['ask', p]) / 2) for p in 'ohlc']
    stream = io.StringIO(newline='')
    csv.writer(stream, lineterminator=newline).writerow(values)
    return stream.getvalue().encode('utf-8')


def merge_verified(inputs: Inputs, repairs: dict[int, bytes], output: Path) -> dict:
    if set(repairs) != set(inputs.targets):
        raise RepairError('RESIDUAL_GAPS_NO_DERIVED_CACHE')
    header, originals = read_original(inputs.subset)
    if sha(inputs.subset.read_bytes()) != inputs.subset_sha256:
        raise RepairError('ORIGINAL_SUBSET_CHANGED')
    old_keys = {t for t, _ in originals}
    if old_keys.intersection(repairs):
        raise RepairError('REPAIR_WOULD_OVERWRITE_OBSERVATION')
    merged = sorted(originals + list(repairs.items()))
    for value, raw in repairs.items():
        if int(raw.split(b',', 1)[0]) != value or not LOWER <= value < UPPER or value % STEP:
            raise RepairError('REPAIR_ROW_TIMESTAMP_MISMATCH')
    temporary = output.with_suffix('.partial')
    with temporary.open('xb') as target:
        target.write(header)
        for _, raw in merged:
            target.write(raw)
    check_header, check_rows = read_original(temporary)
    preserved = check_header + b''.join(raw for t, raw in check_rows if t in old_keys)
    if sha(preserved) != inputs.subset_sha256 or [t for t, _ in check_rows] != [t for t, _ in merged]:
        raise RepairError('MERGE_BYTE_PARITY_FAILED')
    if sha(inputs.subset.read_bytes()) != inputs.subset_sha256 or output.exists():
        raise RepairError('OUTPUT_OR_SOURCE_CONFLICT')
    temporary.rename(output)
    return {'sha256': sha(output.read_bytes()), 'byte_count': output.stat().st_size,
            'row_count': len(merged), 'original_rows_preserved': len(originals),
            'added_rows': len(repairs), 'original_row_bytes_sha256': sha(preserved),
            'all_original_row_bytes_unchanged': True}


def acquire(inputs: Inputs, output: Path, transport) -> dict:
    """Injected transport permits strictly offline testing of the full control flow."""
    output.mkdir(parents=True, exist_ok=False)
    (output / 'raw').mkdir()
    header, _ = read_original(inputs.subset)
    newline = '\r\n' if header.endswith(b'\r\n') else '\n'
    ledger = {t: {'timestamp': iso(t), 'open_time': t, 'status': 'NOT_REQUESTED',
                  'requirements': inputs.roles[t]} for t in inputs.targets}
    manifest = {'gate': 'TOKYO_FIX_MANUAL_GAP_REPAIR_PREPARATION', 'started_utc': now(),
                'status': 'IN_PROGRESS', 'endpoint': ENDPOINT,
                'authorization': 'User authorized only the frozen 983 missing pre-seal USD_JPY M15 BA timestamps',
                'envelope': [iso(LOWER), iso(UPPER)], 'targets': len(inputs.targets),
                'inputs': inputs.provenance, 'script_sha256': sha(Path(__file__).read_bytes()),
                'python': platform.python_version(), 'requests': [], 'economics_executed': False,
                'full_readiness_claimed': False, 'original_cache_opened': False,
                'mid_columns': 'same-candle arithmetic BA midpoints; original rows copied byte-for-byte'}
    repairs: dict[int, bytes] = {}

    def checkpoint():
        residual = [entry for entry in ledger.values() if entry['status'] != 'REPAIRED']
        save_json(output / 'repair_ledger.json', list(ledger.values()))
        save_json(output / 'residual_gaps.json', residual)
        manifest['repaired_count'] = len(repairs)
        manifest['residual_count'] = len(residual)
        manifest['ledger_sha256'] = sha((output / 'repair_ledger.json').read_bytes())
        manifest['residual_sha256'] = sha((output / 'residual_gaps.json').read_bytes())
        save_json(output / 'repair_manifest.json', manifest)

    checkpoint()
    try:
        for sequence, block in enumerate(groups(inputs.targets), 1):
            parameters = params_for(block)
            record = {'sequence': sequence, 'method': 'GET', 'url': ENDPOINT,
                      'params': parameters, 'requested_timestamps': [iso(t) for t in block],
                      'requested_utc': now()}
            manifest['requests'].append(record)
            for t in block:
                ledger[t].update(status='REQUESTED', request_sequence=sequence)
            checkpoint()
            try:
                status, body, public_headers = transport(parameters)
            except Exception:
                # Never print exceptions/response objects: they could contain headers.
                raise RepairError('NETWORK_REQUEST_FAILED_DETAILS_SUPPRESSED') from None
            record.update(http_status=status, retrieved_utc=now(),
                          response_headers={k: public_headers[k] for k in ('Date', 'RequestID', 'Content-Type') if k in public_headers})
            if status != 200:
                raise RepairError('HTTP_FAILURE_NO_RETRY')
            candles = response_candles(body, block)
            raw_name = f'raw/response_{sequence:04d}.json'
            with (output / raw_name).open('xb') as raw_file:
                raw_file.write(body)
            record.update(raw_response_path=raw_name, raw_response_sha256=sha(body), raw_bytes=len(body))
            failures = []
            for t in block:
                entry = ledger[t]
                entry.update(raw_response_path=raw_name, raw_response_sha256=sha(body))
                if t not in candles:
                    entry['status'] = 'NOT_SUPPLIED_BY_OANDA'
                    failures.append(t)
                    continue
                try:
                    row = candle_row(t, candles[t], newline)
                except RepairError as exc:
                    entry['status'] = str(exc)
                    failures.append(t)
                    continue
                repairs[t] = row
                entry.update(status='REPAIRED', row_sha256=sha(row), row_utf8=row.decode('utf-8'))
            checkpoint()
            if failures:
                raise RepairError('REQUIRED_CANDLES_MISSING_OR_INVALID_STOPPED')
        filename = 'USD_JPY_M15_BA_repaired.csv'
        manifest['derived_cache'] = {'path': filename, **merge_verified(inputs, repairs, output / filename)}
        manifest['status'] = 'REPAIR_COMPLETE_PENDING_SCIENTIFIC_READINESS'
    except (Exception, KeyboardInterrupt) as exc:
        manifest['status'] = 'BLOCKED'
        manifest['failure_code'] = str(exc) if isinstance(exc, RepairError) else 'UNEXPECTED_FAILURE_DETAILS_SUPPRESSED'
    manifest['finished_utc'] = now()
    checkpoint()
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-authorized-repair', action='store_true', required=True)
    parser.parse_args()
    try:
        inputs = preflight()
        # ONLY the user's invocation reaches authentication. No token is accepted as
        # an argument, read from a file, printed, serialized, or included in URLs.
        token = os.environ.get('OANDA_API_TOKEN')
        if not token or not token.strip():
            raise RepairError('OANDA_API_TOKEN_MISSING_FROM_USER_SHELL')
        import requests
        session = requests.Session()
        session.trust_env = False  # no .netrc, proxy credentials, or implicit auth
        session.headers.update({'Authorization': 'Bearer ' + token,
                                'Accept-Datetime-Format': 'RFC3339', 'Accept': 'application/json'})
        del token

        def transport(parameters):
            response = session.get(ENDPOINT, params=parameters, timeout=(10, 30), allow_redirects=False)
            try:
                return response.status_code, response.content, {
                    k: response.headers[k] for k in ('Date', 'RequestID', 'Content-Type') if k in response.headers}
            finally:
                response.close()

        output = ROOT / OUTPUT / datetime.now(timezone.utc).strftime('attempt_%Y%m%dT%H%M%S_%fZ')
        try:
            result = acquire(inputs, output, transport)
        finally:
            session.headers.pop('Authorization', None)
            session.close()
        # Print metadata only: no quotes, financing, account fields or response body.
        print(json.dumps({'status': result['status'], 'repaired_count': result['repaired_count'],
                          'residual_count': result['residual_count'], 'output_directory': str(output),
                          'failure_code': result.get('failure_code')}))
        return 0 if result['status'] == 'REPAIR_COMPLETE_PENDING_SCIENTIFIC_READINESS' else 2
    except (Exception, KeyboardInterrupt) as exc:
        code = str(exc) if isinstance(exc, RepairError) else 'PREFLIGHT_OR_IO_FAILURE_DETAILS_SUPPRESSED'
        print(json.dumps({'status': 'BLOCKED', 'failure_code': code}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
