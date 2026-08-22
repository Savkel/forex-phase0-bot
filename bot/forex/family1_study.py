"""Frozen Family-1 candidate study and one-shot result-artifact plumbing.

Importing this module cannot execute economics.  Historical G10/U8 consumption is available
only through :func:`execute_family1_candidates`, which requires current hash-bound readiness and
complete U14 parity, writes an immutable start marker first, and refuses every retry.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping, MutableMapping, Sequence

import numpy as np

from bot.forex.family1_universe import (
    ANNUALIZATION_DAYS,
    BLOCKS,
    COMPLETION_ARTIFACT_REL,
    EXECUTION_ARTIFACT_REL,
    G10,
    PARITY_ARTIFACT_REL,
    PREREG_REL,
    READINESS_ARTIFACT_REL,
    RESULT_ARTIFACT_REL,
    U14,
    U8,
    CandidateInputs,
    SignalStep,
    _candidate_ic,
    _canonical_sha,
    _json,
    _membership_steps,
    _pair_currencies,
    _path_component_payload,
    _sha256,
    _static_steps,
    candidate_accounting_steps,
    family1_benchmark_books,
    load_frozen_context,
    path_block_diagnostics,
    prepare_candidate,
    stationary_bootstrap_evidence,
    validate_readiness_artifacts,
    write_artifact,
)
from bot.forex.stage_a_carry import (
    AccountingPath,
    AccountingStep,
    FinancingEvent,
    OpenQuote,
    currency_usd_values,
    max_drawdown_from_returns,
    rap,
    run_adverse_dual_accounting_paths,
    run_dual_accounting_paths,
    run_spread3_sensitivity_paths,
)
from bot.forex.stage_a_orchestration import IntegrityError


STUDY_SCHEMA_VERSION = 1
SCENARIOS = ("base", "adverse", "spread_x3")
ADJUDICATION_POLICY = "NO AUTOMATIC CANDIDATE REJECTION OR WINNER SELECTION; FINAL ADJUDICATION IS EXTERNAL."


def _years(signals: Sequence[SignalStep]) -> float:
    return (signals[-1].timestamp - signals[0].timestamp) / 1000 / (ANNUALIZATION_DAYS * 24 * 60 * 60)


def _scenario_paths(
    steps: Sequence[AccountingStep], events: Sequence[FinancingEvent], routes: Mapping[str, object]
) -> dict[str, dict[int, AccountingPath]]:
    return {
        "base": run_dual_accounting_paths(1.0, steps, events, routes),
        "adverse": run_adverse_dual_accounting_paths(1.0, steps, events, routes),
        "spread_x3": run_spread3_sensitivity_paths(1.0, steps, events, routes),
    }


def _trade_diagnostics(path: AccountingPath, signals: Sequence[SignalStep]) -> dict[str, object]:
    previous_weights: dict[str, float] = {}
    previous_units: dict[str, float] = {}
    currency_turnover = []
    routed_turnover = []
    routed_gross = []
    trade_counts = []
    for trade, signal in zip(path.trades, signals):
        keys = set(previous_weights) | set(trade.target_weights)
        currency_turnover.append(sum(abs(trade.target_weights.get(c, 0.0) - previous_weights.get(c, 0.0)) for c in keys))
        values = currency_usd_values(signal.opens)
        route_keys = set(previous_units) | set(trade.target_units)
        routed_turnover.append(sum(
            abs(trade.target_units.get(pair, 0.0) - previous_units.get(pair, 0.0)) * values[_pair_currencies(pair)[0]]
            for pair in route_keys
        ))
        routed_gross.append(sum(
            abs(units) * values[_pair_currencies(pair)[0]] for pair, units in trade.target_units.items()
        ))
        trade_counts.append(len(trade.fills))
        previous_weights = dict(trade.target_weights)
        previous_units = dict(trade.target_units)
    return {
        "currency_turnover_by_trade": currency_turnover,
        "routed_usd_turnover_by_trade": routed_turnover,
        "routed_usd_gross_by_trade": routed_gross,
        "trade_count_by_trade": trade_counts,
    }


def _period_component_arrays(
    path: AccountingPath, signals: Sequence[SignalStep], events: Sequence[FinancingEvent],
    routes: Mapping[str, object],
) -> dict[str, list[float]]:
    component = _path_component_payload(path, signals, events, routes)
    trades = _trade_diagnostics(path, signals)
    starts: dict[int, int] = {}
    ends: dict[int, int] = {}
    period = 0
    for index, (current, nxt) in enumerate(zip(signals, signals[1:])):
        if current.scores is not None:
            starts[index] = period
            ends[index + 1] = period
            period += 1
    if period != 157:
        raise IntegrityError("Family-1 diagnostics require 157 accounting periods")
    arrays = {key: [0.0] * 157 for key in (
        "spot_pnl", "financing", "spread_cost", "currency_turnover", "routed_usd_turnover",
        "routed_usd_gross", "trade_count",
    )}
    for index, cash in enumerate(component["spot_cashflows_by_step"]):
        if index in ends:
            arrays["spot_pnl"][ends[index]] += cash
    for event, cash in zip(events, component["financing_cashflows_by_event"]):
        if event.after_step not in starts:
            raise IntegrityError("financing event is outside an evaluable holding period")
        arrays["financing"][starts[event.after_step]] += cash
    for index, trade in enumerate(path.trades):
        target = ends.get(index) if trade.kind in ("gap_exit", "terminal") else starts.get(index)
        if target is None:
            continue
        arrays["spread_cost"][target] += trade.spread_cost
        arrays["currency_turnover"][target] += trades["currency_turnover_by_trade"][index]
        arrays["routed_usd_turnover"][target] += trades["routed_usd_turnover_by_trade"][index]
        arrays["routed_usd_gross"][target] = trades["routed_usd_gross_by_trade"][index]
        arrays["trade_count"][target] += trades["trade_count_by_trade"][index]
    if abs(sum(arrays["spread_cost"]) - path.total_spread_cost) > 1e-12:
        raise IntegrityError("spread-cost diagnostic attribution mismatch")
    if abs(sum(arrays["financing"]) - path.total_financing) > 1e-12:
        raise IntegrityError("financing diagnostic attribution mismatch")
    if abs(sum(arrays["spot_pnl"]) + path.total_financing - path.total_spread_cost - (path.equities[-1] - 1)) > 1e-12:
        raise IntegrityError("spot/financing/spread attribution mismatch")
    return arrays


def _block_diagnostics(
    path: AccountingPath, signals: Sequence[SignalStep], events: Sequence[FinancingEvent],
    routes: Mapping[str, object],
) -> list[dict[str, object]]:
    economics = list(path_block_diagnostics(path, signals))
    arrays = _period_component_arrays(path, signals, events, routes)
    result = []
    for block, base in zip(BLOCKS, economics):
        start, stop = int(block["start"]), int(block["stop"])
        result.append({
            **base,
            "currency_turnover": sum(arrays["currency_turnover"][start:stop]),
            "routed_usd_turnover": sum(arrays["routed_usd_turnover"][start:stop]),
            "mean_routed_usd_gross": float(np.mean(arrays["routed_usd_gross"][start:stop])),
            "trade_count": int(sum(arrays["trade_count"][start:stop])),
            "spread_cost": sum(arrays["spread_cost"][start:stop]),
            "financing": sum(arrays["financing"][start:stop]),
            "spot_pnl": sum(arrays["spot_pnl"][start:stop]),
        })
    return result


def path_diagnostics(
    path: AccountingPath, signals: Sequence[SignalStep], events: Sequence[FinancingEvent],
    routes: Mapping[str, object],
) -> dict[str, object]:
    years = _years(signals)
    total_return = path.equities[-1] - 1
    cagr = path.equities[-1] ** (1 / years) - 1
    mdd = max_drawdown_from_returns(path.period_returns)
    arrays = _period_component_arrays(path, signals, events, routes)
    turnover = sum(arrays["currency_turnover"])
    routed = sum(arrays["routed_usd_turnover"])
    return {
        "final_equity": path.equities[-1], "total_return": total_return,
        "elapsed_years": years, "cagr": cagr, "rap": rap(path.period_returns),
        "max_drawdown": mdd,
        "calmar": cagr / abs(mdd) if cagr > 0 and np.isfinite(mdd) and mdd != 0 else "NOT_INTERPRETABLE",
        "currency_turnover": turnover, "annualized_currency_turnover": turnover / years,
        "routed_usd_turnover": routed, "annualized_routed_usd_turnover": routed / years,
        "mean_routed_usd_gross": float(np.mean(arrays["routed_usd_gross"])),
        "max_routed_usd_gross": max(arrays["routed_usd_gross"]),
        "trade_count": int(sum(arrays["trade_count"])),
        "total_spread_cost": path.total_spread_cost, "total_financing": path.total_financing,
        "spot_pnl": sum(arrays["spot_pnl"]),
        "blocks": _block_diagnostics(path, signals, events, routes),
    }


def concentration_diagnostics(inputs: CandidateInputs, *, omitted: str | None = None) -> dict[str, object]:
    active = tuple(c for c in inputs.definition.currencies if c != omitted)
    k = len(active) // 3
    histories = {c: [] for c in inputs.definition.currencies}
    hhi = []
    for signal in inputs.signal_steps:
        if signal.scores is None:
            continue
        from bot.forex.stage_a_carry import currency_targets
        selected = currency_targets({c: signal.scores[c] for c in active}, k)
        weights = {c: (0.0 if c == omitted else selected.get(c, 0.0)) for c in inputs.definition.currencies}
        hhi.append(sum((abs(value) / 2) ** 2 for value in weights.values()))
        for currency, value in weights.items():
            histories[currency].append(abs(value))
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


BenchmarkBookKey = tuple[tuple[str, ...], tuple[str, ...]]
BenchmarkBookEvidence = dict[str, dict[str, object]]


def _benchmark_book_key(book: Mapping[str, Sequence[str]]) -> BenchmarkBookKey:
    return tuple(book["longs"]), tuple(book["shorts"])


def _benchmark_book_evidence(
    inputs: CandidateInputs, book: Mapping[str, Sequence[str]],
    *, columns: Sequence[str], signals: Sequence[SignalStep],
) -> BenchmarkBookEvidence:
    scenarios = _scenario_paths(_static_steps(signals, columns, book), inputs.financing_events, inputs.routes)
    evidence: BenchmarkBookEvidence = {}
    for denominator in (360, 365):
        base = scenarios["base"][denominator]
        evidence[str(denominator)] = {
            "rap": rap(base.period_returns),
            "max_drawdown": max_drawdown_from_returns(base.period_returns),
            "total_return": base.equities[-1] - 1,
            "adverse_total_return": scenarios["adverse"][denominator].equities[-1] - 1,
            "spread_x3_total_return": scenarios["spread_x3"][denominator].equities[-1] - 1,
            "blocks": {
                block["block_id"]: {key: block[key] for key in ("rap", "max_drawdown", "total_return")}
                for block in path_block_diagnostics(base, signals)
            },
        }
    return evidence


def _ensemble(
    inputs: CandidateInputs, books: Sequence[Mapping[str, Sequence[str]]],
    *, columns: Sequence[str], signals: Sequence[SignalStep],
    benchmark_cache: MutableMapping[BenchmarkBookKey, BenchmarkBookEvidence] | None = None,
) -> dict[str, object]:
    cache: MutableMapping[BenchmarkBookKey, BenchmarkBookEvidence] = (
        {} if benchmark_cache is None else benchmark_cache
    )
    values = {str(d): {
        "rap": [], "max_drawdown": [], "total_return": [], "adverse_total_return": [],
        "spread_x3_total_return": [], "blocks": {block["block_id"]: {"rap": [], "max_drawdown": [], "total_return": []} for block in BLOCKS},
    } for d in (360, 365)}
    for book in books:
        book_key = _benchmark_book_key(book)
        evidence = cache.get(book_key)
        if evidence is None:
            evidence = _benchmark_book_evidence(inputs, book, columns=columns, signals=signals)
            cache[book_key] = evidence
        for denominator in (360, 365):
            target = values[str(denominator)]
            item = evidence[str(denominator)]
            for metric in ("rap", "max_drawdown", "total_return", "adverse_total_return", "spread_x3_total_return"):
                target[metric].append(item[metric])
            for block_id, block in item["blocks"].items():
                cell = target["blocks"][block_id]
                for key in ("rap", "max_drawdown", "total_return"):
                    cell[key].append(block[key])
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


def _loco_study(
    inputs: CandidateInputs,
    benchmark_cache: MutableMapping[BenchmarkBookKey, BenchmarkBookEvidence],
) -> dict[str, object]:
    result = {}
    for omitted in inputs.definition.currencies:
        active = tuple(c for c in inputs.definition.currencies if c != omitted)
        k = len(active) // 3
        steps = _membership_steps(inputs.signal_steps, inputs.definition, omitted)
        scenarios = _scenario_paths(steps, inputs.financing_events, inputs.routes)
        books = family1_benchmark_books(active, k)
        benchmark = _ensemble(
            inputs, books, columns=inputs.definition.currencies, signals=inputs.signal_steps,
            benchmark_cache=benchmark_cache,
        )
        result[omitted] = {
            "N": len(active), "k": k,
            "benchmark_books_sha256": _canonical_sha(books),
            "benchmark": benchmark,
            "concentration": concentration_diagnostics(inputs, omitted=omitted),
            "denominators": {
                str(d): {
                    "base": path_diagnostics(scenarios["base"][d], inputs.signal_steps, inputs.financing_events, inputs.routes),
                    "adverse_total_return": scenarios["adverse"][d].equities[-1] - 1,
                    "spread_x3_total_return": scenarios["spread_x3"][d].equities[-1] - 1,
                    "benchmark_rap_excess": rap(scenarios["base"][d].period_returns) - benchmark["medians"][str(d)]["rap"],
                    "benchmark_mdd_difference": max_drawdown_from_returns(scenarios["base"][d].period_returns) - benchmark["medians"][str(d)]["max_drawdown"],
                } for d in (360, 365)
            },
        }
    return result


def candidate_study(inputs: CandidateInputs) -> dict[str, object]:
    if inputs.definition not in (G10, U8):
        raise PermissionError("candidate_study is frozen for G10/U8 only")
    steps = candidate_accounting_steps(inputs.signal_steps, inputs.definition)
    scenarios = _scenario_paths(steps, inputs.financing_events, inputs.routes)
    books = family1_benchmark_books(inputs.definition.currencies, inputs.definition.k)
    benchmark_cache: dict[BenchmarkBookKey, BenchmarkBookEvidence] = {}
    benchmark = _ensemble(
        inputs, books, columns=inputs.definition.currencies, signals=inputs.signal_steps,
        benchmark_cache=benchmark_cache,
    )
    ic_series = _candidate_ic(inputs.signal_steps, inputs.definition, inputs.routes)
    ic, _ = stationary_bootstrap_evidence(ic_series, lower_quantile=0.025)
    denominators = {}
    for denominator in (360, 365):
        base = path_diagnostics(scenarios["base"][denominator], inputs.signal_steps, inputs.financing_events, inputs.routes)
        median = benchmark["medians"][str(denominator)]
        denominators[str(denominator)] = {
            "base": base,
            "benchmark": median,
            "benchmark_rap_excess": base["rap"] - median["rap"],
            "benchmark_mdd_difference": base["max_drawdown"] - median["max_drawdown"],
            "adverse_total_return": scenarios["adverse"][denominator].equities[-1] - 1,
            "spread_x3_total_return": scenarios["spread_x3"][denominator].equities[-1] - 1,
        }
    difference_keys = (
        "final_equity", "total_return", "cagr", "rap", "max_drawdown", "currency_turnover",
        "annualized_currency_turnover", "routed_usd_turnover", "annualized_routed_usd_turnover",
        "mean_routed_usd_gross", "total_spread_cost", "total_financing", "spot_pnl",
    )
    return {
        "candidate_id": inputs.definition.candidate_id,
        "N": len(inputs.definition.currencies), "k": inputs.definition.k,
        "currencies": list(inputs.definition.currencies),
        "benchmark_books": [{"longs": list(x["longs"]), "shorts": list(x["shorts"])} for x in books],
        "benchmark_books_sha256": _canonical_sha(books),
        "benchmark": benchmark,
        "ic": {**ic, "period_count": len(ic_series), "series": ic_series, "bonferroni_new_candidate_count": 2},
        "concentration": concentration_diagnostics(inputs),
        "denominators": denominators,
        "D365_MINUS_D360": {
            **{key: denominators["365"]["base"][key] - denominators["360"]["base"][key] for key in difference_keys},
            "benchmark_rap_excess": denominators["365"]["benchmark_rap_excess"] - denominators["360"]["benchmark_rap_excess"],
            "benchmark_mdd_difference": denominators["365"]["benchmark_mdd_difference"] - denominators["360"]["benchmark_mdd_difference"],
            "adverse_total_return": denominators["365"]["adverse_total_return"] - denominators["360"]["adverse_total_return"],
            "spread_x3_total_return": denominators["365"]["spread_x3_total_return"] - denominators["360"]["spread_x3_total_return"],
        },
        "loco": _loco_study(inputs, benchmark_cache),
        "adjudication_policy": ADJUDICATION_POLICY,
        "candidate_disposition": "PENDING_EXTERNAL_ADJUDICATION",
    }


def diagnostic_flags(candidate: Mapping[str, object], control: Mapping[str, object]) -> dict[str, object]:
    flags = {}
    for denominator in ("360", "365"):
        item = candidate["denominators"][denominator]
        base = item["base"]
        reference = control["denominators"][denominator]["base"]
        delta = base["cagr"] - reference["cagr"]
        magnitude = abs(base["max_drawdown"])
        flags[denominator] = {
            "delta_cagr": delta,
            "DELTA_CAGR_GE_1PP_REFERENCE": delta >= 0.01,
            "CAGR_GE_4PCT_TARGET": base["cagr"] >= 0.04,
            "CAGR_GE_5PCT_TARGET": base["cagr"] >= 0.05,
            "MAXDD_PREFERRED": magnitude <= 0.25,
            "MAXDD_ELEVATED_RISK": 0.25 < magnitude <= 0.30,
            "MAXDD_SEVERE_RISK": magnitude > 0.30,
            "rap_vs_control": np.sign(base["rap"] - reference["rap"]).item(),
            "calmar_vs_control": (
                "NOT_INTERPRETABLE" if isinstance(base["calmar"], str) or isinstance(reference["calmar"], str)
                else np.sign(base["calmar"] - reference["calmar"]).item()
            ),
            "benchmark_relative_rap_direction": np.sign(item["benchmark_rap_excess"]).item(),
            "benchmark_relative_mdd_direction": np.sign(item["benchmark_mdd_difference"]).item(),
            "adverse_return_direction": np.sign(item["adverse_total_return"]).item(),
            "spread_x3_return_direction": np.sign(item["spread_x3_total_return"]).item(),
            "turnover_vs_control": np.sign(base["currency_turnover"] - reference["currency_turnover"]).item(),
            "spread_cost_vs_control": np.sign(base["total_spread_cost"] - reference["total_spread_cost"]).item(),
            "financing_vs_control": np.sign(base["total_financing"] - reference["total_financing"]).item(),
            "routed_gross_vs_control": np.sign(base["mean_routed_usd_gross"] - reference["mean_routed_usd_gross"]).item(),
            "concentration_hhi_vs_control": np.sign(
                candidate["concentration"]["hhi_mean"] - control["concentration"]["hhi_mean"]
            ).item(),
        }
    keys = set(flags["360"]) - {"delta_cagr"}
    flags["DELTA_CAGR_GE_1PP_REFERENCE_BOTH_DENOMINATORS"] = all(
        flags[d]["DELTA_CAGR_GE_1PP_REFERENCE"] for d in ("360", "365")
    )
    flags["DENOMINATOR_DIRECTIONAL_DISAGREEMENT"] = any(flags["360"][key] != flags["365"][key] for key in keys)
    return flags


def _control_from_parity(parity: Mapping[str, object]) -> Mapping[str, object]:
    control = parity.get("control_diagnostics")
    if not isinstance(control, Mapping):
        raise IntegrityError("complete U14 control diagnostics are absent from parity artifact")
    return control


def execute_family1_candidates(root: Path) -> Path:
    root = Path(root)
    integrity = validate_readiness_artifacts(root)
    parity_path = root / PARITY_ARTIFACT_REL
    if not parity_path.is_file():
        raise IntegrityError("complete U14 parity artifact is required")
    parity = _json(parity_path)
    if parity.get("status") != "U14_PARITY_PASSED" or parity.get("section12_parity", {}).get("mismatch_count") != 0:
        raise IntegrityError("complete U14 Section-12 parity has not passed")
    for path in (root / EXECUTION_ARTIFACT_REL, root / RESULT_ARTIFACT_REL, root / COMPLETION_ARTIFACT_REL):
        if path.exists():
            raise PermissionError(f"Family-1 candidate economics already consumed or started: {path}")
    execution = {
        "schema_version": STUDY_SCHEMA_VERSION,
        "status": "ECONOMICS_STARTED",
        "candidate_ids": [G10.candidate_id, U8.candidate_id],
        "consumption_count": 1,
        "network_accessed": False,
        "preregistration_sha256": _sha256(root / PREREG_REL),
        "readiness_artifact_sha256": _sha256(root / READINESS_ARTIFACT_REL),
        "parity_artifact_sha256": _sha256(parity_path),
        "integrity": integrity,
    }
    write_artifact(root / EXECUTION_ARTIFACT_REL, execution)
    context = load_frozen_context(root)
    candidates = {definition.candidate_id: candidate_study(prepare_candidate(context, definition)) for definition in (G10, U8)}
    control = _control_from_parity(parity)
    result = {
        "schema_version": STUDY_SCHEMA_VERSION,
        "status": "PENDING_EXTERNAL_ADJUDICATION",
        "automatic_candidate_rejection_or_winner_selection": False,
        "adjudication_policy": ADJUDICATION_POLICY,
        "network_accessed": False,
        "execution_artifact_sha256": _sha256(root / EXECUTION_ARTIFACT_REL),
        "preregistration_sha256": execution["preregistration_sha256"],
        "readiness_artifact_sha256": execution["readiness_artifact_sha256"],
        "parity_artifact_sha256": execution["parity_artifact_sha256"],
        "control": control,
        "candidates": candidates,
        "diagnostic_flags": {key: diagnostic_flags(value, control) for key, value in candidates.items()},
        "candidate_disposition": "PENDING_EXTERNAL_ADJUDICATION",
    }
    write_artifact(root / RESULT_ARTIFACT_REL, result)
    completion = {
        "schema_version": STUDY_SCHEMA_VERSION,
        "status": "ECONOMICS_COMPLETED_PENDING_EXTERNAL_ADJUDICATION",
        "execution_artifact_sha256": result["execution_artifact_sha256"],
        "result_artifact_sha256": _sha256(root / RESULT_ARTIFACT_REL),
        "candidate_ids": [G10.candidate_id, U8.candidate_id],
        "network_accessed": False,
    }
    write_artifact(root / COMPLETION_ARTIFACT_REL, completion)
    return root / RESULT_ARTIFACT_REL
