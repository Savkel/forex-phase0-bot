"""Offline, synthetic-only full-gap classification tests."""
import json

import pytest
import requests

from scripts import classify_tokyo_m15_gaps as c
from scripts import repair_tokyo_m15_gaps as r


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Network forbidden')
    monkeypatch.setattr(requests.sessions.Session, 'request', forbidden)


def candle(t):
    return {'time': r.iso(t), 'bid': dict.fromkeys('ohlc', '100'),
            'ask': dict.fromkeys('ohlc', '101'), 'complete': True, 'volume': 1}


def response(items):
    return json.dumps({'instrument': 'USD_JPY', 'granularity': 'M15', 'candles': items}).encode()


@pytest.fixture
def inputs(tmp_path):
    targets = [r.LOWER+i*r.STEP for i in (1, 2, 4, 6)]
    roles = {t: [{'role': 'passive', 'kind': 'INTERMEDIATE', 'timestamp': r.iso(t),
                  'jst_date': '2014-01-06'}] for t in targets}
    return r.Inputs(tmp_path/'not_read.csv', 'synthetic', targets, roles, {'synthetic': True})


def test_missing_and_invalid_continue_and_classify_every_target(inputs, tmp_path):
    calls = []
    def fake(params):
        calls.append(params)
        if len(calls) == 1:
            bar = candle(inputs.targets[1])
            bar['complete'] = False
            return 200, response([bar]), {}
        return 200, response([candle(r.stamp(params['from']))]), {'Authorization': 'PRIVATE'}
    output = tmp_path/'classification'
    result = c.classify(inputs, {}, output, fake)
    assert len(calls) == 3
    assert result['status'] == 'CLASSIFICATION_UNRESOLVED'
    entries = json.loads((output/'gap_classification.json').read_text())
    assert [x['status'] for x in entries] == ['ABSENT_FROM_OANDA', 'REQUEST_ERROR_UNRESOLVED', 'RECOVERABLE', 'RECOVERABLE']
    assert entries[1]['reason'] == 'INCOMPLETE_CANDLE'
    assert not any('row_utf8' in x for x in entries)
    assert result['classification_sha256'] == r.sha((output/'gap_classification.json').read_bytes())
    assert not list(output.glob('*.csv'))
    assert 'PRIVATE' not in (output/'classification_manifest.json').read_text()


def test_seed_is_reused_and_absence_does_not_stop_completion(inputs, tmp_path):
    calls = []
    def fake(params):
        calls.append(params)
        return 200, response([]), {}
    result = c.classify(inputs, {inputs.targets[-1]: {'evidence': 'synthetic'}}, tmp_path/'map', fake)
    assert result['status'] == 'GAP_MAP_COMPLETE' and len(calls) == 2
    assert result['summary']['unique_timestamp_counts'] == dict(zip(c.STATES, (0, 4, 0)))
    assert result['reused_absences'] == 1


@pytest.mark.parametrize('mode', ['http500', 'network', 'schema', 'unexpected_timestamp'])
def test_bad_response_unresolved_not_absent_and_continues(inputs, tmp_path, mode):
    calls = []
    def fake(params):
        calls.append(params)
        if len(calls) == 1:
            if mode == 'network':
                raise RuntimeError('PRIVATE')
            if mode == 'schema':
                return 200, b'{"private":"PRIVATE"}', {}
            if mode == 'unexpected_timestamp':
                return 200, response([candle(r.UPPER)]), {}
            return 500, b'PRIVATE', {}
        return 200, response([]), {}
    output = tmp_path/mode
    result = c.classify(inputs, {}, output, fake)
    assert len(calls) == 3 and result['status'] == 'CLASSIFICATION_UNRESOLVED'
    assert result['summary']['unique_timestamp_counts'] == dict(zip(c.STATES, (0, 2, 2)))
    assert 'PRIVATE' not in (output/'classification_manifest.json').read_text()
    assert not (output/'raw/response_0001.json').exists()


@pytest.mark.parametrize('status', [401, 403, 429])
def test_denied_or_rate_limited_stops_without_mislabeling(inputs, tmp_path, status):
    calls = []
    def fake(params):
        calls.append(params)
        return status, b'PRIVATE', {}
    result = c.classify(inputs, {}, tmp_path/'map', fake)
    assert len(calls) == 1
    assert result['summary']['unique_timestamp_counts'] == dict(zip(c.STATES, (0, 0, 4)))


def test_role_overlap_and_intermediate_only_are_distinct():
    requirements = [{'role': 'passive', 'kind': 'INTERMEDIATE'}, {'role': 'primary', 'kind': 'ENTRY'}]
    assert c.categories(requirements) == ['primary_entry']
    assert c.categories(requirements[:1]) == ['passive_intermediate_only']
    shared = [{'role': 'passive', 'kind': 'ENTRY'}, {'role': 'early', 'kind': 'DECISION_BAR'}]
    assert c.categories(shared) == ['decision_bar', 'passive_entry', 'timing_null_controls']


def test_existing_output_is_never_overwritten(inputs, tmp_path):
    with pytest.raises(FileExistsError):
        c.classify(inputs, {}, tmp_path, lambda _: pytest.fail('must not fetch'))
