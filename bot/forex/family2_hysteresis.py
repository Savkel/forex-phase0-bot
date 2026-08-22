"""Frozen Family-2 rank-hysteresis infrastructure; importing never executes economics."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from bot.forex.family1_study import ADJUDICATION_POLICY, _scenario_paths, path_diagnostics
from bot.forex.family1_universe import (
    BLOCKS, NUMERIC_TOLERANCE, PARITY_ARTIFACT_REL as FAMILY1_PARITY_REL,
    RESULT_ARTIFACT_REL as FAMILY1_RESULT_REL, U14, CandidateInputs, SignalStep,
    _canonical_bytes, _canonical_sha, _comparison_stats, _json, _sha256,
    accounting_membership_records, candidate_accounting_steps, event_identity,
    family1_benchmark_books, load_frozen_context, prepare_candidate, write_artifact,
)
from bot.forex.stage_a_carry import AccountingStep, max_drawdown_from_returns, rap
from bot.forex.stage_a_orchestration import IntegrityError


PREREG_REL = Path("prereg/2026-08-22-tms-carry-unlevered-family-2-rank-hysteresis-prereg.md")
READINESS_REL = Path("prereg/2026-08-22-tms-carry-unlevered-family-2-rank-hysteresis-readiness.json")
H0_PARITY_REL = Path("prereg/2026-08-22-tms-carry-unlevered-family-2-rank-hysteresis-h0-parity.json")
EXECUTION_REL = Path("prereg/2026-08-22-tms-carry-unlevered-family-2-rank-hysteresis-execution.json")
RESULT_REL = Path("reports/forex/family2/family2-rank-hysteresis-result.json")
COMPLETION_REL = Path("reports/forex/family2/family2-rank-hysteresis-completion.json")
H_VALUES = (0, 1, 2, 3)


def _ordered(scores: Mapping[str, float], active: Sequence[str]) -> tuple[str, ...]:
    if set(active) - set(scores):
        raise IntegrityError("hysteresis score columns are incomplete")
    return tuple(sorted(active, key=lambda c: (-float(scores[c]), c)))


def hysteresis_accounting_steps(
    signals: Sequence[SignalStep], h: int, *, omitted: str | None = None,
) -> tuple[tuple[AccountingStep, ...], tuple[dict[str, object], ...]]:
    """Apply the frozen causal state machine and emit auditable rotation records."""
    if h not in H_VALUES or omitted not in (None, *U14.currencies):
        raise ValueError("invalid frozen h/omission")
    active = tuple(c for c in U14.currencies if c != omitted)
    n, k = len(active), len(active) // 3
    if k != 4:
        raise IntegrityError("Family-2 requires k=4")
    prior_longs: set[str] = set()
    prior_shorts: set[str] = set()
    steps: list[AccountingStep] = []
    records: list[dict[str, object]] = []
    evaluable_index = 0
    for signal in signals:
        if signal.scores is None:
            steps.append(AccountingStep(signal.timestamp, {c: 0.0 for c in U14.currencies}, signal.opens, signal.kind))
            records.append({
                "timestamp": signal.timestamp, "kind": signal.kind, "evaluable_index": None,
                "state_reset": True, "counted_rotation": False,
                "prior_longs": sorted(prior_longs), "prior_shorts": sorted(prior_shorts),
                "final_longs": [], "final_shorts": [], "suppressed_replacements": 0,
            })
            prior_longs.clear(); prior_shorts.clear()
            continue
        order = _ordered(signal.scores, active)
        ranks = {c: i + 1 for i, c in enumerate(order)}
        control_longs, control_shorts = set(order[:k]), set(order[-k:])
        fresh = signal.kind == "gap_reentry" or not prior_longs or not prior_shorts
        if fresh:
            retained_longs: set[str] = set(); retained_shorts: set[str] = set()
            longs, shorts = set(control_longs), set(control_shorts)
        else:
            retained_longs = {c for c in prior_longs if ranks[c] <= k + h}
            retained_shorts = {c for c in prior_shorts if ranks[c] >= n - k - h + 1}
            longs, shorts = set(retained_longs), set(retained_shorts)
            for currency in order:
                if len(longs) == k:
                    break
                if currency not in longs and currency not in shorts:
                    longs.add(currency)
            for currency in reversed(order):
                if len(shorts) == k:
                    break
                if currency not in longs and currency not in shorts:
                    shorts.add(currency)
        if len(longs) != k or len(shorts) != k or longs & shorts:
            raise IntegrityError("hysteresis sleeves violate frozen scale/disjointness")
        retained_outside_long = retained_longs - control_longs
        retained_outside_short = retained_shorts - control_shorts
        displaced_long = control_longs - longs
        displaced_short = control_shorts - shorts
        if len(retained_outside_long) != len(displaced_long) or len(retained_outside_short) != len(displaced_short):
            raise IntegrityError("retained/displaced rotation counts do not reconcile")
        counted = not fresh and signal.kind == "rebalance"
        rank_list = lambda values: [c for c in order if c in values]
        record = {
            "timestamp": signal.timestamp, "kind": signal.kind, "evaluable_index": evaluable_index,
            "state_reset": fresh, "counted_rotation": counted,
            "ranks": {c: ranks[c] for c in order},
            "prior_longs": rank_list(prior_longs), "prior_shorts": rank_list(prior_shorts),
            "retained_longs": rank_list(retained_longs), "retained_shorts": rank_list(retained_shorts),
            "exited_longs": rank_list(prior_longs - longs), "exited_shorts": rank_list(prior_shorts - shorts),
            "entered_longs": rank_list(longs - prior_longs), "entered_shorts": rank_list(shorts - prior_shorts),
            "final_longs": rank_list(longs), "final_shorts": rank_list(shorts),
            "retained_outside_control_longs": rank_list(retained_outside_long),
            "retained_outside_control_shorts": rank_list(retained_outside_short),
            "displaced_control_longs": rank_list(displaced_long),
            "displaced_control_shorts": rank_list(displaced_short),
            "actual_long_replacements": (k - len(prior_longs & longs)) if counted else 0,
            "actual_short_replacements": (k - len(prior_shorts & shorts)) if counted else 0,
            "suppressed_long_replacements": len(retained_outside_long) if counted else 0,
            "suppressed_short_replacements": len(retained_outside_short) if counted else 0,
            "suppressed_replacements": (len(retained_outside_long) + len(retained_outside_short)) if counted else 0,
            "avoided_long_replacements": len(retained_outside_long) if counted else 0,
            "avoided_short_replacements": len(retained_outside_short) if counted else 0,
            "avoided_replacements": (len(retained_outside_long) + len(retained_outside_short)) if counted else 0,
        }
        weights = {c: (0.25 if c in longs else -0.25 if c in shorts else 0.0) for c in U14.currencies}
        steps.append(AccountingStep(signal.timestamp, weights, signal.opens, signal.kind))
        records.append(record)
        prior_longs, prior_shorts = longs, shorts
        evaluable_index += 1
    if evaluable_index != 157:
        raise IntegrityError("Family-2 requires 157 evaluable decisions")
    return tuple(steps), tuple(records)


def _concentration(steps: Sequence[AccountingStep]) -> dict[str, object]:
    histories = {c: [] for c in U14.currencies}; hhi = []
    for step in steps:
        if step.kind in ("gap_exit", "terminal"):
            continue
        values = [abs(step.target_weights[c]) for c in U14.currencies]
        hhi.append(sum((value / 2) ** 2 for value in values))
        for currency, value in zip(U14.currencies, values):
            histories[currency].append(value)
    currencies = {}
    for currency, values in histories.items():
        longest = current = 0
        for value in values:
            current = current + 1 if value > 0 else 0
            longest = max(longest, current)
        currencies[currency] = {
            "selection_frequency": sum(value > 0 for value in values) / len(values),
            "mean_absolute_weight": float(np.mean(values)),
            "longest_consecutive_selected_run": longest,
        }
    return {"hhi_mean": float(np.mean(hhi)), "hhi_min": min(hhi), "hhi_max": max(hhi), "currencies": currencies}


def _rotation_diagnostics(records: Sequence[Mapping[str, object]]) -> dict[str, object]:
    counted = [record for record in records if record.get("counted_rotation")]
    keys = (
        "actual_long_replacements", "actual_short_replacements",
        "suppressed_long_replacements", "suppressed_short_replacements", "suppressed_replacements",
        "avoided_long_replacements", "avoided_short_replacements", "avoided_replacements",
    )
    totals = {key: int(sum(int(record[key]) for record in counted)) for key in keys}
    blocks = {}
    for block in BLOCKS:
        selected = [r for r in counted if block["start"] <= int(r["evaluable_index"]) < block["stop"]]
        blocks[block["block_id"]] = {key: int(sum(int(record[key]) for record in selected)) for key in keys}
    return {"ordinary_rebalance_count": len(counted), "totals": totals, "blocks": blocks, "records": list(records)}


def _reuse(root: Path) -> tuple[Mapping[str, object], Mapping[str, object]]:
    parity = _json(root / FAMILY1_PARITY_REL)
    if parity.get("status") != "U14_PARITY_PASSED" or parity.get("section12_parity", {}).get("mismatch_count") != 0:
        raise IntegrityError("authoritative Family-1 U14 parity is unavailable")
    return parity, parity["control_diagnostics"]


def _denominator_payload(scenarios, inputs: CandidateInputs, benchmark: Mapping[str, object]) -> dict[str, object]:
    result = {}
    for denominator in (360, 365):
        base = path_diagnostics(
            scenarios["base"][denominator], inputs.signal_steps, inputs.financing_events, inputs.routes
        )
        matched = benchmark[str(denominator)]
        result[str(denominator)] = {
            "base": base, "benchmark": matched,
            "benchmark_rap_excess": base["rap"] - matched["rap"],
            "benchmark_mdd_difference": base["max_drawdown"] - matched["max_drawdown"],
            "adverse_total_return": scenarios["adverse"][denominator].equities[-1] - 1,
            "spread_x3_total_return": scenarios["spread_x3"][denominator].equities[-1] - 1,
        }
    return result


def _difference(denominators: Mapping[str, object]) -> dict[str, float]:
    keys = (
        "final_equity", "total_return", "cagr", "rap", "max_drawdown", "currency_turnover",
        "annualized_currency_turnover", "routed_usd_turnover", "annualized_routed_usd_turnover",
        "mean_routed_usd_gross", "total_spread_cost", "total_financing", "spot_pnl",
    )
    result = {key: denominators["365"]["base"][key] - denominators["360"]["base"][key] for key in keys}
    for key in ("benchmark_rap_excess", "benchmark_mdd_difference", "adverse_total_return", "spread_x3_total_return"):
        result[key] = denominators["365"][key] - denominators["360"][key]
    return result


def hysteresis_study(inputs: CandidateInputs, h: int, control: Mapping[str, object]) -> dict[str, object]:
    if inputs.definition != U14 or h not in H_VALUES:
        raise PermissionError("Family-2 study is frozen to U14/h=0..3")
    steps, records = hysteresis_accounting_steps(inputs.signal_steps, h)
    scenarios = _scenario_paths(steps, inputs.financing_events, inputs.routes)
    benchmark = {d: control["denominators"][d]["benchmark"] for d in ("360", "365")}
    denominators = _denominator_payload(scenarios, inputs, benchmark)
    loco = {}
    for omitted in U14.currencies:
        active = tuple(c for c in U14.currencies if c != omitted)
        loco_steps, loco_records = hysteresis_accounting_steps(inputs.signal_steps, h, omitted=omitted)
        loco_scenarios = _scenario_paths(loco_steps, inputs.financing_events, inputs.routes)
        frozen = control["loco"][omitted]
        cells = {}
        for denominator in (360, 365):
            d = str(denominator); expected = frozen["denominators"][d]
            base = path_diagnostics(loco_scenarios["base"][denominator], inputs.signal_steps, inputs.financing_events, inputs.routes)
            cells[d] = {
                "base": base,
                "adverse_total_return": loco_scenarios["adverse"][denominator].equities[-1] - 1,
                "spread_x3_total_return": loco_scenarios["spread_x3"][denominator].equities[-1] - 1,
                "benchmark_rap": expected["benchmark_rap"],
                "benchmark_max_drawdown": expected["benchmark_max_drawdown"],
                "benchmark_adverse_total_return": expected["benchmark_adverse_total_return"],
                "benchmark_spread_x3_total_return": expected["benchmark_spread_x3_total_return"],
                "benchmark_rap_excess": base["rap"] - expected["benchmark_rap"],
                "benchmark_blocks": expected["benchmark_blocks"],
            }
        books = family1_benchmark_books(active, 4)
        loco[omitted] = {
            "N": 13, "k": 4, "benchmark_books_sha256": _canonical_sha(books),
            "benchmark_economics_reused": True, "concentration": _concentration(loco_steps),
            "rotation": _rotation_diagnostics(loco_records), "denominators": cells,
        }
    return {
        "configuration_id": f"H{h}" if h else "H0_CONTROL", "h": h,
        "N": 14, "k": 4, "currencies": list(U14.currencies), "currency_gross": 2,
        "benchmark_books_sha256": control["benchmark_books_sha256"],
        "benchmark_book_count": control["benchmark_book_count"], "benchmark_economics_reused": True,
        "ic": control["ic"], "ic_reused": True,
        "concentration": _concentration(steps), "rotation": _rotation_diagnostics(records),
        "denominators": denominators, "D365_MINUS_D360": _difference(denominators), "loco": loco,
        "candidate_disposition": "PENDING_EXTERNAL_ADJUDICATION",
    }


def _control_comparable(study: Mapping[str, object]) -> dict[str, object]:
    loco = {currency: {
        "N": value["N"], "k": value["k"], "denominators": value["denominators"],
    } for currency, value in study["loco"].items()}
    return {
        "candidate_id": U14.candidate_id, "N": study["N"], "k": study["k"],
        "currencies": study["currencies"], "benchmark_books_sha256": study["benchmark_books_sha256"],
        "benchmark_book_count": study["benchmark_book_count"], "ic": study["ic"],
        "concentration": study["concentration"], "denominators": study["denominators"],
        "D365_MINUS_D360": study["D365_MINUS_D360"], "loco": loco,
        "candidate_disposition": study["candidate_disposition"],
    }


def _source_hashes(root: Path) -> dict[str, str]:
    paths = (
        PREREG_REL, Path("bot/forex/family2_hysteresis.py"), Path("run_family2_hysteresis.py"),
        Path("bot/forex/family1_universe.py"), Path("bot/forex/family1_study.py"),
        Path("bot/forex/stage_a_carry.py"), FAMILY1_PARITY_REL, FAMILY1_RESULT_REL,
    )
    return {str(path).replace(chr(92), "/"): _sha256(root / path) for path in paths}


def build_readiness(root: Path, inputs: CandidateInputs | None = None) -> dict[str, object]:
    root = Path(root); context = load_frozen_context(root); inputs = inputs or prepare_candidate(context, U14)
    parity, control = _reuse(root)
    paths = {}
    for h in H_VALUES:
        steps, records = hysteresis_accounting_steps(inputs.signal_steps, h)
        paths[str(h)] = {
            "membership_sha256": _canonical_sha(accounting_membership_records(steps)),
            "rotation_state_sha256": _canonical_sha(records), "economic_outputs_computed": False,
        }
    return {
        "schema_version": 1, "status": "FAMILY2_READINESS_PASSED", "network_accessed": False,
        "performance_computed": False, "preregistration_sha256": _sha256(root / PREREG_REL),
        "source_sha256": _source_hashes(root), "cache_sha256": dict(sorted(context.cache_sha256.items())),
        "family1_parity_sha256": _sha256(root / FAMILY1_PARITY_REL),
        "family1_result_sha256": _sha256(root / FAMILY1_RESULT_REL),
        "family1_parity_status": parity["status"], "u14_control_benchmark_sha256": control["benchmark_books_sha256"],
        "u14_ic_sha256": _canonical_sha(control["ic"]), "h_values": list(H_VALUES),
        "N": 14, "k": 4, "currency_gross": 2, "signal_step_count": len(inputs.signal_steps),
        "financing_event_count": len(inputs.financing_events), "financing_event_sha256": _canonical_sha(event_identity(inputs.financing_events)),
        "configuration_paths": paths, "nonzero_h_economics_authorized": False,
    }


def emit_readiness(root: Path) -> Path:
    path = Path(root) / READINESS_REL; write_artifact(path, build_readiness(Path(root))); return path


def validate_readiness(root: Path) -> Mapping[str, object]:
    path = Path(root) / READINESS_REL
    if not path.is_file():
        raise IntegrityError("Family-2 readiness artifact is missing")
    expected, actual = build_readiness(Path(root)), _json(path)
    if _canonical_bytes(expected) != _canonical_bytes(actual):
        raise IntegrityError("Family-2 readiness artifact identity mismatch")
    return actual


def run_h0_parity(root: Path) -> dict[str, object]:
    root = Path(root); readiness = validate_readiness(root)
    inputs = prepare_candidate(load_frozen_context(root), U14); _, control = _reuse(root)
    steps, _ = hysteresis_accounting_steps(inputs.signal_steps, 0)
    expected_steps = tuple(candidate_accounting_steps(inputs.signal_steps, U14))
    discrete_exact = steps == expected_steps
    discrete = _comparison_stats(accounting_membership_records(expected_steps), accounting_membership_records(steps))
    if not discrete_exact or discrete["mismatch_count"]:
        raise IntegrityError("Family-2 H0 discrete parity failed")
    study = hysteresis_study(inputs, 0, control)
    numeric = _comparison_stats(control, _control_comparable(study))
    if numeric["mismatch_count"]:
        raise IntegrityError("Family-2 H0 numeric parity failed")
    if study["rotation"]["totals"]["suppressed_replacements"] != 0:
        raise IntegrityError("H0 cannot suppress replacements")
    return {
        "schema_version": 1, "status": "H0_PARITY_PASSED", "network_accessed": False,
        "nonzero_h_economics_computed": False, "preregistration_sha256": _sha256(root / PREREG_REL),
        "readiness_artifact_sha256": _sha256(root / READINESS_REL),
        "family1_parity_sha256": readiness["family1_parity_sha256"],
        "discrete": {"exact": True, "comparison": discrete, "membership_sha256": _canonical_sha(accounting_membership_records(steps))},
        "numeric": {"tolerance": NUMERIC_TOLERANCE, **numeric},
        "reused_evidence": {"ic_sha256": readiness["u14_ic_sha256"], "benchmark_books_sha256": readiness["u14_control_benchmark_sha256"]},
        "control_study": study, "candidate_disposition": "PENDING_EXTERNAL_ADJUDICATION",
    }


def emit_h0_parity(root: Path) -> Path:
    path = Path(root) / H0_PARITY_REL; write_artifact(path, run_h0_parity(Path(root))); return path


def execute_family2(root: Path) -> Path:
    root = Path(root); readiness = validate_readiness(root)
    parity_path = root / H0_PARITY_REL
    if not parity_path.is_file():
        raise IntegrityError("H0 parity artifact is required")
    parity = _json(parity_path)
    if parity.get("status") != "H0_PARITY_PASSED" or parity.get("numeric", {}).get("mismatch_count") != 0:
        raise IntegrityError("H0 parity has not passed")
    for path in (root / EXECUTION_REL, root / RESULT_REL, root / COMPLETION_REL):
        if path.exists():
            raise PermissionError(f"Family-2 economics already consumed or started: {path}")
    execution = {
        "schema_version": 1, "status": "ECONOMICS_STARTED", "consumption_count": 1,
        "configuration_ids": ["H1", "H2", "H3"], "network_accessed": False,
        "preregistration_sha256": readiness["preregistration_sha256"],
        "readiness_artifact_sha256": _sha256(root / READINESS_REL), "h0_parity_sha256": _sha256(parity_path),
    }
    write_artifact(root / EXECUTION_REL, execution)
    inputs = prepare_candidate(load_frozen_context(root), U14); _, control = _reuse(root)
    configurations = {f"H{h}": hysteresis_study(inputs, h, control) for h in (1, 2, 3)}
    result = {
        "schema_version": 1, "status": "PENDING_EXTERNAL_ADJUDICATION",
        "automatic_candidate_rejection_or_winner_selection": False, "adjudication_policy": ADJUDICATION_POLICY,
        "network_accessed": False, "execution_artifact_sha256": _sha256(root / EXECUTION_REL),
        "control": parity["control_study"], "configurations": configurations,
        "candidate_disposition": "PENDING_EXTERNAL_ADJUDICATION",
    }
    write_artifact(root / RESULT_REL, result)
    write_artifact(root / COMPLETION_REL, {
        "schema_version": 1, "status": "ECONOMICS_COMPLETED_PENDING_EXTERNAL_ADJUDICATION",
        "execution_artifact_sha256": result["execution_artifact_sha256"],
        "result_artifact_sha256": _sha256(root / RESULT_REL), "network_accessed": False,
    })
    return root / RESULT_REL
