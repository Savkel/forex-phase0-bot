from __future__ import annotations

import gzip
import json

import pytest

from bot.forex import family6_execution as execution
from bot.forex.family1_universe import _sha256
from bot.forex.family5_breadth import exclusive_json
from bot.forex.stage_a_orchestration import IntegrityError

INFRASTRUCTURE = "1" * 40
EXECUTION_HEAD = "2" * 40
AUTH_CHANGE = (str(execution.AUTHORIZATION_REL).replace(chr(92), "/"),)


def _sources(root):
    for rel in execution.SOURCE_PATHS:
        path = root / rel; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(rel)
    return execution.execution_source_sha256(root)


def _authorization(root, sources, **changes):
    value = {
        "schema_version": 1, "status": "FAMILY6_ECONOMICS_EXECUTION_AUTHORIZED",
        "external_economics_authorized": True, "infrastructure_commit": INFRASTRUCTURE,
        "base_checkpoint_commit": execution.BASE_CHECKPOINT_COMMIT,
        "preregistration_sha256": execution.PREREG_SHA256,
        "readiness_sha256": execution.READINESS_SHA256, "parity_sha256": execution.PARITY_SHA256,
        "execution_source_sha256": sources, "candidate_ids": list(execution.CANDIDATE_ORDER),
        "command": execution.EXECUTION_COMMAND, "consumption_count": 1,
        "estimated_artifact_bytes": execution.ESTIMATED_ARTIFACT_BYTES,
        "minimum_free_bytes": execution.MINIMUM_FREE_BYTES,
        "stage_b_authorized": False, "network_fetch_authorized": False,
    }
    value.update(changes); exclusive_json(root / execution.AUTHORIZATION_REL, value); return value


def _frozen():
    return {"control": {"ic": {"x": 1}}, "benchmark_reuse": {"FULL": {}}, "ic_sha256": "ic"}


def _runner(root, sink, frozen, progress):
    progress.append({"candidate_id": "HURDLE_1X", "case": "FULL"})
    sink.append({"candidate_id": "HURDLE_1X"}, {"value": 1.0})
    return {candidate: {"candidate_disposition": "PENDING_EXTERNAL_ADJUDICATION"}
            for candidate in execution.CANDIDATE_ORDER}


def test_fixed_command_order_and_cli_help(capsys):
    import run_family6_economics as cli
    assert execution.CANDIDATE_ORDER == ("HURDLE_1X", "HURDLE_2X")
    assert execution.EXECUTION_COMMAND == "python -B run_family6_economics.py execute-candidates"
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0 and "execute-candidates" in capsys.readouterr().out


def test_authorization_is_exact_and_prereg_bound(monkeypatch, tmp_path):
    sources = _sources(tmp_path); _authorization(tmp_path, sources)
    ancestry = []
    monkeypatch.setattr(execution, "_is_ancestor",
        lambda root, older, newer: ancestry.append((older, newer)) or True)
    monkeypatch.setattr(execution, "_tracked_changes",
        lambda root, older, newer: AUTH_CHANGE)
    assert execution._validate_authorization(
        tmp_path, head=EXECUTION_HEAD,
        source_hashes=sources)["infrastructure_commit"] == INFRASTRUCTURE
    assert ancestry == [(execution.BASE_CHECKPOINT_COMMIT, INFRASTRUCTURE),
                        (INFRASTRUCTURE, EXECUTION_HEAD)]
    with pytest.raises(IntegrityError, match="stale"):
        execution._validate_authorization(
            tmp_path, head=EXECUTION_HEAD, ancestor=True,
            tracked_changes=AUTH_CHANGE + ("README.md",), source_hashes=sources)
    value = json.loads((tmp_path / execution.AUTHORIZATION_REL).read_text())
    value["candidate_ids"] = list(reversed(value["candidate_ids"]))
    (tmp_path / execution.AUTHORIZATION_REL).write_text(json.dumps(value))
    with pytest.raises(IntegrityError, match="stale"):
        execution._validate_authorization(tmp_path, head=EXECUTION_HEAD, ancestor=True,
            tracked_changes=AUTH_CHANGE, source_hashes=sources)
    with pytest.raises(OSError, match="requires"):
        execution._disk_preflight(tmp_path, execution.MINIMUM_FREE_BYTES - 1)


def test_disk_failure_precedes_consumption_marker(monkeypatch, tmp_path):
    sources = _sources(tmp_path); _authorization(tmp_path, sources)
    monkeypatch.setattr(execution, "_validate_frozen_evidence", lambda root: _frozen())
    with pytest.raises(OSError, match="requires"):
        execution.execute_candidates(tmp_path, runner=lambda *args: pytest.fail("economics entered"),
            free_bytes=execution.MINIMUM_FREE_BYTES - 1, head=EXECUTION_HEAD, ancestor=True,
            tracked_changes=AUTH_CHANGE,
            source_hashes=sources, frozen=_frozen())
    assert not (tmp_path / execution.EXECUTION_REL).exists()


def test_success_emits_hash_bound_artifacts_and_blocks_rerun(monkeypatch, tmp_path):
    sources = _sources(tmp_path); _authorization(tmp_path, sources)
    monkeypatch.setattr(execution, "_validate_frozen_evidence", lambda root: _frozen())
    monkeypatch.setattr(execution, "execution_source_sha256", lambda root: sources)
    result_path = execution.execute_candidates(
        tmp_path, runner=_runner, free_bytes=execution.MINIMUM_FREE_BYTES,
        head=EXECUTION_HEAD, ancestor=True, tracked_changes=AUTH_CHANGE,
        source_hashes=sources, frozen=_frozen())
    result = json.loads(result_path.read_text()); completion = json.loads((tmp_path / execution.COMPLETION_REL).read_text())
    assert result["candidate_order"] == list(execution.CANDIDATE_ORDER)
    assert completion["result_sha256"] == _sha256(result_path)
    assert completion["scientific_consumption_count"] == 1
    with gzip.open(tmp_path / execution._archive_rel(1), "rt") as handle:
        assert json.loads(handle.readline())["identity"]["candidate_id"] == "HURDLE_1X"
    with pytest.raises(PermissionError, match="already exists"):
        execution.execute_candidates(tmp_path, runner=_runner, free_bytes=execution.MINIMUM_FREE_BYTES,
            head=EXECUTION_HEAD, ancestor=True, tracked_changes=AUTH_CHANGE,
            source_hashes=sources, frozen=_frozen())


def test_failure_is_not_completed_and_retry_requires_exact_recovery(monkeypatch, tmp_path):
    sources = _sources(tmp_path); _authorization(tmp_path, sources)
    monkeypatch.setattr(execution, "_validate_frozen_evidence", lambda root: _frozen())
    monkeypatch.setattr(execution, "execution_source_sha256", lambda root: sources)
    def fail(root, sink, frozen, progress):
        progress.append({"candidate_id": "HURDLE_1X", "case": "FULL"}); raise OSError("disk")
    kwargs = dict(free_bytes=execution.MINIMUM_FREE_BYTES, head=EXECUTION_HEAD, ancestor=True,
                  tracked_changes=AUTH_CHANGE, source_hashes=sources, frozen=_frozen())
    with pytest.raises(OSError, match="disk"):
        execution.execute_candidates(tmp_path, runner=fail, **kwargs)
    failure_path = tmp_path / execution._failure_rel(1)
    failure = json.loads(failure_path.read_text())
    assert failure["completed_scientific_one_shot_count"] == 0
    assert not (tmp_path / execution.RESULT_REL).exists() and not (tmp_path / execution.COMPLETION_REL).exists()
    with pytest.raises(PermissionError, match="recovery"):
        execution.execute_candidates(tmp_path, runner=_runner, **kwargs)
    recovery = {
        "schema_version": 1, "status": "FAMILY6_OPERATIONAL_RETRY_AUTHORIZED",
        "external_retry_authorized": True, "retry_attempt": 2, "identical_frozen_execution": True,
        "scientific_changes": False, "candidate_ids": list(execution.CANDIDATE_ORDER),
        "command": execution.EXECUTION_COMMAND, "preregistration_sha256": execution.PREREG_SHA256,
        "readiness_sha256": execution.READINESS_SHA256, "parity_sha256": execution.PARITY_SHA256,
        "execution_source_sha256": sources,
        "original_authorization_sha256": _sha256(tmp_path / execution.AUTHORIZATION_REL),
        "previous_execution_sha256": _sha256(tmp_path / execution._marker_rel(1)),
        "previous_failure_sha256": _sha256(failure_path),
        "previous_archive_sha256": _sha256(tmp_path / execution._archive_rel(1)),
    }
    exclusive_json(tmp_path / execution._recovery_rel(2), recovery)
    execution.execute_candidates(tmp_path, runner=_runner, **kwargs)
    completion = json.loads((tmp_path / execution.COMPLETION_REL).read_text())
    assert completion["operational_attempt_count"] == 2 and completion["scientific_consumption_count"] == 1
