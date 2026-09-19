"""Frozen Family-4 rebalance-cadence infrastructure; imports never run economics."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Mapping, MutableMapping, Sequence

import numpy as np

from bot.forex.family1_study import ADJUDICATION_POLICY, path_diagnostics
from bot.forex.family1_universe import (
    BLOCKS, NUMERIC_TOLERANCE, U14, CandidateInputs, SignalStep, _canonical_bytes,
    _canonical_sha, _comparison_stats, _json, _sha256, accounting_membership_records,
    event_identity, family1_benchmark_books, load_frozen_context, path_block_diagnostics,
    prepare_candidate, write_artifact,
)
from bot.forex.family2_hysteresis import (
    _concentration, _difference, _rotation_diagnostics, hysteresis_accounting_steps,
)
from bot.forex.family3_weighting import (
    COMPLETION_REL as FAMILY3_COMPLETION_REL, EQ_PARITY_REL as FAMILY3_PARITY_REL,
    READINESS_REL as FAMILY3_READINESS_REL, RESULT_REL as FAMILY3_RESULT_REL,
    _comparable as family3_comparable, weight_turnover_diagnostics,
)
from bot.forex.stage_a_carry import (
    AccountingPath, AccountingStep, FinancingEvent, TradeRecord, _quote_usd,
    apply_financing_stress, fill_open, max_drawdown_from_returns,
    position_financing_cashflow_usd, rap, rollover_multiplier, solve_target_units,
)
from bot.forex.stage_a_orchestration import IntegrityError

PREREG_REL = Path("prereg/2026-09-19-tms-carry-unlevered-family-4-rebalance-cadence-prereg.md")
READINESS_REL = Path("prereg/2026-09-19-tms-carry-unlevered-family-4-rebalance-cadence-readiness.json")
M1_PARITY_REL = Path("prereg/2026-09-19-tms-carry-unlevered-family-4-rebalance-cadence-m1-parity.json")
EXECUTION_REL = Path("prereg/2026-09-19-tms-carry-unlevered-family-4-rebalance-cadence-execution.json")
RESULT_REL = Path("reports/forex/family4/family4-rebalance-cadence-result.json")
COMPLETION_REL = Path("reports/forex/family4/family4-rebalance-cadence-completion.json")
CANDIDATE_CADENCES = {"M1_CONTROL": 1, "M2": 2, "M4": 4}


@dataclass(frozen=True)
class CadenceStep:
    timestamp: int
    target_weights: Mapping[str, float]
    opens: Mapping[str, object]
    kind: str
    execute: bool


def _candidate_id(m: int) -> str:
    matches = [key for key, value in CANDIDATE_CADENCES.items() if m == value]
    if len(matches) != 1:
        raise ValueError("m is outside the frozen Family-4 candidates")
    return matches[0]


def _ordered(scores: Mapping[str, float], active: Sequence[str]) -> tuple[str, ...]:
    if set(scores) != set(U14.currencies) or any(not isfinite(float(scores[c])) for c in active):
        raise IntegrityError("Family-4 score columns are incomplete/non-finite")
    return tuple(sorted(active, key=lambda c: (-float(scores[c]), c)))


def cadence_accounting_steps(signals: Sequence[SignalStep], m: int, *, omitted: str | None = None):
    """Frozen segment-local cadence layered over the H2 state machine."""
    _candidate_id(m)
    if omitted not in (None, *U14.currencies):
        raise ValueError("invalid omission")
    active = tuple(c for c in U14.currencies if c != omitted)
    n, k = len(active), len(active) // 3
    if k != 4:
        raise IntegrityError("Family-4 requires k=4")
    prior_longs: set[str] = set(); prior_shorts: set[str] = set()
    steps: list[CadenceStep] = []; records: list[dict[str, object]] = []
    evaluable_index = 0; segment_index: int | None = None
    for signal in signals:
        if signal.scores is None:
            steps.append(CadenceStep(signal.timestamp, {c: 0.0 for c in U14.currencies}, signal.opens, signal.kind, True))
            records.append({"timestamp": signal.timestamp, "kind": signal.kind, "evaluable_index": None,
                "segment_index": None, "action": signal.kind, "execute": True, "state_reset": True,
                "counted_rotation": False, "prior_longs": sorted(prior_longs),
                "prior_shorts": sorted(prior_shorts), "final_longs": [], "final_shorts": [],
                "suppressed_replacements": 0})
            prior_longs.clear(); prior_shorts.clear(); segment_index = None
            continue
        segment_index = 0 if segment_index is None else segment_index + 1
        execute = segment_index % m == 0
        order = _ordered(signal.scores, active); ranks = {c: i + 1 for i, c in enumerate(order)}
        control_longs, control_shorts = set(order[:k]), set(order[-k:])
        rank_list = lambda values: [c for c in order if c in values]
        if not execute:
            longs, shorts = set(prior_longs), set(prior_shorts)
            if len(longs) != k or len(shorts) != k:
                raise IntegrityError("hold-mark without initialized H2 state")
            weights = {c: (0.25 if c in longs else -0.25 if c in shorts else 0.0) for c in U14.currencies}
            steps.append(CadenceStep(signal.timestamp, weights, signal.opens, "hold_mark", False))
            records.append({"timestamp": signal.timestamp, "kind": "hold_mark", "source_kind": signal.kind,
                "evaluable_index": evaluable_index, "segment_index": segment_index, "action": "hold_mark",
                "execute": False, "state_reset": False, "counted_rotation": False,
                "ranks": {c: ranks[c] for c in order}, "prior_longs": rank_list(prior_longs),
                "prior_shorts": rank_list(prior_shorts), "final_longs": rank_list(longs),
                "final_shorts": rank_list(shorts), "suppressed_replacements": 0})
            evaluable_index += 1
            continue
        fresh = segment_index == 0 or signal.kind == "gap_reentry" or not prior_longs or not prior_shorts
        if fresh:
            retained_longs: set[str] = set(); retained_shorts: set[str] = set()
            longs, shorts = set(control_longs), set(control_shorts)
        else:
            retained_longs = {c for c in prior_longs if ranks[c] <= k + 2}
            retained_shorts = {c for c in prior_shorts if ranks[c] >= n - k - 2 + 1}
            longs, shorts = set(retained_longs), set(retained_shorts)
            for currency in order:
                if len(longs) == k: break
                if currency not in longs and currency not in shorts: longs.add(currency)
            for currency in reversed(order):
                if len(shorts) == k: break
                if currency not in longs and currency not in shorts: shorts.add(currency)
        if len(longs) != k or len(shorts) != k or longs & shorts:
            raise IntegrityError("Family-4 sleeves violate frozen scale/disjointness")
        retained_outside_long = retained_longs - control_longs
        retained_outside_short = retained_shorts - control_shorts
        displaced_long = control_longs - longs; displaced_short = control_shorts - shorts
        if len(retained_outside_long) != len(displaced_long) or len(retained_outside_short) != len(displaced_short):
            raise IntegrityError("Family-4 retained/displaced counts do not reconcile")
        counted = not fresh and signal.kind == "rebalance"
        record = {"timestamp": signal.timestamp, "kind": signal.kind, "evaluable_index": evaluable_index,
            "segment_index": segment_index, "action": "execute", "execute": True,
            "state_reset": fresh, "counted_rotation": counted, "ranks": {c: ranks[c] for c in order},
            "prior_longs": rank_list(prior_longs), "prior_shorts": rank_list(prior_shorts),
            "retained_longs": rank_list(retained_longs), "retained_shorts": rank_list(retained_shorts),
            "exited_longs": rank_list(prior_longs-longs), "exited_shorts": rank_list(prior_shorts-shorts),
            "entered_longs": rank_list(longs-prior_longs), "entered_shorts": rank_list(shorts-prior_shorts),
            "final_longs": rank_list(longs), "final_shorts": rank_list(shorts),
            "retained_outside_control_longs": rank_list(retained_outside_long),
            "retained_outside_control_shorts": rank_list(retained_outside_short),
            "displaced_control_longs": rank_list(displaced_long), "displaced_control_shorts": rank_list(displaced_short),
            "actual_long_replacements": (k-len(prior_longs&longs)) if counted else 0,
            "actual_short_replacements": (k-len(prior_shorts&shorts)) if counted else 0,
            "suppressed_long_replacements": len(retained_outside_long) if counted else 0,
            "suppressed_short_replacements": len(retained_outside_short) if counted else 0,
            "suppressed_replacements": (len(retained_outside_long)+len(retained_outside_short)) if counted else 0,
            "avoided_long_replacements": len(retained_outside_long) if counted else 0,
            "avoided_short_replacements": len(retained_outside_short) if counted else 0,
            "avoided_replacements": (len(retained_outside_long)+len(retained_outside_short)) if counted else 0}
        weights = {c: (0.25 if c in longs else -0.25 if c in shorts else 0.0) for c in U14.currencies}
        steps.append(CadenceStep(signal.timestamp, weights, signal.opens, signal.kind, True)); records.append(record)
        prior_longs, prior_shorts = longs, shorts; evaluable_index += 1
    if evaluable_index != 157:
        raise IntegrityError("Family-4 requires 157 evaluable decisions")
    return tuple(steps), tuple(records)


def static_cadence_steps(signals: Sequence[SignalStep], book: Mapping[str, Sequence[str]], m: int,
                         *, columns: Sequence[str] = U14.currencies) -> tuple[CadenceStep, ...]:
    """Static memberships with candidate-matched cadence and forced overrides."""
    _candidate_id(m); longs, shorts = set(book["longs"]), set(book["shorts"])
    if len(longs) != 4 or len(shorts) != 4 or longs & shorts:
        raise IntegrityError("invalid static book")
    active = {c: (0.25 if c in longs else -0.25 if c in shorts else 0.0) for c in columns}
    result = []; segment_index: int | None = None
    for signal in signals:
        if signal.scores is None:
            segment_index = None
            result.append(CadenceStep(signal.timestamp, {c: 0.0 for c in columns}, signal.opens, signal.kind, True))
        else:
            segment_index = 0 if segment_index is None else segment_index + 1
            execute = segment_index % m == 0
            result.append(CadenceStep(signal.timestamp, dict(active), signal.opens,
                                      signal.kind if execute else "hold_mark", execute))
    return tuple(result)


def run_cadence_accounting_path(initial_equity: float, steps: Sequence[CadenceStep],
        financing_events: Sequence[FinancingEvent], routes: Mapping[str, object], denominator: int,
        *, spread_multiplier: float = 1.0, adverse_financing: bool = False) -> AccountingPath:
    """Stage-A accounting with a single frozen addition: exact-unit weekly hold marks."""
    if denominator not in (360, 365) or not steps:
        raise ValueError("D360 or D365 and at least one step required")
    if any(steps[i].timestamp >= steps[i+1].timestamp for i in range(len(steps)-1)):
        raise ValueError("steps must be strictly ordered")
    by_step: dict[int, list[FinancingEvent]] = {}
    for event in financing_events:
        by_step.setdefault(event.after_step, []).append(event)
    equity = float(initial_equity); positions: dict[str, float] = {}; prior_opens = None
    trades = []; equities = []; period_returns = []; total_spread = total_financing = 0.0
    holding_start_equity: float | None = None
    for i, step in enumerate(steps):
        if prior_opens is not None:
            for pair, q in positions.items():
                equity += q * (step.opens[pair].mid-prior_opens[pair].mid) * _quote_usd(pair, step.opens)
        equity_before_trade = equity
        if step.kind in ("rebalance", "hold_mark") and holding_start_equity is not None:
            period_returns.append(equity_before_trade/holding_start_equity-1)
            holding_start_equity = equity_before_trade
        elif step.kind in ("rebalance", "gap_reentry"):
            holding_start_equity = equity_before_trade
        if step.execute:
            target = solve_target_units(step.target_weights, equity, routes, step.opens)
            all_pairs = set(positions) | set(target.units); fills = {}; cost = 0.0
            for pair in all_pairs:
                delta = target.units.get(pair, 0.0)-positions.get(pair, 0.0)
                if delta:
                    quote = step.opens[pair]; fills[pair] = fill_open(1 if delta > 0 else -1, quote.bid, quote.ask)
                    cost += abs(delta)*abs(fills[pair]-quote.mid)*_quote_usd(pair, step.opens)*spread_multiplier
            equity -= cost; total_spread += cost; positions = dict(target.units)
        else:
            if step.kind != "hold_mark":
                raise IntegrityError("only hold-mark may skip execution")
            fills = {}; cost = 0.0
        for event in by_step.get(i, []):
            for pair, q in positions.items():
                if q == 0 or pair not in event.opens: continue
                cash = position_financing_cashflow_usd(event.schedule, pair, q, event.opens[pair].mid,
                    denominator, rollover_multiplier(event.day, pair) if event.days_charged is None else event.days_charged,
                    _quote_usd(pair, event.opens))
                if adverse_financing: cash = apply_financing_stress(cash)
                equity += cash; total_financing += cash
        if not isfinite(equity) or equity <= 0:
            raise ValueError("accounting path equity is non-finite or non-positive")
        if step.kind in ("gap_exit", "terminal"):
            if holding_start_equity is None: raise ValueError(f"{step.kind} without open holding period")
            period_returns.append(equity/holding_start_equity-1); holding_start_equity = None
        trades.append(TradeRecord(step.timestamp, step.kind, dict(step.target_weights), dict(positions), fills, cost))
        equities.append(equity); prior_opens = step.opens
    if holding_start_equity is not None:
        raise ValueError("accounting path must end flat")
    return AccountingPath(denominator, tuple(equities), tuple(period_returns), tuple(trades),
                          total_spread, total_financing)


def _dual(steps, inputs, *, spread_multiplier=1.0, adverse_financing=False):
    return {d: run_cadence_accounting_path(1.0, steps, inputs.financing_events, inputs.routes, d,
        spread_multiplier=spread_multiplier, adverse_financing=adverse_financing) for d in (360, 365)}


def _scenarios(steps, inputs):
    return {"base": _dual(steps, inputs), "adverse": _dual(steps, inputs, spread_multiplier=2, adverse_financing=True),
            "spread_x3": _dual(steps, inputs, spread_multiplier=3)}


def _accounting_view(steps: Sequence[CadenceStep]) -> tuple[AccountingStep, ...]:
    return tuple(AccountingStep(s.timestamp, s.target_weights, s.opens,
        "rebalance" if s.kind == "hold_mark" else s.kind) for s in steps)


BenchmarkKey = tuple[int, tuple[str, ...], tuple[str, ...]]


def _benchmark_evidence(inputs: CandidateInputs, book: Mapping[str, Sequence[str]], m: int):
    steps = static_cadence_steps(inputs.signal_steps, book, m); scenarios = _scenarios(steps, inputs)
    evidence = {}
    for denominator in (360, 365):
        base = scenarios["base"][denominator]
        evidence[str(denominator)] = {"rap": rap(base.period_returns),
            "max_drawdown": max_drawdown_from_returns(base.period_returns),
            "total_return": base.equities[-1]-1,
            "adverse_total_return": scenarios["adverse"][denominator].equities[-1]-1,
            "spread_x3_total_return": scenarios["spread_x3"][denominator].equities[-1]-1,
            "blocks": {block["block_id"]: {key: block[key] for key in ("rap", "max_drawdown", "total_return")}
                for block in path_block_diagnostics(base, inputs.signal_steps)}}
    return evidence


def cadence_benchmark_ensemble(inputs: CandidateInputs, books, m: int,
        *, cache: MutableMapping[BenchmarkKey, dict] | None = None) -> dict[str, object]:
    """Candidate-matched benchmark cadence; cache only identical book/cadence paths."""
    store = {} if cache is None else cache
    values = {str(d): {"rap": [], "max_drawdown": [], "total_return": [], "adverse_total_return": [],
        "spread_x3_total_return": [], "blocks": {b["block_id"]: {"rap": [], "max_drawdown": [],
        "total_return": []} for b in BLOCKS}} for d in (360, 365)}
    for book in books:
        key = (m, tuple(book["longs"]), tuple(book["shorts"]))
        evidence = store.get(key)
        if evidence is None:
            evidence = _benchmark_evidence(inputs, book, m); store[key] = evidence
        for denominator in (360, 365):
            target, item = values[str(denominator)], evidence[str(denominator)]
            for metric in ("rap", "max_drawdown", "total_return", "adverse_total_return", "spread_x3_total_return"):
                target[metric].append(item[metric])
            for block_id, block in item["blocks"].items():
                for metric in ("rap", "max_drawdown", "total_return"):
                    target["blocks"][block_id][metric].append(block[metric])
    medians = {}
    for denominator, target in values.items():
        medians[denominator] = {key: float(np.median(target[key])) for key in
            ("rap", "max_drawdown", "total_return", "adverse_total_return", "spread_x3_total_return")}
        medians[denominator]["blocks"] = {bid: {key: float(np.median(cell[key])) for key in cell}
            for bid, cell in target["blocks"].items()}
    return {"path_count": len(books), "distributions": values, "medians": medians}


def cadence_diagnostics(steps: Sequence[CadenceStep], records: Sequence[Mapping[str, object]]):
    actions = [{"timestamp": s.timestamp, "kind": s.kind, "execute": s.execute,
                "segment_index": r.get("segment_index")} for s, r in zip(steps, records)]
    executed = [a for a in actions if a["execute"] and a["kind"] not in ("gap_exit", "terminal")]
    gaps = [executed[i]["timestamp"]-executed[i-1]["timestamp"] for i in range(1, len(executed))]
    return {"action_schedule_sha256": _canonical_sha(actions), "actions": actions,
        "execute_count": len(executed), "hold_mark_count": sum(a["kind"] == "hold_mark" for a in actions),
        "forced_exit_count": sum(a["kind"] == "gap_exit" for a in actions),
        "gap_reentry_count": sum(a["kind"] == "gap_reentry" for a in actions),
        "terminal_flat_count": sum(a["kind"] == "terminal" for a in actions),
        "elapsed_days_between_executions": [x/86_400_000 for x in gaps]}


def _rotation_records(records):
    drop = {"segment_index", "action", "execute", "source_kind"}
    return tuple({key: value for key, value in record.items() if key not in drop} for record in records)


def _denominators(scenarios, inputs: CandidateInputs, benchmark):
    result = {}
    for denominator in (360, 365):
        base = path_diagnostics(scenarios["base"][denominator], inputs.signal_steps,
                                inputs.financing_events, inputs.routes)
        matched = benchmark["medians"][str(denominator)]
        result[str(denominator)] = {"base": base, "benchmark": matched,
            "benchmark_rap_excess": base["rap"]-matched["rap"],
            "benchmark_mdd_difference": base["max_drawdown"]-matched["max_drawdown"],
            "adverse_total_return": scenarios["adverse"][denominator].equities[-1]-1,
            "spread_x3_total_return": scenarios["spread_x3"][denominator].equities[-1]-1}
    return result


def cadence_study(inputs: CandidateInputs, m: int, reused_ic: Mapping[str, object]) -> dict[str, object]:
    """Complete future per-candidate evidence; caller controls execution authorization."""
    candidate_id = _candidate_id(m); steps, records = cadence_accounting_steps(inputs.signal_steps, m)
    scenarios = _scenarios(steps, inputs); books = family1_benchmark_books(U14.currencies, 4)
    cache: dict[BenchmarkKey, dict] = {}
    benchmark = cadence_benchmark_ensemble(inputs, books, m, cache=cache)
    denominators = _denominators(scenarios, inputs, benchmark); loco = {}
    for omitted in U14.currencies:
        active = tuple(c for c in U14.currencies if c != omitted)
        loco_steps, loco_records = cadence_accounting_steps(inputs.signal_steps, m, omitted=omitted)
        loco_scenarios = _scenarios(loco_steps, inputs); loco_books = family1_benchmark_books(active, 4)
        loco_benchmark = cadence_benchmark_ensemble(inputs, loco_books, m, cache=cache); cells = {}
        for denominator in (360, 365):
            d = str(denominator); matched = loco_benchmark["medians"][d]
            base = path_diagnostics(loco_scenarios["base"][denominator], inputs.signal_steps,
                                    inputs.financing_events, inputs.routes)
            cells[d] = {"base": base,
                "adverse_total_return": loco_scenarios["adverse"][denominator].equities[-1]-1,
                "spread_x3_total_return": loco_scenarios["spread_x3"][denominator].equities[-1]-1,
                "benchmark_rap": matched["rap"], "benchmark_max_drawdown": matched["max_drawdown"],
                "benchmark_adverse_total_return": matched["adverse_total_return"],
                "benchmark_spread_x3_total_return": matched["spread_x3_total_return"],
                "benchmark_rap_excess": base["rap"]-matched["rap"], "benchmark_blocks": matched["blocks"]}
        view = _accounting_view(loco_steps)
        loco[omitted] = {"N": 13, "k": 4, "benchmark_books_sha256": _canonical_sha(loco_books),
            "benchmark_economics_reused": False, "benchmark": loco_benchmark,
            "concentration": _concentration(view), "rotation": _rotation_diagnostics(_rotation_records(loco_records)),
            "weight_turnover": weight_turnover_diagnostics(view, inputs.signal_steps),
            "cadence": cadence_diagnostics(loco_steps, loco_records), "denominators": cells}
    view = _accounting_view(steps)
    return {"configuration_id": candidate_id, "m": m, "base_configuration": "EQ_H2", "h": 2,
        "N": 14, "k": 4, "currencies": list(U14.currencies), "currency_gross": 2,
        "benchmark_books_sha256": _canonical_sha(books), "benchmark_book_count": len(books),
        "benchmark_economics_reused": False, "benchmark": benchmark,
        "ic": dict(reused_ic), "ic_reused": True, "concentration": _concentration(view),
        "rotation": _rotation_diagnostics(_rotation_records(records)), "weight_turnover": weight_turnover_diagnostics(view, inputs.signal_steps),
        "cadence": cadence_diagnostics(steps, records), "denominators": denominators,
        "D365_MINUS_D360": _difference(denominators), "loco": loco,
        "candidate_disposition": "PENDING_EXTERNAL_ADJUDICATION"}


def _load_eq_h2(root: Path):
    result = _json(root/FAMILY3_RESULT_REL); completion = _json(root/FAMILY3_COMPLETION_REL)
    if result.get("status") != "PENDING_EXTERNAL_ADJUDICATION" or \
            completion.get("status") != "ECONOMICS_COMPLETED_PENDING_EXTERNAL_ADJUDICATION":
        raise IntegrityError("frozen Family-3 artifacts unavailable")
    control = result.get("control")
    if not isinstance(control, Mapping) or control.get("configuration_id") != "EQ_H2":
        raise IntegrityError("frozen EQ_H2 control unavailable")
    return control, control["ic"]


def _source_hashes(root: Path):
    paths = (PREREG_REL, Path("bot/forex/family4_cadence.py"), Path("run_family4_cadence.py"),
        Path("bot/forex/family3_weighting.py"), Path("bot/forex/family2_hysteresis.py"),
        Path("bot/forex/family1_study.py"), Path("bot/forex/family1_universe.py"),
        Path("bot/forex/stage_a_carry.py"), FAMILY3_READINESS_REL, FAMILY3_PARITY_REL,
        FAMILY3_RESULT_REL, FAMILY3_COMPLETION_REL)
    return {str(path).replace(chr(92), "/"): _sha256(root/path) for path in paths}


def build_readiness(root: Path, inputs: CandidateInputs | None = None):
    root = Path(root); context = load_frozen_context(root); inputs = inputs or prepare_candidate(context, U14)
    _, ic = _load_eq_h2(root); expected, _ = hysteresis_accounting_steps(inputs.signal_steps, 2)
    configurations = {}
    for candidate_id, m in CANDIDATE_CADENCES.items():
        steps, records = cadence_accounting_steps(inputs.signal_steps, m)
        for step in steps:
            gross = sum(abs(float(x)) for x in step.target_weights.values())
            if step.kind not in ("gap_exit", "terminal") and abs(gross-2) > NUMERIC_TOLERANCE:
                raise IntegrityError("Family-4 gross invariant failed")
        configurations[candidate_id] = {"m": m,
            "action_schedule_sha256": cadence_diagnostics(steps, records)["action_schedule_sha256"],
            "membership_sha256": _canonical_sha(accounting_membership_records(_accounting_view(steps))),
            "economic_outputs_computed": False}
    if _accounting_view(cadence_accounting_steps(inputs.signal_steps, 1)[0]) != expected:
        raise IntegrityError("M1 target path does not exactly preserve EQ_H2")
    books = family1_benchmark_books(U14.currencies, 4)
    static_schedules = {key: _canonical_sha([{"timestamp": s.timestamp, "kind": s.kind, "execute": s.execute}
        for s in static_cadence_steps(inputs.signal_steps, books[0], m)]) for key, m in CANDIDATE_CADENCES.items()}
    return {"schema_version": 1, "status": "FAMILY4_READINESS_PASSED", "network_accessed": False,
        "performance_computed": False, "preregistration_sha256": _sha256(root/PREREG_REL),
        "source_sha256": _source_hashes(root), "cache_sha256": dict(sorted(context.cache_sha256.items())),
        "family3_result_sha256": _sha256(root/FAMILY3_RESULT_REL),
        "family3_completion_sha256": _sha256(root/FAMILY3_COMPLETION_REL),
        "selected_base": "EQ_H2", "h": 2, "N": 14, "k": 4, "currency_gross": 2,
        "signal_step_count": len(inputs.signal_steps), "financing_event_count": len(inputs.financing_events),
        "financing_event_sha256": _canonical_sha(event_identity(inputs.financing_events)),
        "ic_reuse_only": True, "ic_sha256": _canonical_sha(ic),
        "benchmark_book_count": len(books), "benchmark_books_sha256": _canonical_sha(books),
        "matched_static_benchmark_cadence": True, "static_schedule_sha256": static_schedules,
        "configurations": configurations, "noncontrol_economics_authorized": False}


def emit_readiness(root: Path) -> Path:
    path = Path(root)/READINESS_REL; write_artifact(path, build_readiness(Path(root))); return path


def validate_readiness(root: Path):
    path = Path(root)/READINESS_REL; expected = build_readiness(Path(root))
    if not path.is_file() or _canonical_bytes(expected) != _canonical_bytes(_json(path)):
        raise IntegrityError("Family-4 readiness artifact identity mismatch")
    return _json(path)


def _parity_payload(study: Mapping[str, object]):
    loco = {currency: {key: value[key] for key in ("N", "k", "benchmark_books_sha256",
        "benchmark_economics_reused", "benchmark", "concentration", "rotation", "weight_turnover", "denominators")}
        for currency, value in study["loco"].items()}
    keys = ("N", "k", "currencies", "currency_gross", "benchmark_books_sha256", "benchmark_book_count",
        "benchmark_economics_reused", "benchmark", "ic", "ic_reused", "concentration", "rotation",
        "weight_turnover", "denominators", "D365_MINUS_D360", "candidate_disposition")
    return {key: study[key] for key in keys} | {"loco": loco}


def run_m1_parity(root: Path):
    root = Path(root); readiness = validate_readiness(root)
    inputs = prepare_candidate(load_frozen_context(root), U14); expected, ic = _load_eq_h2(root)
    expected_steps, expected_records = hysteresis_accounting_steps(inputs.signal_steps, 2)
    actual_steps, actual_records = cadence_accounting_steps(inputs.signal_steps, 1)
    discrete = _comparison_stats({"timestamps_kinds": [(s.timestamp, s.kind) for s in expected_steps],
        "memberships": accounting_membership_records(expected_steps), "rotation": expected_records,
        "routes": inputs.routes, "financing_events": event_identity(inputs.financing_events)},
        {"timestamps_kinds": [(s.timestamp, s.kind) for s in actual_steps],
        "memberships": accounting_membership_records(_accounting_view(actual_steps)),
        "rotation": _rotation_records(actual_records), "routes": inputs.routes,
        "financing_events": event_identity(inputs.financing_events)})
    if discrete["mismatch_count"]:
        raise IntegrityError("M1 discrete parity failed")
    study = cadence_study(inputs, 1, ic)
    numeric = _comparison_stats(_parity_payload(expected), _parity_payload(study))
    if numeric["mismatch_count"] or numeric["max_abs_difference"] > NUMERIC_TOLERANCE:
        raise IntegrityError("M1 numeric parity failed")
    if _canonical_sha(study["ic"]) != readiness["ic_sha256"]:
        raise IntegrityError("Family-4 IC reuse identity failed")
    return {"schema_version": 1, "status": "M1_CONTROL_PARITY_PASSED", "network_accessed": False,
        "noncontrol_economics_computed": False, "preregistration_sha256": _sha256(root/PREREG_REL),
        "readiness_artifact_sha256": _sha256(root/READINESS_REL),
        "family3_result_sha256": readiness["family3_result_sha256"],
        "discrete": {"exact": True, "comparison": discrete},
        "numeric": {"tolerance": NUMERIC_TOLERANCE, **numeric},
        "reused_evidence": {"ic_only": True, "ic_sha256": readiness["ic_sha256"]},
        "control_study": study, "candidate_disposition": "PENDING_EXTERNAL_ADJUDICATION"}


def emit_m1_parity(root: Path) -> Path:
    path = Path(root)/M1_PARITY_REL; write_artifact(path, run_m1_parity(Path(root))); return path


def execute_family4(root: Path) -> Path:
    """One-shot future execution; never called by readiness/parity."""
    root = Path(root); readiness = validate_readiness(root); parity_path = root/M1_PARITY_REL
    if not parity_path.is_file(): raise IntegrityError("M1 parity artifact required")
    parity = _json(parity_path)
    if parity.get("status") != "M1_CONTROL_PARITY_PASSED" or parity.get("numeric", {}).get("mismatch_count") != 0:
        raise IntegrityError("M1 parity has not passed")
    for path in (root/EXECUTION_REL, root/RESULT_REL, root/COMPLETION_REL):
        if path.exists(): raise PermissionError(f"Family-4 economics already consumed or started: {path}")
    execution = {"schema_version": 1, "status": "ECONOMICS_STARTED", "consumption_count": 1,
        "configuration_ids": ["M2", "M4"], "network_accessed": False,
        "preregistration_sha256": readiness["preregistration_sha256"],
        "readiness_artifact_sha256": _sha256(root/READINESS_REL), "m1_parity_sha256": _sha256(parity_path)}
    write_artifact(root/EXECUTION_REL, execution)
    inputs = prepare_candidate(load_frozen_context(root), U14); _, ic = _load_eq_h2(root)
    candidates = {key: cadence_study(inputs, m, ic) for key, m in CANDIDATE_CADENCES.items() if m != 1}
    result = {"schema_version": 1, "status": "PENDING_EXTERNAL_ADJUDICATION",
        "automatic_candidate_rejection_or_winner_selection": False,
        "adjudication_policy": ADJUDICATION_POLICY, "network_accessed": False,
        "execution_artifact_sha256": _sha256(root/EXECUTION_REL),
        "control": parity["control_study"], "candidates": candidates,
        "candidate_disposition": "PENDING_EXTERNAL_ADJUDICATION"}
    write_artifact(root/RESULT_REL, result)
    write_artifact(root/COMPLETION_REL, {"schema_version": 1,
        "status": "ECONOMICS_COMPLETED_PENDING_EXTERNAL_ADJUDICATION",
        "execution_artifact_sha256": result["execution_artifact_sha256"],
        "result_artifact_sha256": _sha256(root/RESULT_REL), "network_accessed": False})
    return root/RESULT_REL
