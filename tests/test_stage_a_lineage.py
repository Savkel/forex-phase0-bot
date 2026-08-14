import json
from pathlib import Path

import pytest

from bot.forex.stage_a_lineage import (
    EconomicsBoundary, LineageError, append_pre_statistics_defect,
    LineageEventStore, load_lineage_registry, resolve_lineage_state,
    validate_authorization_lineage,
)
from bot.forex.stage_a_orchestration import Authorization
from bot.forex.stage_a_orchestration import ArtifactStore, record_material_defect


def _registry_path() -> Path:
    return Path(__file__).resolve().parents[1] / "prereg/2026-08-14-tms-carry-stage-a-lineage.json"


def test_current_registry_inherits_attempt_one_across_new_run_and_freeze():
    state=load_lineage_registry(_registry_path(),Path(__file__).resolve().parents[1])
    assert state.stage_lineage_id=="stage-a-tms-pro-carry-development-v1"
    assert state.next_attempt_id==2
    assert state.attempts[0]["attempt_id"]==1
    assert state.attempts[0]["authorization_consumed"] is True
    assert state.attempts[0]["economics_started"] is False
    assert state.attempts[0]["run_id"]!="new-run-id"
    assert len(state.pre_statistics_defects)==2
    assert state.post_statistics_material_defect_count==0
    assert state.corrected_economic_execution_used is False


def test_registry_missing_or_tampered_evidence_fails_closed(tmp_path):
    root=Path(__file__).resolve().parents[1]
    raw=json.loads(_registry_path().read_text())
    raw["attempts"][0]["evidence"][0]["sha256"]="0"*64
    path=tmp_path/"lineage.json"; path.write_text(json.dumps(raw))
    with pytest.raises(LineageError,match="evidence"):
        load_lineage_registry(path,root)


def test_defect_history_is_append_only():
    state=load_lineage_registry(_registry_path(),Path(__file__).resolve().parents[1])
    old=[dict(x) for x in state.pre_statistics_defects]
    new={"defect_id":3,"classification":"PRE_STATISTICS_INFRA_DEFECT",
         "root_cause":"synthetic","reviewer_confirmed":True,
         "outcome_independent":True,"performance_computed":False}
    updated=append_pre_statistics_defect(old,new)
    assert updated[:2]==old and updated[-1]["defect_id"]==3
    with pytest.raises(LineageError):
        append_pre_statistics_defect([dict(old[0],root_cause="changed"),old[1]],new,
                                     expected_prefix=old)


def test_economics_boundary_is_irreversible_and_preflight_safe():
    boundary=EconomicsBoundary()
    boundary.assert_pre_statistics()
    assert boundary.state=="PRE_STATISTICS"
    boundary.start_economics()
    assert boundary.state=="ECONOMICS_STARTED"
    with pytest.raises(LineageError): boundary.start_economics()
    with pytest.raises(LineageError): boundary.assert_pre_statistics()


def test_metadata_preflight_reports_boundary_without_crossing_it():
    from bot.forex.stage_a_preflight import project_preflight
    report=project_preflight(Path(__file__).resolve().parents[1])
    assert report["performance_computed"] is False
    assert report["execution_eligible"] is False
    assert report["lineage"]["economics_boundary"]=="PRE_STATISTICS"


def test_authorization_requires_lineage_attempt_and_separate_counters():
    state=load_lineage_registry(_registry_path(),Path(__file__).resolve().parents[1])
    base=dict(authorization_id="future",run_id="new-run",approved=True,attempt=2,
              execution_manifest_sha256="a"*64,spec_sha256="b"*64,
              implementation_sha256="c"*64,stage_lineage_id=state.stage_lineage_id,
              pre_statistics_defect_count=2,post_statistics_material_defect_count=0,
              corrected_economic_execution_used=False)
    base["lineage_registry_sha256"]="d"*64
    auth=Authorization(**base)
    validate_authorization_lineage(auth,state,"new-run","d"*64)
    for update in ({"attempt":1},{"stage_lineage_id":"wrong"},
                   {"pre_statistics_defect_count":1},
                   {"post_statistics_material_defect_count":1},
                   {"corrected_economic_execution_used":True}):
        with pytest.raises(PermissionError):
            validate_authorization_lineage(Authorization(**{**base,**update}),state,"new-run","d"*64)
    with pytest.raises(PermissionError):
        validate_authorization_lineage(Authorization(**{**base,"lineage_registry_sha256":"0"*64}),
                                       state,"new-run","d"*64)


def test_consumed_attempt_one_authorization_is_rejected_for_new_freeze():
    state=load_lineage_registry(_registry_path(),Path(__file__).resolve().parents[1])
    old=Authorization("old","stage-a-new",True,1,"a"*64,"b"*64,"c"*64,
                      state.stage_lineage_id,2,0,False,"d"*64)
    with pytest.raises(PermissionError):
        validate_authorization_lineage(old,state,"stage-a-new")


def test_pre_statistics_attempt_does_not_add_post_statistics_allowance(tmp_path):
    store=ArtifactStore(tmp_path)
    store.write_result("new-run",2,{"prior_operational_attempt":1,
        "retry_reason":"PRE_STATISTICS_CORRECTION","terminal_disposition":"CLOSED_FAIL"})
    first=record_material_defect(store,"new-run",2,"post-stat defect one",reviewer_id="r1",
        reviewer_confirmed=True,spec_unchanged=True,performance_independent=True,
        why_preflight_missed="arose only after economics began")
    assert json.loads(first.read_text())["qualification"]["defect_number"]==1
    store.write_result("new-run",3,{"prior_operational_attempt":2,"corrects_attempt":2,
        "retry_reason":"VOID_CORRECTION","terminal_disposition":"CLOSED_FAIL"})
    second=record_material_defect(store,"new-run",3,"post-stat defect two",reviewer_id="r2",
        reviewer_confirmed=True,spec_unchanged=True,performance_independent=True,
        why_preflight_missed="arose only after corrected economics began")
    assert json.loads(second.read_text())["status"]=="SUSPENDED_INFRA"


def test_stable_lineage_overlay_advances_attempt_across_new_run_ids(tmp_path):
    base=load_lineage_registry(_registry_path(),Path(__file__).resolve().parents[1])
    store=LineageEventStore(tmp_path,base.stage_lineage_id)
    store.consume_authorization(2,"run-a","freeze-a","auth-a")
    after=resolve_lineage_state(base,store)
    assert after.next_attempt_id==3
    assert after.economics_boundary=="PRE_STATISTICS"
    with pytest.raises(LineageError):
        store.consume_authorization(2,"run-b","freeze-b","auth-b")
    store.start_economics(2,"run-a","freeze-a")
    after_start=resolve_lineage_state(base,store)
    assert after_start.next_attempt_id==3
    assert after_start.economics_boundary=="ECONOMICS_STARTED"


def test_stable_lineage_overlay_rejects_gap_and_tamper(tmp_path):
    base=load_lineage_registry(_registry_path(),Path(__file__).resolve().parents[1])
    store=LineageEventStore(tmp_path,base.stage_lineage_id)
    with pytest.raises(LineageError): store.consume_authorization(3,"run","freeze","auth")
    store.consume_authorization(2,"run","freeze","auth")
    marker=next(tmp_path.glob("*.authorization-consumed.json"))
    raw=json.loads(marker.read_text()); raw["run_id"]="tampered"; marker.write_text(json.dumps(raw))
    with pytest.raises(LineageError): resolve_lineage_state(base,store)


def test_new_freeze_manifest_binds_current_lineage_and_financing_readiness():
    root=Path(__file__).resolve().parents[1]
    manifest=json.loads((root/"prereg/2026-08-14-tms-carry-stage-a-orchestration-manifest.json").read_text())
    meta=manifest["freeze_metadata"]
    assert meta["old_freeze_execution_eligible"] is False
    assert meta["financing_readiness"]["records_sha256"]=="7e93e702816833ba5ed2de7432c1476af576186fb52da462de2e4c48a3f26dbf"
    assert meta["financing_readiness"]["actual_venue_evidenced_held_pair_events"]==5211
    assert meta["financing_readiness"]["closed_market_no_event_records"]==911
    assert meta["lineage"]["next_operational_attempt"]==2
    assert meta["lineage"]["pre_statistics_infra_defect_count"]==2
    assert meta["lineage"]["post_statistics_material_defect_count"]==0
    assert meta["lineage"]["corrected_economic_execution_used"] is False
