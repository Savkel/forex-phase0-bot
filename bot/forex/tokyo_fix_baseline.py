"""Frozen Tokyo mechanics. Pure functions; no data access, network or execution CLI."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import math

import numpy as np

from bot.forex.tokyo_fix_readiness import IntegrityError, L, U, STEP, scheduled_windows

ROLES = ('primary', 'early', 'late', 'passive')
SEED, BLOCK, REPLICATES = 20260923, 20, 10000


@dataclass(frozen=True)
class Window:
    label: str
    role: str
    decision: int
    entry: int
    exit: int


def intents(labels):
    if not labels or labels != sorted(set(labels)):
        raise IntegrityError('Invalid paired-date sequence')
    result = {role: [] for role in ROLES}
    for label in labels:
        for role, (a, b) in scheduled_windows(date.fromisoformat(label)).items():
            if not L <= a-STEP < a <= b < U:
                raise IntegrityError('Intent outside permitted envelope')
            result[role].append(Window(label, role, a-STEP, a, b))
    return result


def required_observations(label):
    return {t for a, b in scheduled_windows(date.fromisoformat(label)).values()
            for t in range(a-STEP, b+STEP, STEP)}


def complete_cases(labels, present, invalid=frozenset()):
    kept, excluded = [], []
    for label in labels:
        required = required_observations(label)
        missing, bad = sorted(required-present), sorted(required.intersection(invalid))
        if missing or bad:
            excluded.append({'jst_date': label, 'missing_timestamps_ms': missing,
                             'invalid_timestamps_ms': bad, 'reason': 'INCOMPLETE_MATCHED_DATE'})
        else:
            kept.append(label)
    return kept, excluded


def exposure_grid(stamps, plan):
    ts = np.asarray(stamps, dtype=np.int64)
    if ts.ndim != 1 or len(ts) < 2 or np.any(np.diff(ts) <= 0) or np.any(ts % STEP) or ts[0] < L or ts[-1] >= U:
        raise IntegrityError('Invalid full permitted grid')
    positions = {int(t): i for i, t in enumerate(ts)}
    masks = {}
    for role in ROLES:
        mask = np.zeros(len(ts)-1, dtype=np.int8)
        for w in plan[role]:
            required = range(w.decision, w.exit+STEP, STEP)
            if any(t not in positions for t in required):
                raise IntegrityError('Missing frozen required observation')
            a, b = positions[w.entry], positions[w.exit]
            if np.any(mask[a:b]):
                raise IntegrityError('Overlapping holding windows')
            mask[a:b] = 1
        masks[role] = mask
    n = len(ts)-1
    N = G = int(masks['primary'].sum())/n
    q = int(masks['passive'].sum())/n
    f = matched_fraction(G, q)
    return {'N': N, 'G': G, 'q': q, 'f': f, 'normalization': N/q,
            'interval_count': n, 'gross_parity_residual': abs(f*q-G)}, masks


def matched_fraction(gross, unit_gross):
    if not math.isfinite(gross) or not math.isfinite(unit_gross) or gross < 0 or unit_gross <= 0:
        raise IntegrityError('Undefined exposure normalization')
    f = gross/unit_gross
    if f > 1:
        raise IntegrityError('Matching would introduce leverage')
    return f


def executable_quotes(bid, ask, stress=False):
    if not all(math.isfinite(x) for x in (bid, ask)) or not 0 < bid <= ask:
        raise IntegrityError('Invalid executable quote')
    if stress:
        midpoint, half = (ask+bid)/2, (ask-bid)/2
        bid, ask = midpoint-2*half, midpoint+2*half
        if bid <= 0:
            raise IntegrityError('Nonpositive stressed bid')
    return bid, ask


def rebalance(cash, units, bid, ask, fraction):
    executable_quotes(bid, ask)
    if not all(math.isfinite(x) for x in (cash, units, fraction)) or not 0 <= fraction <= 1:
        raise IntegrityError('Invalid accounting state')
    equity = cash+units*bid
    if equity <= 0:
        raise IntegrityError('Nonpositive liquidation equity')
    if fraction == 0:
        return equity, 0.0, -units
    if fraction == 1:
        # All cash is invested exactly; no phantom residual cash/rebalances.
        delta = cash/ask if cash >= 0 else cash/bid
        return 0.0, units+delta, delta
    numerator = fraction*equity-units*bid
    delta = numerator/(bid+fraction*(ask-bid)) if numerator > 0 else numerator/bid
    next_cash = cash-delta*(ask if delta > 0 else bid)
    return next_cash, units+delta, delta


def simulate(stamps, bids, asks, windows, fraction=1.0, passive=False, stress=False):
    """Economics function: call only with synthetic data or explicit one-shot authorization."""
    if len(stamps) != len(bids) or len(stamps) != len(asks) or not windows:
        raise IntegrityError('Mismatched/empty ledger input')
    indices = {int(t): i for i, t in enumerate(stamps)}
    if len(indices) != len(stamps):
        raise IntegrityError('Duplicate ledger timestamp')
    before = np.empty(len(stamps), dtype=np.float64)
    after = np.empty(len(stamps), dtype=np.float64)
    cash_path = np.empty(len(stamps), dtype=np.float64)
    units_path = np.zeros(len(stamps), dtype=np.float64)
    deltas = np.zeros(len(stamps), dtype=np.float64)
    cash, units, cursor = 10000.0, 0.0, 0
    trades = []
    for w in windows:
        if any(t not in indices for t in range(w.decision, w.exit+STEP, STEP)):
            raise IntegrityError('Missing ledger observation')
        a, b = indices[w.entry], indices[w.exit]
        if a < cursor or units != 0:
            raise IntegrityError('Overlapping or carried position')
        before[cursor:a] = after[cursor:a] = cash
        cash_path[cursor:a] = cash
        start = cash
        purchase_units = None
        turnover = 0.0
        for i in range(a, b+1):
            bid, ask = executable_quotes(float(bids[i]), float(asks[i]), stress)
            before[i] = cash+units*bid
            if i == b:
                turnover += abs(units)
                deltas[i] = -units
                cash, units = float(before[i]), 0.0
            elif i == a or passive:
                cash, units, delta = rebalance(cash, units, bid, ask, fraction)
                deltas[i] = delta
                turnover += abs(delta)
                if i == a:
                    purchase_units = units
            after[i] = cash+units*bid
            cash_path[i], units_path[i] = cash, units
            if not math.isfinite(after[i]) or after[i] <= 0:
                raise IntegrityError('Invalid post-transaction equity')
        trades.append({'jst_date': w.label, 'entry_ms': w.entry, 'exit_ms': w.exit,
                       'starting_equity': start, 'ending_equity': cash,
                       'return': cash/start-1, 'entry_units': purchase_units,
                       'turnover_units': turnover, 'financing': 0.0})
        cursor = b+1
    before[cursor:] = after[cursor:] = cash
    cash_path[cursor:] = cash
    return {'before': before, 'after': after, 'trades': trades,
            'cash': cash_path, 'units': units_path, 'delta_units': deltas,
            'total_return': cash/10000-1, 'max_drawdown': max_drawdown(before, after)}


def max_drawdown(before, after):
    curve = np.column_stack((before, after)).ravel()
    if len(curve) == 0 or not np.all(np.isfinite(curve)) or np.any(curve <= 0):
        raise IntegrityError('Invalid equity path')
    peaks = np.maximum.accumulate(curve)
    return float(np.min(curve/peaks-1))


def bootstrap_starts(n):
    if type(n) is not int or n <= 0:
        raise IntegrityError('Empty/invalid paired sample')
    return np.random.Generator(np.random.PCG64(SEED)).integers(
        0, n, size=(REPLICATES, (n+BLOCK-1)//BLOCK), dtype=np.int64, endpoint=False)


def circular_indices(starts, n):
    return ((np.asarray(starts, dtype=np.int64)[:, None]+np.arange(BLOCK)) % n).ravel()[:n]


def timing_test(contrast, starts):
    d = np.asarray(contrast, dtype=np.float64)
    n = len(d)
    if d.ndim != 1 or n == 0 or not np.all(np.isfinite(d)):
        raise IntegrityError('Invalid paired contrast; no deletion/imputation')
    if starts.shape != (REPLICATES, (n+BLOCK-1)//BLOCK) or starts.dtype != np.int64 or np.any(starts < 0) or np.any(starts >= n):
        raise IntegrityError('Bootstrap start matrix mismatch')
    observed = math.fsum(d)/n
    centered = d-observed
    exceed = 0
    for row in starts:
        value = math.fsum(centered[circular_indices(row, n)])/n
        exceed += value >= observed
    return {'mean_contrast': observed, 'exceedances': int(exceed),
            'p_value': (1+int(exceed))/(REPLICATES+1), 'n': n,
            'starts_sha256': hashlib.sha256(starts.astype('<i8').tobytes(order='C')).hexdigest()}


def economics(stamps, bids, asks, labels):
    plan = intents(labels)
    exposures, _ = exposure_grid(stamps, plan)
    starts = bootstrap_starts(len(labels))
    all_legs, results = {}, {}
    for cost, stress in (('base', False), ('stress', True)):
        legs = {role: simulate(stamps, bids, asks, plan[role], stress=stress)
                for role in ('primary', 'early', 'late')}
        legs['unit_passive'] = simulate(stamps, bids, asks, plan['passive'], passive=True, stress=stress)
        legs['matched_passive'] = simulate(stamps, bids, asks, plan['passive'], fraction=exposures['f'], passive=True, stress=stress)
        primary = legs['primary']
        alpha = primary['total_return']-exposures['normalization']*legs['unit_passive']['total_return']
        daily = {name: np.array([t['return'] for t in leg['trades']]) for name, leg in legs.items()}
        contrast = daily['primary']-(daily['early']+daily['late'])/2
        blocks = {}
        for name, first, last in (('2014_2016', '2014', '2016'), ('2017_2020', '2017', '2020'), ('2021_end', '2021', '2024')):
            chosen = [i for i, label in enumerate(labels) if first <= label[:4] <= last]
            if not chosen:
                raise IntegrityError('Empty chronological evidence block')
            metrics = {}
            for role, leg in legs.items():
                begin, end = leg['trades'][chosen[0]], leg['trades'][chosen[-1]]
                a, b = np.searchsorted(stamps, [begin['entry_ms'], end['exit_ms']])
                metrics[role] = {'return': end['ending_equity']/begin['starting_equity']-1,
                                 'max_drawdown': max_drawdown(leg['before'][a:b+1], leg['after'][a:b+1])}
            blocks[name] = {'n': len(chosen), 'legs': metrics,
                            'alpha': metrics['primary']['return']-exposures['normalization']*metrics['unit_passive']['return'],
                            'mean_contrast': math.fsum(contrast[chosen])/len(chosen), 'automatic_gate': False}
        results[cost] = {'alpha': alpha, 'legs': {name: {'total_return': leg['total_return'], 'max_drawdown': leg['max_drawdown']}
                                               for name, leg in legs.items()},
                         'timing': timing_test(contrast, starts), 'chronological_blocks': blocks}
        all_legs[cost] = legs
    gates = {'base_alpha_positive': results['base']['alpha'] > 0,
             'stress_alpha_positive': results['stress']['alpha'] > 0,
             'base_no_deeper_drawdown': results['base']['legs']['primary']['max_drawdown'] >= results['base']['legs']['matched_passive']['max_drawdown']}
    return {'costs': results, 'exposures': exposures, 'gates': gates,
            'verdict': 'SURVIVES_PREDEFINED_KILL_TESTS_PENDING_EXTERNAL_ADJUDICATION' if all(gates.values()) else 'CLOSED_FAIL',
            'timing_significance_gate': None, 'research': 'HISTORICAL_DEVELOPMENT_COMPLETE_CASE',
            'account_mode': 'UNKNOWN', 'venue_assumption': 'OANDA_V20_DAILY_1700_AMERICA_NEW_YORK'}, all_legs, starts
