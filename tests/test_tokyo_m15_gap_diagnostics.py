"""Synthetic diagnostics only; authenticated execution is user-run."""
import json

import pytest
import requests

from scripts import diagnose_tokyo_m15_gaps as d
from scripts import repair_tokyo_m15_gaps as r


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Live network is forbidden')
    monkeypatch.setattr(requests.sessions.Session, 'request', forbidden)


def candle(t):
    return {'time': r.iso(t), 'bid': dict.fromkeys('ohlc', '100'),
            'ask': dict.fromkeys('ohlc', '101'), 'volume': 1, 'complete': True}


def body(items):
    return json.dumps({'instrument': 'USD_JPY', 'granularity': 'M15', 'candles': items}).encode()


@pytest.fixture
def inputs(tmp_path):
    targets = [r.stamp(x) for x in ('2014-02-12T01:00:00Z', '2018-09-28T05:00:00Z')]
    path = tmp_path/'synthetic.csv'
    path.write_bytes((','.join(r.COLUMNS)+'\n').encode()+b''.join(
        r.candle_row(t+i*r.STEP, candle(t+i*r.STEP), '\n') for t in targets for i in (-1, 1, 2)))
    return r.Inputs(path, r.sha(path.read_bytes()), targets, {}, {'synthetic': True})


def test_plan_only_six_bounded_queries_and_verified_neighbours(inputs):
    plan = d.plan(inputs)
    assert len(plan) == 6
    for i, target in enumerate(inputs.targets):
        short, exact, bracket = plan[i*3:i*3+3]
        assert short['params']['to'] == r.iso(target-1)
        assert exact['params']['to'] == r.iso(target+r.STEP)
        assert bracket['allowed'] == [target+i*r.STEP for i in (-1, 0, 1, 2)]
        assert len(bracket['known_good']) == 3
    inputs.targets = []
    with pytest.raises(r.RepairError):
        d.plan(inputs)


def test_empty_first_diagnostic_does_not_hide_remaining_cases(inputs, tmp_path):
    calls = []
    plan = d.plan(inputs)
    def fake(params):
        case = plan[len(calls)]
        calls.append(params)
        bars = [] if case['case'] == 'known_good_original_range' else [candle(t) for t in case['allowed']]
        return 200, body(bars), {'Authorization': 'SECRET', 'RequestID': 'synthetic'}
    output = tmp_path/'diagnostic'
    result = d.diagnose(inputs, output, fake)
    assert len(calls) == 6 and result['status'] == 'DIAGNOSTICS_COMPLETE_PENDING_REVIEW'
    assert [x['target_returned'] for x in result['requests']] == [False, True, True]*2
    for item in result['requests']:
        assert r.sha((output/item['raw_response_path']).read_bytes()) == item['raw_response_sha256']
    assert 'SECRET' not in (output/'diagnostic_manifest.json').read_text()
    assert not list(output.glob('*.csv'))
    with pytest.raises(FileExistsError):
        d.diagnose(inputs, output, fake)


@pytest.mark.parametrize('case', ['network', 'http', 'outside'])
def test_failure_stops_without_leaking_private_errors(inputs, tmp_path, case):
    calls = []
    def fake(params):
        calls.append(params)
        if case == 'network':
            raise RuntimeError('SENSITIVE_EXCEPTION')
        if case == 'http':
            return 401, b'SENSITIVE_RESPONSE', {}
        return 200, body([candle(r.UPPER)]), {}
    output = tmp_path/case
    result = d.diagnose(inputs, output, fake)
    assert result['status'] == 'BLOCKED' and len(calls) == 1
    assert not list((output/'raw').iterdir())
    assert 'SENSITIVE' not in (output/'diagnostic_manifest.json').read_text()
