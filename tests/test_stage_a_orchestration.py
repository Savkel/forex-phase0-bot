import json
from pathlib import Path

import pytest

from bot.forex.stage_a_orchestration import (
    ArtifactStore, AssembledRealInputs, Authorization, FrozenRunConfig, IntegrityError, RealInputPlan, RunState,
    RunStateMachine, build_run_id, canonical_bytes, execute_synthetic_fixture,
    _required_financing_open_days, assemble_real_inputs, execute_real_authorized,
    _execution_lineage_disposition,record_material_defect, validate_integrity_snapshot,
)


def _config(**updates):
    data={
        "spec_sha256":"a"*64,"artifact_sha256":{"universe":"b"*64,"mask":"c"*64,"readiness":"d"*64},
        "implementation_sha256":"e"*64,"runtime":{"python":"3.11.9","arch":"7.2.0"},
        "cache_sha256":{f"L{i}":f"{i:064x}" for i in range(13)},
        "transaction_map_sha256":"f"*64,"financing_sha256":"1"*64,
        "manifest_sha256":"2"*64,"benchmark_seed":20260809,"benchmark_count":1000,
        "bootstrap_seed":20260808,"bootstrap_reps":10000,
        "accounting_scenarios":("D360","D365"),"gate_definition_version":1,
        "gate_definition_sha256":"3"*64,
        "execution_manifest_sha256":"4"*64,
        "stage_lineage_id":"stage-a-test","lineage_registry_sha256":"5"*64,
    }
    data.update(updates); return FrozenRunConfig(**data)


def _snapshot(config=None):
    c=config or _config()
    return {"spec_sha256":c.spec_sha256,"artifact_sha256":dict(c.artifact_sha256),
            "implementation_sha256":c.implementation_sha256,"runtime":dict(c.runtime),
            "cache_sha256":dict(c.cache_sha256),"transaction_map_sha256":c.transaction_map_sha256,
            "financing_sha256":c.financing_sha256,"manifest_sha256":c.manifest_sha256,
            "benchmark_seed":c.benchmark_seed,"benchmark_count":c.benchmark_count,
            "bootstrap_seed":c.bootstrap_seed,"bootstrap_reps":c.bootstrap_reps,
            "accounting_scenarios":["D360","D365"],"gate_definition_version":1,
            "gate_definition_sha256":c.gate_definition_sha256,
            "execution_manifest_sha256":c.execution_manifest_sha256,
            "stage_lineage_id":c.stage_lineage_id,"lineage_registry_sha256":c.lineage_registry_sha256,
            "active":True,"try_absent":True,"gbp_direct":True,"output_ignored":True,
            "prior_conflicting_run":False}


def _authorization(config,run_id=None):
    return Authorization("human",run_id or build_run_id(config),True,1,
                         config.execution_manifest_sha256,config.spec_sha256,
                         config.implementation_sha256)


@pytest.mark.parametrize("field",["spec_sha256","transaction_map_sha256","financing_sha256","manifest_sha256"])
def test_integrity_rejects_wrong_identity(field):
    c=_config(); s=_snapshot(c); s[field]="0"*64
    with pytest.raises(IntegrityError): validate_integrity_snapshot(c,s)


def test_integrity_rejects_wrong_cache_missing_leg_and_runtime():
    c=_config()
    for mutate in (
        lambda s:s["cache_sha256"].update({"L0":"9"*64}),
        lambda s:s["cache_sha256"].pop("L0"),
        lambda s:s["runtime"].update({"arch":"7.3.0"}),
    ):
        s=_snapshot(c); mutate(s)
        with pytest.raises(IntegrityError): validate_integrity_snapshot(c,s)


def test_integrity_rejects_superseded_routing_or_single_denominator():
    c=_config()
    for key,value in (("active",False),("try_absent",False),("gbp_direct",False),
                      ("accounting_scenarios",["D365"])):
        s=_snapshot(c); s[key]=value
        with pytest.raises(IntegrityError): validate_integrity_snapshot(c,s)


def test_integrity_rejects_prior_conflicting_run_artifact():
    c=_config(); s=_snapshot(c); s["prior_conflicting_run"]=True
    with pytest.raises(IntegrityError): validate_integrity_snapshot(c,s)


def test_run_id_and_serialization_are_deterministic():
    a=_config(); b=_config(artifact_sha256={"readiness":"d"*64,"mask":"c"*64,"universe":"b"*64})
    assert build_run_id(a)==build_run_id(b)
    assert canonical_bytes({"z":2,"a":1})==b'{"a":1,"z":2}\n'


def test_state_machine_invalid_transition_and_readiness_has_no_verdict():
    sm=RunStateMachine("run")
    with pytest.raises(ValueError): sm.transition("authorize")
    sm.transition("preflight_fail",reason="cache mismatch")
    assert sm.state is RunState.READINESS_BLOCKED and sm.terminal_disposition is None


def test_state_machine_happy_path_has_no_rerun():
    sm=RunStateMachine("run"); sm.transition("preflight_pass"); sm.transition("authorize")
    sm.transition("start"); sm.transition("complete",disposition="CLOSED_FAIL")
    with pytest.raises(ValueError): sm.transition("authorize")


def test_void_retention_corrected_lineage_and_second_defect_suspends(tmp_path):
    store=ArtifactStore(tmp_path); sm=RunStateMachine("run")
    sm.transition("preflight_pass"); sm.transition("authorize"); sm.transition("start")
    original=store.write_result("run",1,{"terminal_disposition":"SURVIVES_KILL_TEST"})
    sm.transition("complete",disposition="SURVIVES_KILL_TEST")
    sm.qualify_material_defect("reviewed evidence",reviewer_confirmed=True,spec_unchanged=True)
    void=store.write_void("run",1,original,"reviewed evidence")
    assert original.exists() and void.exists()
    with pytest.raises(FileExistsError): store.write_result("run",1,{"terminal_disposition":"CLOSED_FAIL"})
    sm.transition("authorize_correction"); sm.transition("start_correction")
    corrected=store.write_result("run",2,{"corrects_attempt":1,"retry_reason":"VOID_CORRECTION"})
    assert json.loads(corrected.read_text())["lineage"]["corrects_attempt"]==1
    sm.transition("complete",disposition="CLOSED_FAIL")
    sm.qualify_material_defect("second",reviewer_confirmed=True,spec_unchanged=True)
    assert sm.state is RunState.SUSPENDED_INFRA


def test_nonqualifying_issue_cannot_soften_existing_verdict():
    sm=RunStateMachine("run"); sm.transition("preflight_pass"); sm.transition("authorize")
    sm.transition("start"); sm.transition("complete",disposition="CLOSED_FAIL")
    with pytest.raises(ValueError): sm.qualify_material_defect("minor",reviewer_confirmed=False,spec_unchanged=True)
    assert sm.state is RunState.RESULT_COMPLETE and sm.terminal_disposition=="CLOSED_FAIL"


def test_execute_denied_before_evaluator_and_authorization_is_run_bound(tmp_path):
    c=_config(); called=[]
    with pytest.raises(PermissionError): execute_synthetic_fixture(c,_snapshot(c),None,lambda:called.append(True),ArtifactStore(tmp_path))
    assert called==[]
    wrong=_authorization(c,build_run_id(c)+"x")
    with pytest.raises(PermissionError): execute_synthetic_fixture(c,_snapshot(c),wrong,lambda:called.append(True),ArtifactStore(tmp_path))
    assert called==[]


@pytest.mark.parametrize("field",["execution_manifest_sha256","spec_sha256","implementation_sha256"])
def test_authorization_is_bound_to_every_frozen_identity(field,tmp_path):
    c=_config(); values={**_authorization(c).__dict__,field:"0"*64}
    with pytest.raises(PermissionError):
        execute_synthetic_fixture(c,_snapshot(c),Authorization(**values),lambda:{"terminal_verdict":"CLOSED_FAIL"},ArtifactStore(tmp_path))


def test_execute_integrity_failure_prevents_evaluator(tmp_path):
    c=_config(); s=_snapshot(c); s["spec_sha256"]="0"*64; called=[]
    auth=_authorization(c)
    with pytest.raises(IntegrityError): execute_synthetic_fixture(c,s,auth,lambda:called.append(True),ArtifactStore(tmp_path))
    assert called==[]


def test_integrity_is_immutable_before_synthetic_evaluator(tmp_path):
    c=_config(); store=ArtifactStore(tmp_path); seen=[]
    def evaluator():
        seen.append((tmp_path/f"{build_run_id(c)}.attempt-01.integrity.json").is_file())
        result=_auditable_gate_results()
        result["gates"]["G4"]=False
        result["scenarios"][360]["G4"]=False
        result["scenario_metrics"][360]["G4"]["stressed_total_return"]=-.01
        result["terminal_verdict"]="CLOSED_FAIL"
        return result
    auth=_authorization(c)
    output=execute_synthetic_fixture(c,_snapshot(c),auth,evaluator,store)
    assert seen==[True] and output.is_file()


def test_output_bytes_are_deterministic_across_fresh_stores(tmp_path):
    a=ArtifactStore(tmp_path/"a").write_result("run",1,{"z":2,"a":1}).read_bytes()
    b=ArtifactStore(tmp_path/"b").write_result("run",1,{"a":1,"z":2}).read_bytes()
    assert a==b


def _auditable_gate_results():
    currencies=("AUD","CAD","CHF","CZK","EUR","GBP","HUF","JPY","NOK","NZD","PLN","SEK","USD","ZAR")
    scenario={"G1":True,"G3":True,"G4":True,"G5":True}
    metrics={
        "G1":{"strategy_rap":.2,"benchmark_median_rap":.1,"excess":.1},
        "G3":{"strategy_mdd":-.1,"benchmark_median_mdd":-.2},
        "G4":{"stressed_total_return":.01},
        "G5":{"loco_excesses":{c:.01 for c in currencies},"pass_count":14,
              "worst_currency":"AUD","worst_excess":.01},
    }
    return {"gates":{f"G{i}":True for i in range(1,6)},
            "scenarios":{360:scenario,365:scenario},
            "scenario_metrics":{360:metrics,365:metrics},
            "G2_metrics":{"mean_ic":.02,"lower_bound":.01,"one_sided_confidence":.95,
                          "lower_bound_quantile":.05,"threshold":0.0},
            "terminal_verdict":"SURVIVES_KILL_TEST"}


@pytest.mark.parametrize("missing",[
    ("G2_metrics",None,None),
    ("G2_metrics","lower_bound",None),
    ("scenario_metrics",360,"G1"),
    ("scenario_metrics",360,"G3"),
    ("scenario_metrics",360,"G4"),
    ("scenario_metrics",360,"G5"),
])
def test_result_serialization_rejects_missing_mandatory_gate_operands(tmp_path,missing):
    results=_auditable_gate_results(); group,branch,leaf=missing
    if branch is None: results.pop(group)
    elif leaf is None: results[group].pop(branch)
    else: results[group][branch].pop(leaf)
    with pytest.raises(ValueError,match="auditable"):
        ArtifactStore(tmp_path).write_result("run",1,{"results":results,
            "terminal_disposition":"SURVIVES_KILL_TEST"})


def test_complete_auditable_result_round_trips_deterministically(tmp_path):
    value={"results":_auditable_gate_results(),"terminal_disposition":"SURVIVES_KILL_TEST"}
    a=ArtifactStore(tmp_path/"a").write_result("run",1,value).read_bytes()
    b=ArtifactStore(tmp_path/"b").write_result("run",1,value).read_bytes()
    assert a==b
    assert json.loads(a)==json.loads(b)


@pytest.mark.parametrize("mutation",["g1_arithmetic","nonfinite","g2_constants","outer_terminal"])
def test_result_serialization_rejects_inconsistent_audit_operands(tmp_path,mutation):
    results=_auditable_gate_results(); outer="SURVIVES_KILL_TEST"
    if mutation=="g1_arithmetic": results["scenario_metrics"][360]["G1"]["excess"]+=.01
    elif mutation=="nonfinite": results["scenario_metrics"][360]["G3"]["strategy_mdd"]=float("nan")
    elif mutation=="g2_constants": results["G2_metrics"]["one_sided_confidence"]=.90
    else: outer="CLOSED_FAIL"
    with pytest.raises(ValueError,match="auditable"):
        ArtifactStore(tmp_path).write_result("run",1,{"results":results,
            "terminal_disposition":outer})


def test_integrated_void_requires_policy_evidence_and_second_defect_suspends(tmp_path):
    store=ArtifactStore(tmp_path); store.write_result("run",1,{"terminal_disposition":"CLOSED_FAIL"})
    with pytest.raises(ValueError):
        record_material_defect(store,"run",1,"bug",reviewer_id="r",reviewer_confirmed=False,
                               spec_unchanged=True,performance_independent=True,
                               why_preflight_missed="fixture defect")
    void=record_material_defect(store,"run",1,"bug",reviewer_id="r",reviewer_confirmed=True,
                                spec_unchanged=True,performance_independent=True,why_preflight_missed="fixture defect")
    assert json.loads(void.read_text())["status"]=="VOID_RETAINED"
    store.write_result("run",2,{"corrects_attempt":1,"retry_reason":"VOID_CORRECTION","terminal_disposition":"CLOSED_FAIL"})
    suspension=record_material_defect(store,"run",2,"bug2",reviewer_id="r2",reviewer_confirmed=True,
                                      spec_unchanged=True,performance_independent=True,why_preflight_missed="fixture defect")
    assert json.loads(suspension.read_text())["status"]=="SUSPENDED_INFRA"


def test_real_boundary_writes_both_integrity_artifacts_before_economics(monkeypatch,tmp_path):
    c=_config(); run_id=build_run_id(c); plan=RealInputPlan(run_id,c,_snapshot(c),{"output":"out"},(),1,None)
    seen=[]
    assembled=AssembledRealInputs((),(),{},(),{"status":"DEEP_INTEGRITY_PASSED","performance_computed":False})
    monkeypatch.setattr("bot.forex.stage_a_orchestration.assemble_real_inputs",lambda root,p:assembled)
    def compute(value):
        out=tmp_path/"out"
        seen.extend([next(out.glob("*.integrity.json")).is_file(),next(out.glob("*.deep-integrity.json")).is_file()])
        result=_auditable_gate_results()
        result["gates"]["G4"]=False
        result["scenarios"][360]["G4"]=False
        result["scenario_metrics"][360]["G4"]["stressed_total_return"]=-.01
        result["terminal_verdict"]="CLOSED_FAIL"
        return result
    monkeypatch.setattr("bot.forex.stage_a_orchestration._compute_real_stage_a",compute)
    auth=_authorization(c)
    result=execute_real_authorized(tmp_path,plan,{"performance_computed":False},auth)
    payload=json.loads(result.read_text())
    assert seen==[True,True]
    assert set(payload["result"]["integrity_artifacts"])=={"metadata","deep"}
    start=json.loads(next((tmp_path/"out").glob("*.execution-start.json")).read_text())
    assert start["economics_boundary"]=="ECONOMICS_STARTED"


def test_consumed_authorization_cannot_execute_same_attempt_twice(monkeypatch,tmp_path):
    c=_config(); run_id=build_run_id(c); plan=RealInputPlan(run_id,c,_snapshot(c),{"output":"out"},(),1,None)
    assembled=AssembledRealInputs((),(),{},(),{"status":"DEEP_INTEGRITY_PASSED"})
    calls=[]
    monkeypatch.setattr("bot.forex.stage_a_orchestration.assemble_real_inputs",lambda root,p:assembled)
    failed=_auditable_gate_results(); failed["gates"]["G4"]=False
    failed["scenarios"][360]["G4"]=False
    failed["scenario_metrics"][360]["G4"]["stressed_total_return"]=-.01
    failed["terminal_verdict"]="CLOSED_FAIL"
    monkeypatch.setattr("bot.forex.stage_a_orchestration._compute_real_stage_a",lambda value:(calls.append(1) or failed))
    auth=_authorization(c)
    execute_real_authorized(tmp_path,plan,{},auth)
    with pytest.raises(PermissionError): execute_real_authorized(tmp_path,plan,{},auth)
    assert calls==[1]


def test_real_boundary_preserves_undetermined_suspension(monkeypatch,tmp_path):
    c=_config(); run_id=build_run_id(c); plan=RealInputPlan(run_id,c,_snapshot(c),{"output":"out"},(),1,None)
    assembled=AssembledRealInputs((),(),{},(),{"status":"DEEP_INTEGRITY_PASSED"})
    monkeypatch.setattr("bot.forex.stage_a_orchestration.assemble_real_inputs",lambda root,p:assembled)
    monkeypatch.setattr("bot.forex.stage_a_orchestration._compute_real_stage_a",
                        lambda value:{"terminal_verdict":"UNDETERMINED","reason":"synthetic degenerate input"})
    auth=_authorization(c)
    payload=json.loads(execute_real_authorized(tmp_path,plan,{},auth).read_text())["result"]
    assert payload["terminal_disposition"]=="UNDETERMINED"
    assert payload["state_history"][-1]["to"]=="UNDETERMINED_SUSPENDED"


def test_undetermined_retry_is_not_a_void_correction():
    sm=RunStateMachine("run",state=RunState.UNDETERMINED_SUSPENDED,material_defects=0)
    sm.transition("authorize_retry"); sm.transition("start_retry")
    sm.transition("complete",disposition="CLOSED_FAIL")
    assert sm.material_defects==0
    assert [x["event"] for x in sm.history]==["authorize_retry","start_retry","complete"]


def test_first_defect_after_undetermined_retry_is_not_second_defect(tmp_path):
    store=ArtifactStore(tmp_path)
    store.write_result("run",2,{"corrects_attempt":1,"retry_reason":"UNDETERMINED",
                                "terminal_disposition":"CLOSED_FAIL"})
    evidence=record_material_defect(store,"run",2,"first defect",reviewer_id="reviewer",
        reviewer_confirmed=True,spec_unchanged=True,performance_independent=True,
        why_preflight_missed="only manifested during authorized computation")
    payload=json.loads(evidence.read_text())
    assert payload["status"]=="VOID_RETAINED"
    assert payload["qualification"]["defect_number"]==1


def test_real_assembler_parses_synthetic_financing_mask_and_thirteen_caches(tmp_path):
    import pandas as pd
    repo=Path(__file__).resolve().parents[1]
    universe=json.loads((repo/"prereg/2026-08-14-tms-carry-no-try-direct-gbp-universe.json").read_text())
    readiness=json.loads((repo/"prereg/2026-08-14-tms-carry-no-try-direct-gbp-price-readiness.json").read_text())
    currencies=universe["currencies"]; scores={c:i/10 for i,c in enumerate(currencies)}
    rates={}
    for pair in universe["investable_financing_pairs"]:
        symbol=pair.split(".")[0]; base,quote=symbol[:3],symbol[3:]
        value=scores[base]-scores[quote]; rates[pair]=[value,-value]
    parsed={"old.pdf":{"valid_from":"2024-01-01","valid_to":"2024-01-01","units":"pct","rows":rates},
            "current.pdf":{"valid_from":"2024-01-02","valid_to":"2024-01-03","units":"pct","rows":rates}}
    decision="2024-01-02T00:00:00+00:00"; terminal="2024-01-03T00:00:00+00:00"
    mask={"evaluable_rebalances":[{"decision_utc":decision,"hold_end_utc":terminal}],
          "excluded_rebalances":[],"last_hold_end_utc":terminal}
    paths={"universe":"universe.json","mask":"mask.json","readiness":"readiness.json","financing":"parsed.json","output":"out"}
    for name,value in (("universe",universe),("mask",mask),("readiness",readiness),("parsed",parsed)):
        (tmp_path/f"{name}.json").write_text(json.dumps(value),encoding="utf-8")
    stamps=[int(pd.Timestamp(x).value//10**6) for x in (decision,"2024-01-02T21:00:00+00:00",terminal,"2024-01-03T21:00:00+00:00")]
    for leg in readiness["routed_legs"]:
        name=leg["v20_instrument"]; path=tmp_path/f"{name}.csv"
        pd.DataFrame({"open_time":stamps,"complete":[True]*4,"bid_o":[1.0]*4,"ask_o":[1.0]*4}).to_csv(path,index=False)
        paths[f"cache:{name}"]=path.name
    c=_config(); mapping=((stamps[0],stamps[0]),(stamps[2],stamps[2]))
    plan=RealInputPlan(build_run_id(c),c,_snapshot(c),paths,mapping)
    assembled=assemble_real_inputs(tmp_path,plan)
    assert assembled.deep_integrity["status"]=="DEEP_INTEGRITY_PASSED"
    assert len(assembled.signal_steps)==2 and assembled.signal_steps[-1].kind=="terminal"
    assert len(assembled.financing_events)==1


def test_required_financing_days_ignore_all_leg_closure_but_reject_partial_gap():
    from datetime import datetime, timezone
    from bot.forex.stage_a_carry import OpenQuote, SignalStep
    start=int(datetime(2023,4,3,tzinfo=timezone.utc).timestamp()*1000)
    end=int(datetime(2023,4,10,tzinfo=timezone.utc).timestamp()*1000)
    good_friday=int(datetime(2023,4,7,21,tzinfo=timezone.utc).timestamp()*1000)
    monday=int(datetime(2023,4,3,21,tzinfo=timezone.utc).timestamp()*1000)
    currencies=("AUD","CAD","CHF","CZK","EUR","GBP","JPY","USD")
    pairs={c:f"{c}USD.pro" for c in currencies if c!="USD"}
    opens={p:OpenQuote(1,1) for p in pairs.values()}
    signals=[SignalStep(start,{c:float(8-i) for i,c in enumerate(currencies)},opens),
             SignalStep(end,None,opens,"terminal")]
    available={p:{monday} for p in pairs.values()}
    routes={c:{"legs":[[pairs[c],1]]} if c!="USD" else {"legs":[]} for c in currencies}
    days=_required_financing_open_days(signals,available,routes,
                                        lambda t,required:{p:opens[p] for p in required})
    assert good_friday not in set().union(*available.values())
    assert list(days)==[datetime(2023,4,3,tzinfo=timezone.utc).date()]
    # An inactive universe leg is irrelevant.
    days=_required_financing_open_days(signals,{**available,"NZDUSD.pro":set()},routes,
                                        lambda t,required:{p:opens[p] for p in required})
    assert list(days)


def test_required_financing_days_require_eurusd_only_for_eligible_eur_cross():
    from datetime import datetime, timezone
    from bot.forex.stage_a_carry import OpenQuote, SignalStep
    start=int(datetime(2024,2,1,tzinfo=timezone.utc).timestamp()*1000)
    end=int(datetime(2024,2,2,tzinfo=timezone.utc).timestamp()*1000)
    rollover=int(datetime(2024,2,1,21,tzinfo=timezone.utc).timestamp()*1000)
    currencies=("AUD","CAD","CHF","CZK","EUR","GBP","HUF","USD")
    routes={
        "AUD":{"legs":[["AUDUSD.pro",1]]}, "CAD":{"legs":[["USDCAD.pro",-1]]},
        "CHF":{"legs":[["USDCHF.pro",-1]]}, "CZK":{"legs":[["EURCZK.pro",-1],["EURUSD.pro",1]]},
        "EUR":{"legs":[["EURUSD.pro",1]]}, "GBP":{"legs":[["GBPUSD.pro",1]]},
        "HUF":{"legs":[["EURHUF.pro",-1],["EURUSD.pro",1]]}, "USD":{"legs":[]},
    }
    opens={p:OpenQuote(1,1) for p in {leg[0] for route in routes.values() for leg in route["legs"]}}
    signals=[SignalStep(start,{c:float(8-i) for i,c in enumerate(currencies)},opens),
             SignalStep(end,None,opens,"terminal")]
    availability={p:{rollover} for p in opens}
    availability["EURUSD.pro"]=set()
    with pytest.raises(IntegrityError,match="missing required financing conversion OPEN"):
        _required_financing_open_days(signals,availability,routes,
                                      lambda t,required:{p:opens[p] for p in required})


def test_economic_exception_is_retained_and_cannot_silently_rerun(monkeypatch,tmp_path):
    c=_config(); run_id=build_run_id(c); plan=RealInputPlan(run_id,c,_snapshot(c),{"output":"out"},(),1,None)
    assembled=AssembledRealInputs((),(),{},(),{"status":"DEEP_INTEGRITY_PASSED"})
    monkeypatch.setattr("bot.forex.stage_a_orchestration.assemble_real_inputs",lambda root,p:assembled)
    monkeypatch.setattr("bot.forex.stage_a_orchestration._compute_real_stage_a",lambda value:(_ for _ in ()).throw(RuntimeError("synthetic defect")))
    auth=_authorization(c)
    with pytest.raises(RuntimeError): execute_real_authorized(tmp_path,plan,{},auth)
    assert (tmp_path/"out"/f"{run_id}.attempt-01.execution-start.json").is_file()
    assert (tmp_path/"out"/f"{run_id}.attempt-01.execution-failure.json").is_file()
