"""USER-RUN ONLY: frozen, exclusive one-shot historical DEVELOPMENT economics."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from bot.forex import tokyo_fix_baseline as b
from bot.forex import tokyo_fix_readiness as v
from scripts import prepare_tokyo_fix_readiness as p
from scripts import repair_tokyo_m15_gaps as r

OUTPUT = 'reports/forex/tokyo_fix/economics_once_complete_case_20260924'


def verify_ready():
    path = r.ROOT/p.READY/'readiness.json'
    ready = json.loads(path.read_text())
    if ready['status'] != 'READY_FOR_USER_RUN_ONE_SHOT_ECONOMICS' or ready['economics_executed'] is not False:
        raise v.IntegrityError('Not authorized by completed readiness')
    if set(ready['bindings']) != set(p.binding_files()):
        raise v.IntegrityError('Missing/unknown readiness bindings')
    for name, expected in ready['bindings'].items():
        if v.digest(r.ROOT/name) != expected:
            raise v.IntegrityError('Readiness binding changed: '+name)
    if ready['versions'] != p.versions():
        raise v.IntegrityError('Runtime version drift')
    if v.digest(r.ROOT/p.READY/'focused_tests.txt') != ready['focused_tests_sha256']:
        raise v.IntegrityError('Test evidence changed')
    stamps, bids, asks, dates = p.validated_inputs()
    if dates != ready['dates'] or dates != json.loads((r.ROOT/p.DATES).read_text()):
        raise v.IntegrityError('Frozen evaluability changed')
    if p.schedule_checks(stamps, dates['included_dates']) != ready['exposure_readiness']:
        raise v.IntegrityError('Schedule/exposure drift')
    return ready, stamps, bids, asks, dates


def execute():
    output = r.ROOT/OUTPUT
    if output.exists():
        raise v.IntegrityError('One-shot already attempted; no rerun permitted')
    ready, stamps, bids, asks, dates = verify_ready()
    # mkdir is the atomic, exclusive run claim. Any failed attempt is preserved.
    output.mkdir(parents=True, exist_ok=False)
    v.write_json_new(output/'execution.json', {'status': 'STARTED_NO_RETRY', 'started_utc': r.now(),
                                             'readiness_sha256': v.digest(r.ROOT/p.READY/'readiness.json'),
                                             'bindings': ready['bindings']})
    try:
        results, legs, starts = b.economics(stamps, bids, asks, dates['included_dates'])
        results['sample'] = dates
        results['limitations'] = ['Complete-case historical estimand; missingness may be nonrandom.',
                                 'Availability mask is retrospective evaluability, not a live trading signal.',
                                 'No untouched OOS, account-specific feasibility or guaranteed-fill claim.',
                                 'No financing only under the frozen DAILY research venue assumption.']
        for name, first, last in (('2014_2016', '2014', '2016'), ('2017_2020', '2017', '2020'), ('2021_end', '2021', '2024')):
            excluded = sum(first <= x['jst_date'][:4] <= last for x in dates['excluded_dates'])
            for cost in ('base', 'stress'):
                block = results['costs'][cost]['chronological_blocks'][name]
                block['excluded_date_count'] = excluded
                block['exclusion_rate'] = excluded/(excluded+block['n'])
        arrays = {'stamps': stamps, 'bootstrap_starts': starts}
        ledgers = {}
        for cost, books in legs.items():
            ledgers[cost] = {}
            for name, book in books.items():
                ledgers[cost][name] = book['trades']
                arrays[cost+'_'+name+'_before'] = book['before']
                arrays[cost+'_'+name+'_after'] = book['after']
                for field in ('cash', 'units', 'delta_units'):
                    arrays[cost+'_'+name+'_'+field] = book[field]
        v.write_json_new(output/'results.json', results)
        v.write_json_new(output/'daily_ledgers.json', ledgers)
        with (output/'curves_bootstrap.npz').open('xb') as handle:
            np.savez_compressed(handle, **arrays)
        v.write_json_new(output/'completion.json', {
            'status': 'ECONOMICS_COMPLETED_PENDING_EXTERNAL_ADJUDICATION', 'finished_utc': r.now(),
            'files': {name: v.digest(output/name) for name in ('results.json', 'daily_ledgers.json', 'curves_bootstrap.npz', 'execution.json')},
            'network_used': False, 'sealed_data_accessed': False})
        print(json.dumps({'status': 'ECONOMICS_COMPLETED_PENDING_EXTERNAL_ADJUDICATION', 'output': str(output)}))
        return 0
    except (Exception, KeyboardInterrupt):
        v.write_json_new(output/'failure.json', {'status': 'FAILED_ATTEMPT_PRESERVED_NO_AUTOMATIC_RETRY',
                                              'time_utc': r.now()})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-one-shot-economics', action='store_true', required=True)
    parser.parse_args()
    return execute()


if __name__ == '__main__':
    raise SystemExit(main())
