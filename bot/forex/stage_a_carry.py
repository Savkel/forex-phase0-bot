"""Pure Stage-A carry mechanics.

This module never loads project data and has no runnable historical entry point.  Real-data
execution is deliberately separated from :mod:`stage_a_preflight` and requires a future gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from math import isfinite
from typing import Callable, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FinancingSchedule:
    valid_from: date
    valid_to: date
    rates: Mapping[str, tuple[float, float]]


@dataclass(frozen=True)
class RepresentationFit:
    scores: dict[str, float]
    r2: float
    max_rel_eps: float


@dataclass(frozen=True)
class OpenQuote:
    bid: float
    ask: float

    @property
    def mid(self) -> float:
        if not (0 < self.bid <= self.ask):
            raise ValueError("OPEN bid/ask must be positive and ordered")
        return (float(self.bid) + float(self.ask)) / 2.0


@dataclass(frozen=True)
class AccountingStep:
    timestamp: int
    target_weights: Mapping[str, float]
    opens: Mapping[str, OpenQuote]
    kind: str = "rebalance"


@dataclass(frozen=True)
class SignalStep:
    timestamp: int
    scores: Mapping[str, float] | None
    opens: Mapping[str, OpenQuote]
    kind: str = "rebalance"


@dataclass(frozen=True)
class FrozenDecision:
    decision: datetime
    evaluable: bool
    eligible_by_leg: Sequence[Iterable[int]]
    opens_by_timestamp: Mapping[int, Mapping[str, OpenQuote]]
    terminal: bool = False


@dataclass(frozen=True)
class FinancingEvent:
    day: date
    schedule: FinancingSchedule
    opens: Mapping[str, OpenQuote]
    days_charged: float | None
    after_step: int = 0


@dataclass(frozen=True)
class TargetUnits:
    edge_notionals: dict[str, float]
    base_usd_values: dict[str, float]
    units: dict[str, float]


@dataclass(frozen=True)
class TradeRecord:
    timestamp: int
    kind: str
    target_weights: dict[str, float]
    target_units: dict[str, float]
    fills: dict[str, float]
    spread_cost: float


@dataclass(frozen=True)
class AccountingPath:
    denominator: int
    equities: tuple[float, ...]
    period_returns: tuple[float, ...]
    trades: tuple[TradeRecord, ...]
    total_spread_cost: float
    total_financing: float


def select_signal(schedules: Sequence[FinancingSchedule], decision: datetime,
                  *, evaluable: bool = True) -> FinancingSchedule | None:
    """Latest schedule whose complete printed interval ended before decision."""
    if not evaluable:
        return None
    eligible = [s for s in schedules if s.valid_to < decision.date()]
    if not eligible:
        raise ValueError("no complete financing interval before decision")
    return max(eligible, key=lambda s: (s.valid_to, s.valid_from))


def select_accounting_schedule(schedules: Sequence[FinancingSchedule], day: date) -> FinancingSchedule:
    """Contemporaneous F(d), with later-starting overlap precedence; accounting only."""
    eligible=[s for s in schedules if s.valid_from<=day<=s.valid_to]
    if not eligible: raise ValueError(f"no authoritative financing schedule for {day}")
    return max(eligible,key=lambda s:s.valid_from)


def first_common_h1(target_ms: int, eligible_by_leg: Sequence[Iterable[int]],
                    max_delay_hours: int = 48) -> int:
    if not eligible_by_leg:
        raise ValueError("no routed legs")
    common = set.intersection(*(set(map(int, x)) for x in eligible_by_leg))
    later = [x for x in common if x >= int(target_ms)]
    if not later:
        raise ValueError("no common H1 timestamp at/after target within 48 hours")
    chosen = min(later)
    if chosen - int(target_ms) > int(max_delay_hours) * 3_600_000:
        raise ValueError(f"first common H1 timestamp exceeds {max_delay_hours}-hour maximum")
    return chosen


def fill_open(side: int, bid_open: float, ask_open: float) -> float:
    if side not in (-1, 1) or not (0 < bid_open <= ask_open):
        raise ValueError("side must be +/-1 and OPEN bid/ask must be positive and ordered")
    return float(ask_open if side > 0 else bid_open)


def currency_targets(scores: Mapping[str, float], k: int) -> dict[str, float]:
    if not scores or 2 * int(k) > len(scores) or k < 1:
        raise ValueError("invalid N/k")
    if any(not isfinite(float(v)) for v in scores.values()):
        raise ValueError("latent carry scores must be finite")
    order = sorted(scores, key=lambda c: (-float(scores[c]), c))
    longs, shorts = set(order[:k]), set(order[-k:])
    weight = 1.0 / k
    return {c: weight if c in longs else -weight if c in shorts else 0.0
            for c in sorted(scores)}


def pair_positions(weights: Mapping[str, float], routes: Mapping[str, object]) -> dict[str, float]:
    out: dict[str, float] = {}
    for currency, weight in weights.items():
        raw = routes[currency]
        legs = raw.get("legs", []) if isinstance(raw, Mapping) else raw
        for pair, coefficient in legs:
            out[pair] = out.get(pair, 0.0) + float(weight) * float(coefficient)
    return {p: q for p, q in out.items() if q != 0}


def _pair_currencies(pair: str) -> tuple[str, str]:
    symbol = pair.split(".", 1)[0].replace("_", "")
    if len(symbol) != 6:
        raise ValueError(f"invalid FX pair {pair}")
    return symbol[:3], symbol[3:]


def reconstruct_exposures(positions: Mapping[str, float], currencies: Sequence[str]) -> dict[str, float]:
    out = {c: 0.0 for c in currencies}
    for pair, q in positions.items():
        base, quote = _pair_currencies(pair)
        if base not in out or quote not in out:
            raise ValueError(f"route pair {pair} outside currency columns")
        out[base] += float(q); out[quote] -= float(q)
    return out


def currency_usd_values(opens: Mapping[str, OpenQuote]) -> dict[str, float]:
    """Recover deterministic same-time currency midpoint values from a routed FX tree."""
    values={"USD":1.0}; pending=dict(opens)
    while pending:
        progressed=False
        for pair,quote in list(pending.items()):
            base,counter=_pair_currencies(pair); mid=quote.mid
            if counter in values:
                values[base]=mid*values[counter]
            elif base in values:
                values[counter]=values[base]/mid
            else:
                continue
            del pending[pair]; progressed=True
        if not progressed:
            raise ValueError("OPEN midpoint graph is disconnected from USD")
    return values


def solve_target_units(weights: Mapping[str,float], equity_usd: float,
                       routes: Mapping[str,object],
                       opens: Mapping[str,OpenQuote]) -> TargetUnits:
    """Map frozen currency-gross-2 targets to unique routed pair base units."""
    if not isfinite(equity_usd) or equity_usd <= 0:
        raise ValueError("equity must be finite and positive")
    vals=np.asarray(list(weights.values()),dtype=float)
    gross=float(np.sum(np.abs(vals))); net=float(np.sum(vals))
    if not np.isfinite(vals).all() or abs(net)>1e-12 or not (abs(gross-2)<1e-12 or gross==0):
        raise ValueError("targets must be zero-sum with currency gross 2, or entirely flat")
    scaled={c:float(v)*equity_usd for c,v in weights.items()}
    edge=pair_positions(scaled,routes)
    rebuilt=reconstruct_exposures(edge,list(weights))
    if any(abs(rebuilt[c]-scaled[c])>1e-8*max(1.0,equity_usd) for c in weights):
        raise ValueError("routing does not reconstruct target currency exposure")
    if len(edge)>max(0,len(weights)-1):
        raise ValueError("routing edge solution is not a unique spanning-tree solution")
    currency_values=currency_usd_values(opens)
    base_values={}
    for pair in edge:
        base,_=_pair_currencies(pair)
        if base not in currency_values:
            raise ValueError(f"missing USD midpoint value for {base}")
        base_values[pair]=currency_values[base]
    units={p:edge[p]/base_values[p] for p in edge}
    return TargetUnits(edge,base_values,units)


def _quote_usd(pair: str, opens: Mapping[str,OpenQuote]) -> float:
    _,quote=_pair_currencies(pair)
    return currency_usd_values(opens)[quote]


def run_accounting_path(initial_equity: float, steps: Sequence[AccountingStep],
                        financing_events: Sequence[FinancingEvent],
                        routes: Mapping[str,object], denominator: int,
                        *, spread_multiplier: float = 1.0,
                        adverse_financing: bool = False) -> AccountingPath:
    """Run one complete synthetic accounting path; callers supply causally frozen targets."""
    if denominator not in (360,365) or not steps:
        raise ValueError("D360 or D365 and at least one accounting step are required")
    if any(steps[i].timestamp>=steps[i+1].timestamp for i in range(len(steps)-1)):
        raise ValueError("accounting steps must be strictly ordered")
    by_step: dict[int,list[FinancingEvent]]={}
    for event in financing_events:
        by_step.setdefault(event.after_step,[]).append(event)
    equity=float(initial_equity); positions:dict[str,float]={}; prior_opens=None
    trades=[]; equities=[]; period_returns=[]; total_spread=0.0; total_financing=0.0
    holding_start_equity: float | None=None
    for i,step in enumerate(steps):
        if prior_opens is not None:
            for pair,q in positions.items():
                equity += q*(step.opens[pair].mid-prior_opens[pair].mid)*_quote_usd(pair,step.opens)
        equity_before_trade=equity
        if step.kind=="rebalance" and holding_start_equity is not None:
            # Ordinary rebalance cost starts the new holding period.
            period_returns.append(equity_before_trade/holding_start_equity-1)
            holding_start_equity=equity_before_trade
        elif step.kind in ("rebalance","gap_reentry"):
            holding_start_equity=equity_before_trade
        target=solve_target_units(step.target_weights,equity,routes,step.opens)
        all_pairs=set(positions)|set(target.units); fills={}; cost=0.0
        for pair in all_pairs:
            delta=target.units.get(pair,0.0)-positions.get(pair,0.0)
            if delta:
                quote=step.opens[pair]; fills[pair]=fill_open(1 if delta>0 else -1,quote.bid,quote.ask)
                cost += (abs(delta)*abs(fills[pair]-quote.mid)*_quote_usd(pair,step.opens)
                         *spread_multiplier)
        equity-=cost; total_spread+=cost; positions=dict(target.units)
        for event in by_step.get(i,[]):
            for pair,q in positions.items():
                if q==0: continue
                if pair not in event.opens: continue
                cash=position_financing_cashflow_usd(
                    event.schedule,pair,q,event.opens[pair].mid,denominator,
                    rollover_multiplier(event.day,pair) if event.days_charged is None else event.days_charged,
                    _quote_usd(pair,event.opens))
                if adverse_financing: cash=apply_financing_stress(cash)
                equity+=cash; total_financing+=cash
        if not isfinite(equity) or equity<=0:
            raise ValueError("accounting path equity is non-finite or non-positive")
        if step.kind in ("gap_exit","terminal"):
            if holding_start_equity is None:
                raise ValueError(f"{step.kind} without an open evaluable holding period")
            # Frozen exception: gap/terminal exit cost belongs to the preceding holding period.
            period_returns.append(equity/holding_start_equity-1)
            holding_start_equity=None
        trades.append(TradeRecord(step.timestamp,step.kind,dict(step.target_weights),
                                  dict(target.units),fills,cost))
        equities.append(equity)
        prior_opens=step.opens
    if holding_start_equity is not None:
        raise ValueError("accounting path must end with a terminal or gap exit")
    return AccountingPath(denominator,tuple(equities),tuple(period_returns),tuple(trades),
                          total_spread,total_financing)


def run_dual_accounting_paths(initial_equity: float, steps: Sequence[AccountingStep],
                              financing_events: Sequence[FinancingEvent],
                              routes: Mapping[str,object], *, spread_multiplier: float = 1.0,
                              adverse_financing: bool = False) -> dict[int,AccountingPath]:
    """Mandatory independent D360/D365 paths; no post-hoc financing substitution."""
    return {d:run_accounting_path(initial_equity,steps,financing_events,routes,d,
                                  spread_multiplier=spread_multiplier,
                                  adverse_financing=adverse_financing)
            for d in (360,365)}


def run_adverse_dual_accounting_paths(initial_equity: float,
                                      steps: Sequence[AccountingStep],
                                      financing_events: Sequence[FinancingEvent],
                                      routes: Mapping[str,object]) -> dict[int,AccountingPath]:
    """Frozen G4 corner: spread x2, debit x1.25 x1.10, credit x0.80."""
    return run_dual_accounting_paths(initial_equity,steps,financing_events,routes,
                                     spread_multiplier=2.0,adverse_financing=True)


def run_spread3_sensitivity_paths(initial_equity: float,
                                  steps: Sequence[AccountingStep],
                                  financing_events: Sequence[FinancingEvent],
                                  routes: Mapping[str,object]) -> dict[int,AccountingPath]:
    """Frozen reported, non-gating spread x3 sensitivity."""
    return run_dual_accounting_paths(initial_equity,steps,financing_events,routes,
                                     spread_multiplier=3.0)


def _book_weights(currencies: Sequence[str], longs: Sequence[str],
                  shorts: Sequence[str]) -> dict[str,float]:
    if len(longs)!=len(shorts) or not longs or set(longs)&set(shorts):
        raise ValueError("benchmark book membership must be balanced and disjoint")
    k=len(longs); ls=set(longs); ss=set(shorts)
    return {c:(1.0/k if c in ls else -1.0/k if c in ss else 0.0) for c in currencies}


def run_static_benchmark_paths(initial_equity: float,
                               market_steps: Sequence[AccountingStep],
                               financing_events: Sequence[FinancingEvent],
                               routes: Mapping[str,object], currencies: Sequence[str],
                               *, count: int = 1000, seed: int = 20260809,
                               k: int = 4,
                               routing_currencies: Sequence[str] | None = None) -> dict[int,list[AccountingPath]]:
    """Run frozen-membership books through the identical accounting engine."""
    if count!=1000 or seed!=20260809 or k!=4:
        raise ValueError("Stage-A benchmark requires 1000 books, seed 20260809, k=4")
    result={360:[],365:[]}
    weight_columns=tuple(routing_currencies or currencies)
    for book in benchmark_books(currencies,k,count,seed):
        active=_book_weights(weight_columns,book["longs"],book["shorts"])
        steps=[AccountingStep(s.timestamp,
                              {c:0.0 for c in weight_columns} if s.kind in ("gap_exit","terminal") else active,
                              s.opens,s.kind) for s in market_steps]
        paths=run_dual_accounting_paths(initial_equity,steps,financing_events,routes)
        for d in result: result[d].append(paths[d])
    return result


def run_loco_accounting_paths(initial_equity: float, signal_steps: Sequence[SignalStep],
                              financing_events: Sequence[FinancingEvent],
                              routes: Mapping[str,object], currencies: Sequence[str],
                              *, k: int = 4) -> dict[str,dict[int,AccountingPath]]:
    """Run all active-currency omissions with N=13/k=4 and both denominators."""
    if len(currencies)!=14 or k!=4 or "TRY" in currencies:
        raise ValueError("Stage-A LOCO requires all 14 no-TRY currencies and k=4")
    out={}
    for omitted in currencies:
        steps=[]
        for s in signal_steps:
            if s.scores is None:
                weights={c:0.0 for c in currencies}
            else:
                scores={c:v for c,v in s.scores.items() if c!=omitted}
                if set(scores)!=set(currencies)-{omitted}:
                    raise ValueError("LOCO signal cross-section mismatch")
                selected=currency_targets(scores,k)
                weights={c:(0.0 if c==omitted else selected[c]) for c in currencies}
            steps.append(AccountingStep(s.timestamp,weights,s.opens,s.kind))
        out[omitted]=run_dual_accounting_paths(initial_equity,steps,financing_events,routes)
    return out


def run_full_loco_pipelines(initial_equity: float, signal_steps: Sequence[SignalStep],
                           financing_events: Sequence[FinancingEvent],
                           routes: Mapping[str,object], currencies: Sequence[str]) -> dict[str,dict[str,object]]:
    """All 14 LOCO strategies plus their unchanged-seed 1,000-book dual-accounting ensembles."""
    strategy=run_loco_accounting_paths(initial_equity,signal_steps,financing_events,routes,currencies)
    out={}
    for omitted in currencies:
        active=tuple(c for c in currencies if c!=omitted)
        market=[AccountingStep(s.timestamp,{},s.opens,s.kind) for s in signal_steps]
        benchmarks=run_static_benchmark_paths(initial_equity,market,financing_events,routes,active,
                                               routing_currencies=currencies)
        out[omitted]={"N":13,"k":4,"strategy":strategy[omitted],"benchmark":benchmarks}
    return out


def fit_latent_carry(pair_midpoints: Mapping[str, float], currencies: Sequence[str],
                     min_r2: float = .90, max_rel_eps: float = .25) -> RepresentationFit:
    cols = list(currencies); index = {c:i for i,c in enumerate(cols)}
    rows=[]; y=[]
    for pair, value in pair_midpoints.items():
        base, quote = _pair_currencies(pair)
        if base not in index or quote not in index:
            raise ValueError(f"pair {pair} outside representation")
        row=np.zeros(len(cols)); row[index[base]]=1; row[index[quote]]=-1
        rows.append(row); y.append(float(value))
    a=np.asarray(rows); obs=np.asarray(y)
    if len(obs)<len(cols)-1 or not np.isfinite(obs).all():
        raise ValueError("representation is underidentified or non-finite")
    constrained=np.vstack([a,np.ones(len(cols))]); rhs=np.r_[obs,0.0]
    beta=np.linalg.lstsq(constrained,rhs,rcond=None)[0]
    residual=obs-a@beta; denom=float(np.sum((obs-obs.mean())**2))
    r2=1-float(residual@residual)/denom if denom>0 else (1.0 if np.allclose(residual,0) else -np.inf)
    sd=float(np.std(obs)); rel=float(np.max(np.abs(residual))/sd) if sd>0 else (0.0 if np.allclose(residual,0) else np.inf)
    if not (isfinite(r2) and isfinite(rel) and r2>=min_r2 and rel<=max_rel_eps):
        raise ValueError(f"representation gate failed: r2={r2}, max_rel_eps={rel}")
    return RepresentationFit(dict(zip(cols,map(float,beta))),r2,rel)


def build_causal_signal_steps(decisions: Sequence[FrozenDecision],
                              schedules: Sequence[FinancingSchedule],
                              currencies: Sequence[str], pair_grid: Sequence[str],
                              subgraph_currencies: Sequence[str], *, k: int = 4) -> list[SignalStep]:
    """Bind mask, full-interval signal, representation gates and first-common H1 execution."""
    if len(currencies)!=14 or k!=4 or "TRY" in currencies:
        raise ValueError("active causal builder requires the frozen N=14 no-TRY universe and k=4")
    out=[]; previous_evaluable=False
    for item in decisions:
        if item.decision.tzinfo is None or item.decision.utcoffset()!=timedelta(0):
            raise ValueError("decision timestamps must be UTC-aware")
        target_ms=int(item.decision.timestamp()*1000)
        execution=first_common_h1(target_ms,item.eligible_by_leg,48)
        if execution not in item.opens_by_timestamp:
            raise ValueError("first common H1 OPEN payload unavailable")
        if item.terminal:
            out.append(SignalStep(execution,None,item.opens_by_timestamp[execution],"terminal"))
            previous_evaluable=False
            continue
        if not item.evaluable:
            if previous_evaluable:
                out.append(SignalStep(execution,None,item.opens_by_timestamp[execution],"gap_exit"))
            previous_evaluable=False
            continue
        signal=select_signal(schedules,item.decision,evaluable=True)
        midpoints={p:(signal.rates[p][0]-signal.rates[p][1])/2.0 for p in pair_grid}
        full=fit_latent_carry(midpoints,currencies,.90,.25)
        sub=set(subgraph_currencies)
        subpairs={p:v for p,v in midpoints.items() if set(_pair_currencies(p))<=sub}
        fit_latent_carry(subpairs,subgraph_currencies,.90,.25)
        kind="gap_reentry" if not previous_evaluable and out else "rebalance"
        # Membership is generated here, then carried as scores into downstream strategy/LOCO builders.
        currency_targets(full.scores,k)
        out.append(SignalStep(execution,full.scores,item.opens_by_timestamp[execution],kind))
        previous_evaluable=True
    if not out or out[-1].kind!="terminal":
        raise ValueError("frozen decision sequence must include terminal liquidation")
    return out


def accounting_steps_from_signals(signal_steps: Sequence[SignalStep],
                                  currencies: Sequence[str], *, k: int = 4) -> list[AccountingStep]:
    steps=[]
    for step in signal_steps:
        weights=({c:0.0 for c in currencies} if step.scores is None
                 else currency_targets(step.scores,k))
        steps.append(AccountingStep(step.timestamp,weights,step.opens,step.kind))
    return steps


def build_financing_events(signal_steps: Sequence[SignalStep],
                           schedules: Sequence[FinancingSchedule],
                           opens_21utc_by_day: Mapping[date,Mapping[str,OpenQuote]]) -> list[FinancingEvent]:
    """Construct events only for venue-evidenced business-day 21:00 OPENs while held."""
    events=[]
    for i,(start,end) in enumerate(zip(signal_steps,signal_steps[1:])):
        if start.scores is None:
            continue
        start_dt=datetime.fromtimestamp(start.timestamp/1000,tz=timezone.utc)
        end_dt=datetime.fromtimestamp(end.timestamp/1000,tz=timezone.utc)
        for day,opens in sorted(opens_21utc_by_day.items()):
            instant=datetime.combine(day,time(21),tzinfo=timezone.utc)
            if start_dt<=instant<end_dt:
                if day.weekday()>=5:
                    raise ValueError("financing OPEN supplied for a weekend")
                schedule=select_accounting_schedule(schedules,day)
                # Each instrument's frozen rollover exception is applied inside the path.
                events.append(FinancingEvent(day,schedule,opens,None,after_step=i))
    return events


def financing_cashflow_usd(base_notional: float, pair_mid: float, annual_rate_pct: float,
                           quote_basis: int, days_charged: float,
                           quote_to_usd: float) -> float:
    if quote_basis not in (360,365) or pair_mid<=0 or quote_to_usd<=0 or days_charged<0:
        raise ValueError("invalid financing input")
    return (float(base_notional)*pair_mid*(annual_rate_pct/100.0/quote_basis)
            *days_charged*quote_to_usd)


def position_financing_cashflow_usd(schedule: FinancingSchedule, instrument: str,
                                    base_position: float, pair_mid: float, quote_basis: int,
                                    days_charged: float, quote_to_usd: float) -> float:
    """Choose printed long/short rate by pair-base position direction."""
    if base_position==0: return 0.0
    try: long_rate,short_rate=schedule.rates[instrument]
    except KeyError as exc: raise ValueError(f"missing financing rate for {instrument}") from exc
    rate=long_rate if base_position>0 else short_rate
    return financing_cashflow_usd(abs(base_position),pair_mid,rate,quote_basis,
                                  days_charged,quote_to_usd)


def rollover_multiplier(day: date, instrument: str) -> int:
    if day.weekday() >= 5:
        return 0
    triple_weekday = 3 if (instrument == "USDCAD.pro" and day >= date(2025,10,2)) else 2
    return 3 if day.weekday() == triple_weekday else 1


def apply_financing_stress(cashflow: float) -> float:
    return float(cashflow) * (.80 if cashflow >= 0 else 1.25 * 1.10)


def spread_cost(turnover_notional: float, bid_open: float, ask_open: float,
                multiplier: float = 1.0) -> float:
    if turnover_notional < 0 or not (0 < bid_open <= ask_open) or multiplier < 0:
        raise ValueError("invalid spread input")
    mid=(bid_open+ask_open)/2
    return float(turnover_notional) * .5 * (ask_open-bid_open)/mid * multiplier


def benchmark_books(currencies: Sequence[str], k: int, count: int = 1000,
                    seed: int = 20260809) -> list[dict[str, tuple[str,...]]]:
    if 2*k>len(currencies): raise ValueError("invalid benchmark N/k")
    universe=np.array(list(currencies),dtype=object); rng=np.random.Generator(np.random.PCG64(seed)); out=[]
    for _ in range(count):
        draw=rng.choice(universe,size=2*k,replace=False).tolist()
        longs=tuple(sorted(draw[:k])); shorts=tuple(sorted(draw[k:]))
        out.append({"longs":longs,"shorts":shorts})
    return out


def turnover(previous: Mapping[str,float], target: Mapping[str,float]) -> float:
    return float(sum(abs(float(target.get(c,0))-float(previous.get(c,0)))
                     for c in set(previous)|set(target)))


def spearman_ic(carry: Sequence[float], spot_returns: Sequence[float]) -> float:
    if len(carry)!=len(spot_returns) or len(carry)<2: raise ValueError("invalid IC cross-section")
    a=pd.Series(carry,dtype=float).rank(method="average"); b=pd.Series(spot_returns,dtype=float).rank(method="average")
    value=float(a.corr(b,method="pearson"))
    if not isfinite(value): raise ValueError("degenerate IC cross-section")
    return value


def currency_spot_log_returns(pair_log_returns: Mapping[str,float],
                              currencies: Sequence[str], numeraire: str="USD") -> dict[str,float]:
    """Recover common-numeraire currency log returns from pair log returns."""
    cols=[c for c in currencies if c!=numeraire]; index={c:i for i,c in enumerate(cols)}
    rows=[]; obs=[]
    for pair,value in pair_log_returns.items():
        base,quote=_pair_currencies(pair); row=np.zeros(len(cols))
        if base!=numeraire: row[index[base]]+=1
        if quote!=numeraire: row[index[quote]]-=1
        rows.append(row); obs.append(float(value))
    a=np.asarray(rows); y=np.asarray(obs)
    values,residuals,rank,_=np.linalg.lstsq(a,y,rcond=None)
    if rank<len(cols) or not np.allclose(a@values,y,rtol=1e-10,atol=1e-12):
        raise ValueError("spot route returns do not identify a consistent currency cross-section")
    return {**dict(zip(cols,map(float,values))),numeraire:0.0}


def spot_ic_series(signal_steps: Sequence[SignalStep], currencies: Sequence[str]) -> list[float]:
    """Lagged carry rank versus subsequent midpoint spot-only common-numeraire returns."""
    out=[]
    for current,nxt in zip(signal_steps,signal_steps[1:]):
        if current.scores is None:
            continue
        if set(current.scores)!=set(currencies):
            raise ValueError("IC carry cross-section does not match active currencies")
        common=set(current.opens)&set(nxt.opens)
        pair_returns={p:float(np.log(nxt.opens[p].mid/current.opens[p].mid)) for p in common}
        returns=currency_spot_log_returns(pair_returns,currencies)
        out.append(spearman_ic([current.scores[c] for c in currencies],
                               [returns[c] for c in currencies]))
    if not out:
        raise ValueError("no evaluable spot-only IC intervals")
    return out


def _round_half_up(value: float) -> int:
    return int(Decimal(str(value)).quantize(Decimal("1"),rounding=ROUND_HALF_UP))


def stationary_bootstrap_lower_bound(series: Sequence[float], reps: int = 10_000,
                                     seed: int = 20260808,
                                     block_selector: Callable[[np.ndarray],float]|None = None) -> tuple[float,int]:
    x=np.asarray(series,dtype=float)
    if x.ndim!=1 or len(x)<2 or not np.isfinite(x).all() or reps<1: raise ValueError("invalid bootstrap input")
    if block_selector is None:
        try:
            from arch.bootstrap import StationaryBootstrap, optimal_block_length
        except ImportError as exc:
            raise RuntimeError("frozen inference requires arch>=7.2,<8") from exc
        selected=float(optimal_block_length(x)["stationary"].iloc[0])
    else: selected=float(block_selector(x))
    b=_round_half_up(selected) if isfinite(selected) else 0
    if not isfinite(selected) or b<1 or b>len(x)/2: raise ValueError("degenerate stationary-bootstrap block length")
    rng=np.random.Generator(np.random.PCG64(seed))
    if block_selector is None:
        boot=StationaryBootstrap(b,x,seed=rng)
        means=np.array([float(np.mean(data[0][0])) for data in boot.bootstrap(reps)])
    else:
        means=[]; p=1.0/b
        for _ in range(reps):
            idx=np.empty(len(x),dtype=int); idx[0]=rng.integers(len(x))
            for i in range(1,len(x)):
                idx[i]=rng.integers(len(x)) if rng.random()<p else (idx[i-1]+1)%len(x)
            means.append(float(np.mean(x[idx])))
        means=np.asarray(means)
    return float(np.percentile(means,5)),b


def rap(returns: Sequence[float]) -> float:
    x=np.asarray(returns,dtype=float); sd=float(np.std(x,ddof=1))
    value=float(np.mean(x)/sd) if sd>0 else np.nan
    if not isfinite(value): raise ValueError("non-finite RAP")
    return value


def max_drawdown_gate(strategy_mdd: float, benchmark_median_mdd: float) -> bool:
    if not all(isfinite(x) and x<=0 for x in (strategy_mdd,benchmark_median_mdd)):
        raise ValueError("MDD values must be finite and non-positive")
    return strategy_mdd >= benchmark_median_mdd


def max_drawdown_from_returns(returns: Sequence[float]) -> float:
    x=np.asarray(returns,dtype=float)
    if x.ndim!=1 or not np.isfinite(x).all() or np.any(x<=-1): raise ValueError("invalid return path")
    equity=np.r_[1.0,np.cumprod(1+x)]; peaks=np.maximum.accumulate(equity)
    return float(np.min(equity/peaks-1))


def evaluate_frozen_gates(strategy_returns: Sequence[float],
                          benchmark_returns: Sequence[Sequence[float]],
                          ic_lower_bound: float, stressed_total_return: float,
                          loco_rap_excesses: Sequence[float]) -> dict[str,object]:
    """Disabled legacy interface: one accounting scenario can never issue a verdict."""
    raise RuntimeError("single-scenario evaluation is disabled; use mandatory dual-accounting gates")


def evaluate_dual_accounting_gates(
        scenarios: Mapping[int,Mapping[str,object]], ic_lower_bound: float) -> dict[str,object]:
    """Apply G2 once and require G1/G3/G4/G5 independently under D360 and D365."""
    if set(scenarios)!={360,365}:
        raise ValueError("both and only D360/D365 accounting scenarios are required")
    if not isfinite(ic_lower_bound):
        return {"gates":None,"scenarios":None,"terminal_verdict":"UNDETERMINED",
                "reason":"non-finite or degenerate G2 bootstrap evidence"}
    g2=ic_lower_bound>0; per={}
    for denominator in (360,365):
        item=scenarios[denominator]
        bench=item["benchmark_returns"]; strategy=item["strategy_returns"]
        loco=item["loco_rap_excesses"]; stressed=float(item["stressed_total_return"])
        if len(bench)!=1000 or len(loco)!=14:
            raise ValueError("frozen benchmark/LOCO counts required in each scenario")
        srap=rap(strategy); braps=[rap(x) for x in bench]
        smdd=max_drawdown_from_returns(strategy)
        bmdd=float(np.median([max_drawdown_from_returns(x) for x in bench]))
        per[denominator]={
            "G1":srap>float(np.median(braps)),
            "G3":max_drawdown_gate(smdd,bmdd),
            "G4":isfinite(stressed) and stressed>0,
            "G5":all(isfinite(float(x)) and float(x)>0 for x in loco),
        }
    gates={"G1":all(per[d]["G1"] for d in per),"G2":g2,
           "G3":all(per[d]["G3"] for d in per),
           "G4":all(per[d]["G4"] for d in per),
           "G5":all(per[d]["G5"] for d in per)}
    return {"gates":gates,"scenarios":per,
            "terminal_verdict":"SURVIVES_KILL_TEST" if all(gates.values()) else "CLOSED_FAIL"}


def _path_total_return(path: AccountingPath, initial_equity: float) -> float:
    if not path.equities or initial_equity<=0:
        raise ValueError("invalid accounting path for total return")
    return path.equities[-1]/initial_equity-1


def derive_dual_gate_inputs(initial_equity: float,
                            strategy: Mapping[int,AccountingPath],
                            benchmarks: Mapping[int,Sequence[AccountingPath]],
                            adverse_strategy: Mapping[int,AccountingPath],
                            loco: Mapping[str,Mapping[str,object]]) -> dict[int,dict[str,object]]:
    """Derive G1/G3/G4/G5 inputs only from complete frozen accounting paths."""
    if any(set(x)!={360,365} for x in (strategy,benchmarks,adverse_strategy)) or len(loco)!=14:
        raise ValueError("complete dual paths and all 14 LOCO cases are required")
    out={}
    for d in (360,365):
        bench=list(benchmarks[d])
        if len(bench)!=1000: raise ValueError("each denominator requires 1000 benchmark paths")
        loco_excess=[]
        for case in loco.values():
            s=case["strategy"][d]; b=case["benchmark"][d]
            if len(b)!=1000: raise ValueError("each LOCO denominator requires 1000 benchmarks")
            loco_excess.append(rap(s.period_returns)-float(np.median([rap(x.period_returns) for x in b])))
        out[d]={"strategy_returns":strategy[d].period_returns,
                "benchmark_returns":[x.period_returns for x in bench],
                "stressed_total_return":_path_total_return(adverse_strategy[d],initial_equity),
                "loco_rap_excesses":loco_excess}
    return out


def evaluate_complete_stage_a(initial_equity: float,
                              strategy: Mapping[int,AccountingPath],
                              benchmarks: Mapping[int,Sequence[AccountingPath]],
                              adverse_strategy: Mapping[int,AccountingPath],
                              spread3_strategy: Mapping[int,AccountingPath],
                              loco: Mapping[str,Mapping[str,object]],
                              ic_series: Sequence[float]) -> dict[str,object]:
    """Only complete-path verdict boundary; deterministic degeneracy is UNDETERMINED."""
    try:
        ic_lower,block=stationary_bootstrap_lower_bound(ic_series,10_000,20260808)
        inputs=derive_dual_gate_inputs(initial_equity,strategy,benchmarks,adverse_strategy,loco)
        result=evaluate_dual_accounting_gates(inputs,ic_lower)
        if set(spread3_strategy)!={360,365}:
            raise ValueError("spread x3 sensitivity requires both accounting scenarios")
        result["non_gating_sensitivities"]={
            "spread_x3_total_return":{d:_path_total_return(spread3_strategy[d],initial_equity)
                                      for d in (360,365)}}
        result["G2_block_length"]=block
        return result
    except (ValueError,RuntimeError,KeyError) as exc:
        return {"gates":None,"scenarios":None,"terminal_verdict":"UNDETERMINED",
                "reason":str(exc)}


def loco_definitions(currencies: Sequence[str], k: int = 4) -> list[dict[str,object]]:
    full=tuple(currencies); out=[]
    for omitted in full:
        active=tuple(c for c in full if c!=omitted)
        out.append({"omitted":omitted,"rankable":active,"latent_columns":full,
                    "N":len(active),"k":k})
    return out
