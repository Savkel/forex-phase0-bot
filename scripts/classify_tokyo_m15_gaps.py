"""USER-RUN: classify frozen gaps only; no cache merge, ledger or economics."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from scripts import repair_tokyo_m15_gaps as r

DIAGNOSTIC = r.OUTPUT/'diagnostic_20260924T132708_720967Z'
DIAGNOSTIC_SHA = '0a346eca6f250f715944c987e1f031167e180f9fe304e627173cdd101c3aa924'
STATES = ('RECOVERABLE', 'ABSENT_FROM_OANDA', 'REQUEST_ERROR_UNRESOLVED')


def verified_absences(inputs):
    path = r.ROOT/DIAGNOSTIC/'diagnostic_manifest.json'
    if r.sha(path.read_bytes()) != DIAGNOSTIC_SHA:
        raise r.RepairError('DIAGNOSTIC_HASH_MISMATCH')
    report = json.loads(path.read_text())
    if report['status'] != 'DIAGNOSTICS_COMPLETE_PENDING_REVIEW' or len(report['requests']) != 6:
        raise r.RepairError('DIAGNOSTIC_INCOMPLETE')
    seeds = {}
    for request in report['requests']:
        raw = (path.parent/request['raw_response_path']).read_bytes()
        if r.sha(raw) != request['raw_response_sha256'] or request['http_status'] != 200:
            raise r.RepairError('DIAGNOSTIC_RESPONSE_BINDING_FAILED')
        candles = r.response_candles(raw, request['allowed'])
        if [r.iso(t) for t in sorted(candles)] != request['returned_timestamps']:
            raise r.RepairError('DIAGNOSTIC_TIMESTAMP_MISMATCH')
        if request['case'] == 'bracketed_missing':
            t = r.stamp(request['target'])
            if t not in inputs.targets or sorted(candles) != [t-r.STEP, t+r.STEP]:
                raise r.RepairError('DIAGNOSTIC_ABSENCE_NOT_ESTABLISHED')
            seeds[t] = {'evidence_manifest': str(DIAGNOSTIC/'diagnostic_manifest.json'),
                        'evidence_manifest_sha256': DIAGNOSTIC_SHA,
                        'raw_response_path': str(DIAGNOSTIC/request['raw_response_path']),
                        'raw_response_sha256': request['raw_response_sha256']}
    if len(seeds) != 2:
        raise r.RepairError('DIAGNOSTIC_TARGET_COUNT_MISMATCH')
    return seeds


def categories(requirements):
    pairs = {(x['role'], x['kind']) for x in requirements}
    labels = set()
    for kind in ('ENTRY', 'EXIT'):
        if ('primary', kind) in pairs:
            labels.add('primary_'+kind.lower())
        if ('passive', kind) in pairs:
            labels.add('passive_'+kind.lower())
    if any(role in ('early', 'late') for role, _ in pairs):
        labels.add('timing_null_controls')
    if pairs == {('passive', 'INTERMEDIATE')}:
        labels.add('passive_intermediate_only')
    if ('primary', 'INTERMEDIATE') in pairs:
        labels.add('primary_intermediate')
    if any(kind == 'DECISION_BAR' for _, kind in pairs):
        labels.add('decision_bar')
    return sorted(labels)


def summary(entries):
    names = ('primary_entry', 'primary_exit', 'timing_null_controls', 'passive_entry',
             'passive_exit', 'passive_intermediate_only', 'primary_intermediate', 'decision_bar')
    return {'unique_timestamp_counts': {s: sum(x['status'] == s for x in entries) for s in STATES},
            'counts_by_role_overlapping': {
                name: {s: sum(x['status'] == s and name in x['categories'] for x in entries) for s in STATES}
                for name in names},
            'absent_requirement_counts': dict(Counter(
                x['role']+'/'+x['kind'] for entry in entries if entry['status'] == 'ABSENT_FROM_OANDA'
                for x in entry['requirements'])),
            'scope': 'Absence is from the queried practice USD_JPY M15 BA endpoint, not all OANDA archives.'}


def classify(inputs, seeds, output, transport):
    if not set(seeds) <= set(inputs.targets):
        raise r.RepairError('UNAPPROVED_SEED_TIMESTAMP')
    pending = [t for t in inputs.targets if t not in seeds]
    blocks = r.groups(pending) if pending else []
    output.mkdir(parents=True, exist_ok=False)
    (output/'raw').mkdir()
    entries = {t: {'timestamp': r.iso(t), 'open_time': t, 'requirements': inputs.roles[t],
                   'categories': categories(inputs.roles[t]), 'status': 'REQUEST_ERROR_UNRESOLVED',
                   'reason': 'NOT_REQUESTED'} for t in inputs.targets}
    for t, evidence in seeds.items():
        entries[t].update(status='ABSENT_FROM_OANDA', reason='VERIFIED_PRIOR_BRACKETED_RESPONSE', **evidence)
    report = {'gate': 'TOKYO_FIX_FULL_GAP_CLASSIFICATION', 'started_utc': r.now(),
              'endpoint': r.ENDPOINT, 'status': 'IN_PROGRESS', 'inputs': inputs.provenance,
              'script_sha256': r.sha(Path(__file__).read_bytes()),
              'validator_sha256': r.sha(Path(r.__file__).read_bytes()),
              'maximum_requests': len(blocks), 'reused_absences': len(seeds), 'requests': [],
              'economics_executed': False, 'cache_modified': False, 'original_cache_opened': False}
    def checkpoint():
        rows = list(entries.values())
        r.save_json(output/'gap_classification.json', rows)
        report['classification_sha256'] = r.sha((output/'gap_classification.json').read_bytes())
        report['summary'] = summary(rows)
        r.save_json(output/'classification_manifest.json', report)
    checkpoint()
    try:
        for sequence, block in enumerate(blocks, 1):
            params = r.params_for(block)  # validated original range semantics
            request = {'sequence': sequence, 'params': params, 'requested_utc': r.now(),
                       'timestamps': [r.iso(t) for t in block]}
            report['requests'].append(request)
            for t in block:
                entries[t].update(reason='REQUEST_STARTED', request_sequence=sequence)
            checkpoint()
            try:
                try:
                    status, raw, headers = transport(params)
                except Exception:
                    raise r.RepairError('NETWORK_ERROR_DETAILS_SUPPRESSED') from None
                request.update(http_status=status, retrieved_utc=r.now(),
                               response_headers={k: headers[k] for k in ('Date', 'RequestID', 'Content-Type') if k in headers})
                if status != 200:
                    raise r.RepairError('HTTP_ERROR')
                candles = r.response_candles(raw, block)
                name = f'raw/response_{sequence:04d}.json'
                with (output/name).open('xb') as handle:
                    handle.write(raw)
                request.update(raw_response_path=name, raw_response_sha256=r.sha(raw))
                for t in block:
                    entry = entries[t]
                    entry.update(raw_response_path=name, raw_response_sha256=r.sha(raw))
                    if t not in candles:
                        entry.update(status='ABSENT_FROM_OANDA', reason='VALID_200_RESPONSE_OMITS_TIMESTAMP')
                        continue
                    try:
                        r.candle_row(t, candles[t], '\n')  # validate only; discard row
                        entry.update(status='RECOVERABLE', reason='VALID_COMPLETE_BA_CANDLE')
                    except r.RepairError as exc:
                        entry.update(reason=str(exc))
            except r.RepairError as exc:
                request['failure_code'] = str(exc)
                for t in block:
                    entries[t].update(status='REQUEST_ERROR_UNRESOLVED', reason=str(exc))
                # Never retry, bypass denied access, or continue through throttling.
                if request.get('http_status') in (401, 403, 429):
                    report['stopped_reason'] = 'AUTHORIZATION_OR_RATE_LIMIT'
                    break
            checkpoint()  # an absent/invalid candle never stops subsequent blocks
        report['status'] = ('GAP_MAP_COMPLETE' if all(x['status'] != 'REQUEST_ERROR_UNRESOLVED'
                                                    for x in entries.values()) else 'CLASSIFICATION_UNRESOLVED')
    except (Exception, KeyboardInterrupt):
        report.update(status='CLASSIFICATION_UNRESOLVED', stopped_reason='INTERRUPTED_OR_IO_ERROR_DETAILS_SUPPRESSED')
    report['finished_utc'] = r.now()
    checkpoint()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-authorized-classification', action='store_true', required=True)
    parser.parse_args()
    try:
        inputs = r.preflight()
        seeds = verified_absences(inputs)
        token = os.environ.get('OANDA_API_TOKEN')
        if not token or not token.strip():
            raise r.RepairError('OANDA_API_TOKEN_MISSING_FROM_USER_SHELL')
        import requests
        session = requests.Session()
        session.trust_env = False
        session.headers.update({'Authorization': 'Bearer '+token,
                                'Accept-Datetime-Format': 'RFC3339', 'Accept': 'application/json'})
        del token
        def transport(params):
            response = session.get(r.ENDPOINT, params=params, timeout=(10, 30), allow_redirects=False)
            try:
                return response.status_code, response.content, {
                    k: response.headers[k] for k in ('Date', 'RequestID', 'Content-Type') if k in response.headers}
            finally:
                response.close()
        output = r.ROOT/r.OUTPUT/datetime.now(timezone.utc).strftime('classification_%Y%m%dT%H%M%S_%fZ')
        try:
            report = classify(inputs, seeds, output, transport)
        finally:
            session.headers.pop('Authorization', None)
            session.close()
        print(json.dumps({'status': report['status'], 'output_directory': str(output), 'summary': report['summary']}))
        return 0 if report['status'] == 'GAP_MAP_COMPLETE' else 2
    except (Exception, KeyboardInterrupt) as exc:
        print(json.dumps({'status': 'BLOCKED', 'failure_code': str(exc) if isinstance(exc, r.RepairError)
                          else 'PREFLIGHT_OR_IO_ERROR_DETAILS_SUPPRESSED'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
