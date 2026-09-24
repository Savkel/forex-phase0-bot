"""USER-RUN: six bounded range diagnostics; never repairs or computes economics."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from scripts import repair_tokyo_m15_gaps as r


def plan(inputs: r.Inputs) -> list[dict]:
    # Two isolated gaps, chosen by timestamp metadata, with observed neighbours.
    _, rows = r.read_original(inputs.subset)
    present = {t for t, _ in rows}
    result = []
    for text in ('2014-02-12T01:00:00Z', '2018-09-28T05:00:00Z'):
        t = r.stamp(text)
        if t not in inputs.targets or not {t-r.STEP, t+r.STEP, t+2*r.STEP} <= present:
            raise r.RepairError('DIAGNOSTIC_TIMESTAMP_PRECONDITION_FAILED')
        # Compare the original short range on a known-good candle, an exact
        # boundary request for the gap, and a tightly bracketed control request.
        for name, start, end in (
            ('known_good_original_range', t-r.STEP, t-1),
            ('missing_exact_boundary', t, t+r.STEP),
            ('bracketed_missing', t-r.STEP, t+2*r.STEP),
        ):
            if not r.LOWER <= start <= end < r.UPPER:
                raise r.RepairError('DIAGNOSTIC_RANGE_OUTSIDE_ENVELOPE')
            params = r.params_for([start])
            params['to'] = r.iso(end)
            # Permit an inclusive endpoint in diagnostics, recording it exactly.
            allowed = list(range(start, (end // r.STEP)*r.STEP+1, r.STEP))
            result.append({'case': name, 'target': r.iso(t), 'params': params,
                           'allowed': allowed,
                           'known_good': [r.iso(x) for x in allowed if x in present]})
    return result


def diagnose(inputs: r.Inputs, output: Path, transport) -> dict:
    requests = plan(inputs)
    output.mkdir(parents=True, exist_ok=False)
    (output/'raw').mkdir()
    report = {'gate': 'TOKYO_FIX_GAP_REPAIR_DIAGNOSE_AND_RESUME',
              'status': 'IN_PROGRESS', 'started_utc': r.now(), 'endpoint': r.ENDPOINT,
              'script_sha256': r.sha(Path(__file__).read_bytes()),
              'repair_script_sha256': r.sha(Path(r.__file__).read_bytes()),
              'inputs': inputs.provenance, 'requests': [],
              'economics_executed': False, 'repair_executed': False,
              'all_983_unavailable_claimed': False}
    try:
        for number, item in enumerate(requests, 1):
            record = {**item, 'requested_utc': r.now()}
            report['requests'].append(record)
            r.save_json(output/'diagnostic_manifest.json', report)
            try:
                status, body, headers = transport(item['params'])
            except Exception:
                raise r.RepairError('NETWORK_REQUEST_FAILED_DETAILS_SUPPRESSED') from None
            record.update(http_status=status, retrieved_utc=r.now(),
                          response_headers={k: headers[k] for k in ('Date', 'RequestID', 'Content-Type') if k in headers})
            if status != 200:
                raise r.RepairError('HTTP_FAILURE_NO_RETRY')
            candles = r.response_candles(body, item['allowed'])
            filename = f'raw/response_{number:04d}.json'
            with (output/filename).open('xb') as handle:
                handle.write(body)
            record.update(raw_response_path=filename, raw_response_sha256=r.sha(body),
                          returned_timestamps=[r.iso(t) for t in sorted(candles)],
                          target_returned=r.stamp(item['target']) in candles)
            validation = {}
            for t, candle in candles.items():
                try:
                    r.candle_row(t, candle, '\n')  # structural validation only
                    validation[r.iso(t)] = 'VALID_BA_CANDLE'
                except r.RepairError as exc:
                    validation[r.iso(t)] = str(exc)
            record['structural_validation'] = validation
        report['status'] = 'DIAGNOSTICS_COMPLETE_PENDING_REVIEW'
    except (Exception, KeyboardInterrupt) as exc:
        report.update(status='BLOCKED', failure_code=str(exc) if isinstance(exc, r.RepairError)
                      else 'UNEXPECTED_FAILURE_DETAILS_SUPPRESSED')
    report['finished_utc'] = r.now()
    r.save_json(output/'diagnostic_manifest.json', report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-authorized-diagnostics', action='store_true', required=True)
    parser.parse_args()
    try:
        inputs = r.preflight()
        plan(inputs)  # validate all six bounded requests before authentication
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
        output = r.ROOT/r.OUTPUT/datetime.now(timezone.utc).strftime('diagnostic_%Y%m%dT%H%M%S_%fZ')
        try:
            report = diagnose(inputs, output, transport)
        finally:
            session.headers.pop('Authorization', None)
            session.close()
        print(json.dumps({'status': report['status'], 'output_directory': str(output),
                          'failure_code': report.get('failure_code')}))
        return 0 if report['status'] == 'DIAGNOSTICS_COMPLETE_PENDING_REVIEW' else 2
    except (Exception, KeyboardInterrupt) as exc:
        print(json.dumps({'status': 'BLOCKED', 'failure_code': str(exc) if isinstance(exc, r.RepairError)
                          else 'PREFLIGHT_OR_IO_FAILURE_DETAILS_SUPPRESSED'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
