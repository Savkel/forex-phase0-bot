"""Frozen Family-3 carry-strength-weighting infrastructure; imports never run economics."""
from __future__ import annotations

from math import fsum, isfinite
from pathlib import Path
from typing import Mapping, MutableMapping, Sequence

import numpy as np

from bot.forex.family1_study import ADJUDICATION_POLICY, _scenario_paths, path_diagnostics
from bot.forex.family1_universe import (
    BLOCKS, NUMERIC_TOLERANCE, U14, CandidateInputs, SignalStep, _canonical_bytes,
    _canonical_sha, _comparison_stats, _json, _sha256, accounting_membership_records,
    event_identity, family1_benchmark_books, load_frozen_context, path_block_diagnostics,
    prepare_candidate, write_artifact,
)
from bot.forex.family2_hysteresis import (
    COMPLETION_REL as FAMILY2_COMPLETION_REL, H0_PARITY_REL as FAMILY2_PARITY_REL,
    READINESS_REL as FAMILY2_READINESS_REL, RESULT_REL as FAMILY2_RESULT_REL,
    _concentration, _difference, _rotation_diagnostics, hysteresis_accounting_steps,
)
from bot.forex.stage_a_carry import AccountingStep, max_drawdown_from_returns, rap
from bot.forex.stage_a_orchestration import IntegrityError


PREREG_REL = Path("prereg/2026-08-22-tms-carry-unlevered-family-3-carry-strength-weighting-prereg.md")
READINESS_REL = Path("prereg/2026-08-22-tms-carry-unlevered-family-3-carry-strength-weighting-readiness.json")
EQ_PARITY_REL = Path("prereg/2026-08-22-tms-carry-unlevered-family-3-carry-strength-weighting-eq-h2-parity.json")
EXECUTION_REL = Path("prereg/2026-08-22-tms-carry-unlevered-family-3-carry-strength-weighting-execution.json")
RESULT_REL = Path("reports/forex/family3/family3-carry-strength-weighting-result.json")
COMPLETION_REL = Path("reports/forex/family3/family3-carry-strength-weighting-completion.json")

CANDIDATE_TAUS = {"EQ_H2": 0.0, "CS_MILD": 0.10, "CS_STRONG": 0.20}
WEIGHT_BOUNDS = {"EQ_H2": (0.25, 0.25), "CS_MILD": (0.20, 0.30), "CS_STRONG": (0.15, 0.35)}


def _candidate_id(tau: float) -> str:
    matches = [key for key, value in CANDIDATE_TAUS.items() if tau == value]
    if len(matches) != 1:
        raise ValueError("tau is outside the frozen Family-3 candidates")
    return matches[0]


def strength_weight_targets(
    scores: Mapping[str, float], longs: Sequence[str], shorts: Sequence[str], tau: float,
    *, active: Sequence[str], columns: Sequence[str] = U14.currencies,
) -> dict[str, float]:
    """Apply the frozen centered/L1 causal formula to fixed four-currency sleeves."""
    candidate_id = _candidate_id(tau)
    active_set, long_set, short_set = set(active), set(longs), set(shorts)
    if len(long_set) != 4 or len(short_set) != 4 or long_set & short_set:
        raise IntegrityError("Family-3 requires disjoint four-currency sleeves")
    if not long_set | short_set <= active_set or active_set - set(scores):
        raise IntegrityError("Family-3 score/membership columns are incomplete")
    active_scores = [float(scores[c]) for c in active]
    if any(not isfinite(value) for value in active_scores):
        raise IntegrityError("Family-3 scores must be finite")
    score_range = max(active_scores) - min(active_scores)
    result = {currency: 0.0 for currency in columns}

    def sleeve(members: set[str], sign: int) -> None:
        ordered = tuple(sorted(members))
        oriented = [sign * float(scores[c]) for c in ordered]
        mean = fsum(oriented) / 4
        deviations = [value - mean for value in oriented]
        dispersion = fsum(abs(value) for value in deviations)
        if dispersion == 0 or score_range == 0:
            magnitudes = [0.25] * 4
        else:
            denominator = max(dispersion, 1e-12 * score_range)
            magnitudes = [0.25 + tau * value / denominator for value in deviations]
        lower, upper = WEIGHT_BOUNDS[candidate_id]
        if any(value < lower - NUMERIC_TOLERANCE or value > upper + NUMERIC_TOLERANCE for value in magnitudes):
            raise IntegrityError("Family-3 weight bound failed")
        if abs(fsum(magnitudes) - 1.0) > NUMERIC_TOLERANCE:
            raise IntegrityError("Family-3 sleeve sum failed")
        for currency, magnitude in zip(ordered, magnitudes):
            result[currency] = sign * float(magnitude)

    sleeve(long_set, 1); sleeve(short_set, -1)
    if abs(fsum(result.values())) > NUMERIC_TOLERANCE or abs(fsum(abs(x) for x in result.values()) - 2) > NUMERIC_TOLERANCE:
        raise IntegrityError("Family-3 gross/net invariant failed")
    return result


def weighted_h2_accounting_steps(
    signals: Sequence[SignalStep], tau: float, *, omitted: str | None = None,
) -> tuple[tuple[AccountingStep, ...], tuple[dict[str, object], ...]]:
    """Preserve frozen H2 memberships and replace only within-sleeve weights."""
    _candidate_id(tau)
    equal_steps, records = hysteresis_accounting_steps(signals, 2, omitted=omitted)
    active = tuple(c for c in U14.currencies if c != omitted)
    weighted = []
    for signal, equal_step, record in zip(signals, equal_steps, records):
        if signal.scores is None:
            weights = dict(equal_step.target_weights)
        else:
            weights = strength_weight_targets(
                signal.scores, record["final_longs"], record["final_shorts"], tau,
                active=active, columns=U14.currencies,
            )
        weighted.append(AccountingStep(signal.timestamp, weights, signal.opens, signal.kind))
    result = tuple(weighted)
    if tau == 0 and result != equal_steps:
        raise IntegrityError("EQ_H2 does not exactly preserve frozen H2 steps")
    return result, records


def weighted_static_accounting_steps(
    signals: Sequence[SignalStep], book: Mapping[str, Sequence[str]], tau: float,
    *, active: Sequence[str], columns: Sequence[str] = U14.currencies,
) -> tuple[AccountingStep, ...]:
    """Keep book memberships static; vary only weights causally."""
    longs, shorts = tuple(book["longs"]), tuple(book["shorts"])
    result = []
    for signal in signals:
        weights = (
            {currency: 0.0 for currency in columns} if signal.scores is None else
            strength_weight_targets(signal.scores, longs, shorts, tau, active=active, columns=columns)
        )
        result.append(AccountingStep(signal.timestamp, weights, signal.opens, signal.kind))
    return tuple(result)


def weight_turnover_diagnostics(
    steps: Sequence[AccountingStep], signals: Sequence[SignalStep],
) -> dict[str, object]:
    """Decompose currency turnover into same-sleeve resizing and membership/sign changes."""
    previous: dict[str, float] = {}; records = []; evaluable = 0
    for step, signal in zip(steps, signals):
        target = step.target_weights; currencies = set(previous) | set(target)
        total = fsum(abs(float(target.get(c, 0)) - float(previous.get(c, 0))) for c in currencies)
        weight_only = fsum(
            abs(abs(float(target[c])) - abs(float(previous[c])))
            for c in currencies if float(previous.get(c, 0)) * float(target.get(c, 0)) > 0
        )
        period_index = evaluable if signal.scores is not None else (evaluable - 1 if evaluable else None)
        records.append({
            "timestamp": step.timestamp, "kind": step.kind, "period_index": period_index,
            "total_currency_turnover": total, "weight_only_currency_turnover": weight_only,
            "membership_or_sign_currency_turnover": total - weight_only,
        })
        if signal.scores is not None:
            evaluable += 1
        previous = dict(target)
    if evaluable != 157:
        raise IntegrityError("Family-3 turnover diagnostics require 157 periods")
    keys = ("total_currency_turnover", "weight_only_currency_turnover", "membership_or_sign_currency_turnover")
    totals = {key: fsum(float(record[key]) for record in records) for key in keys}
    if abs(totals[keys[0]] - totals[keys[1]] - totals[keys[2]]) > NUMERIC_TOLERANCE:
        raise IntegrityError("Family-3 turnover decomposition failed")
    blocks = {}
    for block in BLOCKS:
        selected = [r for r in records if r["period_index"] is not None and block["start"] <= r["period_index"] < block["stop"]]
        blocks[block["block_id"]] = {key: fsum(float(record[key]) for record in selected) for key in keys}
    return {
        "definition": "same-sign continuing-position magnitude changes are weight-only; remainder is membership/sign turnover",
        "all_weight_changes_in_realized_routed_cost_accounting": True,
        "totals": totals, "blocks": blocks, "records": records,
    }


BenchmarkKey = tuple[float, tuple[str, ...], tuple[str, ...], tuple[str, ...]]


def _benchmark_evidence(
    inputs: CandidateInputs, book: Mapping[str, Sequence[str]], tau: float, active: Sequence[str],
) -> dict[str, dict[str, object]]:
    steps = weighted_static_accounting_steps(inputs.signal_steps, book, tau, active=active)
    scenarios = _scenario_paths(steps, inputs.financing_events, inputs.routes)
    evidence = {}
    for denominator in (360, 365):
        base = scenarios["base"][denominator]
        evidence[str(denominator)] = {
            "rap": rap(base.period_returns), "max_drawdown": max_drawdown_from_returns(base.period_returns),
            "total_return": base.equities[-1] - 1,
            "adverse_total_return": scenarios["adverse"][denominator].equities[-1] - 1,
            "spread_x3_total_return": scenarios["spread_x3"][denominator].equities[-1] - 1,
            "blocks": {
                block["block_id"]: {key: block[key] for key in ("rap", "max_drawdown", "total_return")}
                for block in path_block_diagnostics(base, inputs.signal_steps)
            },
        }
    return evidence


def weighted_benchmark_ensemble(
    inputs: CandidateInputs, books: Sequence[Mapping[str, Sequence[str]]], tau: float,
    *, active: Sequence[str], cache: MutableMapping[BenchmarkKey, dict[str, dict[str, object]]] | None = None,
) -> dict[str, object]:
    """Recompute candidate-matched fixed-book economics with deterministic caching."""
    store = {} if cache is None else cache
    values = {str(d): {
        "rap": [], "max_drawdown": [], "total_return": [], "adverse_total_return": [],
        "spread_x3_total_return": [],
        "blocks": {block["block_id"]: {"rap": [], "max_drawdown": [], "total_return": []} for block in BLOCKS},
    } for d in (360, 365)}
    active_key = tuple(active)
    for book in books:
        key = (tau, active_key, tuple(book["longs"]), tuple(book["shorts"]))
        evidence = store.get(key)
        if evidence is None:
            evidence = _benchmark_evidence(inputs, book, tau, active)
            store[key] = evidence
        for denominator in (360, 365):
            target, item = values[str(denominator)], evidence[str(denominator)]
            for metric in ("rap", "max_drawdown", "total_return", "adverse_total_return", "spread_x3_total_return"):
                target[metric].append(item[metric])
            for block_id, block in item["blocks"].items():
                for metric in ("rap", "max_drawdown", "total_return"):
                    target["blocks"][block_id][metric].append(block[metric])
    medians = {}
    for denominator, target in values.items():
        medians[denominator] = {
            key: float(np.median(target[key]))
            for key in ("rap", "max_drawdown", "total_return", "adverse_total_return", "spread_x3_total_return")
        }
        medians[denominator]["blocks"] = {
            block_id: {key: float(np.median(cell[key])) for key in cell}
            for block_id, cell in target["blocks"].items()
        }
    return {"path_count": len(books), "distributions": values, "medians": medians}


def _denominators(scenarios, inputs: CandidateInputs, benchmark: Mapping[str, object]) -> dict[str, object]:
    result = {}
    for denominator in (360, 365):
        base = path_diagnostics(scenarios["base"][denominator], inputs.signal_steps, inputs.financing_events, inputs.routes)
        matched = benchmark["medians"][str(denominator)]
        result[str(denominator)] = {
            "base": base, "benchmark": matched,
            "benchmark_rap_excess": base["rap"] - matched["rap"],
            "benchmark_mdd_difference": base["max_drawdown"] - matched["max_drawdown"],
            "adverse_total_return": scenarios["adverse"][denominator].equities[-1] - 1,
            "spread_x3_total_return": scenarios["spread_x3"][denominator].equities[-1] - 1,
        }
    return result


def weighting_study(inputs: CandidateInputs, tau: float, reused_ic: Mapping[str, object]) -> dict[str, object]:
    """Compute complete per-candidate evidence; the caller controls authorization."""
    candidate_id = _candidate_id(tau)
    if inputs.definition != U14:
        raise PermissionError("Family-3 study is frozen to U14")
    steps, rotation_records = weighted_h2_accounting_steps(inputs.signal_steps, tau)
    scenarios = _scenario_paths(steps, inputs.financing_events, inputs.routes)
    books = family1_benchmark_books(U14.currencies, 4)
    cache: dict[BenchmarkKey, dict[str, dict[str, object]]] = {}
    benchmark = weighted_benchmark_ensemble(inputs, books, tau, active=U14.currencies, cache=cache)
    denominators = _denominators(scenarios, inputs, benchmark)
    loco = {}
    for omitted in U14.currencies:
        active = tuple(c for c in U14.currencies if c != omitted)
        loco_steps, loco_records = weighted_h2_accounting_steps(inputs.signal_steps, tau, omitted=omitted)
        loco_scenarios = _scenario_paths(loco_steps, inputs.financing_events, inputs.routes)
        loco_books = family1_benchmark_books(active, 4)
        loco_benchmark = weighted_benchmark_ensemble(inputs, loco_books, tau, active=active, cache=cache)
        cells = {}
        for denominator in (360, 365):
            d, matched = str(denominator), loco_benchmark["medians"][str(denominator)]
            base = path_diagnostics(loco_scenarios["base"][denominator], inputs.signal_steps, inputs.financing_events, inputs.routes)
            cells[d] = {
                "base": base,
                "adverse_total_return": loco_scenarios["adverse"][denominator].equities[-1] - 1,
                "spread_x3_total_return": loco_scenarios["spread_x3"][denominator].equities[-1] - 1,
                "benchmark_rap": matched["rap"], "benchmark_max_drawdown": matched["max_drawdown"],
                "benchmark_adverse_total_return": matched["adverse_total_return"],
                "benchmark_spread_x3_total_return": matched["spread_x3_total_return"],
                "benchmark_rap_excess": base["rap"] - matched["rap"],
                "benchmark_blocks": matched["blocks"],
            }
        loco[omitted] = {
            "N": 13, "k": 4, "benchmark_books_sha256": _canonical_sha(loco_books),
            "benchmark_economics_reused": False, "benchmark": loco_benchmark,
            "concentration": _concentration(loco_steps), "rotation": _rotation_diagnostics(loco_records),
            "weight_turnover": weight_turnover_diagnostics(loco_steps, inputs.signal_steps),
            "denominators": cells,
        }
    return {
        "configuration_id": candidate_id, "tau": tau, "base_configuration": "H2", "h": 2,
        "N": 14, "k": 4, "currencies": list(U14.currencies), "currency_gross": 2,
        "benchmark_books_sha256": _canonical_sha(books), "benchmark_book_count": len(books),
        "benchmark_economics_reused": False, "benchmark": benchmark,
        "ic": dict(reused_ic), "ic_reused": True,
        "concentration": _concentration(steps), "rotation": _rotation_diagnostics(rotation_records),
        "weight_turnover": weight_turnover_diagnostics(steps, inputs.signal_steps),
        "denominators": denominators, "D365_MINUS_D360": _difference(denominators), "loco": loco,
        "candidate_disposition": "PENDING_EXTERNAL_ADJUDICATION",
    }


def _load_h2(root: Path) -> tuple[Mapping[str, object], Mapping[str, object]]:
    result = _json(root / FAMILY2_RESULT_REL); completion = _json(root / FAMILY2_COMPLETION_REL)
    if result.get("status") != "PENDING_EXTERNAL_ADJUDICATION":
        raise IntegrityError("frozen Family-2 result is unavailable")
    if completion.get("status") != "ECONOMICS_COMPLETED_PENDING_EXTERNAL_ADJUDICATION":
        raise IntegrityError("frozen Family-2 completion is unavailable")
    h2 = result.get("configurations", {}).get("H2")
    if not isinstance(h2, Mapping) or h2.get("h") != 2:
        raise IntegrityError("frozen Family-2 H2 evidence is unavailable")
    return h2, h2["ic"]


def _source_hashes(root: Path) -> dict[str, str]:
    paths = (
        PREREG_REL, Path("bot/forex/family3_weighting.py"), Path("run_family3_weighting.py"),
        Path("bot/forex/family2_hysteresis.py"), Path("bot/forex/family1_study.py"),
        Path("bot/forex/family1_universe.py"), Path("bot/forex/stage_a_carry.py"),
        FAMILY2_READINESS_REL, FAMILY2_PARITY_REL, FAMILY2_RESULT_REL, FAMILY2_COMPLETION_REL,
    )
    return {str(path).replace(chr(92), "/"): _sha256(root / path) for path in paths}


def build_readiness(root: Path, inputs: CandidateInputs | None = None) -> dict[str, object]:
    root = Path(root); context = load_frozen_context(root); inputs = inputs or prepare_candidate(context, U14)
    _, ic = _load_h2(root); expected, _ = hysteresis_accounting_steps(inputs.signal_steps, 2)
    configurations = {}
    for candidate_id, tau in CANDIDATE_TAUS.items():
        steps, _ = weighted_h2_accounting_steps(inputs.signal_steps, tau)
        if accounting_membership_records(steps) != accounting_membership_records(expected):
            raise IntegrityError("Family-3 changed frozen H2 memberships")
        configurations[candidate_id] = {
            "tau": tau, "weights_sha256": _canonical_sha([dict(step.target_weights) for step in steps]),
            "membership_sha256": _canonical_sha(accounting_membership_records(steps)),
            "economic_outputs_computed": False,
        }
    books = family1_benchmark_books(U14.currencies, 4)
    return {
        "schema_version": 1, "status": "FAMILY3_READINESS_PASSED", "network_accessed": False,
        "performance_computed": False, "preregistration_sha256": _sha256(root / PREREG_REL),
        "source_sha256": _source_hashes(root), "cache_sha256": dict(sorted(context.cache_sha256.items())),
        "family2_result_sha256": _sha256(root / FAMILY2_RESULT_REL),
        "family2_completion_sha256": _sha256(root / FAMILY2_COMPLETION_REL),
        "selected_base": "H2", "h": 2, "N": 14, "k": 4, "currency_gross": 2,
        "signal_step_count": len(inputs.signal_steps), "financing_event_count": len(inputs.financing_events),
        "financing_event_sha256": _canonical_sha(event_identity(inputs.financing_events)),
        "h2_membership_sha256": _canonical_sha(accounting_membership_records(expected)),
        "ic_reuse_only": True, "ic_sha256": _canonical_sha(ic),
        "benchmark_book_count": len(books), "benchmark_books_sha256": _canonical_sha(books),
        "static_memberships_candidate_weights": True, "configurations": configurations,
        "nonzero_tau_economics_authorized": False,
    }


def emit_readiness(root: Path) -> Path:
    path = Path(root) / READINESS_REL; write_artifact(path, build_readiness(Path(root))); return path


def validate_readiness(root: Path) -> Mapping[str, object]:
    path = Path(root) / READINESS_REL
    if not path.is_file() or _canonical_bytes(build_readiness(Path(root))) != _canonical_bytes(_json(path)):
        raise IntegrityError("Family-3 readiness artifact identity mismatch")
    return _json(path)


def _comparable(study: Mapping[str, object]) -> dict[str, object]:
    loco = {currency: {
        key: value[key] for key in ("N", "k", "benchmark_books_sha256", "concentration", "rotation", "denominators")
    } for currency, value in study["loco"].items()}
    return {
        key: study[key] for key in (
            "N", "k", "currencies", "currency_gross", "benchmark_books_sha256", "benchmark_book_count",
            "ic", "concentration", "rotation", "denominators", "D365_MINUS_D360",
        )
    } | {"loco": loco, "candidate_disposition": study["candidate_disposition"]}


def run_eq_h2_parity(root: Path) -> dict[str, object]:
    root = Path(root); readiness = validate_readiness(root)
    inputs = prepare_candidate(load_frozen_context(root), U14); h2, ic = _load_h2(root)
    expected_steps, expected_rotation = hysteresis_accounting_steps(inputs.signal_steps, 2)
    actual_steps, actual_rotation = weighted_h2_accounting_steps(inputs.signal_steps, 0.0)
    expected_discrete = {
        "timestamps_kinds": [(step.timestamp, step.kind) for step in expected_steps],
        "memberships": accounting_membership_records(expected_steps), "rotation": expected_rotation,
        "routes": inputs.routes, "financing_events": event_identity(inputs.financing_events),
    }
    actual_discrete = {
        "timestamps_kinds": [(step.timestamp, step.kind) for step in actual_steps],
        "memberships": accounting_membership_records(actual_steps), "rotation": actual_rotation,
        "routes": inputs.routes, "financing_events": event_identity(inputs.financing_events),
    }
    discrete = _comparison_stats(expected_discrete, actual_discrete)
    if expected_steps != actual_steps or discrete["mismatch_count"]:
        raise IntegrityError("Family-3 EQ_H2 discrete parity failed")
    study = weighting_study(inputs, 0.0, ic)
    numeric = _comparison_stats(_comparable(h2), _comparable(study))
    if numeric["mismatch_count"]:
        raise IntegrityError("Family-3 EQ_H2 numeric parity failed")
    if _canonical_sha(study["ic"]) != readiness["ic_sha256"]:
        raise IntegrityError("Family-3 IC reuse identity failed")
    return {
        "schema_version": 1, "status": "EQ_H2_PARITY_PASSED", "network_accessed": False,
        "nonzero_tau_economics_computed": False,
        "preregistration_sha256": _sha256(root / PREREG_REL),
        "readiness_artifact_sha256": _sha256(root / READINESS_REL),
        "family2_result_sha256": readiness["family2_result_sha256"],
        "discrete": {"exact": True, "comparison": discrete, "membership_sha256": readiness["h2_membership_sha256"]},
        "numeric": {"tolerance": NUMERIC_TOLERANCE, **numeric},
        "reused_evidence": {"ic_only": True, "ic_sha256": readiness["ic_sha256"]},
        "recomputed_benchmark_sha256": _canonical_sha(study["benchmark"]),
        "control_study": study, "candidate_disposition": "PENDING_EXTERNAL_ADJUDICATION",
    }


def emit_eq_h2_parity(root: Path) -> Path:
    path = Path(root) / EQ_PARITY_REL; write_artifact(path, run_eq_h2_parity(Path(root))); return path


def execute_family3(root: Path) -> Path:
    """One-shot future candidate execution; never called by readiness or parity."""
    root = Path(root); readiness = validate_readiness(root); parity_path = root / EQ_PARITY_REL
    if not parity_path.is_file():
        raise IntegrityError("EQ_H2 parity artifact is required")
    parity = _json(parity_path)
    if parity.get("status") != "EQ_H2_PARITY_PASSED" or parity.get("numeric", {}).get("mismatch_count") != 0:
        raise IntegrityError("EQ_H2 parity has not passed")
    for path in (root / EXECUTION_REL, root / RESULT_REL, root / COMPLETION_REL):
        if path.exists():
            raise PermissionError(f"Family-3 economics already consumed or started: {path}")
    execution = {
        "schema_version": 1, "status": "ECONOMICS_STARTED", "consumption_count": 1,
        "configuration_ids": ["CS_MILD", "CS_STRONG"], "network_accessed": False,
        "preregistration_sha256": readiness["preregistration_sha256"],
        "readiness_artifact_sha256": _sha256(root / READINESS_REL),
        "eq_h2_parity_sha256": _sha256(parity_path),
    }
    write_artifact(root / EXECUTION_REL, execution)
    inputs = prepare_candidate(load_frozen_context(root), U14); _, ic = _load_h2(root)
    candidates = {key: weighting_study(inputs, tau, ic) for key, tau in CANDIDATE_TAUS.items() if tau}
    result = {
        "schema_version": 1, "status": "PENDING_EXTERNAL_ADJUDICATION",
        "automatic_candidate_rejection_or_winner_selection": False,
        "adjudication_policy": ADJUDICATION_POLICY, "network_accessed": False,
        "execution_artifact_sha256": _sha256(root / EXECUTION_REL),
        "control": parity["control_study"], "candidates": candidates,
        "candidate_disposition": "PENDING_EXTERNAL_ADJUDICATION",
    }
    write_artifact(root / RESULT_REL, result)
    write_artifact(root / COMPLETION_REL, {
        "schema_version": 1, "status": "ECONOMICS_COMPLETED_PENDING_EXTERNAL_ADJUDICATION",
        "execution_artifact_sha256": result["execution_artifact_sha256"],
        "result_artifact_sha256": _sha256(root / RESULT_REL), "network_accessed": False,
    })
    return root / RESULT_REL
