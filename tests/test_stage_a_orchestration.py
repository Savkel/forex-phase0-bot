import json
from pathlib import Path

import pytest

from bot.forex.stage_a_orchestration import (
    ArtifactStore, AssembledRealInputs, Authorization, FrozenRunConfig, IntegrityError, RealInputPlan, RunState,
    RunStateMachine, build_run_id, canonical_bytes, execute_synthetic_fixture,
    assemble_real_inputs, execute_real_authorized, record_material_defect, validate_integrity_snapshot,
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
            "active":True,"try_absent":True,"gbp_direct":True,"output_ignored":True,
            "prior_conflicting_run":False}


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
    wrong=Authorization("approval",build_run_id(c)+"x",True,1,c.execution_manifest_sha256)
    with pytest.raises(PermissionError): execute_synthetic_fixture(c,_snapshot(c),wrong,lambda:called.append(True),ArtifactStore(tmp_path))
    assert called==[]


def test_execute_integrity_failure_prevents_evaluator(tmp_path):
    c=_config(); s=_snapshot(c); s["spec_sha256"]="0"*64; called=[]
    auth=Authorization("approval",build_run_id(c),True,1,c.execution_manifest_sha256)
    with pytest.raises(IntegrityError): execute_synthetic_fixture(c,s,auth,lambda:called.append(True),ArtifactStore(tmp_path))
    assert called==[]


def test_integrity_is_immutable_before_synthetic_evaluator(tmp_path):
    c=_config(); store=ArtifactStore(tmp_path); seen=[]
    def evaluator():
        seen.append((tmp_path/f"{build_run_id(c)}.attempt-01.integrity.json").is_file())
        return {"terminal_verdict":"CLOSED_FAIL"}
    auth=Authorization("approval",build_run_id(c),True,1,c.execution_manifest_sha256)
    output=execute_synthetic_fixture(c,_snapshot(c),auth,evaluator,store)
    assert seen==[True] and output.is_file()


def test_output_bytes_are_deterministic_across_fresh_stores(tmp_path):
    a=ArtifactStore(tmp_path/"a").write_result("run",1,{"z":2,"a":1}).read_bytes()
    b=ArtifactStore(tmp_path/"b").write_result("run",1,{"a":1,"z":2}).read_bytes()
    assert a==b


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
        return {"terminal_verdict":"CLOSED_FAIL"}
    monkeypatch.setattr("bot.forex.stage_a_orchestration._compute_real_stage_a",compute)
    auth=Authorization("human",run_id,True,1,c.execution_manifest_sha256)
    result=execute_real_authorized(tmp_path,plan,{"performance_computed":False},auth)
    payload=json.loads(result.read_text())
    assert seen==[True,True]
    assert set(payload["result"]["integrity_artifacts"])=={"metadata","deep"}


def test_real_boundary_preserves_undetermined_suspension(monkeypatch,tmp_path):
    c=_config(); run_id=build_run_id(c); plan=RealInputPlan(run_id,c,_snapshot(c),{"output":"out"},(),1,None)
    assembled=AssembledRealInputs((),(),{},(),{"status":"DEEP_INTEGRITY_PASSED"})
    monkeypatch.setattr("bot.forex.stage_a_orchestration.assemble_real_inputs",lambda root,p:assembled)
    monkeypatch.setattr("bot.forex.stage_a_orchestration._compute_real_stage_a",lambda value:{"terminal_verdict":"UNDETERMINED"})
    auth=Authorization("human",run_id,True,1,c.execution_manifest_sha256)
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


def test_economic_exception_is_retained_and_cannot_silently_rerun(monkeypatch,tmp_path):
    c=_config(); run_id=build_run_id(c); plan=RealInputPlan(run_id,c,_snapshot(c),{"output":"out"},(),1,None)
    assembled=AssembledRealInputs((),(),{},(),{"status":"DEEP_INTEGRITY_PASSED"})
    monkeypatch.setattr("bot.forex.stage_a_orchestration.assemble_real_inputs",lambda root,p:assembled)
    monkeypatch.setattr("bot.forex.stage_a_orchestration._compute_real_stage_a",lambda value:(_ for _ in ()).throw(RuntimeError("synthetic defect")))
    auth=Authorization("human",run_id,True,1,c.execution_manifest_sha256)
    with pytest.raises(RuntimeError): execute_real_authorized(tmp_path,plan,{},auth)
    assert (tmp_path/"out"/f"{run_id}.attempt-01.execution-start.json").is_file()
    assert (tmp_path/"out"/f"{run_id}.attempt-01.execution-failure.json").is_file()
