"""Offline synthetic-only verification. Never invoke the user repair entrypoint."""
import json
from pathlib import Path

import pytest
import requests

from scripts import repair_tokyo_m15_gaps as repair


@pytest.fixture(autouse=True)
def no_http(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Network is forbidden in preparation tests')
    monkeypatch.setattr(requests.sessions.Session, 'request', forbidden)


def candle(t):
    return {'time': repair.iso(t).replace('.000Z', '.000000000Z'),
            'bid': {'o': '100.001', 'h': '100.003', 'l': '100.000', 'c': '100.002'},
            'ask': {'o': '100.011', 'h': '100.013', 'l': '100.010', 'c': '100.012'},
            'volume': 7, 'complete': True}


def response(items):
    return json.dumps({'instrument': 'USD_JPY', 'granularity': 'M15', 'candles': items}).encode()


@pytest.fixture
def inputs(tmp_path):
    # No real prices, reports or caches are read by these tests.
    path = tmp_path / 'permitted.csv'
    header = (','.join(repair.COLUMNS) + '\r\n').encode()
    old = [repair.LOWER + repair.STEP * i for i in (0, 3, 5)]
    path.write_bytes(header + b''.join(repair.candle_row(t, candle(t), '\r\n') for t in old))
    targets = [repair.LOWER + repair.STEP * i for i in (1, 2, 4)]
    roles = {t: [{'timestamp': repair.iso(t), 'role': 'passive', 'kind': 'INTERMEDIATE',
                  'jst_date': '2014-01-06'}] for t in targets}
    return repair.Inputs(path, repair.sha(path.read_bytes()), targets, roles, {'synthetic': True})


def test_exact_requests_never_span_observed_candles_or_seal(inputs):
    blocks = repair.groups(inputs.targets)
    assert list(map(len, blocks)) == [2, 1]
    for block in blocks:
        params = repair.params_for(block)
        assert params['from'] == repair.iso(block[0])
        assert params['to'] == repair.iso(block[-1] + repair.STEP - 1)
        assert 'count' not in params
        assert params['price'] == 'BA' and params['granularity'] == 'M15'
        assert params['smooth'] == 'false' and params['includeFirst'] == 'true'
        assert params['alignmentTimezone'] == 'UTC' and params['dailyAlignment'] == 0
    last = repair.params_for([repair.UPPER - repair.STEP])
    assert last['to'] == '2024-01-05T23:59:59.999Z'
    with pytest.raises(repair.RepairError):
        repair.params_for(inputs.targets)


@pytest.mark.parametrize('targets', [[], [repair.UPPER], [repair.LOWER-1],
                                    [repair.LOWER+1], [repair.LOWER,repair.LOWER],
                                    [repair.LOWER+repair.STEP,repair.LOWER]])
def test_request_rejects_invalid_target_grid(targets):
    with pytest.raises(repair.RepairError):
        repair.groups(targets)


@pytest.mark.parametrize('mutation', ['outside', 'duplicate', 'pair', 'granularity', 'nanosecond'])
def test_response_identity_and_timestamp_guards(mutation):
    t = repair.LOWER
    data = {'instrument': 'USD_JPY', 'granularity': 'M15', 'candles': [candle(t)]}
    if mutation == 'outside':
        data['candles'][0]['time'] = repair.iso(repair.UPPER)
    elif mutation == 'duplicate':
        data['candles'].append(candle(t))
    elif mutation == 'pair':
        data['instrument'] = 'EUR_USD'
    elif mutation == 'granularity':
        data['granularity'] = 'H1'
    else:
        data['candles'][0]['time'] = '2014-01-06T00:00:00.000000001Z'
    with pytest.raises(repair.RepairError):
        repair.response_candles(json.dumps(data).encode(), [t])


@pytest.mark.parametrize('mutation', ['incomplete', 'crossed', 'nan', 'negative', 'ohlc', 'volume'])
def test_invalid_authoritative_bar_is_not_repaired(mutation):
    t = repair.LOWER
    item = candle(t)
    if mutation == 'incomplete': item['complete'] = False
    if mutation == 'crossed': item['ask'] = {p: '99.0' for p in 'ohlc'}
    if mutation == 'nan': item['bid']['o'] = 'NaN'
    if mutation == 'negative': item['bid']['l'] = '-1'
    if mutation == 'ohlc': item['bid']['h'] = '99'
    if mutation == 'volume': item['volume'] = True
    with pytest.raises(repair.RepairError):
        repair.candle_row(t, item, '\n')


def test_complete_repair_preserves_every_original_byte_and_exact_ledger(inputs, tmp_path):
    before = inputs.subset.read_bytes()
    calls = []
    blocks = repair.groups(inputs.targets)
    def fake(params):
        block = blocks[len(calls)]
        calls.append(params)
        return 200, response([candle(t) for t in block]), {'RequestID': 'synthetic-request', 'Authorization': 'NEVER_STORE'}
    out = tmp_path / 'result'
    result = repair.acquire(inputs, out, fake)
    assert result['status'] == 'REPAIR_COMPLETE_PENDING_SCIENTIFIC_READINESS'
    assert result['repaired_count'] == 3 and result['residual_count'] == 0
    assert result['derived_cache']['row_count'] == 6
    assert result['derived_cache']['original_row_bytes_sha256'] == inputs.subset_sha256
    assert inputs.subset.read_bytes() == before
    ledger = json.loads((out / 'repair_ledger.json').read_text())
    assert [x['open_time'] for x in ledger] == inputs.targets
    for entry in ledger:
        assert repair.sha(entry['row_utf8'].encode()) == entry['row_sha256']
        assert repair.sha((out / entry['raw_response_path']).read_bytes()) == entry['raw_response_sha256']
    assert 'NEVER_STORE' not in (out / 'repair_manifest.json').read_text()
    assert json.loads((out / 'residual_gaps.json').read_text()) == []


def test_missing_bar_stops_before_next_request_and_no_derived_cache(inputs, tmp_path):
    calls = []
    def fake(params):
        calls.append(params)
        return 200, response([candle(inputs.targets[0])]), {}
    out = tmp_path / 'missing'
    result = repair.acquire(inputs, out, fake)
    assert result['status'] == 'BLOCKED' and len(calls) == 1
    assert result['repaired_count'] == 1 and result['residual_count'] == 2
    residual = json.loads((out / 'residual_gaps.json').read_text())
    assert [x['status'] for x in residual] == ['NOT_SUPPLIED_BY_OANDA', 'NOT_REQUESTED']
    assert not (out / 'USD_JPY_M15_BA_repaired.csv').exists()


@pytest.mark.parametrize('failure', ['network', 'redirect', 'http'])
def test_authentication_and_http_errors_do_not_leak_or_retry(inputs, tmp_path, failure, capsys):
    calls = []
    def fake(params):
        calls.append(params)
        if failure == 'network':
            raise RuntimeError('Bearer SYNTHETIC_SECRET_NOT_A_REAL_TOKEN')
        return (302 if failure == 'redirect' else 401), b'SYNTHETIC_SECRET_NOT_A_REAL_TOKEN', {}
    out = tmp_path / failure
    result = repair.acquire(inputs, out, fake)
    assert result['status'] == 'BLOCKED' and len(calls) == 1
    for path in out.rglob('*'):
        if path.is_file():
            assert b'SYNTHETIC_SECRET_NOT_A_REAL_TOKEN' not in path.read_bytes()
    assert 'SYNTHETIC_SECRET' not in capsys.readouterr().out
    assert not list((out / 'raw').iterdir())


def test_existing_attempt_is_never_overwritten(inputs, tmp_path):
    out = tmp_path / 'exists'
    out.mkdir()
    marker = out / 'marker'
    marker.write_bytes(b'KEEP')
    with pytest.raises(FileExistsError):
        repair.acquire(inputs, out, lambda _: pytest.fail('must not request'))
    assert marker.read_bytes() == b'KEEP'


def test_merge_rejects_overwriting_or_incomplete_repairs(inputs, tmp_path):
    with pytest.raises(repair.RepairError):
        repair.merge_verified(inputs, {}, tmp_path / 'missing.csv')
    target = repair.LOWER
    conflicting = repair.Inputs(inputs.subset, inputs.subset_sha256, [target], {}, {})
    with pytest.raises(repair.RepairError):
        repair.merge_verified(conflicting, {target: repair.candle_row(target, candle(target), '\n')}, tmp_path / 'overwrite.csv')


def test_derived_cache_is_deterministic(inputs, tmp_path):
    repairs = {t: repair.candle_row(t, candle(t), '\r\n') for t in inputs.targets}
    a, b = tmp_path / 'a.csv', tmp_path / 'b.csv'
    assert repair.merge_verified(inputs, repairs, a) == repair.merge_verified(inputs, repairs, b)
    assert a.read_bytes() == b.read_bytes()
