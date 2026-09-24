"""Synthetic-only ledger, null, causality and safety tests; never real economics."""
from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal, localcontext
import json
import math

import numpy as np
import pytest
import requests

from bot.forex import tokyo_fix_baseline as b
from bot.forex import tokyo_fix_readiness as v
from scripts import prepare_tokyo_fix_readiness as p
from scripts import run_tokyo_fix as run


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Network is forbidden')
    monkeypatch.setattr(requests.sessions.Session, 'request', forbidden)


def fixture_data():
    labels = ['2020-02-03', '2020-02-04', '2020-02-05']
    plan = b.intents(labels)
    start = min(w.decision for windows in plan.values() for w in windows)-v.STEP
    end = max(w.exit for windows in plan.values() for w in windows)+v.STEP
    ts = np.arange(start, end+v.STEP, v.STEP, dtype=np.int64)
    bids = 100+np.sin(np.arange(len(ts))/7)
    asks = bids+0.025+0.005*np.cos(np.arange(len(ts))/3)
    return labels, plan, ts, bids, asks


def reference_book(ts, bids, asks, windows, fraction, passive, stress):
    # Independently solve the post-cost target by Decimal bisection in units.
    with localcontext() as ctx:
        ctx.prec = 48
        cash, units = Decimal(10000), Decimal(0)
        rows, returns = [], []
        active = {t: (w, t == w.entry, t == w.exit) for w in windows
                  for t in range(w.entry, w.exit+v.STEP, v.STEP)}
        f = Decimal(str(fraction))
        for i, t in enumerate(ts):
            bid, ask = Decimal(str(bids[i])), Decimal(str(asks[i]))
            if stress:
                spread = ask-bid
                bid, ask = bid-spread/2, ask+spread/2
            pre = cash+units*bid
            if int(t) in active:
                _, entry, exit_ = active[int(t)]
                if entry:
                    start = cash
                if exit_:
                    cash, units = pre, Decimal(0)
                    returns.append(float(cash/start-1))
                elif entry or passive:
                    old = units
                    if f == 1:
                        units, cash = units+cash/ask, Decimal(0)
                    elif f == 0:
                        cash, units = pre, Decimal(0)
                    else:
                        low, high = Decimal(0), old+cash/ask
                        for _ in range(180):
                            target = (low+high)/2
                            delta = target-old
                            new_cash = cash-delta*(ask if delta > 0 else bid)
                            error = target*bid-f*(new_cash+target*bid)
                            if error > 0:
                                high = target
                            else:
                                low = target
                        units = (low+high)/2
                        delta = units-old
                        cash -= delta*(ask if delta > 0 else bid)
            rows.append((float(pre), float(cash+units*bid)))
        return np.array(rows), np.array(returns)


@pytest.mark.parametrize('fraction,passive', [(1, False), (1, True), (3/94, True), (0, True)])
@pytest.mark.parametrize('stress', [False, True])
def test_independent_decimal_ledger_every_pre_post_mark(fraction, passive, stress):
    _, plan, ts, bids, asks = fixture_data()
    windows = plan['passive' if passive else 'primary']
    actual = b.simulate(ts, bids, asks, windows, fraction, passive, stress)
    expected, daily = reference_book(ts, bids, asks, windows, fraction, passive, stress)
    np.testing.assert_allclose(actual['before']/10000, expected[:, 0]/10000, rtol=0, atol=1e-12)
    np.testing.assert_allclose(actual['after']/10000, expected[:, 1]/10000, rtol=0, atol=1e-12)
    np.testing.assert_allclose([x['return'] for x in actual['trades']], daily, rtol=0, atol=1e-12)
    assert all(x['financing'] == 0 for x in actual['trades'])


def test_hand_ledger_spread_once_compounding_and_controls():
    labels, plan, ts, bids, asks = fixture_data()
    bids[:], asks[:] = 100, 101
    for role in ('primary', 'early', 'late', 'passive'):
        book = b.simulate(ts, bids, asks, plan[role], passive=role == 'passive')
        assert book['total_return'] == pytest.approx((100/101)**3-1, abs=1e-12)
        assert book['trades'][0]['entry_units'] == 10000/101
        assert book['trades'][1]['starting_equity'] == book['trades'][0]['ending_equity']
        stressed = b.simulate(ts, bids, asks, plan[role], passive=role == 'passive', stress=True)
        assert stressed['total_return'] == pytest.approx((99.5/101.5)**3-1, abs=1e-12)


def test_future_prices_do_not_change_intent_sizing_or_past_ledger():
    labels, plan, ts, bids, asks = fixture_data()
    before = b.simulate(ts, bids, asks, plan['primary'])
    split = int(np.searchsorted(ts, plan['primary'][1].exit))
    changed_bid, changed_ask = bids.copy(), asks.copy()
    changed_bid[split:] *= 1.1; changed_ask[split:] *= 1.1
    after = b.simulate(ts, changed_bid, changed_ask, plan['primary'])
    assert b.intents(labels) == plan
    with pytest.raises(FrozenInstanceError):
        plan['primary'][0].entry = 0
    np.testing.assert_array_equal(before['after'][:split], after['after'][:split])
    assert before['trades'][1]['entry_units'] == after['trades'][1]['entry_units']


def test_common_date_mask_excludes_all_legs_and_keeps_calendar_eligibility():
    labels, plan, ts, _, _ = fixture_data()
    missing = plan['late'][1].exit
    kept, excluded = b.complete_cases(labels, set(ts)-{missing})
    assert labels == ['2020-02-03', '2020-02-04', '2020-02-05']
    assert kept == [labels[0], labels[2]]
    assert excluded[0]['jst_date'] == labels[1]
    assert all([w.label for w in windows] == kept for windows in b.intents(kept).values())
    assert b.complete_cases(labels, set(ts), {missing})[0] == kept
    bad = np.array([t for t in ts if t != missing])
    with pytest.raises(v.IntegrityError):
        b.exposure_grid(bad, plan)


def test_masked_full_grid_exposure_and_rollover_flatness():
    labels, _, ts, _, _ = fixture_data()
    plan = b.intents([labels[0], labels[2]])
    metrics, masks = b.exposure_grid(ts, plan)
    assert metrics['N'] == metrics['G'] == 6/(len(ts)-1)
    assert metrics['q'] == 188/(len(ts)-1)
    assert metrics['f'] == pytest.approx(3/94)
    assert metrics['gross_parity_residual'] <= 1e-12
    for windows in plan.values():
        for w in windows:
            entry, exit_ = v.scheduled_windows(date.fromisoformat(w.label))['passive']
            assert entry-v.STEP < w.entry < w.exit < exit_+v.STEP
    assert b.matched_fraction(0, 1) == 0
    for g, q in [(1, 0), (1, -1), (2, 1), (float('nan'), 1)]:
        with pytest.raises(v.IntegrityError):
            b.matched_fraction(g, q)


def test_exact_bootstrap_rng_wrap_truncation_and_full_sample_shape():
    for n in (1, 21, 2401):
        starts = b.bootstrap_starts(n)
        reference = np.random.Generator(np.random.PCG64(20260923)).integers(
            0, n, size=(10000, math.ceil(n/20)), dtype=np.int64, endpoint=False)
        np.testing.assert_array_equal(starts, reference)
        np.testing.assert_array_equal(starts, b.bootstrap_starts(n))
        row = starts[0]
        expected = [(int(start)+j) % n for start in row for j in range(20)][:n]
        assert b.circular_indices(row, n).tolist() == expected
    assert b.circular_indices(np.array([20, 5]), 21).tolist() == [20]+list(range(19))+[5]


def test_independent_centering_fsum_ties_plus_one_and_shared_indices():
    d = np.array([0.01, -0.03, 0.02, 0.04, -0.06, 0.0, 0.001]*3)
    starts = b.bootstrap_starts(len(d))
    observed = math.fsum(d)/len(d)
    centered = [float(x)-observed for x in d]
    count = 0
    for row in starts.tolist():
        indices = [(start+j) % len(d) for start in row for j in range(20)][:len(d)]
        count += math.fsum(centered[i] for i in indices)/len(d) >= observed
    result = b.timing_test(d, starts)
    assert result['exceedances'] == count and result['p_value'] == (1+count)/10001
    assert b.timing_test(d*2, starts)['starts_sha256'] == result['starts_sha256']
    assert b.timing_test(np.zeros(21), starts)['p_value'] == 1
    assert b.timing_test(np.full(21, 0.125), starts)['p_value'] == 1/10001
    assert b.timing_test(np.full(21, -0.125), starts)['p_value'] == 1
    for bad in (np.array([]), np.full(21, np.nan), np.full(21, np.inf)):
        with pytest.raises(v.IntegrityError):
            b.timing_test(bad, starts)


def test_determinism_and_missing_ledger_quote_fail_closed():
    _, plan, ts, bids, asks = fixture_data()
    first = b.simulate(ts, bids, asks, plan['primary'])
    second = b.simulate(ts, bids, asks, plan['primary'])
    np.testing.assert_array_equal(first['after'], second['after'])
    assert first['trades'] == second['trades']
    missing = int(np.searchsorted(ts, plan['primary'][0].entry+v.STEP))
    with pytest.raises(v.IntegrityError):
        b.simulate(np.delete(ts, missing), np.delete(bids, missing), np.delete(asks, missing), plan['primary'])


@pytest.mark.parametrize('mutation', ['unknown', 'duplicate', 'sealed', 'crossed', 'nonfinite', 'incomplete'])
def test_row_integrity_guards(mutation):
    stamp = v.L+v.STEP
    row = {'open_time': str(stamp), 'time': v.iso(stamp), 'volume': '1', 'complete': 'True'}
    row.update({side+'_'+part: value for side, value in [('bid', '100'), ('ask', '101'), ('mid', '100.5')] for part in 'ohlc'})
    previous = v.L
    if mutation == 'unknown': row['extra'] = 'x'
    if mutation == 'duplicate': previous = stamp
    if mutation == 'sealed': row['open_time'] = str(v.U)
    if mutation == 'crossed': row['bid_o'] = '102'
    if mutation == 'nonfinite': row['ask_o'] = 'nan'
    if mutation == 'incomplete': row['complete'] = 'False'
    if mutation in ('unknown', 'duplicate', 'sealed'):
        with pytest.raises(v.IntegrityError): p.validate_row(row, previous)
    else:
        assert p.validate_row(row, previous)[-1] == 'INVALID_CANDLE'


def test_one_shot_existing_attempt_blocks_before_any_input_or_economics(tmp_path, monkeypatch):
    monkeypatch.setattr(run.r, 'ROOT', tmp_path)
    (tmp_path/run.OUTPUT).mkdir(parents=True)
    monkeypatch.setattr(run, 'verify_ready', lambda: pytest.fail('must stop first'))
    with pytest.raises(v.IntegrityError, match='already attempted'):
        run.execute()


def test_one_shot_failed_execution_retains_claim_and_no_second_run(tmp_path, monkeypatch):
    monkeypatch.setattr(run.r, 'ROOT', tmp_path)
    ready = tmp_path/p.READY/'readiness.json'
    ready.parent.mkdir(parents=True)
    ready.write_text('{}')
    monkeypatch.setattr(run, 'verify_ready', lambda: ({'bindings': {}}, [], [], [], {'included_dates': []}))
    def fail(*args):
        raise v.IntegrityError('synthetic failure')
    monkeypatch.setattr(b, 'economics', fail)
    with pytest.raises(v.IntegrityError): run.execute()
    assert (tmp_path/run.OUTPUT/'execution.json').exists()
    assert (tmp_path/run.OUTPUT/'failure.json').exists()
    with pytest.raises(v.IntegrityError, match='already attempted'): run.execute()


def test_hash_drift_blocks_before_loading_quotes(tmp_path, monkeypatch):
    monkeypatch.setattr(run.r, 'ROOT', tmp_path)
    path = tmp_path/p.READY/'readiness.json'
    path.parent.mkdir(parents=True)
    (tmp_path/'source').write_text('changed')
    path.write_text(json.dumps({'status': 'READY_FOR_USER_RUN_ONE_SHOT_ECONOMICS', 'economics_executed': False,
                                'bindings': {'source': 'incorrect'}}))
    monkeypatch.setattr(p, 'binding_files', lambda: ['source'])
    monkeypatch.setattr(p, 'validated_inputs', lambda: pytest.fail('no quotes before hash checks'))
    with pytest.raises(v.IntegrityError, match='binding changed'): run.verify_ready()


def test_synthetic_end_to_end_economics_and_one_shot_artifact_pipeline(tmp_path, monkeypatch):
    # Three tiny synthetic date samples cover the fixed evidence blocks; no cache IO.
    labels = ['2014-02-03', '2018-02-05', '2022-02-07']
    stamps = np.array(sorted(set().union(*(b.required_observations(x) for x in labels))), dtype=np.int64)
    bids = 100+np.sin(np.arange(len(stamps))/5)
    asks = bids+0.03
    result, legs, starts = b.economics(stamps, bids, asks, labels)
    assert starts.shape == (10000, 1)
    assert result['costs']['base']['timing']['starts_sha256'] == result['costs']['stress']['timing']['starts_sha256']
    assert result['timing_significance_gate'] is None
    for cost in ('base', 'stress'):
        assert all(not block['automatic_gate'] for block in result['costs'][cost]['chronological_blocks'].values())
        for name, book in legs[cost].items():
            assert len(book['trades']) == 3
            price_bid = bids if cost == 'base' else bids-(asks-bids)/2
            np.testing.assert_allclose(book['cash']+book['units']*price_bid, book['after'], rtol=0, atol=1e-10)
            np.testing.assert_allclose(np.cumsum(book['delta_units']), book['units'], rtol=0, atol=1e-10)
    monkeypatch.setattr(run.r, 'ROOT', tmp_path)
    path = tmp_path/p.READY/'readiness.json'
    path.parent.mkdir(parents=True)
    path.write_text('{}')
    dates = {'included_dates': labels, 'excluded_dates': []}
    monkeypatch.setattr(run, 'verify_ready', lambda: ({'bindings': {}}, stamps, bids, asks, dates))
    assert run.execute() == 0
    output = tmp_path/run.OUTPUT
    completion = json.loads((output/'completion.json').read_text())
    assert all(v.digest(output/name) == sha for name, sha in completion['files'].items())
    with pytest.raises(v.IntegrityError, match='already attempted'): run.execute()
