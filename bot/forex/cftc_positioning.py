"""Frozen exploratory ledger. Economics functions require explicit runner authorization.

Pure functions accept arrays; they never open files or fetch data. Tests use only
synthetic prices. Reuse the established executable quotes/passive/DD primitives.
"""
from __future__ import annotations

import math
import numpy as np

from bot.forex.cftc_positioning_readiness import STEP, require
from bot.forex.tokyo_fix_baseline import executable_quotes, rebalance, max_drawdown

CAPITAL = 10000.0


def equity(cash, units, bid, ask):
    result = cash+units*(bid if units >= 0 else ask)
    require(math.isfinite(result) and result > 0, 'Nonpositive/nonfinite executable equity')
    return result


def profile(bids, asks, signal, *, stress=False, passive=False):
    """Exact cash/units ledger starting at one JPY; homogeneous in capital.

    Passive is always long f=1, rebalanced at every intermediate open. At f=1
    these rebalances have zero incremental units/cost, proved by synthetic tests.
    Short strategy units are fixed after the initial executable-equity sizing.
    """
    require(signal in (-1, 0, 1) and len(bids) == len(asks) and len(bids) >= 2,
            'Invalid ledger inputs')
    require(not passive or signal == 1, 'Passive must be long')
    cash, units = 1.0, 0.0
    before, after, cash_path, units_path, changes, costs, turnover = ([] for _ in range(7))
    for i, (b, a) in enumerate(zip(bids, asks)):
        b, a = executable_quotes(float(b), float(a), stress)
        before.append(equity(cash, units, b, a))
        delta = 0.0
        if i == len(bids)-1:
            delta = -units
            cash -= delta*(a if delta > 0 else b)
            units = 0.0
        elif i == 0:
            if signal == 1:
                cash, units, delta = rebalance(cash, units, b, a, 1.0)
            elif signal == -1:
                delta = -cash/(2*a-b)
                cash -= delta*b
                units = delta
        elif passive:
            cash, units, delta = rebalance(cash, units, b, a, 1.0)
        after.append(equity(cash, units, b, a))
        cash_path.append(cash)
        units_path.append(units)
        changes.append(delta)
        costs.append(abs(delta)*(a-b)/2)  # execution shortfall versus contemporaneous mid, already paid
        turnover.append(abs(delta)*(a+b)/2)
    require(units == 0.0, 'Rollover exposure')
    return {k: np.asarray(v, dtype=float) for k, v in
            zip(('before', 'after', 'cash', 'units', 'delta', 'spread_cost_jpy', 'turnover_jpy'),
                (before, after, cash_path, units_path, changes, costs, turnover))}


def book(profiles, labels, signals):
    require(len(profiles) == len(labels) == len(signals) and len(labels) > 0, 'Empty/unpaired book')
    capital = CAPITAL
    paths = {k: [] for k in profiles[0]}
    trades = []
    for p, label, signal in zip(profiles, labels, signals):
        start = capital
        for k in paths:
            paths[k].append(p[k]*start)
        capital *= float(p['after'][-1])
        require(math.isfinite(capital) and capital > 0, 'Compounded equity invalid')
        trades.append({'monday': label, 'signal': int(signal), 'starting_equity': start,
                       'ending_equity': capital, 'net_return': float(p['after'][-1])-1,
                       'spread_cost_jpy': float(p['spread_cost_jpy'].sum())*start,
                       'turnover_jpy': float(p['turnover_jpy'].sum())*start, 'financing': 0.0})
    curves = {k: np.concatenate(v) for k, v in paths.items()}
    stats = {'net_return': capital/CAPITAL-1,
             'max_drawdown': max_drawdown(curves['before'], curves['after']),
             'spread_cost_jpy': float(curves['spread_cost_jpy'].sum()),
             'turnover_jpy': float(curves['turnover_jpy'].sum()), 'financing': 0.0,
             'starting_equity_jpy': CAPITAL, 'ending_equity_jpy': capital}
    return stats, curves, trades


def rotated_signals(signals):
    a = np.asarray(signals)
    require(a.ndim == 1 and len(a) > 0 and np.all(np.isin(a, (-1, 0, 1))), 'Invalid rotation sample')
    return [np.roll(a, shift) for shift in range(len(a))]


def rotation_rank(factors, signals, passive_return):
    """Every shift, identity and ties included. No RNG or significance assertion."""
    n = len(signals)
    require(factors.shape == (n, 3) and np.all(np.isfinite(factors)) and np.all(factors > 0),
            'Invalid long/short/cash factors')
    normalization = sum(int(x) for x in signals)/n
    alphas = []
    for rotated in rotated_signals(signals):
        capital = CAPITAL
        for i, signal in enumerate(rotated):
            capital *= float(factors[i, int(signal)+1])
            require(math.isfinite(capital) and capital > 0, 'Invalid rotation equity')
        alphas.append(capital/CAPITAL-1-normalization*passive_return)
    exceed = sum(a >= alphas[0] for a in alphas)
    return {'alpha_by_shift': alphas, 'observed_alpha': alphas[0],
            'exceedances_including_identity_and_ties': exceed, 'rotation_count': n,
            'descriptive_rank_p': exceed/n, 'significance_claim': False}


def economics(stamps, bids, asks, mask):
    """USER-RUN ONLY on research prices. Synthetic tests may call this function."""
    rows = [r for r in mask if r['status'] == 'SUPPORTED']
    require(rows and len(stamps) == len(bids) == len(asks), 'Unpaired economics inputs')
    require(np.all(np.diff(stamps) > 0), 'Unsorted price grid')
    indices = {int(t): i for i, t in enumerate(stamps)}
    slices, out_stamps, labels, signals = [], [], [], []
    previous_exit = None
    for r in rows:
        a, b = r['entry_ms'], r['exit_ms']
        require(r['decision_ms'] < a < b and (previous_exit is None or a > previous_exit),
                'Noncausal/overlapping window')
        expected = list(range(a, b+STEP, STEP))
        require(len(expected) == 95 and all(t in indices for t in expected), 'Incomplete required window')
        ids = [indices[t] for t in expected]
        slices.append((np.asarray(bids)[ids], np.asarray(asks)[ids]))
        out_stamps.extend(expected)
        labels.append(r['monday'])
        signals.append(r['signal'])
        previous_exit = b
    require(all(x in (-1, 1) for x in signals), 'Frozen nonzero cohort changed; no f=1 fallback')
    output, archives = {}, {}
    for stress in (False, True):
        name = 'spread_stress' if stress else 'base'
        candidates = [{s: profile(b,a,s,stress=stress) for s in (-1,0,1)} for b,a in slices]
        passives = [profile(b,a,1,stress=stress,passive=True) for b,a in slices]
        chosen = [p[s] for p,s in zip(candidates,signals)]
        strategy, curve, trades = book(chosen, labels, signals)
        passive, pc, pt = book(passives, labels, [1]*len(labels))
        alpha = strategy['net_return']-sum(signals)/len(signals)*passive['net_return']
        factors = np.array([[p[s]['after'][-1] for s in (-1,0,1)] for p in candidates])
        null = rotation_rank(factors, signals, passive['net_return'])
        require(null['observed_alpha'] == alpha, 'Identity rotation/accounting parity failed')
        blocks = []
        for lo, hi in ((2014,2016), (2017,2019), (2020,2024)):
            ids = [i for i,label in enumerate(labels) if lo <= int(label[:4]) <= hi]
            if not ids:
                blocks.append({'years': [lo,hi], 'supported': 0, 'status': 'NO_OBSERVATIONS'})
                continue
            bs, _, _ = book([chosen[i] for i in ids], [labels[i] for i in ids], [signals[i] for i in ids])
            bp, _, _ = book([passives[i] for i in ids], [labels[i] for i in ids], [1]*len(ids))
            norm = sum(signals[i] for i in ids)/len(ids)
            blocks.append({'years': [lo,hi], 'supported': len(ids), 'N_over_q': norm,
                           'strategy': bs, 'passive': bp, 'alpha': bs['net_return']-norm*bp['net_return'],
                           'automatic_block_gate': False})
        directional = {}
        for s, label in ((-1,'actual_short_trades'), (1,'actual_long_trades')):
            value = 1.0
            for p, sig in zip(chosen, signals):
                if sig == s:
                    value *= float(p['after'][-1])
            directional[label] = {'count': signals.count(s), 'compounded_net_return': value-1}
        output[name] = {'strategy': strategy, 'unit_passive': passive, 'gross_matched_passive': passive,
                        'f': 1.0, 'N_over_q': sum(signals)/len(signals), 'alpha': alpha,
                        'cash_return': 0.0, 'rotation_null': null, 'blocks': blocks,
                        'directional_accounting': directional}
        archives[name] = {'stamps': np.array(out_stamps), 'strategy': curve, 'passive': pc,
                          'strategy_trades': trades, 'passive_trades': pt}
    gates = {'base_alpha_positive': output['base']['alpha'] > 0,
             'base_drawdown_no_deeper': output['base']['strategy']['max_drawdown'] >= output['base']['gross_matched_passive']['max_drawdown'],
             'spread_stress_alpha_positive': output['spread_stress']['alpha'] > 0}
    output.update(status='EXPLORATORY_COMPLETED_PENDING_EXTERNAL_REVIEW', exploratory_only=True,
                  validation_claim=False, significance_claim=False, necessary_requirements=gates,
                  all_necessary_requirements_passed=all(gates.values()),
                  accounting_note='Negative signed normalization times long return is not an executable short return.',
                  curve_note='Only required windows stored; omitted intervals are cash with unchanged equity.')
    return output, archives
