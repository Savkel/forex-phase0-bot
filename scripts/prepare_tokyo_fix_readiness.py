"""Pre-economics structural checks only. Never calls ledger or timing economics."""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import subprocess

import numpy as np

from bot.forex import tokyo_fix_baseline as b
from bot.forex import tokyo_fix_readiness as v
from scripts import repair_tokyo_m15_gaps as r
from scripts import classify_tokyo_m15_gaps as c

MAP = r.OUTPUT/'classification_20260924T135846_438176Z'
MAP_SHA = '1828b2a89b81be880e1b4d72211c01d08028f45a9c948b0351d24f23434e9b64'
AMENDMENT = 'prereg/2026-09-24-tokyo-fix-complete-case-amendment.md'
DATES = 'prereg/2026-09-24-tokyo-fix-complete-case-dates.json'
READY = 'reports/forex/tokyo_fix/complete_case_readiness_20260924'
TESTS = ['tests/test_tokyo_calendar.py', 'tests/test_tokyo_fix_readiness.py',
         'tests/test_tokyo_m15_gap_repair.py', 'tests/test_tokyo_m15_gap_diagnostics.py',
         'tests/test_tokyo_m15_gap_classification.py', 'tests/test_tokyo_fix_baseline.py']
SOURCES = ['bot/forex/tokyo_fix_baseline.py', 'bot/forex/tokyo_fix_readiness.py',
           'scripts/prepare_tokyo_fix_readiness.py', 'scripts/run_tokyo_fix.py',
           'scripts/repair_tokyo_m15_gaps.py', 'scripts/classify_tokyo_m15_gaps.py',
           'scripts/diagnose_tokyo_m15_gaps.py', *TESTS]


def versions():
    return {'python': platform.python_version(), 'numpy': np.__version__,
            'tzdata': importlib.metadata.version('tzdata')}


def verify_map(inputs):
    path = r.ROOT/MAP/'classification_manifest.json'
    if r.sha(path.read_bytes()) != MAP_SHA:
        raise v.IntegrityError('Frozen full classification manifest changed')
    manifest = json.loads(path.read_text())
    path = r.ROOT/MAP/'gap_classification.json'
    if r.sha(path.read_bytes()) != manifest['classification_sha256']:
        raise v.IntegrityError('Frozen gap ledger changed')
    entries = json.loads(path.read_text())
    if [x['open_time'] for x in entries] != inputs.targets or manifest['status'] != 'GAP_MAP_COMPLETE':
        raise v.IntegrityError('Incomplete classification')
    confirmed = set(c.verified_absences(inputs))
    if manifest['inputs'] != inputs.provenance:
        raise v.IntegrityError('Classification input binding drift')
    for record in manifest['requests']:
        raw = (r.ROOT/MAP/record['raw_response_path']).read_bytes()
        block = [r.stamp(t) for t in record['timestamps']]
        if record['http_status'] != 200 or r.sha(raw) != record['raw_response_sha256'] or record['params'] != r.params_for(block):
            raise v.IntegrityError('Raw availability evidence mismatch')
        if r.response_candles(raw, block) or confirmed.intersection(block):
            raise v.IntegrityError('Absence/coverage contradiction')
        confirmed.update(block)
    if confirmed != set(inputs.targets):
        raise v.IntegrityError('Availability map does not cover all targets')
    for x in entries:
        if x['status'] != 'ABSENT_FROM_OANDA' or x['requirements'] != inputs.roles[x['open_time']]:
            raise v.IntegrityError('Frozen map role/status mismatch')
    return entries


def validate_row(row, previous):
    """Return stamp, execution opens, and quote-validity code; never a return."""
    if set(row) != set(r.COLUMNS):
        raise v.IntegrityError('Unknown/missing cache columns')
    stamp = int(row['open_time'])
    if not v.L <= stamp < v.U or stamp % v.STEP or (previous is not None and stamp <= previous):
        raise v.IntegrityError('Cache timestamp identity/order/seal failure')
    parsed = datetime.fromisoformat(row['time'].replace('Z', '+00:00'))
    if parsed.utcoffset() != timedelta(0) or v.utc_ms(parsed) != stamp:
        raise v.IntegrityError('Disagreeing time fields')
    try:
        q = {s+p: float(row[s+'_'+p]) for s in ('bid', 'ask') for p in 'ohlc'}
        if not all(math.isfinite(x) and x > 0 for x in q.values()):
            raise ValueError
        if any(q['ask'+p] < q['bid'+p] for p in 'ohlc'):
            raise ValueError
        for side in ('bid', 'ask'):
            if not q[side+'l'] <= min(q[side+'o'], q[side+'c']) <= max(q[side+'o'], q[side+'c']) <= q[side+'h']:
                raise ValueError
        if row['complete'] not in ('True', 'true'):
            raise ValueError
        volume = float(row['volume'])
        if not math.isfinite(volume) or volume < 0 or not volume.is_integer():
            raise ValueError
        for part in 'ohlc':
            midpoint = float(row['mid_'+part])
            if not math.isfinite(midpoint) or not q['bid'+part] <= midpoint <= q['ask'+part]:
                raise ValueError
        b.executable_quotes(q['bido'], q['asko'], stress=True)
    except (ValueError, TypeError, v.IntegrityError):
        return stamp, None, None, 'INVALID_CANDLE'
    return stamp, q['bido'], q['asko'], None


def validated_inputs():
    inputs = r.preflight()  # reads only previously isolated, hash-bound pre-seal subset
    entries = verify_map(inputs)
    calendar = v.calendar_dates()
    ts, bids, asks, invalid = [], [], [], set()
    previous = None
    with inputs.subset.open(encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            stamp, bid, ask, issue = validate_row(row, previous)
            previous = stamp
            ts.append(stamp); bids.append(bid); asks.append(ask)
            if issue:
                invalid.add(stamp)
    observed = set(ts)
    support = v.support_check(observed, calendar['eligible_dates'])
    if support['missing'] != json.loads((r.ROOT/r.EVIDENCE/'timestamp_support.json').read_text())['missing']:
        raise v.IntegrityError('Original missingness evidence changed')
    included, excluded = b.complete_cases(calendar['eligible_dates'], observed, invalid)
    gap_dates = sorted({x['jst_date'] for entry in entries for x in entry['requirements']})
    if [x['jst_date'] for x in excluded] != gap_dates or len(included) != 2401 or invalid:
        # Do not silently expand or change the externally specified 44-date mask.
        raise v.IntegrityError('Additional quote/evaluability blocker beyond frozen absence map')
    evidence = {'calendar_eligible_count': 2446, 'boundary_evaluable_count': 2445,
                'boundary_exclusions': calendar['boundary_exclusions'],
                'evaluable_count': len(included), 'excluded_count': len(excluded),
                'exclusion_rate_of_boundary_evaluable': len(excluded)/2445,
                'eligible_not_evaluable_including_boundary_count': 45,
                'eligible_not_evaluable_including_boundary_rate': 45/2446,
                'included_dates': included, 'excluded_dates': excluded,
                'classification_manifest': str(MAP/'classification_manifest.json'),
                'classification_manifest_sha256': MAP_SHA,
                'subset_sha256': inputs.subset_sha256,
                'quote_integrity_issues': len(invalid), 'economics_executed': False}
    return np.array(ts, dtype=np.int64), np.array(bids), np.array(asks), evidence


def schedule_checks(stamps, labels):
    plan = b.intents(labels)
    exposure, masks = b.exposure_grid(stamps, plan)
    for role, windows in plan.items():
        for w in windows:
            day = date.fromisoformat(w.label)
            p, end = v.scheduled_windows(day)['passive']
            if not p-v.STEP < w.entry <= w.exit < end+v.STEP:
                raise v.IntegrityError('Rollover exposure')
    if any(int(masks[role].sum()) != len(labels)*3 for role in ('primary', 'early', 'late')):
        raise v.IntegrityError('Intraday holding duration mismatch')
    if int(masks['passive'].sum()) != len(labels)*94 or exposure['gross_parity_residual'] > 1e-12:
        raise v.IntegrityError('Passive schedule/exposure matching mismatch')
    return exposure


def binding_files():
    return [*SOURCES, AMENDMENT, DATES, r.PREREG, 'CLAUDE.md',
            'governance/2026-09-24-intraday-passive-benchmark-amendment.md',
            'provenance/tokyo_v20_daily_research_venue.md']


def main():
    stamps, _, _, dates = validated_inputs()
    frozen = json.loads((r.ROOT/DATES).read_text())
    if frozen != dates:
        raise v.IntegrityError('Frozen complete-case mask differs from readiness')
    exposure = schedule_checks(stamps, dates['included_dates'])
    report = r.ROOT/READY
    report.mkdir(parents=True, exist_ok=False)
    tests = subprocess.run(['python', '-m', 'pytest', *TESTS, '-q'], cwd=r.ROOT,
                           capture_output=True, text=True, check=False)
    (report/'focused_tests.txt').write_text(tests.stdout+tests.stderr, encoding='utf-8')
    if tests.returncode:
        v.write_json_new(report/'readiness.json', {'status': 'BLOCKED_TESTS', 'economics_executed': False})
        return 2
    manifest = {'status': 'READY_FOR_USER_RUN_ONE_SHOT_ECONOMICS', 'economics_executed': False,
                'dates': dates, 'exposure_readiness': exposure, 'versions': versions(),
                'bindings': {name: v.digest(r.ROOT/name) for name in binding_files()},
                'focused_tests_sha256': v.digest(report/'focused_tests.txt'),
                'checks': ['seal_guard_synthetic', 'calendar_hashes', 'timezone_DST_rollover',
                           'full_map_raw_hashes', 'entire_permitted_subset_quote_validity',
                           'complete_case_mask_parity', 'paired_window_support', 'cash_units_hand_ledgers',
                           'causal_pending_intents', 'incremental_rebalance_costs', 'no_leverage_matching',
                           'centered_circular_bootstrap_parity', 'determinism', 'one_shot_fail_closed'],
                'implementation_commit_status': 'LOCAL_UNCOMMITTED_HASH_BOUND',
                'account_mode': 'UNKNOWN', 'venue_assumption': 'OANDA_V20_DAILY_1700_AMERICA_NEW_YORK'}
    v.write_json_new(report/'readiness.json', manifest)
    print(json.dumps({'status': manifest['status'], 'evaluable_count': dates['evaluable_count'],
                      'excluded_count': dates['excluded_count'], 'economics_executed': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
