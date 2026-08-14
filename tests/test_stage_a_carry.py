from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
import pytest

from bot.forex.stage_a_carry import (
    AccountingStep, FinancingEvent, FrozenDecision, OpenQuote, SignalStep,
    FinancingSchedule, apply_financing_stress, benchmark_books, currency_spot_log_returns, currency_targets,
    evaluate_dual_accounting_gates, evaluate_frozen_gates,
    accounting_steps_from_signals, build_causal_signal_steps, build_financing_events,
    first_common_h1, fit_latent_carry, financing_cashflow_usd, fill_open,
    loco_definitions, max_drawdown_gate, pair_positions, position_financing_cashflow_usd,
    reconstruct_exposures, run_dual_accounting_paths, run_loco_accounting_paths,
    run_static_benchmark_paths, solve_target_units,
    rollover_multiplier, select_accounting_schedule, select_signal, spearman_ic,
    stationary_bootstrap_lower_bound, turnover,
)


UTC = timezone.utc


def test_full_interval_signal_lag_and_no_lookahead():
    old = FinancingSchedule(date(2024, 1, 1), date(2024, 1, 7), {"EURUSD.pro": (1, -1)})
    live = FinancingSchedule(date(2024, 1, 8), date(2024, 1, 14), {"EURUSD.pro": (9, -9)})
    assert select_signal([old, live], datetime(2024, 1, 8, tzinfo=UTC)) == old
    assert select_signal([old, live], datetime(2024, 1, 15, tzinfo=UTC)) == live


def test_gap_is_flat_and_reentry_uses_causal_schedule():
    s = FinancingSchedule(date(2024, 1, 1), date(2024, 1, 7), {})
    assert select_signal([s], datetime(2024, 1, 8, tzinfo=UTC), evaluable=False) is None
    assert select_signal([s], datetime(2024, 1, 9, tzinfo=UTC), evaluable=True) == s


def test_contemporaneous_financing_overlap_is_accounting_only():
    old=FinancingSchedule(date(2024,1,1),date(2024,1,10),{"X":(1,-1)})
    new=FinancingSchedule(date(2024,1,8),date(2024,1,10),{"X":(9,-9)})
    assert select_accounting_schedule([old,new],date(2024,1,9))==new
    assert select_signal([old,new],datetime(2024,1,11,tzinfo=UTC))==new


def test_first_common_h1_and_delay_fail_closed():
    target = 1_000
    assert first_common_h1(target, [{900, 2_000, 3_000}, {2_000, 4_000}], 1) == 2_000
    with pytest.raises(ValueError, match="48"):
        first_common_h1(0, [{49 * 3_600_000}, {49 * 3_600_000}], 48)


def test_bid_ask_open_direction():
    assert fill_open(1, 1.0, 1.2) == 1.2
    assert fill_open(-1, 1.0, 1.2) == 1.0
    with pytest.raises(ValueError):
        fill_open(0, 1.0, 1.2)


ROUTES = {
    "GBP": [["GBPUSD.pro", 1]], "CAD": [["USDCAD.pro", -1]],
    "HUF": [["EURHUF.pro", -1], ["EURUSD.pro", 1]],
    "EUR": [["EURUSD.pro", 1]], "USD": [],
}


def test_routing_signs_and_exact_reconstruction():
    weights = {"EUR": 0, "GBP": .25, "CAD": -.25, "HUF": .25, "USD": -.25}
    pairs = pair_positions(weights, ROUTES)
    assert pairs == {"GBPUSD.pro": .25, "USDCAD.pro": .25,
                     "EURHUF.pro": -.25, "EURUSD.pro": .25}
    assert reconstruct_exposures(pairs, list(weights)) == pytest.approx(weights)


def test_latent_representation_and_fail_closed_gate():
    true = {"EUR": 1.0, "USD": 0.0, "GBP": -1.0}
    mids = {"EURUSD.pro": 1.0, "GBPUSD.pro": -1.0, "EURGBP.pro": 2.0}
    fit = fit_latent_carry(mids, list(true), min_r2=.9, max_rel_eps=.25)
    assert fit.scores == pytest.approx(true)
    with pytest.raises(ValueError, match="representation"):
        fit_latent_carry({**mids, "EURGBP.pro": 20.0}, list(true), .999, .001)


def test_financing_debit_credit_and_sign_aware_stress():
    credit = financing_cashflow_usd(100, 2, 3.65, 365, 1, 1)
    debit = financing_cashflow_usd(100, 2, -3.65, 365, 1, 1)
    assert credit == pytest.approx(0.02) and debit == pytest.approx(-0.02)
    assert apply_financing_stress(credit) == pytest.approx(.016)
    assert apply_financing_stress(debit) == pytest.approx(-.0275)
    assert rollover_multiplier(date(2025,10,1),"USDCAD.pro")==3
    assert rollover_multiplier(date(2025,10,2),"USDCAD.pro")==3
    assert rollover_multiplier(date(2025,10,8),"USDCAD.pro")==1
    schedule=FinancingSchedule(date(2025,1,1),date(2025,1,7),{"EURUSD.pro":(3.65,-7.30)})
    assert position_financing_cashflow_usd(schedule,"EURUSD.pro",100,2,365,1,1)==pytest.approx(.02)
    assert position_financing_cashflow_usd(schedule,"EURUSD.pro",-100,2,365,1,1)==pytest.approx(-.04)


def test_ranking_normal_boundary_and_all_equal_ties():
    codes=list("ABCDEFGHIJKLMN")
    w=currency_targets(dict(zip(codes,range(14))),4)
    assert [c for c in codes if w[c] > 0] == ["K","L","M","N"]
    equal=currency_targets({c:0 for c in reversed(codes)},4)
    assert [c for c,v in equal.items() if v>0] == ["A","B","C","D"]
    assert [c for c,v in equal.items() if v<0] == ["K","L","M","N"]
    boundary={c:0 for c in codes}; boundary.update(A=2,B=2,C=2,D=1,E=1)
    assert set(c for c,v in currency_targets(boundary,4).items() if v>0)==set("ABCD")


def test_benchmark_seed_membership_resets_and_turnover():
    currencies=list("ABCDEFGHIJKLMN")
    a=benchmark_books(currencies,4,5,20260809); b=benchmark_books(currencies,4,5,20260809)
    assert a == b and all(len(x["longs"])==len(x["shorts"])==4 for x in a)
    assert a[0] == {"longs":("C","E","J","K"),"shorts":("B","F","G","M")}
    weights={c:(.25 if c in a[0]["longs"] else -.25 if c in a[0]["shorts"] else 0) for c in currencies}
    assert turnover({},weights)==2 and turnover(weights,weights)==0


def test_spot_only_spearman_known_example_average_ties():
    assert spearman_ic([1,2,3,4],[10,20,30,40]) == pytest.approx(1)
    assert spearman_ic([1,1,2],[1,2,3]) == pytest.approx(.8660254038)
    returns=currency_spot_log_returns({"GBPUSD.pro":.1,"USDCAD.pro":.2},["GBP","USD","CAD"])
    assert returns==pytest.approx({"GBP":.1,"USD":0,"CAD":-.2})


def test_stationary_bootstrap_determinism_and_invalid_fail_closed(monkeypatch):
    x=np.array([-.2,.1,.3,.2,-.1,.4,.1,.2])
    fake=lambda _: 2.0
    a=stationary_bootstrap_lower_bound(x,100,7,block_selector=fake)
    b=stationary_bootstrap_lower_bound(x,100,7,block_selector=fake)
    assert a==b
    for bad in (lambda _:np.nan, lambda _:0, lambda _:5):
        with pytest.raises(ValueError): stationary_bootstrap_lower_bound(x,10,1,block_selector=bad)


def test_signed_mdd_orientation():
    assert max_drawdown_gate(-.10,-.20)
    assert not max_drawdown_gate(-.30,-.20)


def test_single_scenario_gate_path_is_disabled():
    with pytest.raises(RuntimeError,match="dual-accounting"):
        evaluate_frozen_gates([.01,.02],[[.01,.02]]*1000,.01,.01,[.01]*14)


def test_loco_all_currencies_n13_k4_and_columns_retained():
    currencies=list("ABCDEFGHIJKLMN")
    out=loco_definitions(currencies,4)
    assert len(out)==14 and all(x["N"]==13 and x["k"]==4 for x in out)
    assert all(len(x["latent_columns"])==14 for x in out)


FULL_ROUTES = {
    "EUR": [["EURUSD.pro", 1]], "GBP": [["GBPUSD.pro", 1]],
    "CAD": [["USDCAD.pro", -1]],
    "HUF": [["EURHUF.pro", -1], ["EURUSD.pro", 1]], "USD": [],
}


def _quotes(eurusd=2.0, gbpusd=1.5, usdcad=1.25, eurhuf=400.0, spread=.02):
    def q(mid): return OpenQuote(mid-spread/2, mid+spread/2)
    return {"EURUSD.pro":q(eurusd), "GBPUSD.pro":q(gbpusd),
            "USDCAD.pro":q(usdcad), "EURHUF.pro":q(eurhuf)}


def test_unique_weight_to_units_direct_inverse_and_eur_cross():
    w={"EUR":0.0,"GBP":.5,"CAD":-.5,"HUF":.5,"USD":-.5}
    target=solve_target_units(w,100.0,FULL_ROUTES,_quotes(spread=0))
    assert target.edge_notionals == pytest.approx({"GBPUSD.pro":50,"USDCAD.pro":50,
                                                   "EURHUF.pro":-50,"EURUSD.pro":50})
    assert target.base_usd_values == pytest.approx({"GBPUSD.pro":1.5,"USDCAD.pro":1.0,
                                                    "EURHUF.pro":2.0,"EURUSD.pro":2.0})
    assert target.units == pytest.approx({"GBPUSD.pro":50/1.5,"USDCAD.pro":50,
                                         "EURHUF.pro":-25,"EURUSD.pro":25})
    assert reconstruct_exposures({p:n/100 for p,n in target.edge_notionals.items()},list(w)) == pytest.approx(w)


def test_midpoint_sizes_but_bid_ask_fill_charges_actual_delta():
    steps=[AccountingStep(0,{"GBP":1.0,"USD":-1.0},_quotes(spread=.02)),
           AccountingStep(1,{"GBP":0,"USD":0},_quotes(gbpusd=1.6,spread=.02),kind="terminal")]
    out=run_dual_accounting_paths(100,steps,[],{"GBP":FULL_ROUTES["GBP"],"USD":[]})
    p=out[360]
    assert p.trades[0].target_units["GBPUSD.pro"] == pytest.approx(100/1.5)
    assert p.trades[0].fills["GBPUSD.pro"] == pytest.approx(1.51)
    assert p.trades[1].fills["GBPUSD.pro"] == pytest.approx(1.59)
    assert p.total_spread_cost > 0


def test_financing_direction_quote_conversion_and_no_double_sign():
    schedule=FinancingSchedule(date(2025,1,1),date(2025,1,7),
                               {"EURHUF.pro":(3.6,-7.2),"EURUSD.pro":(0,0)})
    event=FinancingEvent(date(2025,1,2),schedule,_quotes(spread=0),1)
    steps=[AccountingStep(0,{"HUF":1.0,"EUR":0,"USD":-1.0},_quotes(spread=0)),
           AccountingStep(1,{"HUF":0,"EUR":0,"USD":0},_quotes(spread=0),kind="terminal")]
    paths=run_dual_accounting_paths(100,steps,[event],{"HUF":FULL_ROUTES["HUF"],"EUR":FULL_ROUTES["EUR"],"USD":[]})
    # HUF target shorts EURHUF; signed short rate must remain a debit after HUF->USD conversion.
    assert paths[360].total_financing < 0
    assert abs(paths[360].total_financing) > abs(paths[365].total_financing)


def test_dual_paths_diverge_and_resize_from_own_equity():
    schedule=FinancingSchedule(date(2025,1,1),date(2025,1,7),{"GBPUSD.pro":(36.0,-36.0)})
    steps=[AccountingStep(0,{"GBP":1.0,"USD":-1.0},_quotes(spread=0)),
           AccountingStep(1,{"GBP":1.0,"USD":-1.0},_quotes(spread=0)),
           AccountingStep(2,{"GBP":0,"USD":0},_quotes(spread=0),kind="terminal")]
    events=[FinancingEvent(date(2025,1,2),schedule,_quotes(spread=0),1)]
    paths=run_dual_accounting_paths(100,steps,events,{"GBP":FULL_ROUTES["GBP"],"USD":[]})
    assert paths[360].equities[1] != paths[365].equities[1]
    assert paths[360].trades[1].target_units["GBPUSD.pro"] != paths[365].trades[1].target_units["GBPUSD.pro"]
    assert all(sum(abs(v) for v in t.target_weights.values()) in (0,2) for t in paths[360].trades)


def test_gap_exit_reentry_and_terminal_are_actual_costed_turnover():
    routes={"GBP":FULL_ROUTES["GBP"],"USD":[]}
    steps=[AccountingStep(0,{"GBP":1,"USD":-1},_quotes()),
           AccountingStep(1,{"GBP":0,"USD":0},_quotes(),kind="gap_exit"),
           AccountingStep(2,{"GBP":1,"USD":-1},_quotes(),kind="gap_reentry"),
           AccountingStep(3,{"GBP":0,"USD":0},_quotes(),kind="terminal")]
    path=run_dual_accounting_paths(100,steps,[],routes)[360]
    assert [t.kind for t in path.trades]==["rebalance","gap_exit","gap_reentry","terminal"]
    assert all(t.spread_cost>0 for t in path.trades)


def test_dual_gate_requires_both_denominators_and_g2_once():
    good={"strategy_returns":[.02,.01,.03],"benchmark_returns":[[.001,-.001,.001]]*1000,
          "stressed_total_return":.01,"loco_rap_excesses":[.01]*14}
    bad={**good,"stressed_total_return":-.01}
    out=evaluate_dual_accounting_gates({360:good,365:bad},ic_lower_bound=.01)
    assert out["gates"]["G2"] is True and out["scenarios"][360]["G4"] is True
    assert out["scenarios"][365]["G4"] is False and out["terminal_verdict"]=="CLOSED_FAIL"
    undetermined=evaluate_dual_accounting_gates({360:good,365:good},ic_lower_bound=float("nan"))
    assert undetermined["terminal_verdict"]=="UNDETERMINED"


def test_benchmark_books_are_complete_independent_accounting_scenarios():
    currencies=tuple("ABCDEFGHIJKLMN")
    routes={c:[[f"{c}US.pro",1]] for c in currencies[:-1]}; routes[currencies[-1]]=[]
    # Use syntactically valid ISO-like codes and a USD numeraire for the accounting engine.
    currencies=("AUD","CAD","CHF","CZK","EUR","GBP","HUF","JPY","NOK","NZD","PLN","SEK","USD","ZAR")
    routes={c:[[f"{c}USD.pro",1]] for c in currencies if c!="USD"}; routes["USD"]=[]
    opens={f"{c}USD.pro":OpenQuote(1,1) for c in currencies if c!="USD"}
    market=[AccountingStep(0,{},opens),AccountingStep(1,{},opens,kind="terminal")]
    paths=run_static_benchmark_paths(100,market,[],routes,currencies,count=1000)
    assert len(paths[360])==len(paths[365])==1000
    assert paths[360][0] is not paths[365][0]
    assert sum(abs(v) for v in paths[360][0].trades[0].target_weights.values())==pytest.approx(2)


def test_loco_runs_all_14_under_both_denominators_with_n13_k4():
    currencies=("AUD","CAD","CHF","CZK","EUR","GBP","HUF","JPY","NOK","NZD","PLN","SEK","USD","ZAR")
    routes={c:[[f"{c}USD.pro",1]] for c in currencies if c!="USD"}; routes["USD"]=[]
    opens={f"{c}USD.pro":OpenQuote(1,1) for c in currencies if c!="USD"}
    scores={c:float(i) for i,c in enumerate(currencies)}
    steps=[SignalStep(0,scores,opens),SignalStep(1,None,opens,kind="terminal")]
    paths=run_loco_accounting_paths(100,steps,[],routes,currencies)
    assert set(paths)==set(currencies)
    assert all(set(v)=={360,365} for v in paths.values())
    assert all(sum(abs(x) for x in v[360].trades[0].target_weights.values())==pytest.approx(2)
               for v in paths.values())


def test_frozen_builder_owns_causal_signal_representation_and_timestamp():
    currencies=("AUD","CAD","CHF","CZK","EUR","GBP","HUF","JPY","NOK","NZD","PLN","SEK","USD","ZAR")
    pairs=[f"{c}USD.pro" for c in currencies if c!="USD"]
    rates={p:(float(i+1),-float(i+1)) for i,p in enumerate(pairs)}
    old=FinancingSchedule(date(2024,1,1),date(2024,1,1),rates)
    future=FinancingSchedule(date(2024,1,2),date(2024,1,8),{p:(99,-99) for p in pairs})
    opens={p:OpenQuote(1,1) for p in pairs}; execution=1_704_153_600_000
    decisions=[FrozenDecision(datetime(2024,1,2,tzinfo=UTC),True,
                              [{execution} for _ in pairs],{execution:opens}),
               FrozenDecision(datetime(2024,1,3,tzinfo=UTC),False,
                              [{execution+86_400_000} for _ in pairs],{execution+86_400_000:opens},terminal=True)]
    built=build_causal_signal_steps(decisions,[old,future],currencies,pairs,currencies)
    assert built[0].scores["ZAR"]<99 and built[0].timestamp==execution
    steps=accounting_steps_from_signals(built,currencies)
    assert sum(abs(x) for x in steps[0].target_weights.values())==pytest.approx(2)
    assert steps[-1].kind=="terminal" and not any(steps[-1].target_weights.values())


def test_financing_event_builder_uses_contemporaneous_schedule_and_rollover_rule():
    opens={"USDCAD.pro":OpenQuote(1.25,1.25)}
    schedule=FinancingSchedule(date(2025,10,1),date(2025,10,3),{"USDCAD.pro":(3.6,-3.6)})
    start=int(datetime(2025,10,2,tzinfo=UTC).timestamp()*1000)
    end=int(datetime(2025,10,3,tzinfo=UTC).timestamp()*1000)
    signals=[SignalStep(start,{"USD":1,"CAD":-1},opens),SignalStep(end,None,opens,"terminal")]
    events=build_financing_events(signals,[schedule],{date(2025,10,2):opens})
    assert len(events)==1 and events[0].days_charged is None
    assert rollover_multiplier(events[0].day,"USDCAD.pro")==3


def test_financing_event_builder_does_not_invent_good_friday_from_weekday():
    opens={"AUDUSD.pro":OpenQuote(1,1)}
    schedule=FinancingSchedule(date(2023,4,3),date(2023,4,9),{"AUDUSD.pro":(1,-1)})
    start=int(datetime(2023,4,3,tzinfo=UTC).timestamp()*1000)
    end=int(datetime(2023,4,10,tzinfo=UTC).timestamp()*1000)
    signals=[SignalStep(start,{"AUD":1,"USD":-1},opens),SignalStep(end,None,opens,"terminal")]
    # No venue OPEN was observed on Good Friday; weekday status alone must not create an event.
    events=build_financing_events(signals,[schedule],{})
    assert events==[]


def test_financing_event_builder_requires_schedule_for_actual_venue_open():
    opens={"AUDUSD.pro":OpenQuote(1,1)}
    start=int(datetime(2023,4,3,tzinfo=UTC).timestamp()*1000)
    end=int(datetime(2023,4,4,tzinfo=UTC).timestamp()*1000)
    signals=[SignalStep(start,{"AUD":1,"USD":-1},opens),SignalStep(end,None,opens,"terminal")]
    with pytest.raises(ValueError,match="authoritative financing schedule"):
        build_financing_events(signals,[],{date(2023,4,3):opens})
