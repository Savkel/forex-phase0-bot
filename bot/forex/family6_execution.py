"""Separately authorized, one-shot Family-6 non-control economics."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import shutil
import subprocess

from bot.forex.family1_study import ADJUDICATION_POLICY, _scenario_paths, path_diagnostics
from bot.forex.family1_universe import U14, _canonical_sha, _json, _sha256, load_frozen_context, prepare_candidate
from bot.forex.family2_hysteresis import _concentration, _difference, _rotation_diagnostics
from bot.forex.family3_weighting import weight_turnover_diagnostics
from bot.forex.family4_cadence import _accounting_view, cadence_diagnostics
from bot.forex.family5_breadth import exclusive_json
from bot.forex.family5_study import PathArchive, _payload
from bot.forex.family6_hurdle import (
    F5_CONTROL, F5_HASHES, PARITY_REL, PREREG_REL, PREREG_SHA256, READINESS_REL,
    SCENARIOS, STEM, HurdleConfig, _f5_reuse, causal_schedules,
    hurdle_accounting_steps, offline,
)
from bot.forex.stage_a_carry import currency_usd_values
from bot.forex.stage_a_orchestration import IntegrityError

BASE_CHECKPOINT_COMMIT = "e79facfb3a6ca3ac208382cfd5752935a7eaee66"
READINESS_SHA256 = "2494984371ff670cb91da8104b84d2675a8145dea3247b6188673fd23822a3cf"
PARITY_SHA256 = "49e25dab4d3ae254da75f8755271baa58190c5c46fcf2a02f18d27de3fb65d38"
CANDIDATE_ORDER = ("HURDLE_1X", "HURDLE_2X")
EXECUTION_COMMAND = "python -B run_family6_economics.py execute-candidates"
ESTIMATED_ARTIFACT_BYTES = 500_000_000
MINIMUM_FREE_BYTES = 2_000_000_000
REPORT_DIR = Path("reports/forex/family6")
AUTHORIZATION_REL = Path("prereg") / (STEM + "-execution-authorization.json")
EXECUTION_REL = Path("prereg") / (STEM + "-execution.json")
RESULT_REL = REPORT_DIR / "family6-carry-cost-hurdle-result.json"
COMPLETION_REL = REPORT_DIR / "family6-carry-cost-hurdle-completion.json"
SOURCE_PATHS = (
    "bot/forex/family6_execution.py", "run_family6_economics.py",
    "tests/test_family6_execution.py",
)


def _rel(value):
    return str(value).replace(chr(92), "/")


def _marker_rel(attempt):
    return EXECUTION_REL if attempt == 1 else Path("prereg") / (STEM + f"-execution-attempt-{attempt}.json")


def _archive_rel(attempt):
    return REPORT_DIR / f"family6-candidate-paths-attempt-{attempt}.jsonl.gz"


def _failure_rel(attempt):
    return REPORT_DIR / f"family6-execution-attempt-{attempt}-failure.json"


def _recovery_rel(attempt):
    return Path("prereg") / (STEM + f"-execution-attempt-{attempt}-recovery-authorization.json")


def execution_source_sha256(root):
    root = Path(root)
    missing = [rel for rel in SOURCE_PATHS if not (root / rel).is_file()]
    if missing:
        raise IntegrityError("Family-6 execution source missing: " + ", ".join(missing))
    return {rel: _sha256(root / rel) for rel in SOURCE_PATHS}


def _git_head(root):
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True,
    ).stdout.strip()


def _is_ancestor(root, older, newer):
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", older, newer], cwd=root,
        check=False, capture_output=True,
    ).returncode == 0


def _tracked_changes(root, older, newer):
    output = subprocess.run(
        ["git", "diff", "--name-only", f"{older}..{newer}", "--"], cwd=root,
        check=True, capture_output=True, text=True,
    ).stdout
    return tuple(line.strip() for line in output.splitlines() if line.strip())


def _validate_frozen_evidence(root):
    root = Path(root)
    expected = {
        PREREG_REL: PREREG_SHA256, READINESS_REL: READINESS_SHA256,
        PARITY_REL: PARITY_SHA256, F5_CONTROL: F5_HASHES[str(F5_CONTROL)],
    }
    for rel, digest in expected.items():
        if not (root / rel).is_file() or _sha256(root / rel) != digest:
            raise IntegrityError("frozen evidence changed: " + _rel(rel))
    readiness, parity = _json(root / READINESS_REL), _json(root / PARITY_REL)
    if readiness.get("status") != "FAMILY6_READINESS_PASSED":
        raise IntegrityError("Family-6 readiness is not valid")
    if parity.get("status") != "FAMILY6_CONTROL_PARITY_PASSED" or parity.get("parity", {}).get("mismatch_count") != 0:
        raise IntegrityError("Family-6 CONTROL parity is not valid")
    f5_ready, f5_parity, control, ic_sha, case_hashes = _f5_reuse(root)
    return {
        "readiness": readiness, "parity": parity, "family5_readiness": f5_ready,
        "family5_parity": f5_parity, "control": control, "ic_sha256": ic_sha,
        "benchmark_reuse": case_hashes,
    }


def _validate_authorization(root, *, head=None, ancestor=None, tracked_changes=None,
                            source_hashes=None):
    root = Path(root); path = root / AUTHORIZATION_REL
    if not path.is_file():
        raise PermissionError("prereg-bound external economics authorization required")
    value = _json(path)
    required = {
        "schema_version", "status", "external_economics_authorized", "infrastructure_commit",
        "base_checkpoint_commit", "preregistration_sha256", "readiness_sha256", "parity_sha256",
        "execution_source_sha256", "candidate_ids", "command", "consumption_count",
        "estimated_artifact_bytes", "minimum_free_bytes", "stage_b_authorized",
        "network_fetch_authorized",
    }
    if set(value) != required or value.get("schema_version") != 1:
        raise PermissionError("invalid Family-6 execution authorization schema")
    if value.get("status") != "FAMILY6_ECONOMICS_EXECUTION_AUTHORIZED" or value.get("external_economics_authorized") is not True:
        raise PermissionError("Family-6 economics is not explicitly authorized")
    head = head or _git_head(root)
    infrastructure = value.get("infrastructure_commit")
    valid_commit = (isinstance(infrastructure, str) and len(infrastructure) == 40
                    and all(c in "0123456789abcdef" for c in infrastructure))
    ancestor = (_is_ancestor(root, BASE_CHECKPOINT_COMMIT, infrastructure)
                and _is_ancestor(root, infrastructure, head)) if ancestor is None and valid_commit else ancestor
    tracked_changes = (_tracked_changes(root, infrastructure, head)
                       if tracked_changes is None and valid_commit else tracked_changes)
    source_hashes = source_hashes or execution_source_sha256(root)
    expected = {
        "base_checkpoint_commit": BASE_CHECKPOINT_COMMIT,
        "preregistration_sha256": PREREG_SHA256, "readiness_sha256": READINESS_SHA256,
        "parity_sha256": PARITY_SHA256, "execution_source_sha256": source_hashes,
        "candidate_ids": list(CANDIDATE_ORDER), "command": EXECUTION_COMMAND,
        "consumption_count": 1, "estimated_artifact_bytes": ESTIMATED_ARTIFACT_BYTES,
        "minimum_free_bytes": MINIMUM_FREE_BYTES, "stage_b_authorized": False,
        "network_fetch_authorized": False,
    }
    if (not valid_commit or not ancestor or tuple(tracked_changes or ()) != (_rel(AUTHORIZATION_REL),)
            or any(value.get(key) != expected_value for key, expected_value in expected.items())):
        raise IntegrityError("execution authorization is stale or differs from the frozen execution")
    return value


def _validate_recovery(root, attempt, authorization_sha, source_hashes):
    root = Path(root); path = root / _recovery_rel(attempt)
    if not path.is_file():
        raise PermissionError("external identical-execution recovery authorization required")
    previous = attempt - 1
    marker, failure, archive = (root / _marker_rel(previous), root / _failure_rel(previous), root / _archive_rel(previous))
    value = _json(path)
    required = {
        "schema_version", "status", "external_retry_authorized", "retry_attempt",
        "identical_frozen_execution", "scientific_changes", "candidate_ids", "command",
        "preregistration_sha256", "readiness_sha256", "parity_sha256",
        "execution_source_sha256", "original_authorization_sha256",
        "previous_execution_sha256", "previous_failure_sha256", "previous_archive_sha256",
    }
    if set(value) != required or value.get("schema_version") != 1:
        raise PermissionError("invalid recovery authorization schema")
    expected = {
        "status": "FAMILY6_OPERATIONAL_RETRY_AUTHORIZED", "external_retry_authorized": True,
        "retry_attempt": attempt, "identical_frozen_execution": True, "scientific_changes": False,
        "candidate_ids": list(CANDIDATE_ORDER), "command": EXECUTION_COMMAND,
        "preregistration_sha256": PREREG_SHA256, "readiness_sha256": READINESS_SHA256,
        "parity_sha256": PARITY_SHA256, "execution_source_sha256": source_hashes,
        "original_authorization_sha256": authorization_sha,
        "previous_execution_sha256": _sha256(marker), "previous_failure_sha256": _sha256(failure),
        "previous_archive_sha256": _sha256(archive) if archive.is_file() else None,
    }
    if any(value.get(key) != expected_value for key, expected_value in expected.items()):
        raise IntegrityError("recovery authorization does not bind the identical failed execution")
    return value


def _next_attempt(root, authorization_sha, source_hashes):
    root = Path(root)
    if (root / RESULT_REL).exists() or (root / COMPLETION_REL).exists():
        raise PermissionError("Family-6 economics result/completion already exists")
    attempt = 1
    while (root / _marker_rel(attempt)).exists():
        if not (root / _failure_rel(attempt)).is_file():
            raise PermissionError("started attempt lacks a documented failure artifact")
        attempt += 1
    for rel in (_failure_rel(attempt), _archive_rel(attempt), _marker_rel(attempt)):
        if (root / rel).exists():
            raise PermissionError("orphan/current-attempt artifact blocks execution")
    recovery = None
    if attempt > 1:
        recovery = _validate_recovery(root, attempt, authorization_sha, source_hashes)
    return attempt, recovery


def _disk_preflight(root, free_bytes=None):
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(root).free if free_bytes is None else int(free_bytes)
    if free < MINIMUM_FREE_BYTES:
        raise OSError(f"Family-6 requires {MINIMUM_FREE_BYTES} free bytes; found {free}")
    return free


def _scenario_summary(paths, inputs, sink, identity, values):
    result = {}
    for scenario in SCENARIOS:
        result[scenario] = {}
        for denominator in (360, 365):
            payload = _payload(paths[scenario][denominator], inputs, scenario, *values)
            sink.append({**identity, "scenario": scenario, "denominator": denominator}, payload)
            result[scenario][str(denominator)] = {key: payload[key] for key in
                ("total_return", "cagr", "calmar", "rap", "max_drawdown", "blocks")}
    return result


def _hurdle_diagnostics(records):
    counts = Counter(record["decision"] for record in records)
    applied = [record for record in records if record["hurdle_applied"]]
    return {
        "decision_counts": dict(sorted(counts.items())), "hurdle_evaluation_count": len(applied),
        "records_sha256": _canonical_sha(records), "records": list(records),
    }


def _candidate_study(inputs, schedules, candidate_id, control, case_hashes, sink, progress):
    values = ([currency_usd_values(s.opens) for s in inputs.signal_steps],
              [currency_usd_values(e.opens) for e in inputs.financing_events])
    cases = {}
    for omitted in (None, *U14.currencies):
        key = omitted or "FULL"
        steps, records = hurdle_accounting_steps(
            inputs.signal_steps, schedules, inputs.financing_events, inputs.routes,
            HurdleConfig(candidate_id), omitted=omitted,
        )
        paths = _scenario_paths(_accounting_view(steps), inputs.financing_events, inputs.routes)
        scenarios = _scenario_summary(paths, inputs, sink,
            {"role": "strategy", "candidate_id": candidate_id, "omitted": omitted}, values)
        frozen = control if omitted is None else control["loco"][omitted]
        denominators = {}
        for denominator in (360, 365):
            d = str(denominator); base = path_diagnostics(
                paths["base"][denominator], inputs.signal_steps, inputs.financing_events, inputs.routes)
            old = frozen["denominators"][d]
            cell = {"base": base, "adverse_total_return": paths["adverse"][denominator].equities[-1] - 1,
                    "spread_x3_total_return": paths["spread_x3"][denominator].equities[-1] - 1}
            if omitted is None:
                cell.update(benchmark=old["benchmark"],
                    benchmark_rap_excess=base["rap"] - old["benchmark"]["rap"],
                    benchmark_mdd_difference=base["max_drawdown"] - old["benchmark"]["max_drawdown"])
            else:
                for name in ("benchmark_rap", "benchmark_max_drawdown", "benchmark_adverse_total_return",
                             "benchmark_spread_x3_total_return", "benchmark_blocks"):
                    cell[name] = old[name]
                cell["benchmark_rap_excess"] = base["rap"] - old["benchmark_rap"]
            denominators[d] = cell
        view = _accounting_view(steps); h2_records = tuple(r["h2"] for r in records)
        case = {
            "N": 14 if omitted is None else 13, "k": 4,
            "benchmark_economics_reused": True, "benchmark_reuse": case_hashes[key],
            "concentration": _concentration(view), "rotation": _rotation_diagnostics(h2_records),
            "weight_turnover": weight_turnover_diagnostics(view, inputs.signal_steps),
            "cadence": cadence_diagnostics(steps, h2_records),
            "hurdle": _hurdle_diagnostics(records), "denominators": denominators,
            "scenarios": scenarios,
        }
        cases[key] = case; progress.append({"candidate_id": candidate_id, "case": key})
    full = cases.pop("FULL")
    return {**full, "configuration_id": candidate_id, "m": 1, "base_configuration": "EQ_H2",
        "h": 2, "currencies": list(U14.currencies), "currency_gross": 2,
        "benchmark_book_count": 1000, "benchmark_control_reference": _rel(F5_CONTROL),
        "ic": control["ic"], "ic_reused": True, "D365_MINUS_D360": _difference(full["denominators"]),
        "loco": cases, "candidate_disposition": "PENDING_EXTERNAL_ADJUDICATION"}


def _run_economics(root, sink, frozen, progress):
    context = load_frozen_context(root); inputs = prepare_candidate(context, U14)
    schedules = causal_schedules(context)
    return {candidate_id: _candidate_study(
        inputs, schedules, candidate_id, frozen["control"], frozen["benchmark_reuse"], sink, progress,
    ) for candidate_id in CANDIDATE_ORDER}


def execute_candidates(root, *, runner=None, free_bytes=None, head=None, ancestor=None,
                       tracked_changes=None, source_hashes=None, frozen=None):
    root = Path(root); production_runner = runner is None; runner = runner or _run_economics
    with offline():
        source_hashes = source_hashes or execution_source_sha256(root)
        _validate_authorization(root, head=head, ancestor=ancestor,
                                tracked_changes=tracked_changes, source_hashes=source_hashes)
        authorization_sha = _sha256(root / AUTHORIZATION_REL)
        frozen = frozen or _validate_frozen_evidence(root)
        free = _disk_preflight(root / REPORT_DIR, free_bytes)
        attempt, recovery = _next_attempt(root, authorization_sha, source_hashes)
        marker_rel, archive_rel = _marker_rel(attempt), _archive_rel(attempt)
        marker = {
            "schema_version": 1, "status": "ECONOMICS_STARTED", "operational_attempt": attempt,
            "scientific_consumption_count": 1, "candidate_ids": list(CANDIDATE_ORDER),
            "command": EXECUTION_COMMAND, "authorization_sha256": authorization_sha,
            "recovery_authorization_sha256": (_sha256(root / _recovery_rel(attempt)) if recovery else None),
            "preregistration_sha256": PREREG_SHA256, "readiness_sha256": READINESS_SHA256,
            "parity_sha256": PARITY_SHA256, "execution_source_sha256": source_hashes,
            "minimum_free_bytes": MINIMUM_FREE_BYTES, "observed_free_bytes": free,
            "network_accessed": False, "stage_b_accessed": False,
        }
        exclusive_json(root / marker_rel, marker)
        progress = []; sink = None; archive = None
        try:
            sink = PathArchive(root / archive_rel)
            candidates = runner(root, sink, frozen, progress)
            archive = sink.close(); sink = None; archive["path"] = _rel(archive_rel)
            if tuple(candidates) != CANDIDATE_ORDER:
                raise IntegrityError("candidate execution order/completeness differs")
            expected_progress = [
                {"candidate_id": candidate, "case": omitted or "FULL"}
                for candidate in CANDIDATE_ORDER for omitted in (None, *U14.currencies)
            ]
            if production_runner and (progress != expected_progress or archive["records"] != 180):
                raise IntegrityError("Family-6 case/path execution is incomplete")
            if execution_source_sha256(root) != source_hashes:
                raise IntegrityError("Family-6 execution source changed during economics")
            _validate_frozen_evidence(root)
            result = {
                "schema_version": 1, "status": "PENDING_EXTERNAL_ADJUDICATION",
                "adjudication_policy": ADJUDICATION_POLICY,
                "automatic_candidate_rejection_or_winner_selection": False,
                "candidate_order": list(CANDIDATE_ORDER), "candidates": candidates,
                "control_reuse": {"path": _rel(F5_CONTROL), "sha256": F5_HASHES[str(F5_CONTROL)],
                    "family6_control_parity_path": _rel(PARITY_REL), "family6_control_parity_sha256": PARITY_SHA256},
                "benchmark_reuse": frozen["benchmark_reuse"], "ic_sha256": frozen["ic_sha256"],
                "archive": archive, "execution_sha256": _sha256(root / marker_rel),
                "authorization_sha256": authorization_sha, "execution_source_sha256": source_hashes,
                "preregistration_sha256": PREREG_SHA256, "readiness_sha256": READINESS_SHA256,
                "parity_sha256": PARITY_SHA256, "operational_attempt": attempt,
                "network_accessed": False, "stage_b_accessed": False,
            }
            exclusive_json(root / RESULT_REL, result)
            completion = {
                "schema_version": 1, "status": "ECONOMICS_COMPLETED_PENDING_EXTERNAL_ADJUDICATION",
                "result_sha256": _sha256(root / RESULT_REL), "execution_sha256": _sha256(root / marker_rel),
                "authorization_sha256": authorization_sha, "archive_sha256": archive["sha256"],
                "scientific_consumption_count": 1, "operational_attempt_count": attempt,
                "candidate_order": list(CANDIDATE_ORDER), "preregistration_sha256": PREREG_SHA256,
                "readiness_sha256": READINESS_SHA256, "parity_sha256": PARITY_SHA256,
                "execution_source_sha256": source_hashes, "network_accessed": False,
                "stage_b_accessed": False,
            }
            exclusive_json(root / COMPLETION_REL, completion)
            return root / RESULT_REL
        except Exception as exc:
            if sink is not None:
                try:
                    archive = sink.close(); archive["path"] = _rel(archive_rel)
                except Exception:
                    archive = None
            if not (root / RESULT_REL).exists():
                failure = {
                    "schema_version": 1, "status": "INCOMPLETE_INFRASTRUCTURE_FAILURE",
                    "completed_scientific_one_shot_count": 0, "operational_attempt": attempt,
                    "execution_sha256": _sha256(root / marker_rel), "authorization_sha256": authorization_sha,
                    "execution_source_sha256": source_hashes, "candidate_order": list(CANDIDATE_ORDER),
                    "preregistration_sha256": PREREG_SHA256, "readiness_sha256": READINESS_SHA256,
                    "parity_sha256": PARITY_SHA256,
                    "progress": progress, "archive": archive, "exception_type": type(exc).__name__,
                    "exception_message": str(exc), "retry_requires_external_identical_execution_authorization": True,
                    "network_accessed": False, "stage_b_accessed": False,
                }
                exclusive_json(root / _failure_rel(attempt), failure)
            raise
