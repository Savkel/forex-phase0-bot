"""Synthetic-only tests: never open CFTC research prices or calculate their returns."""
from datetime import date, datetime, timedelta, timezone
from fractions import Fraction
import json
from pathlib import Path
import socket
import sys

import numpy as np
import pytest

from bot.forex import cftc_positioning as model
from bot.forex import cftc_positioning_readiness as ready
from bot.forex import cftc_positioning_binding as binding
from bot.forex.tokyo_fix_readiness import IntegrityError


@pytest.fixture(autouse=True)
def no_network_or_research_io(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Tests must not use network/research input')
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(ready, 'load_prices', forbidden)


def row(day, long=10, short=20, oi=100):
    return {'report_date_as_yyyy_mm_dd': day+'T00:00:00.000',
            'cftc_contract_market_code': '097741',
            'market_and_exchange_names': 'JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE',
            'open_interest_all': str(oi), 'lev_money_positions_long': str(long),
            'lev_money_positions_short': str(short)}


@pytest.mark.parametrize('long,short,signal', [(20,10,1),(10,20,-1),(10,10,0)])
def test_futures_spot_inverse_quote_and_fade(long, short, signal):
    r = ready.reports([row('2014-01-07',long,short)])
    assert r[date(2014,1,7)]['signal'] == signal


@pytest.mark.parametrize('report_day,lag', [('2014-01-07',13),('2014-01-06',14)])
def test_lag_derived_from_reporting_week_not_search(report_day, lag):
    r = ready.reports([row(report_day)])
    selected = ready.signal_for(date(2014,1,20),r)
    assert (date(2014,1,20)-date.fromisoformat(selected['report_date'])).days == lag


@pytest.mark.parametrize('dates', [[],['2014-01-06','2014-01-07'],['2013-12-31'],['2014-01-14']])
def test_lag_missing_ambiguous_or_wrong_week_fails(dates):
    with pytest.raises(IntegrityError):
        ready.signal_for(date(2014,1,20), ready.reports([row(d) for d in dates]))


@pytest.mark.parametrize('field,value', [('open_interest_all','0'),('open_interest_all','nan'),
    ('lev_money_positions_long','101'),('lev_money_positions_short','-1'),
    ('lev_money_positions_short','1.5'),('cftc_contract_market_code','000000'),
    ('market_and_exchange_names','MICRO JPY'),('surprise','1')])
def test_invalid_signal_schema_and_contract(field,value):
    r = row('2014-01-07'); r[field] = value
    with pytest.raises(IntegrityError):
        ready.reports([r])


def test_duplicate_report_rejected():
    with pytest.raises(IntegrityError):
        ready.reports([row('2014-01-07')]*2)


@pytest.mark.parametrize('day,hour', [('2014-03-03',22),('2014-03-10',21),
                                    ('2023-10-30',21),('2023-11-06',22)])
def test_dst_strict_rollover_boundary(day,hour):
    decision, a, b = ready.window(date.fromisoformat(day))
    assert datetime.fromtimestamp(a/1000,timezone.utc).hour == hour
    assert a-decision == ready.STEP and b-a == 94*ready.STEP
    assert datetime.fromtimestamp(b/1000,ready.NY).time().isoformat() == '16:45:00'


@pytest.mark.parametrize('day', [date(2014,1,5),date(2024,1,8),date(2013,12,30)])
def test_seal_and_monday_bounds(day):
    with pytest.raises(IntegrityError):
        ready.window(day)


def test_blackouts_inclusive_source_decision_and_exit():
    for lo, hi in ready.BLACKOUTS:
        assert ready.blackout(lo) and ready.blackout(hi)
        assert not ready.blackout(lo-timedelta(days=1),hi+timedelta(days=1))
        assert ready.blackout(date(2014,1,7),lo,date(2014,1,21))


def synthetic_mask():
    reports, present = [], set()
    m = ready.FIRST
    while m <= ready.LAST:
        reports.append(row((m-timedelta(days=13)).isoformat()))
        _,a,b = ready.window(m)
        present.update(range(a,b+ready.STEP,ready.STEP))
        m += timedelta(days=7)
    return ready.reports(reports),present


def test_complete_case_intermediate_boundary_invalid_and_cash_all_matched():
    reports,present = synthetic_mask()
    monday = ready.FIRST
    _,a,b = ready.window(monday)
    reports[monday-timedelta(days=13)]['signal'] = 0
    for stamp in (a,a+ready.STEP,b):
        mask = ready.build_mask(reports,present-{stamp})
        assert mask[0]['status'] == 'INCOMPLETE' and mask[0]['missing'] == [stamp]
    assert ready.build_mask(reports,present,{a})[0]['status'] == 'INCOMPLETE'


def test_exclusions_break_sign_runs_and_exposure_counts_cash():
    mask = [{'status':s,'signal':v,'monday':'2014-01-20'} for s,v in
            [('SUPPORTED',-1),('SUPPORTED',-1),('INCOMPLETE',-1),('SUPPORTED',-1),('SUPPORTED',1)]]
    result = ready.support_summary(mask,1000)
    assert (result['sign_runs'],result['longest_run']) == (3,2)
    assert result['f'] == 1 and result['N_over_q'] == pytest.approx(-0.5)


def rational_ledger(bids,asks,signal,stress=False):
    cash,units = Fraction(1),Fraction(0)
    pre,post,cashes,positions = [],[],[],[]
    for i,(b,a) in enumerate(zip(bids,asks)):
        b,a = Fraction(str(b)),Fraction(str(a))
        if stress:
            b,a = (3*b-a)/2,(3*a-b)/2
        pre.append(cash+units*(b if units >= 0 else a))
        if i == 0:
            units = cash/a if signal == 1 else (-cash/(2*a-b) if signal == -1 else Fraction(0))
            cash -= units*(a if units >= 0 else b)
        elif i == len(bids)-1:
            cash += units*(b if units >= 0 else a)
            units = Fraction(0)
        post.append(cash+units*(b if units >= 0 else a))
        cashes.append(cash); positions.append(units)
    return pre,post,cashes,positions


@pytest.mark.parametrize('signal', [-1,0,1])
@pytest.mark.parametrize('stress', [False,True])
def test_independent_fraction_hand_ledger_and_liquidation(signal,stress):
    bids,asks = [100,103,98,102],[102,105,101,104]
    p = model.profile(bids,asks,signal,stress=stress)
    expected = rational_ledger(bids,asks,signal,stress)
    for key,values in zip(('before','after','cash','units'),expected):
        np.testing.assert_allclose(p[key],[float(v) for v in values],rtol=1e-14,atol=1e-14)
    b,a = model.executable_quotes(bids[0],asks[0],stress)
    assert abs(p['units'][0])*(b if signal >= 0 else a) == pytest.approx(p['after'][0] if signal else 0)
    assert p['units'][-1] == 0 and p['delta'][1:-1].tolist() == [0,0]


def test_passive_f1_equivalence_rebalances_no_phantom_costs():
    b,a = [100,101,99],[101,102,100]
    normal,passive = model.profile(b,a,1),model.profile(b,a,1,passive=True)
    for k in normal:
        np.testing.assert_array_equal(normal[k],passive[k])
    assert passive['delta'][1] == 0 and passive['spread_cost_jpy'][1] == 0


def test_flat_price_spread_round_trip_and_stress():
    for s in (-1,1):
        base = model.profile([100,100],[102,102],s)
        stressed = model.profile([100,100],[102,102],s,stress=True)
        assert stressed['after'][-1] < base['after'][-1] < 1
        assert 1-base['after'][-1] == pytest.approx(base['spread_cost_jpy'].sum())


@pytest.mark.parametrize('b,a', [([101,100],[100,100]),([0,1],[1,2]),([1,np.nan],[2,3])])
def test_bad_quote_no_repair(b,a):
    with pytest.raises(IntegrityError):
        model.profile(b,a,-1)


def test_insolvency_fails_no_rescaling():
    with pytest.raises(IntegrityError):
        model.profile([100,1000],[101,1001],-1)


def test_compounding_and_drawdown_include_entry_spread():
    p = model.profile([100,110],[102,112],1)
    stats,curve,trades = model.book([p,p],['one','two'],[1,1])
    assert stats['ending_equity_jpy'] == pytest.approx(10000*(110/102)**2)
    assert stats['max_drawdown'] == pytest.approx(100/102-1)
    assert trades[1]['starting_equity'] == trades[0]['ending_equity']
    assert stats['spread_cost_jpy'] == pytest.approx(sum(t['spread_cost_jpy'] for t in trades))


def test_rotations_include_all_ties_identity_and_are_deterministic():
    signs = [-1,-1,1]
    factors = np.array([[0.98,1,1.02]]*3)
    result = model.rotation_rank(factors,signs,0.04)
    # Identical direction counts; multiplication order can differ only at floating precision.
    assert result['rotation_count'] == 3 and result['exceedances_including_identity_and_ties'] >= 1
    assert result == model.rotation_rank(factors,signs,0.04)
    tied = model.rotation_rank(np.ones((3,3)),signs,0)
    assert tied['descriptive_rank_p'] == 1 and tied['exceedances_including_identity_and_ties'] == 3
    for rotated in model.rotated_signals(signs):
        assert sorted(rotated) == sorted(signs)


def synthetic_economics():
    mask,stamps,bids,asks = [],[],[],[]
    for i,m in enumerate((date(2014,1,20),date(2017,1,23),date(2020,1,20))):
        decision,a,b = ready.window(m)
        ts = list(range(a,b+ready.STEP,ready.STEP))
        mask.append({'monday':m.isoformat(),'decision_ms':decision,'entry_ms':a,'exit_ms':b,
                     'status':'SUPPORTED','signal':(-1 if i==0 else 1)})
        stamps.extend(ts)
        bids.extend(np.linspace(100+i,101+i,len(ts)))
        asks.extend(np.linspace(100.1+i,101.1+i,len(ts)))
    return np.array(stamps),np.array(bids),np.array(asks),mask


def test_end_to_end_synthetic_blocks_null_direction_and_no_validation():
    data = synthetic_economics()
    result,archives = model.economics(*data)
    assert result == model.economics(*data)[0]
    assert not result['validation_claim'] and not result['significance_claim']
    for scenario in ('base','spread_stress'):
        r = result[scenario]
        assert r['rotation_null']['observed_alpha'] == r['alpha']
        assert r['N_over_q'] == pytest.approx(1/3) and r['f'] == 1
        assert r['blocks'][0]['N_over_q'] == -1 and r['blocks'][1]['N_over_q'] == 1
        assert r['directional_accounting']['actual_short_trades']['count'] == 1
        for leg in ('strategy','passive'):
            assert np.all(archives[scenario][leg]['units'][94::95] == 0)
    damaged = list(data); damaged[0] = damaged[0][1:]; damaged[1] = damaged[1][1:]; damaged[2] = damaged[2][1:]
    with pytest.raises(IntegrityError):
        model.economics(*damaged)


def test_claim_atomic_failed_attempt_consumed(tmp_path):
    path = binding.claim(tmp_path)
    assert path.is_dir()
    with pytest.raises(FileExistsError):
        binding.claim(tmp_path)


def test_binding_rejects_wrong_head_before_reading_inputs(monkeypatch,tmp_path):
    monkeypatch.setattr(binding,'git',lambda *a,**k: 'a'*40)
    with pytest.raises(IntegrityError,match='Wrong frozen HEAD'):
        binding.verify('b'*40,tmp_path)


def test_binding_rejects_tracked_drift(monkeypatch,tmp_path):
    def fake_git(*args,**kwargs):
        if args == ('rev-parse','HEAD'):
            return 'a'*40
        return 'working' if args[0]=='hash-object' else 'committed'
    monkeypatch.setattr(binding,'git',fake_git)
    with pytest.raises(IntegrityError,match='differs from commit'):
        binding.verify('a'*40,tmp_path)


@pytest.mark.parametrize('mutation', ['none','input','evidence','runtime','schema','consumed'])
def test_full_binding_checks(monkeypatch,tmp_path,mutation):
    # Small synthetic tree verifies guards without opening any actual research file.
    monkeypatch.setattr(binding,'SOURCES',['source.py'])
    monkeypatch.setattr(binding,'INPUTS',['input.json'])
    monkeypatch.setattr(binding,'EVIDENCE',[binding.READY])
    monkeypatch.setattr(binding,'git',lambda *a,**k: 'a'*40)
    (tmp_path/'source.py').write_text('synthetic')
    (tmp_path/'input.json').write_text('{}')
    ready.write_json(tmp_path/binding.READY,{'status':'STRUCTURAL_READY_NO_ECONOMICS',
                         'economics_executed':False,'summary':{},'tests_exit_code':0})
    f = {'status':'FROZEN_EXPLORATORY_USER_RUN_ONLY','authorization':'synthetic',
         'runtime':binding.versions(),'bindings':binding.hashes(['source.py','input.json',binding.READY],tmp_path),
         'sample':{},'economics_executed':False}
    if mutation == 'runtime':
        f['runtime']['python'] = 'different'
    if mutation == 'schema':
        f['unknown_override'] = True
    ready.write_json(tmp_path/binding.FREEZE,f)
    if mutation == 'input':
        (tmp_path/'input.json').write_text('changed')
    if mutation == 'evidence':
        (tmp_path/binding.READY).write_text('{}')
    if mutation == 'consumed':
        binding.claim(tmp_path)
    if mutation == 'none':
        assert binding.verify('a'*40,tmp_path) == f
    else:
        with pytest.raises(IntegrityError):
            binding.verify('a'*40,tmp_path)


def test_runner_cannot_execute_without_explicit_flag(monkeypatch):
    from scripts import run_cftc_positioning as runner
    monkeypatch.setattr(sys,'argv',['runner','--expected-freeze','a'*40])
    with pytest.raises(SystemExit):
        runner.main()


def test_runner_synthetic_completion_and_second_claim_blocked(monkeypatch,tmp_path):
    from scripts import run_cftc_positioning as runner
    import pandas as pd
    ts,b,a,mask = synthetic_economics()
    (tmp_path/binding.MASK).parent.mkdir(parents=True)
    ready.write_json(tmp_path/binding.MASK,mask)
    monkeypatch.setattr(runner,'ROOT',tmp_path)
    monkeypatch.setattr(runner,'verify',lambda _: {'sample':{},'bindings':{}})
    monkeypatch.setattr(runner,'claim',lambda:binding.claim(tmp_path))
    monkeypatch.setattr(runner,'readiness',lambda:{'mask':mask,'summary':{}})
    monkeypatch.setattr(runner,'load_prices',lambda:(pd.DataFrame({'open_time':ts,'bid_o':b,'ask_o':a}),set()))
    monkeypatch.setattr(sys,'argv',['runner','--execute-one-shot-exploratory','--expected-freeze','a'*40])
    runner.main()
    completion = json.loads((tmp_path/binding.OUTPUT/'completion.json').read_text())
    assert completion['consumption_count'] == 1 and completion['exploratory_only'] is True
    for name,digest in completion['files'].items():
        assert ready.sha(tmp_path/binding.OUTPUT/name) == digest
    with pytest.raises(FileExistsError):
        runner.main()


def test_runner_failure_consumes_without_economics(monkeypatch,tmp_path):
    from scripts import run_cftc_positioning as runner
    monkeypatch.setattr(runner,'verify',lambda _: {})
    monkeypatch.setattr(runner,'claim',lambda:binding.claim(tmp_path))
    def fail():
        raise IntegrityError('synthetic readiness failure')
    monkeypatch.setattr(runner,'readiness',fail)
    monkeypatch.setattr(sys,'argv',['runner','--execute-one-shot-exploratory','--expected-freeze','a'*40])
    with pytest.raises(IntegrityError):
        runner.main()
    assert (tmp_path/binding.OUTPUT/'failure.json').exists()
    assert not (tmp_path/binding.OUTPUT/'result.json').exists()
