"""Dormant Stage-A real-input orchestration and immutable run governance.

Metadata integrity is safe to run. Economic execution is callable only with a separate,
run-bound human authorization object; the project CLI does not create one in this gate.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Callable, Mapping, Sequence

from bot.forex.stage_a_lineage import (
    EconomicsBoundary, LineageEventStore, StageLineageState, load_lineage_registry,
    resolve_lineage_state,
    validate_authorization_lineage,
)


class IntegrityError(RuntimeError):
    pass


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True)+"\n").encode("ascii")


@dataclass(frozen=True)
class FrozenRunConfig:
    spec_sha256: str
    artifact_sha256: Mapping[str,str]
    implementation_sha256: str
    runtime: Mapping[str,str]
    cache_sha256: Mapping[str,str]
    transaction_map_sha256: str
    financing_sha256: str
    manifest_sha256: str
    stage_lineage_id: str = ""
    lineage_registry_sha256: str = ""
    benchmark_seed: int = 20260809
    benchmark_count: int = 1000
    bootstrap_seed: int = 20260808
    bootstrap_reps: int = 10000
    accounting_scenarios: tuple[str,...] = ("D360","D365")
    gate_definition_version: int = 1
    gate_definition_sha256: str = ""
    execution_manifest_sha256: str = ""

    def canonical(self) -> dict:
        value=asdict(self)
        value["artifact_sha256"]=dict(sorted(self.artifact_sha256.items()))
        value["cache_sha256"]=dict(sorted(self.cache_sha256.items()))
        value["runtime"]=dict(sorted(self.runtime.items()))
        value["accounting_scenarios"]=list(self.accounting_scenarios)
        return value


def build_run_id(config: FrozenRunConfig) -> str:
    return "stage-a-"+hashlib.sha256(canonical_bytes(config.canonical())).hexdigest()


def validate_integrity_snapshot(config: FrozenRunConfig, snapshot: Mapping[str,object]) -> dict:
    expected=config.canonical()
    for key in ("spec_sha256","artifact_sha256","implementation_sha256","runtime",
                "cache_sha256","transaction_map_sha256","financing_sha256","manifest_sha256",
                "stage_lineage_id","lineage_registry_sha256",
                "benchmark_seed","benchmark_count","bootstrap_seed","bootstrap_reps",
                "accounting_scenarios","gate_definition_version","gate_definition_sha256"):
        actual=snapshot.get(key)
        if isinstance(actual,Mapping): actual=dict(sorted(actual.items()))
        if actual!=expected[key]:
            raise IntegrityError(f"frozen integrity mismatch: {key}")
    if snapshot.get("execution_manifest_sha256")!=expected["execution_manifest_sha256"]:
        raise IntegrityError("frozen integrity mismatch: execution_manifest_sha256")
    if len(config.cache_sha256)!=13:
        raise IntegrityError("exactly 13 active price-cache identities are mandatory")
    booleans={"active":True,"try_absent":True,"gbp_direct":True,
              "output_ignored":True,"prior_conflicting_run":False}
    for key,wanted in booleans.items():
        if snapshot.get(key) is not wanted:
            raise IntegrityError(f"frozen integrity mismatch: {key}")
    return {"status":"PREFLIGHT_PASSED","run_id":build_run_id(config),
            "snapshot_sha256":hashlib.sha256(canonical_bytes(snapshot)).hexdigest(),
            "performance_computed":False}


class RunState(Enum):
    PREFLIGHT_PENDING="PREFLIGHT_PENDING"
    PREFLIGHT_PASSED="PREFLIGHT_PASSED"
    READINESS_BLOCKED="READINESS_BLOCKED"
    EXECUTION_AUTHORIZED="EXECUTION_AUTHORIZED"
    EXECUTION_STARTED="EXECUTION_STARTED"
    RESULT_COMPLETE="RESULT_COMPLETE"
    VOID_RETAINED="VOID_RETAINED"
    CORRECTION_AUTHORIZED="CORRECTION_AUTHORIZED"
    CORRECTION_STARTED="CORRECTION_STARTED"
    SUSPENDED_INFRA="SUSPENDED_INFRA"
    UNDETERMINED_SUSPENDED="UNDETERMINED_SUSPENDED"
    RETRY_AUTHORIZED="RETRY_AUTHORIZED"
    RETRY_STARTED="RETRY_STARTED"


@dataclass
class RunStateMachine:
    run_id: str
    state: RunState = RunState.PREFLIGHT_PENDING
    terminal_disposition: str | None = None
    material_defects: int = 0
    history: list[dict] = field(default_factory=list)

    def transition(self,event: str,**details) -> None:
        allowed={
            (RunState.PREFLIGHT_PENDING,"preflight_pass"):RunState.PREFLIGHT_PASSED,
            (RunState.PREFLIGHT_PENDING,"preflight_fail"):RunState.READINESS_BLOCKED,
            (RunState.PREFLIGHT_PASSED,"authorize"):RunState.EXECUTION_AUTHORIZED,
            (RunState.EXECUTION_AUTHORIZED,"start"):RunState.EXECUTION_STARTED,
            (RunState.EXECUTION_AUTHORIZED,"deep_integrity_fail"):RunState.UNDETERMINED_SUSPENDED,
            (RunState.EXECUTION_STARTED,"complete"):RunState.RESULT_COMPLETE,
            (RunState.EXECUTION_STARTED,"undetermined"):RunState.UNDETERMINED_SUSPENDED,
            (RunState.VOID_RETAINED,"authorize_correction"):RunState.CORRECTION_AUTHORIZED,
            (RunState.CORRECTION_AUTHORIZED,"start_correction"):RunState.CORRECTION_STARTED,
            (RunState.CORRECTION_STARTED,"complete"):RunState.RESULT_COMPLETE,
            (RunState.CORRECTION_STARTED,"undetermined"):RunState.UNDETERMINED_SUSPENDED,
            (RunState.UNDETERMINED_SUSPENDED,"authorize_retry"):RunState.RETRY_AUTHORIZED,
            (RunState.RETRY_AUTHORIZED,"start_retry"):RunState.RETRY_STARTED,
            (RunState.RETRY_STARTED,"complete"):RunState.RESULT_COMPLETE,
            (RunState.RETRY_STARTED,"undetermined"):RunState.UNDETERMINED_SUSPENDED,
        }
        target=allowed.get((self.state,event))
        if target is None: raise ValueError(f"invalid Stage-A transition {self.state.value} -> {event}")
        if event=="complete":
            disposition=details.get("disposition")
            if disposition not in ("SURVIVES_KILL_TEST","CLOSED_FAIL","UNDETERMINED"):
                raise ValueError("invalid terminal disposition")
            self.terminal_disposition=disposition
        self.history.append({"from":self.state.value,"event":event,"to":target.value,
                             "details":details})
        self.state=target

    def qualify_material_defect(self,evidence: str,*,reviewer_confirmed: bool,
                                spec_unchanged: bool,performance_independent: bool = True) -> None:
        if self.state not in (RunState.RESULT_COMPLETE,RunState.CORRECTION_STARTED):
            raise ValueError("VOID assessment requires a completed or corrected execution")
        if not evidence or not reviewer_confirmed or not spec_unchanged or not performance_independent:
            raise ValueError("issue does not satisfy the frozen VOID policy")
        self.material_defects+=1
        old=self.state
        self.state=RunState.VOID_RETAINED if self.material_defects==1 else RunState.SUSPENDED_INFRA
        self.history.append({"from":old.value,"event":"material_defect","to":self.state.value,
                             "details":{"evidence":evidence,"defect_number":self.material_defects}})


class ArtifactStore:
    def __init__(self,root: Path):
        self.root=Path(root); self.root.mkdir(parents=True,exist_ok=True)

    def _write_once(self,path: Path,value: object) -> Path:
        path.parent.mkdir(parents=True,exist_ok=True)
        payload=canonical_bytes(value)
        if path.exists():
            if path.read_bytes()==payload: return path
            raise FileExistsError(f"immutable artifact already exists: {path.name}")
        with path.open("xb") as handle: handle.write(payload)
        return path

    def write_integrity(self,run_id: str,value: object,attempt: int = 1) -> Path:
        return self._write_once(self.root/f"{run_id}.attempt-{attempt:02d}.integrity.json",value)

    def write_deep_integrity(self,run_id: str,value: object,attempt: int = 1) -> Path:
        return self._write_once(self.root/f"{run_id}.attempt-{attempt:02d}.deep-integrity.json",value)

    def write_integrity_failure(self,run_id: str,value: object,attempt: int = 1) -> Path:
        suffix=hashlib.sha256(canonical_bytes(value)).hexdigest()[:16]
        return self._write_once(self.root/f"{run_id}.attempt-{attempt:02d}.integrity-failure-{suffix}.json",value)

    def write_execution_start(self,run_id: str,attempt: int,value: object) -> Path:
        path=self.root/f"{run_id}.attempt-{attempt:02d}.execution-start.json"
        if path.exists():
            raise PermissionError("authorization already consumed by this execution attempt")
        return self._write_once(path,value)

    def write_execution_failure(self,run_id: str,attempt: int,value: object) -> Path:
        return self._write_once(self.root/f"{run_id}.attempt-{attempt:02d}.execution-failure.json",value)

    def write_result(self,run_id: str,attempt: int,value: Mapping[str,object]) -> Path:
        reason=value.get("retry_reason")
        if attempt<1 or (attempt>1 and reason not in
                ("PRE_STATISTICS_CORRECTION","UNDETERMINED","VOID_CORRECTION")):
            raise ValueError("result lacks frozen operational-attempt lineage")
        if reason=="VOID_CORRECTION" and not isinstance(value.get("corrects_attempt"),int):
            raise ValueError("corrected economic execution must identify retained original")
        lineage={"corrects_attempt":value.get("corrects_attempt"),
                 "prior_operational_attempt":value.get("prior_operational_attempt") if attempt>1 else None,
                 "retry_reason":reason}
        payload={"schema_version":1,"run_id":run_id,"attempt_id":f"{run_id}-a{attempt:02d}",
                 "lineage":lineage,"result":dict(value)}
        return self._write_once(self.root/f"{run_id}.attempt-{attempt:02d}.result.json",payload)

    def write_void(self,run_id: str,attempt: int,original: Path,evidence: str,
                   qualification: Mapping[str,object] | None = None) -> Path:
        payload={"schema_version":1,"run_id":run_id,"attempt_id":f"{run_id}-a{attempt:02d}",
                 "original_result":original.name,"original_result_sha256":_file_sha256(original),
                 "status":"VOID_RETAINED","evidence":evidence,
                 "qualification":dict(qualification or {})}
        payload["qualification_sha256"]=hashlib.sha256(canonical_bytes(payload["qualification"])).hexdigest()
        return self._write_once(self.root/f"{run_id}.attempt-{attempt:02d}.void.json",payload)

    def write_suspension(self,run_id: str,attempt: int,original: Path,evidence: str) -> Path:
        payload={"schema_version":1,"run_id":run_id,"attempt_id":f"{run_id}-a{attempt:02d}",
                 "original_result":original.name,"status":"SUSPENDED_INFRA",
                 "evidence":evidence,"second_material_defect":True}
        return self._write_once(self.root/f"{run_id}.attempt-{attempt:02d}.suspension.json",payload)


def record_material_defect(store: ArtifactStore,run_id: str,attempt: int,evidence: str,
                           *,reviewer_id: str,reviewer_confirmed: bool,
                           spec_unchanged: bool,performance_independent: bool,
                           why_preflight_missed: str) -> Path:
    """Bind VOID policy checks to immutable original-result retention."""
    if attempt<1 or not reviewer_id:
        raise ValueError("material defect must identify attempt and independent reviewer")
    original=store.root/f"{run_id}.attempt-{attempt:02d}.result.json"
    if not original.is_file(): raise ValueError("original result must be retained before defect disposition")
    prior_defects=0
    if attempt>1:
        retained=json.loads(original.read_text(encoding="utf-8"))
        reason=retained.get("result",{}).get("retry_reason")
        if reason not in ("PRE_STATISTICS_CORRECTION","UNDETERMINED","VOID_CORRECTION"):
            raise ValueError("attempt-2 result lacks frozen retry lineage")
        prior_defects=1 if reason=="VOID_CORRECTION" else 0
    machine=RunStateMachine(run_id,state=RunState.RESULT_COMPLETE,material_defects=prior_defects)
    machine.qualify_material_defect(evidence,reviewer_confirmed=reviewer_confirmed,
                                    spec_unchanged=spec_unchanged,
                                    performance_independent=performance_independent)
    if not why_preflight_missed: raise ValueError("VOID evidence must explain why preflight missed the defect")
    qualification={"reviewer_id":reviewer_id,"reviewer_confirmed":reviewer_confirmed,
                   "spec_unchanged":spec_unchanged,"performance_independent":performance_independent,
                   "why_preflight_missed":why_preflight_missed,
                   "defect_number":machine.material_defects}
    linked=f"reviewer={reviewer_id}; {evidence}"
    if machine.state is RunState.VOID_RETAINED:
        return store.write_void(run_id,attempt,original,linked,qualification)
    return store.write_suspension(run_id,attempt,original,linked)


@dataclass(frozen=True)
class Authorization:
    authorization_id: str
    run_id: str
    approved: bool
    attempt: int = 1
    execution_manifest_sha256: str = ""
    spec_sha256: str = ""
    implementation_sha256: str = ""
    stage_lineage_id: str = ""
    pre_statistics_defect_count: int = 0
    post_statistics_material_defect_count: int = 0
    corrected_economic_execution_used: bool = False
    lineage_registry_sha256: str = ""


def execute_synthetic_fixture(config: FrozenRunConfig, snapshot: Mapping[str,object],
                              authorization: Authorization | None,
                              evaluator: Callable[[],Mapping[str,object]],store: ArtifactStore) -> Path:
    """Integrity-before-statistics boundary. No authorization means evaluator is unreachable."""
    integrity=validate_integrity_snapshot(config,snapshot)
    run_id=build_run_id(config)
    if (authorization is None or not authorization.approved or authorization.run_id!=run_id or
            authorization.execution_manifest_sha256!=config.execution_manifest_sha256 or
            authorization.spec_sha256!=config.spec_sha256 or
            authorization.implementation_sha256!=config.implementation_sha256):
        raise PermissionError("separate human authorization for this exact frozen run is required")
    store.write_integrity(run_id,integrity,authorization.attempt)
    result=evaluator()
    if not isinstance(result,Mapping) or result.get("terminal_verdict") not in (
            "SURVIVES_KILL_TEST","CLOSED_FAIL","UNDETERMINED"):
        raise ValueError("evaluator did not return a frozen terminal disposition")
    return store.write_result(run_id,1,result)


@dataclass(frozen=True)
class RealInputPlan:
    run_id: str
    config: FrozenRunConfig
    snapshot: Mapping[str,object]
    paths: Mapping[str,str]
    transaction_mapping: tuple[tuple[int,int],...]
    attempt: int = 1
    corrects_attempt: int | None = None
    retry_reason: str | None = None
    lineage_state: StageLineageState | None = None

    def output_template(self) -> dict:
        return {"schema_version":1,"run_id":self.run_id,
                "attempt_id":f"{self.run_id}-a{self.attempt:02d}",
                "fingerprints":self.config.canonical(),"integrity_status":"PREFLIGHT_PASSED",
                "scenarios":{"D360":None,"D365":None},"results":None,
                "terminal_disposition":None,
                "lineage":{"stage_lineage_id":self.lineage_state.stage_lineage_id if self.lineage_state else None,
                           "operational_attempt":self.attempt,"prior_operational_attempt":self.attempt-1 if self.attempt>1 else None,
                           "corrects_economic_attempt":self.corrects_attempt,
                           "retry_reason":self.retry_reason,
                           "pre_statistics_defect_count":len(self.lineage_state.pre_statistics_defects) if self.lineage_state else 0,
                           "post_statistics_material_defect_count":self.lineage_state.post_statistics_material_defect_count if self.lineage_state else 0,
                           "corrected_economic_execution_used":self.lineage_state.corrected_economic_execution_used if self.lineage_state else False}}


FROZEN_RUNTIME={"python":"3.11.9","numpy":"1.26.3","pandas":"2.3.0",
                "scipy":"1.11.4","arch":"7.2.0"}
GATE_DEFINITIONS={
    "G1":"RAP strategy exceeds benchmark median under D360 and D365",
    "G2":"one-sided 95% stationary-bootstrap lower bound on mean spot-only Spearman IC > 0",
    "G3":"signed strategy MDD >= benchmark median MDD under D360 and D365",
    "G4":"adverse-corner stressed total return > 0 under D360 and D365",
    "G5":"all 14 LOCO RAP excesses > 0 under D360 and D365",
}
EXECUTION_MANIFEST_PATH="prereg/2026-08-14-tms-carry-stage-a-orchestration-manifest.json"


def _load_and_verify_execution_manifest(root: Path) -> tuple[dict,str]:
    path=root/EXECUTION_MANIFEST_PATH
    if not path.is_file(): raise IntegrityError("committed Stage-A orchestration manifest missing")
    manifest=json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version")!=1: raise IntegrityError("orchestration manifest schema mismatch")
    for relative,expected in manifest.get("source_files",{}).items():
        if _file_sha256(root/relative)!=expected:
            raise IntegrityError(f"orchestration source differs from committed manifest: {relative}")
    gate_hash=hashlib.sha256(canonical_bytes(GATE_DEFINITIONS)).hexdigest()
    if manifest.get("gate_definition_sha256")!=gate_hash:
        raise IntegrityError("gate definitions differ from committed manifest")
    return manifest,hashlib.sha256(canonical_bytes(manifest)).hexdigest()


def _file_sha256(path: Path) -> str:
    digest=hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b""): digest.update(chunk)
    return digest.hexdigest()


def _runtime_fingerprint() -> dict[str,str]:
    import importlib.metadata
    import platform
    return {"python":platform.python_version(),"implementation":platform.python_implementation(),
            "platform":platform.platform(),
            **{name:importlib.metadata.version(name) for name in ("numpy","pandas","scipy","arch")}}


def _cache_paths(root: Path,readiness: Mapping[str,object]) -> dict[str,Path]:
    import pandas as pd
    start=pd.Timestamp(readiness["required_window_utc"][0]).value//10**6
    end=pd.Timestamp(readiness["required_window_utc"][1]).value//10**6
    return {leg["v20_instrument"]:root/"data/forex_ohlcv"/
            f"{leg['v20_instrument']}__H1__BA__a0__w{start}-{end}.csv"
            for leg in readiness["routed_legs"]}


def _transaction_mapping(mask: Mapping[str,object],cache_paths: Mapping[str,Path]) -> tuple[tuple[int,int],...]:
    import bisect
    import pandas as pd
    sets=[]
    for path in cache_paths.values():
        frame=pd.read_csv(path,usecols=["open_time","complete"])
        complete=frame["complete"].astype(str).str.lower().eq("true")
        sets.append(set(frame.loc[complete,"open_time"].astype("int64")))
    common=sorted(set.intersection(*sets))
    targets=sorted({pd.Timestamp(row[key]).value//10**6 for row in mask["evaluable_rebalances"]
                    for key in ("decision_utc","hold_end_utc")})
    mapped=[]
    for target in targets:
        i=bisect.bisect_left(common,target)
        if i==len(common) or common[i]-target>48*3_600_000:
            raise IntegrityError("frozen transaction target lacks first common H1 within 48h")
        mapped.append((int(target),int(common[i])))
    if len(mapped)!=168: raise IntegrityError("exactly 168 transaction mappings are required")
    return tuple(mapped)


def _verify_certified_financing_identity(root: Path,manifest: Mapping[str,object]) -> dict:
    entries=manifest.get("entries",[]); matched=0
    for entry in entries:
        raw=root/"data/tms_swap_archive/raw"/entry["filename"]
        if not raw.is_file() or _file_sha256(raw)!=entry["sha256"]:
            raise IntegrityError(f"certified TMS document mismatch: {entry['filename']}")
        matched+=1
    parser=root/"bot/forex/tms_swap.py"; layout=root/"bot/forex/tms_layout.py"
    if _file_sha256(parser)!=manifest.get("parser_sha256") or _file_sha256(layout)!=manifest.get("layout_parser_sha256"):
        raise IntegrityError("certified parser identity mismatch")
    repro=manifest.get("reproducibility_check",{})
    if repro.get("changed_rate_mappings")!=0 or not manifest.get("pairing_authority"):
        raise IntegrityError("text/layout pairing certification mismatch")
    return {"documents_checked":matched,"parser_sha256":manifest["parser_sha256"],
            "layout_parser_sha256":manifest["layout_parser_sha256"],
            "pairing_cells_compared":repro.get("cells_compared")}


def build_real_input_plan(root: Path) -> tuple[RealInputPlan,dict]:
    """Metadata-only assembly. Never reads candle price fields or financing rates."""
    from bot.forex.stage_a_preflight import FROZEN_SHA256, project_preflight
    root=Path(root); preflight=project_preflight(root)
    paths={
        "spec":"prereg/2026-08-14-tms-carry-no-try-direct-gbp-kill-test-prereg.md",
        "universe":"prereg/2026-08-14-tms-carry-no-try-direct-gbp-universe.json",
        "mask":"prereg/2026-08-14-tms-carry-no-try-direct-gbp-mask.json",
        "readiness":"prereg/2026-08-14-tms-carry-no-try-direct-gbp-price-readiness.json",
        "financing":"data/tms_swap_archive/derived/parsed_all.json",
        "manifest":"provenance/tms_swap_manifest.json",
        "lineage":"prereg/2026-08-14-tms-carry-stage-a-lineage.json",
        "output":"reports/forex/stage_a",
    }
    load=lambda key:json.loads((root/paths[key]).read_text(encoding="utf-8"))
    universe,mask,readiness,manifest=(load(k) for k in ("universe","mask","readiness","manifest"))
    financing_schema=load("financing")
    lineage_base=load_lineage_registry(root/paths["lineage"],root)
    ok_names={x["filename"] for x in manifest["entries"] if x["status"]=="ok"}
    if set(financing_schema)!=ok_names or len(financing_schema)!=manifest["parsed_ok"]:
        raise IntegrityError("parsed financing corpus does not match all certified paired documents")
    if any(set(x)!={"valid_from","valid_to","units","rows"} or not isinstance(x["rows"],dict)
           for x in financing_schema.values()):
        raise IntegrityError("certified financing schema mismatch")
    caches=_cache_paths(root,readiness); mapping=_transaction_mapping(mask,caches)
    execution_manifest,execution_manifest_sha=_load_and_verify_execution_manifest(root)
    runtime=_runtime_fingerprint()
    for name,version in FROZEN_RUNTIME.items():
        if runtime.get(name)!=version: raise IntegrityError(f"result-affecting runtime mismatch: {name}")
    financing_cert=_verify_certified_financing_identity(root,manifest)
    source_paths=("bot/forex/stage_a_carry.py","bot/forex/stage_a_preflight.py",
                  "bot/forex/stage_a_orchestration.py","run_stage_a_carry.py")
    implementation=hashlib.sha256("".join(_file_sha256(root/p) for p in source_paths).encode()).hexdigest()
    if execution_manifest.get("implementation_sha256")!=implementation:
        raise IntegrityError("implementation differs from committed orchestration manifest")
    if execution_manifest.get("runtime")!=runtime:
        raise IntegrityError("runtime differs from committed orchestration manifest")
    config=FrozenRunConfig(
        spec_sha256=FROZEN_SHA256["spec"],
        artifact_sha256={k:FROZEN_SHA256[k] for k in ("universe","mask","readiness")},
        implementation_sha256=implementation,runtime=runtime,
        cache_sha256={leg["v20_instrument"]:leg["sha256"] for leg in readiness["routed_legs"]},
        transaction_map_sha256=hashlib.sha256(canonical_bytes(mapping)).hexdigest(),
        financing_sha256=FROZEN_SHA256["financing"],manifest_sha256=FROZEN_SHA256["manifest"],
        stage_lineage_id=lineage_base.stage_lineage_id,
        lineage_registry_sha256=FROZEN_SHA256["lineage"],
        gate_definition_sha256=hashlib.sha256(canonical_bytes(GATE_DEFINITIONS)).hexdigest(),
        execution_manifest_sha256=execution_manifest_sha)
    expected_freeze={
        "accounting_scenarios":{"D360":{"denominator":360},"D365":{"denominator":365}},
        "active_artifact_sha256":dict(config.artifact_sha256),
        "active_prereg_sha256":config.spec_sha256,
        "benchmark":{"count":config.benchmark_count,"seed":config.benchmark_seed},
        "bootstrap":{"replicates":config.bootstrap_reps,"seed":config.bootstrap_seed},
        "cache_sha256":dict(config.cache_sha256),
        "certified_financing":{"corpus_sha256":config.financing_sha256,
                               "manifest_sha256":config.manifest_sha256},
        "dependency_spec_sha256":_file_sha256(root/"requirements.txt"),
        "stage_lineage":{"stage_lineage_id":config.stage_lineage_id,
                         "registry_sha256":config.lineage_registry_sha256},
        "output_schema_version":1,"price_leg_count":13,"transaction_count":168,
        "transaction_map_sha256":config.transaction_map_sha256,
    }
    if execution_manifest.get("final_freeze")!=expected_freeze:
        raise IntegrityError("final freeze manifest differs from verified active identities")
    output=root/paths["output"]
    lineage=resolve_lineage_state(lineage_base,
        LineageEventStore(output,lineage_base.stage_lineage_id,len(lineage_base.attempts)))
    if lineage.economics_boundary!="PRE_STATISTICS":
        raise IntegrityError("Stage-A economics has started; pre-statistics planning is permanently closed")
    run_id=build_run_id(config); attempt=lineage.next_attempt_id
    corrects=None; retry_reason="PRE_STATISTICS_CORRECTION"
    conflicting=any(output.glob(f"{run_id}.attempt-{attempt:02d}.*")) if output.exists() else False
    snapshot={**config.canonical(),"active":all(x.get("preregistration")==paths["spec"]
                 for x in (universe,mask,readiness)),"try_absent":"TRY" not in universe["currencies"],
              "gbp_direct":universe["routes"]["GBP"]["legs"]==[["GBPUSD.pro",1]] and
                           "EURGBP.pro" not in universe["routing_proof"]["pair_order"],
              "output_ignored":preflight["active"],"prior_conflicting_run":bool(conflicting)}
    integrity=validate_integrity_snapshot(config,snapshot)
    integrity.update({"financing_certification":financing_cert,"transaction_count":len(mapping),
                      "price_leg_count":len(caches),"gate_definitions":GATE_DEFINITIONS,
                      "prose_literals":{"N":universe["N"],"k":universe["k_per_leg"],
                         "gross":universe["target_weight_convention"]["sum_abs_w"],
                         "rebalances_defined":mask["n_rebalances_defined"],
                         "evaluable":mask["n_evaluable"],"excluded":mask["n_excluded"]},
                      "performance_computed":False})
    integrity["lineage"]={"stage_lineage_id":lineage.stage_lineage_id,
        "next_attempt_id":lineage.next_attempt_id,
        "pre_statistics_defect_count":len(lineage.pre_statistics_defects),
        "post_statistics_material_defect_count":lineage.post_statistics_material_defect_count,
        "corrected_economic_execution_used":lineage.corrected_economic_execution_used,
        "economics_boundary":"PRE_STATISTICS"}
    plan=RealInputPlan(run_id,config,snapshot,
                       {**paths,**{f"cache:{k}":str(v.relative_to(root)) for k,v in caches.items()}},
                       mapping,attempt,corrects,retry_reason,lineage)
    return plan,integrity


@dataclass(frozen=True)
class AssembledRealInputs:
    signal_steps: Sequence[object]
    financing_events: Sequence[object]
    routes: Mapping[str,object]
    currencies: tuple[str,...]
    deep_integrity: Mapping[str,object]


def _required_financing_open_days(signal_steps: Sequence[object],
                                  available_by_leg: Mapping[str,set[int]],
                                  routes: Mapping[str,object],
                                  opens_at: Callable[[int,set[str]],Mapping[str,object]]) -> dict:
    """Per-held-leg venue-evidenced 21:00 OPENs; unrelated legs are never required."""
    from datetime import datetime, timezone
    from bot.forex.stage_a_carry import currency_targets, pair_positions
    result={}
    for start,end in zip(signal_steps,signal_steps[1:]):
        if start.scores is None: continue
        held=set(pair_positions(currency_targets(start.scores,4),routes))
        union=set().union(*(available_by_leg[p] for p in held)) if held else set()
        for timestamp in sorted(union):
            instant=datetime.fromtimestamp(timestamp/1000,tz=timezone.utc)
            if not (start.timestamp<=timestamp<end.timestamp and instant.hour==21 and
                    instant.minute==0 and instant.second==0 and instant.weekday()<5): continue
            eligible={p for p in held if timestamp in available_by_leg[p]}
            conversions={"EURUSD.pro"} if any(p.startswith("EUR") and p!="EURUSD.pro"
                                               for p in eligible) else set()
            missing=[p for p in conversions if timestamp not in available_by_leg[p]]
            if missing:
                raise IntegrityError(f"missing required financing conversion OPEN at {timestamp}: {missing[0]}")
            result[instant.date()]=opens_at(timestamp,eligible|conversions)
    return result


def assemble_real_inputs(root: Path,plan: RealInputPlan) -> AssembledRealInputs:
    """Future pre-statistics phase: assemble real inputs and run representation/look-ahead checks."""
    from datetime import date, datetime, timezone
    import pandas as pd
    from bot.forex.stage_a_carry import (
        FinancingSchedule,FrozenDecision,OpenQuote,build_causal_signal_steps,
        build_financing_events,select_signal,
    )
    root=Path(root); read=lambda key:json.loads((root/plan.paths[key]).read_text(encoding="utf-8"))
    universe,mask,readiness,parsed=(read(k) for k in ("universe","mask","readiness","financing"))
    schedules=[]
    for record in parsed.values():
        rates={pair:(float(values[0]),float(values[1])) for pair,values in record["rows"].items()}
        schedules.append(FinancingSchedule(date.fromisoformat(record["valid_from"]),
                                            date.fromisoformat(record["valid_to"]),rates))
    frames={}
    for leg in readiness["routed_legs"]:
        name=leg["v20_instrument"]
        frame=pd.read_csv(root/plan.paths[f"cache:{name}"],
                          usecols=["open_time","complete","bid_o","ask_o"])
        frame=frame[frame["complete"].astype(str).str.lower().eq("true")].set_index("open_time")
        if not frame.index.is_unique: raise IntegrityError(f"duplicate H1 timestamps: {name}")
        frames[name]=frame
    tms_by_v20={x["v20_instrument"]:x["tms_instrument"] for x in readiness["routed_legs"]}
    resolved=dict(plan.transaction_mapping)
    def opens_at(timestamp: int, required: set[str] | None = None) -> dict[str,OpenQuote]:
        result={}
        for name,frame in frames.items():
            tms=tms_by_v20[name]
            if required is not None and tms not in required: continue
            if timestamp not in frame.index: raise IntegrityError(f"missing common OPEN: {name}/{timestamp}")
            row=frame.loc[timestamp]
            result[tms]=OpenQuote(float(row["bid_o"]),float(row["ask_o"]))
        return result
    evaluable={pd.Timestamp(x["decision_utc"]).value//10**6:x for x in mask["evaluable_rebalances"]}
    excluded={pd.Timestamp(x).value//10**6 for x in mask["excluded_rebalances"]}
    decisions=[]; lookahead=0
    for target in sorted(set(evaluable)|excluded):
        execution=resolved[target]; dt=datetime.fromtimestamp(target/1000,tz=timezone.utc)
        is_evaluable=target in evaluable
        if is_evaluable:
            signal=select_signal(schedules,dt)
            if datetime.fromtimestamp(execution/1000,tz=timezone.utc).date()<=signal.valid_to:
                raise IntegrityError("fill is not strictly after complete signal interval")
            lookahead+=1
        decisions.append(FrozenDecision(dt,is_evaluable,[{execution} for _ in frames],
                                        {execution:opens_at(execution)}))
    terminal_target=pd.Timestamp(mask["last_hold_end_utc"]).value//10**6
    terminal_execution=resolved[terminal_target]
    decisions.append(FrozenDecision(datetime.fromtimestamp(terminal_target/1000,tz=timezone.utc),False,
                                    [{terminal_execution} for _ in frames],
                                    {terminal_execution:opens_at(terminal_execution)},terminal=True))
    sub=universe["representation_gate"]["over_identified_subgraph"]["currency_list"]
    signals=build_causal_signal_steps(decisions,schedules,universe["currencies"],
                                      universe["investable_financing_pairs"],sub,k=4)
    availability={tms_by_v20[name]:set(map(int,frame.index)) for name,frame in frames.items()}
    days=_required_financing_open_days(signals,availability,universe["routes"],opens_at)
    events=build_financing_events(signals,schedules,days)
    deep={"status":"DEEP_INTEGRITY_PASSED","run_id":plan.run_id,
          "representation_schedules_checked":sum(x.scores is not None for x in signals),
          "lookahead_assertions":lookahead,"signal_steps":len(signals),
          "financing_events":len(events),"financing_valuation_timestamps":len(days),
          "fill_field":"H1_OPEN_BID_ASK",
          "N":14,"k":4,"currency_gross":2,"try_absent":True,
          "gbp_direct":universe["routes"]["GBP"]["legs"]==[["GBPUSD.pro",1]],
          "performance_computed":False}
    return AssembledRealInputs(signals,events,universe["routes"],tuple(universe["currencies"]),deep)


def _compute_real_stage_a(assembled: AssembledRealInputs) -> Mapping[str,object]:
    """Dormant economic pipeline. Called only after both integrity reports are immutable."""
    from bot.forex.stage_a_carry import (
        accounting_steps_from_signals,evaluate_complete_stage_a,run_adverse_dual_accounting_paths,
        run_dual_accounting_paths,run_full_loco_pipelines,run_spread3_sensitivity_paths,
        run_static_benchmark_paths,spot_ic_series,
    )
    initial_equity=1.0
    steps=accounting_steps_from_signals(assembled.signal_steps,assembled.currencies,k=4)
    strategy=run_dual_accounting_paths(initial_equity,steps,assembled.financing_events,assembled.routes)
    market_steps=[type(step)(step.timestamp,{},step.opens,step.kind) for step in steps]
    benchmarks=run_static_benchmark_paths(initial_equity,market_steps,assembled.financing_events,
                                          assembled.routes,assembled.currencies)
    adverse=run_adverse_dual_accounting_paths(initial_equity,steps,assembled.financing_events,assembled.routes)
    spread3=run_spread3_sensitivity_paths(initial_equity,steps,assembled.financing_events,assembled.routes)
    loco=run_full_loco_pipelines(initial_equity,assembled.signal_steps,assembled.financing_events,
                                 assembled.routes,assembled.currencies)
    ic=spot_ic_series(assembled.signal_steps,assembled.currencies)
    return evaluate_complete_stage_a(initial_equity,strategy,benchmarks,adverse,spread3,loco,ic)


def execute_real_authorized(root: Path,plan: RealInputPlan,metadata_integrity: Mapping[str,object],
                            authorization: Authorization | None) -> Path:
    """One-shot real execution boundary; no authorization means no real values are assembled."""
    validate_integrity_snapshot(plan.config,plan.snapshot)
    if plan.lineage_state is not None:
        validate_authorization_lineage(authorization,plan.lineage_state,plan.run_id,
                                       plan.config.lineage_registry_sha256)
        if authorization.lineage_registry_sha256!=plan.config.lineage_registry_sha256:
            raise PermissionError("authorization lineage registry identity mismatch")
    if (authorization is None or not authorization.approved or authorization.run_id!=plan.run_id or
            authorization.attempt!=plan.attempt or
            authorization.execution_manifest_sha256!=plan.config.execution_manifest_sha256 or
            authorization.spec_sha256!=plan.config.spec_sha256 or
            authorization.implementation_sha256!=plan.config.implementation_sha256):
        raise PermissionError("separate human authorization for this exact frozen run is required")
    store=ArtifactStore(Path(root)/plan.paths["output"])
    lineage_events=None
    if plan.lineage_state is not None:
        lineage_base=load_lineage_registry(Path(root)/plan.paths["lineage"],Path(root))
        lineage_events=LineageEventStore(store.root,plan.lineage_state.stage_lineage_id,
                                         len(lineage_base.attempts))
    if lineage_events is not None:
        lineage_events.consume_authorization(plan.attempt,plan.run_id,
            plan.config.execution_manifest_sha256,authorization.authorization_id,{
                "spec_sha256":authorization.spec_sha256,
                "implementation_sha256":authorization.implementation_sha256,
                "lineage_registry_sha256":authorization.lineage_registry_sha256,
                "pre_statistics_defect_count":authorization.pre_statistics_defect_count,
                "post_statistics_material_defect_count":authorization.post_statistics_material_defect_count,
                "corrected_economic_execution_used":authorization.corrected_economic_execution_used})
    state=RunStateMachine(plan.run_id); state.transition("preflight_pass")
    if plan.retry_reason=="PRE_STATISTICS_CORRECTION":
        state.transition("authorize")
    elif plan.attempt==1:
        state.transition("authorize")
    elif plan.retry_reason=="UNDETERMINED":
        state.state=RunState.UNDETERMINED_SUSPENDED
        state.transition("authorize_retry")
    else:
        state.state=RunState.VOID_RETAINED; state.material_defects=1
        state.transition("authorize_correction")
    metadata_path=store.write_integrity(plan.run_id,metadata_integrity,plan.attempt)
    try:
        assembled=assemble_real_inputs(root,plan)
    except (IntegrityError,ValueError,KeyError) as exc:
        if plan.attempt==1 or plan.retry_reason=="PRE_STATISTICS_CORRECTION":
            state.transition("deep_integrity_fail",reason=str(exc))
        elif plan.retry_reason=="UNDETERMINED": state.state=RunState.UNDETERMINED_SUSPENDED
        else: state.state=RunState.SUSPENDED_INFRA
        store.write_integrity_failure(plan.run_id,{"status":state.state.value,
                                      "reason":str(exc),"performance_computed":False,
                                      "state_history":state.history},plan.attempt)
        raise IntegrityError(str(exc)) from exc
    deep_path=store.write_deep_integrity(plan.run_id,assembled.deep_integrity,plan.attempt)
    state.transition("start" if plan.attempt==1 or plan.retry_reason=="PRE_STATISTICS_CORRECTION" else
                     "start_retry" if plan.retry_reason=="UNDETERMINED" else "start_correction")
    boundary=EconomicsBoundary()
    boundary.start_economics()
    if lineage_events is not None:
        lineage_events.start_economics(plan.attempt,plan.run_id,
                                       plan.config.execution_manifest_sha256)
    store.write_execution_start(plan.run_id,plan.attempt,{"status":"EXECUTION_STARTED",
        "economics_boundary":boundary.state,
        "run_id":plan.run_id,"attempt":plan.attempt,"authorization_id":authorization.authorization_id,
        "stage_lineage_id":authorization.stage_lineage_id,
        "metadata_integrity_sha256":_file_sha256(metadata_path),
        "deep_integrity_sha256":_file_sha256(deep_path)})
    try:
        result=_compute_real_stage_a(assembled)
    except Exception as exc:
        store.write_execution_failure(plan.run_id,plan.attempt,{"status":"EXECUTION_FAILED_RETAINED",
            "run_id":plan.run_id,"attempt":plan.attempt,"exception_type":type(exc).__name__,
            "message":str(exc),"requires_governed_material_defect_review":True})
        raise
    if result["terminal_verdict"]=="UNDETERMINED":
        state.transition("undetermined",reason="frozen inference could not determine G2")
    else:
        state.transition("complete",disposition=result["terminal_verdict"])
    payload={**plan.output_template(),
             "integrity_status":"DEEP_INTEGRITY_PASSED","results":dict(result),
             "terminal_disposition":result["terminal_verdict"],"state_history":state.history,
             "integrity_artifacts":{
                 "metadata":{"file":metadata_path.name,"sha256":_file_sha256(metadata_path)},
                 "deep":{"file":deep_path.name,"sha256":_file_sha256(deep_path)}}}
    if plan.attempt>1:
        payload["prior_operational_attempt"]=plan.attempt-1
    if plan.corrects_attempt is not None:
        payload["corrects_attempt"]=plan.corrects_attempt
    if plan.retry_reason:
        payload["retry_reason"]=plan.retry_reason
    return store.write_result(plan.run_id,plan.attempt,payload)
