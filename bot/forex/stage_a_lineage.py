"""Persistent non-performance Stage-A lineage and economics boundary controls."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


class LineageError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    h=hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class StageLineageState:
    stage_lineage_id: str
    next_attempt_id: int
    attempts: tuple[Mapping[str,object],...]
    pre_statistics_defects: tuple[Mapping[str,object],...]
    post_statistics_material_defect_count: int
    corrected_economic_execution_used: bool
    performance_verdict: str | None
    economics_boundary: str = "PRE_STATISTICS"


class EconomicsBoundary:
    def __init__(self,state: str = "PRE_STATISTICS"):
        if state not in ("PRE_STATISTICS","ECONOMICS_STARTED"):
            raise LineageError("invalid economics boundary state")
        self.state=state

    def assert_pre_statistics(self) -> None:
        if self.state!="PRE_STATISTICS":
            raise LineageError("ECONOMICS_STARTED is irreversible")

    def start_economics(self) -> None:
        self.assert_pre_statistics()
        self.state="ECONOMICS_STARTED"


def load_lineage_registry(path: Path,root: Path) -> StageLineageState:
    try: raw=json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc: raise LineageError("lineage registry is unreadable") from exc
    if raw.get("schema_version")!=1 or not raw.get("stage_lineage_id"):
        raise LineageError("lineage registry identity mismatch")
    attempts=raw.get("attempts",[]); defects=raw.get("pre_statistics_defects",[])
    ids=[int(x.get("attempt_id",-1)) for x in attempts]
    if ids!=list(range(1,len(ids)+1)) or raw.get("next_attempt_id")!=len(ids)+1:
        raise LineageError("operational attempt history is not monotonic")
    defect_ids=[int(x.get("defect_id",-1)) for x in defects]
    if defect_ids!=list(range(1,len(defect_ids)+1)):
        raise LineageError("pre-statistics defect history is not append-only")
    for attempt in attempts:
        for evidence in attempt.get("evidence",[]):
            evidence_path=Path(root)/str(evidence.get("path",""))
            if not evidence_path.is_file() or _sha(evidence_path)!=evidence.get("sha256"):
                raise LineageError("historical attempt evidence missing or tampered")
    if any(x.get("classification")!="PRE_STATISTICS_INFRA_DEFECT" or
           x.get("reviewer_confirmed") is not True or
           x.get("outcome_independent") is not True or
           x.get("performance_computed") is not False for x in defects):
        raise LineageError("pre-statistics defect qualification mismatch")
    if raw.get("economics_boundary")!="PRE_STATISTICS" or raw.get("performance_verdict") is not None:
        raise LineageError("current lineage must remain pre-statistics with no verdict")
    return StageLineageState(raw["stage_lineage_id"],raw["next_attempt_id"],tuple(attempts),
        tuple(defects),int(raw.get("post_statistics_material_defect_count",-1)),
        bool(raw.get("corrected_economic_execution_used")),raw.get("performance_verdict"),
        raw["economics_boundary"])


class LineageEventStore:
    """Write-once operational events whose filenames survive freeze/run-ID changes."""
    def __init__(self,root: Path,stage_lineage_id: str,initial_attempt_count: int = 1,
                 initial_post_statistics_defect_count: int = 0):
        self.root=Path(root); self.stage_lineage_id=stage_lineage_id
        self.initial_attempt_count=initial_attempt_count
        self.initial_post_statistics_defect_count=initial_post_statistics_defect_count

    def _path(self,attempt: int,event: str) -> Path:
        return self.root/f"{self.stage_lineage_id}.attempt-{attempt:02d}.{event}.json"

    @staticmethod
    def _sealed(value: Mapping[str,object]) -> dict:
        payload=dict(value)
        encoded=(json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=True)+"\n").encode("ascii")
        payload["event_sha256"]=hashlib.sha256(encoded).hexdigest()
        return payload

    def _write_once(self,path: Path,value: Mapping[str,object]) -> Path:
        self.root.mkdir(parents=True,exist_ok=True)
        payload=self._sealed(value)
        encoded=(json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=True)+"\n").encode("ascii")
        try:
            with path.open("xb") as handle: handle.write(encoded)
        except FileExistsError: raise
        return path

    def consume_authorization(self,attempt: int,run_id: str,freeze_manifest_sha256: str,
                              authorization_id: str,identities: Mapping[str,object] | None = None) -> Path:
        existing=list(self.root.glob(f"{self.stage_lineage_id}.attempt-*.authorization-consumed.json")) if self.root.exists() else []
        expected=self.initial_attempt_count+len(existing)+1
        if attempt!=expected:
            raise LineageError("operational attempt IDs may not reset, repeat or skip")
        return self._write_once(self._path(attempt,"authorization-consumed"),{
            "schema_version":1,"stage_lineage_id":self.stage_lineage_id,
            "event":"AUTHORIZATION_CONSUMED","attempt_id":attempt,"run_id":run_id,
            "freeze_manifest_sha256":freeze_manifest_sha256,
            "authorization_id":authorization_id,**dict(identities or {})})

    def start_economics(self,attempt: int,run_id: str,freeze_manifest_sha256: str,
                        corrected_economic_execution: bool = False) -> Path:
        consumed=_read_sealed(self._path(attempt,"authorization-consumed"),self.stage_lineage_id)
        if consumed.get("run_id")!=run_id or consumed.get("freeze_manifest_sha256")!=freeze_manifest_sha256:
            raise LineageError("economics boundary does not match consumed authorization")
        return self._write_once(self._path(attempt,"economics-started"),{
            "schema_version":1,"stage_lineage_id":self.stage_lineage_id,
            "event":"ECONOMICS_STARTED","attempt_id":attempt,"run_id":run_id,
            "freeze_manifest_sha256":freeze_manifest_sha256,
            "corrected_economic_execution":bool(corrected_economic_execution)})

    def record_post_statistics_defect(self,attempt: int,run_id: str,freeze_manifest_sha256: str,
                                      result_path: Path,void_path: Path,root_cause: str) -> Path:
        if not root_cause:
            raise LineageError("post-statistics defect requires an outcome-independent root cause")
        started=_read_sealed(self._path(attempt,"economics-started"),self.stage_lineage_id)
        if started.get("run_id")!=run_id or started.get("freeze_manifest_sha256")!=freeze_manifest_sha256:
            raise LineageError("post-statistics defect lacks matching ECONOMICS_STARTED evidence")
        if not Path(result_path).is_file() or not Path(void_path).is_file():
            raise LineageError("post-statistics defect requires retained result and VOID evidence")
        existing=list(self.root.glob(f"{self.stage_lineage_id}.attempt-*.post-statistics-defect.json"))
        defect_number=self.initial_post_statistics_defect_count+len(existing)+1
        status="VOID_RETAINED"
        return self._write_once(self._path(attempt,"post-statistics-defect"),{
            "schema_version":1,"stage_lineage_id":self.stage_lineage_id,
            "event":"POST_STATISTICS_MATERIAL_DEFECT","attempt_id":attempt,
            "run_id":run_id,"freeze_manifest_sha256":freeze_manifest_sha256,
            "root_cause":root_cause,"defect_number":defect_number,"status":status,
            "result_file":Path(result_path).name,"result_sha256":_sha(result_path),
            "void_file":Path(void_path).name,"void_sha256":_sha(void_path)})

    def record_infrastructure_suspension(self,attempt: int,run_id: str,
                                         freeze_manifest_sha256: str,evidence_path: Path) -> Path:
        consumed=_read_sealed(self._path(attempt,"authorization-consumed"),self.stage_lineage_id)
        if consumed.get("run_id")!=run_id or consumed.get("freeze_manifest_sha256")!=freeze_manifest_sha256:
            raise LineageError("infrastructure suspension lacks matching consumed authorization")
        if not Path(evidence_path).is_file():
            raise LineageError("infrastructure suspension evidence is missing")
        return self._write_once(self._path(attempt,"infrastructure-suspended"),{
            "schema_version":1,"stage_lineage_id":self.stage_lineage_id,
            "event":"INFRA_FAILURE_RETAINED","attempt_id":attempt,"run_id":run_id,
            "freeze_manifest_sha256":freeze_manifest_sha256,
            "evidence_file":Path(evidence_path).name,"evidence_sha256":_sha(evidence_path)})

    def record_execution_failure(self,attempt: int,run_id: str,freeze_manifest_sha256: str,
                                 evidence_path: Path,root_cause: str) -> Path:
        started=_read_sealed(self._path(attempt,"economics-started"),self.stage_lineage_id)
        if started.get("run_id")!=run_id or started.get("freeze_manifest_sha256")!=freeze_manifest_sha256:
            raise LineageError("execution failure lacks matching economics lineage")
        if not Path(evidence_path).is_file(): raise LineageError("execution failure evidence missing")
        return self._write_once(self._path(attempt,"execution-failed-retained"),{
            "schema_version":1,"stage_lineage_id":self.stage_lineage_id,"event":"EXECUTION_FAILED_RETAINED",
            "attempt_id":attempt,"run_id":run_id,"freeze_manifest_sha256":freeze_manifest_sha256,
            "root_cause":root_cause,"evidence_file":Path(evidence_path).name,
            "evidence_sha256":_sha(evidence_path)})

    def record_result_complete(self,attempt: int,run_id: str,freeze_manifest_sha256: str,
                               result_path: Path,disposition: str) -> Path:
        if disposition not in ("SURVIVES_KILL_TEST","CLOSED_FAIL","UNDETERMINED"):
            raise LineageError("invalid completed disposition")
        started=_read_sealed(self._path(attempt,"economics-started"),self.stage_lineage_id)
        if started.get("run_id")!=run_id or started.get("freeze_manifest_sha256")!=freeze_manifest_sha256:
            raise LineageError("completed result lacks matching economics lineage")
        return self._write_once(self._path(attempt,"result-complete"),{
            "schema_version":1,"stage_lineage_id":self.stage_lineage_id,"event":"RESULT_COMPLETE",
            "attempt_id":attempt,"run_id":run_id,"freeze_manifest_sha256":freeze_manifest_sha256,
            "disposition":disposition,"result_file":Path(result_path).name,"result_sha256":_sha(result_path)})


def _read_sealed(path: Path,stage_lineage_id: str) -> dict:
    try: raw=json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc: raise LineageError("stable lineage event is unreadable") from exc
    digest=raw.pop("event_sha256",None)
    encoded=(json.dumps(raw,sort_keys=True,separators=(",",":"),ensure_ascii=True)+"\n").encode("ascii")
    if (raw.get("schema_version")!=1 or raw.get("stage_lineage_id")!=stage_lineage_id or
            digest!=hashlib.sha256(encoded).hexdigest()):
        raise LineageError("stable lineage event is missing or tampered")
    raw["event_sha256"]=digest
    return raw


def resolve_lineage_state(base: StageLineageState,store: LineageEventStore) -> StageLineageState:
    consumed=[]
    if store.root.exists():
        for path in store.root.glob(f"{base.stage_lineage_id}.attempt-*.authorization-consumed.json"):
            consumed.append(_read_sealed(path,base.stage_lineage_id))
    consumed.sort(key=lambda x:int(x["attempt_id"]))
    expected=list(range(base.next_attempt_id,base.next_attempt_id+len(consumed)))
    if [int(x.get("attempt_id",-1)) for x in consumed]!=expected:
        raise LineageError("stable operational attempt overlay is not monotonic")
    starts=[]
    if store.root.exists():
        for path in store.root.glob(f"{base.stage_lineage_id}.attempt-*.economics-started.json"):
            starts.append(_read_sealed(path,base.stage_lineage_id))
    consumed_by_attempt={int(x["attempt_id"]):x for x in consumed}
    for start in starts:
        parent=consumed_by_attempt.get(int(start.get("attempt_id",-1)))
        if parent is None or any(start.get(k)!=parent.get(k) for k in ("run_id","freeze_manifest_sha256")):
            raise LineageError("ECONOMICS_STARTED lacks matching consumed authorization")
    boundary="ECONOMICS_STARTED" if starts else base.economics_boundary
    defects=[]
    if store.root.exists():
        for path in store.root.glob(f"{base.stage_lineage_id}.attempt-*.post-statistics-defect.json"):
            defects.append(_read_sealed(path,base.stage_lineage_id))
    defects.sort(key=lambda x:int(x["defect_number"]))
    expected_defects=list(range(base.post_statistics_material_defect_count+1,
                                base.post_statistics_material_defect_count+len(defects)+1))
    if [int(x.get("defect_number",-1)) for x in defects]!=expected_defects:
        raise LineageError("post-statistics defect history is not monotonic")
    starts_by_attempt={int(x["attempt_id"]):x for x in starts}
    for defect in defects:
        attempt=int(defect.get("attempt_id",-1)); parent=starts_by_attempt.get(attempt)
        if parent is None or any(defect.get(k)!=parent.get(k) for k in ("run_id","freeze_manifest_sha256")):
            raise LineageError("post-statistics defect lacks matching economics lineage")
        for prefix in ("result","void"):
            evidence=store.root/str(defect.get(f"{prefix}_file",""))
            if not evidence.is_file() or _sha(evidence)!=defect.get(f"{prefix}_sha256"):
                raise LineageError("post-statistics defect evidence missing or tampered")
    post_count=base.post_statistics_material_defect_count+len(defects)
    suspensions=[]
    if store.root.exists():
        for path in store.root.glob(f"{base.stage_lineage_id}.attempt-*.infrastructure-suspended.json"):
            suspensions.append(_read_sealed(path,base.stage_lineage_id))
    for suspension in suspensions:
        parent=consumed_by_attempt.get(int(suspension.get("attempt_id",-1)))
        if parent is None or any(suspension.get(k)!=parent.get(k) for k in ("run_id","freeze_manifest_sha256")):
            raise LineageError("infrastructure suspension lacks matching authorization lineage")
        evidence=store.root/str(suspension.get("evidence_file",""))
        if not evidence.is_file() or _sha(evidence)!=suspension.get("evidence_sha256"):
            raise LineageError("infrastructure suspension evidence missing or tampered")
    completions=[]; failures=[]
    for pattern,target in (("result-complete",completions),("execution-failed-retained",failures)):
        paths=store.root.glob(f"{base.stage_lineage_id}.attempt-*.{pattern}.json") if store.root.exists() else ()
        for path in paths:
            event=_read_sealed(path,base.stage_lineage_id); target.append(event)
            parent=starts_by_attempt.get(int(event.get("attempt_id",-1)))
            if parent is None or any(event.get(k)!=parent.get(k) for k in ("run_id","freeze_manifest_sha256")):
                raise LineageError("terminal execution event lacks matching economics lineage")
            evidence=store.root/str(event.get("result_file",event.get("evidence_file","")))
            expected=event.get("result_sha256",event.get("evidence_sha256"))
            if not evidence.is_file() or _sha(evidence)!=expected:
                raise LineageError("terminal execution evidence missing or tampered")
    corrected_used=(base.corrected_economic_execution_used or
                    any(x.get("corrected_economic_execution") is True for x in starts))
    completed_valid=[x for x in completions if not any(int(d.get("attempt_id",-1))==int(x["attempt_id"]) for d in defects)]
    verdict=completed_valid[-1]["disposition"] if completed_valid else base.performance_verdict
    return StageLineageState(base.stage_lineage_id,base.next_attempt_id+len(consumed),
        (*base.attempts,*consumed),base.pre_statistics_defects,
        post_count,corrected_used,verdict,boundary)


def append_pre_statistics_defect(records: Sequence[Mapping[str,object]],new: Mapping[str,object],
                                 *,expected_prefix: Sequence[Mapping[str,object]] | None = None) -> list[dict]:
    current=[dict(x) for x in records]
    if expected_prefix is not None and current!=[dict(x) for x in expected_prefix]:
        raise LineageError("existing defect history may not be rewritten")
    if int(new.get("defect_id",-1))!=len(current)+1:
        raise LineageError("defect IDs must append monotonically")
    return [*current,dict(new)]


def validate_authorization_lineage(authorization: object,state: StageLineageState,
                                   expected_run_id: str,expected_registry_sha256: str | None = None) -> None:
    required=(getattr(authorization,"approved",False) is True,
              getattr(authorization,"run_id",None)==expected_run_id,
              getattr(authorization,"stage_lineage_id",None)==state.stage_lineage_id,
              getattr(authorization,"attempt",None)==state.next_attempt_id,
              getattr(authorization,"pre_statistics_defect_count",None)==len(state.pre_statistics_defects),
              getattr(authorization,"post_statistics_material_defect_count",None)==state.post_statistics_material_defect_count,
              getattr(authorization,"corrected_economic_execution_used",None) is state.corrected_economic_execution_used)
    if expected_registry_sha256 is not None:
        required=(*required,getattr(authorization,"lineage_registry_sha256",None)==expected_registry_sha256)
    if not all(required):
        raise PermissionError("authorization does not match persistent Stage-A lineage")
