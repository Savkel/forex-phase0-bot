"""Frozen Family-6 carry/cost hurdle, readiness, and CONTROL-only parity."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import fsum, isfinite
from pathlib import Path
from typing import Mapping
import socket

from bot.forex.family1_study import _scenario_paths
from bot.forex.family1_universe import (
    NUMERIC_TOLERANCE, ParityAccumulator, U14, _canonical_bytes, _canonical_sha,
    _json, _sha256, event_identity, load_frozen_context, prepare_candidate,
)
from bot.forex.family4_cadence import CadenceStep, _accounting_view
from bot.forex.family5_breadth import (
    active_currencies, breadth_accounting_steps, equal_targets, exclusive_json,
    immutable_sources as f5_immutable_sources, select_memberships, validate_signals,
)
from bot.forex.family5_study import _assert_equal, _discrete_path, _payload
from bot.forex.stage_a_carry import (
    FinancingSchedule, OpenQuote, _quote_usd, currency_usd_values, fill_open,
    position_financing_cashflow_usd, rollover_multiplier, select_signal,
    solve_target_units,
)
from bot.forex.stage_a_orchestration import IntegrityError

STEM = "2026-09-22-tms-carry-unlevered-family-6-carry-cost-hurdle"
PREREG_REL = Path("prereg") / (STEM + "-prereg.md")
READINESS_REL = Path("prereg") / (STEM + "-readiness.json")
PARITY_REL = Path("prereg") / (STEM + "-control-parity.json")
PREREG_SHA256 = "38a75c3f821843e740401cc7255f83d621c8030ff013ba3170341ea534af6d1d"
FREEZE_COMMIT = "a34c0fec0ceaafd4f7fc05e9ae32fce544a8fb5d"
CANDIDATES = {"HURDLE_OFF_CONTROL": 0, "HURDLE_1X": 1, "HURDLE_2X": 2}

F5_READINESS = Path("prereg/2026-09-20-tms-carry-unlevered-family-5-portfolio-breadth-readiness.json")
F5_PARITY = Path("prereg/2026-09-20-tms-carry-unlevered-family-5-portfolio-breadth-k4-parity.json")
F5_CONTROL = Path("reports/forex/family5/family5-k4-control.json")
F5_HASHES = {
    str(F5_READINESS): "b24d796cb889d771d2be4540e55d68cbadfafaa62e6a792d39b20900f0da61e0",
    str(F5_PARITY): "eafe337788f6f67ed08a77abd95e335c57243fbb2ee98ab8ebb49c9b504e7a9b",
    str(F5_CONTROL): "e1518d90d3e78d52c53ee125181aa25ffa779637c3605b75b6030bd64a768137",
}
SOURCE_PATHS = ("bot/forex/family6_hurdle.py", "run_family6_hurdle.py",
                "tests/test_family6_hurdle.py")
SCENARIOS = ("base", "adverse", "spread_x3")


@dataclass(frozen=True)
class HurdleConfig:
    candidate_id: str
    h: int = 2
    k: int = 4
    m: int = 1
    weighting: str = "EQ"
    forecast_days: int = 7

    def __post_init__(self):
        if self.candidate_id not in CANDIDATES:
            raise ValueError("candidate must be one frozen Family-6 ID")
        if type(self.h) is not int or self.h != 2 or type(self.k) is not int or self.k != 4:
            raise ValueError("H2 and k=4 are frozen")
        if type(self.m) is not int or self.m != 1 or self.weighting != "EQ":
            raise ValueError("M1 and EQ are frozen")
        if type(self.forecast_days) is not int or self.forecast_days != 7:
            raise ValueError("forecast horizon is frozen at seven calendar days")

    @classmethod
    def from_mapping(cls, value):
        unknown = set(value) - set(cls.__dataclass_fields__)
        if unknown or "candidate_id" not in value:
            raise ValueError("unknown configuration keys or missing candidate_id")
        return cls(**value)

    @property
    def multiplier(self):
        return CANDIDATES[self.candidate_id]


@dataclass
class _Ledger:
    equity: float = 1.0
    positions: dict[str, float] = field(default_factory=dict)
    prior_opens: Mapping[str, OpenQuote] | None = None


def _ordered(scores, active):
    if set(scores) != set(U14.currencies) or any(not isfinite(float(v)) for v in scores.values()):
        raise IntegrityError("exact finite U14 scores required")
    return tuple(sorted(active, key=lambda c: (-float(scores[c]), c)))


def causal_schedules(context):
    """Reconstruct the already-selected causal schedule aligned to signal steps."""
    evaluable = {int(datetime.fromisoformat(x["decision_utc"].replace("Z", "+00:00")).timestamp()*1000)
                 for x in context.mask["evaluable_rebalances"]}
    excluded = {int(datetime.fromisoformat(x.replace("Z", "+00:00")).timestamp()*1000)
                for x in context.mask["excluded_rebalances"]}
    out = []
    previous = False
    for target in sorted(evaluable | excluded):
        decision = datetime.fromtimestamp(target/1000, tz=timezone.utc)
        if target in excluded:
            if previous:
                out.append(None)
            previous = False
            continue
        out.append(select_signal(context.schedules, decision))
        previous = True
    out.append(None)
    if len(out) != len(context.u14_signals):
        raise IntegrityError("causal schedule/signal alignment failed")
    for signal, schedule in zip(context.u14_signals, out):
        if (signal.scores is None) != (schedule is None):
            raise IntegrityError("causal schedule attached to forced transition")
    return tuple(out)


def _mark(ledger, opens):
    if ledger.prior_opens is not None:
        ledger.equity += fsum(q*(opens[p].mid-ledger.prior_opens[p].mid)*_quote_usd(p, opens)
                              for p, q in sorted(ledger.positions.items()))
    if not isfinite(ledger.equity) or ledger.equity <= 0:
        raise IntegrityError("invalid causal hurdle ledger equity")


def _target_cost(ledger, weights, routes, opens):
    target = solve_target_units(weights, ledger.equity, routes, opens)
    cost = fsum(abs(target.units.get(p, 0)-ledger.positions.get(p, 0))
                 * abs(fill_open(1 if target.units.get(p, 0)-ledger.positions.get(p, 0) > 0 else -1,
                                 opens[p].bid, opens[p].ask)-opens[p].mid)
                 * _quote_usd(p, opens)
                 for p in sorted(set(target.units) | set(ledger.positions))
                 if target.units.get(p, 0) != ledger.positions.get(p, 0))
    return target, cost


def _forecast(target, equity, schedule, opens, denominator):
    if schedule is None or denominator not in (360, 365):
        raise IntegrityError("causal schedule and frozen denominator required")
    cells = []
    for pair, units in sorted(target.units.items()):
        if not units:
            continue
        try:
            rate = schedule.rates[pair][0 if units > 0 else 1]
        except KeyError as exc:
            raise IntegrityError("forecast schedule lacks routed pair") from exc
        cells.append(abs(units)*opens[pair].mid*(rate/100/denominator)*7*_quote_usd(pair, opens))
    return fsum(cells)/equity


def hurdle_metrics(ledgers, a_weights, b_weights, routes, opens, schedule):
    """Same-snapshot A/B economics; no future schedule/event input is accepted."""
    dc = {}
    financing = {}
    targets = {}
    for denominator in (360, 365):
        ledger = ledgers[denominator]
        a_target, a_cost = _target_cost(ledger, a_weights, routes, opens)
        b_target, b_cost = _target_cost(ledger, b_weights, routes, opens)
        targets[denominator] = (a_target, b_target)
        dc[denominator] = (b_cost-a_cost)/ledger.equity
        financing[denominator] = {
            "A": _forecast(a_target, ledger.equity, schedule, opens, denominator),
            "B": _forecast(b_target, ledger.equity, schedule, opens, denominator),
        }
    benefit = min(financing[d]["B"]-financing[d]["A"] for d in (360, 365))
    hurdle_cost = max(0.0, dc[360], dc[365])
    return {"dc": dc, "financing": financing, "G": benefit, "K": hurdle_cost,
            "targets": targets}


def _execute_denominator(ledger, denominator, weights, routes, opens, events):
    target, cost = _target_cost(ledger, weights, routes, opens)
    ledger.equity -= cost
    ledger.positions = dict(target.units)
    for event in events:
        for pair, units in sorted(ledger.positions.items()):
            if not units or pair not in event.opens:
                continue
            days = rollover_multiplier(event.day, pair) if event.days_charged is None else event.days_charged
            ledger.equity += position_financing_cashflow_usd(
                event.schedule, pair, units, event.opens[pair].mid, denominator,
                days, _quote_usd(pair, event.opens))
    if not isfinite(ledger.equity) or ledger.equity <= 0:
        raise IntegrityError("invalid post-trade hurdle ledger equity")
    ledger.prior_opens = opens


def _proposal_row(signal, order, prior_longs, prior_shorts, fresh, evaluable_index, segment_index):
    n, k = len(order), 4
    ranks = {c: i+1 for i, c in enumerate(order)}
    control_longs, control_shorts = set(order[:k]), set(order[-k:])
    longs, shorts, retained_longs, retained_shorts = select_memberships(
        order, k, prior_longs, prior_shorts, fresh=fresh)
    outside_l = retained_longs-control_longs
    outside_s = retained_shorts-control_shorts
    displaced_l = control_longs-longs
    displaced_s = control_shorts-shorts
    if len(outside_l) != len(displaced_l) or len(outside_s) != len(displaced_s):
        raise IntegrityError("retained/displaced counts do not reconcile")
    rank_list = lambda values: [c for c in order if c in values]
    counted = not fresh and signal.kind == "rebalance"
    row = {"timestamp": signal.timestamp, "kind": signal.kind, "evaluable_index": evaluable_index,
        "segment_index": segment_index, "action": "execute", "execute": True,
        "state_reset": fresh, "counted_rotation": counted, "ranks": {c: ranks[c] for c in order},
        "prior_longs": rank_list(prior_longs), "prior_shorts": rank_list(prior_shorts),
        "retained_longs": rank_list(retained_longs), "retained_shorts": rank_list(retained_shorts),
        "exited_longs": rank_list(prior_longs-longs), "exited_shorts": rank_list(prior_shorts-shorts),
        "entered_longs": rank_list(longs-prior_longs), "entered_shorts": rank_list(shorts-prior_shorts),
        "final_longs": rank_list(longs), "final_shorts": rank_list(shorts),
        "retained_outside_control_longs": rank_list(outside_l),
        "retained_outside_control_shorts": rank_list(outside_s),
        "displaced_control_longs": rank_list(displaced_l),
        "displaced_control_shorts": rank_list(displaced_s),
        "actual_long_replacements": (k-len(prior_longs&longs)) if counted else 0,
        "actual_short_replacements": (k-len(prior_shorts&shorts)) if counted else 0,
        "suppressed_long_replacements": len(outside_l) if counted else 0,
        "suppressed_short_replacements": len(outside_s) if counted else 0,
        "suppressed_replacements": (len(outside_l)+len(outside_s)) if counted else 0,
        "avoided_long_replacements": len(outside_l) if counted else 0,
        "avoided_short_replacements": len(outside_s) if counted else 0,
        "avoided_replacements": (len(outside_l)+len(outside_s)) if counted else 0}
    return longs, shorts, row


def _forced_row(signal, prior_longs, prior_shorts):
    return {"timestamp": signal.timestamp, "kind": signal.kind, "evaluable_index": None,
        "segment_index": None, "action": signal.kind, "execute": True, "state_reset": True,
        "counted_rotation": False, "prior_longs": sorted(prior_longs),
        "prior_shorts": sorted(prior_shorts), "final_longs": [], "final_shorts": [],
        "suppressed_replacements": 0}


def hurdle_accounting_steps(signals, causal_schedule, financing_events, routes, config,
                            *, omitted=None, require_full=True):
    """Generate accepted targets while evolving only the two unstressed causal ledgers."""
    if not isinstance(config, HurdleConfig):
        raise TypeError("HurdleConfig required")
    if omitted not in (None, *U14.currencies) or len(signals) != len(causal_schedule):
        raise ValueError("invalid omission or schedule alignment")
    validate_signals(signals)
    active = active_currencies(omitted)
    by_step = {}
    for event in financing_events:
        by_step.setdefault(event.after_step, []).append(event)
    ledgers = {360: _Ledger(), 365: _Ledger()}
    prior_longs, prior_shorts = set(), set()
    steps, records = [], []
    evaluable_index = 0
    segment_index = None
    flat = {c: 0.0 for c in U14.currencies}
    for i, (signal, schedule) in enumerate(zip(signals, causal_schedule)):
        for ledger in ledgers.values():
            _mark(ledger, signal.opens)
        if signal.scores is None:
            h2 = _forced_row(signal, prior_longs, prior_shorts)
            steps.append(CadenceStep(signal.timestamp, dict(flat), signal.opens, signal.kind, True))
            records.append({"h2": h2, "hurdle_applied": False, "decision": signal.kind,
                            "accepted_longs": [], "accepted_shorts": []})
            for d, ledger in ledgers.items():
                _execute_denominator(ledger, d, flat, routes, signal.opens, by_step.get(i, ()))
            prior_longs.clear()
            prior_shorts.clear()
            segment_index = None
            continue
        segment_index = 0 if segment_index is None else segment_index+1
        order = _ordered(signal.scores, active)
        fresh = segment_index == 0 or signal.kind == "gap_reentry" or not prior_longs or not prior_shorts
        b_longs, b_shorts, h2 = _proposal_row(
            signal, order, prior_longs, prior_shorts, fresh, evaluable_index, segment_index)
        b_weights = equal_targets(b_longs, b_shorts, 4, active=active)
        changed = not fresh and (b_longs != prior_longs or b_shorts != prior_shorts)
        metrics = None
        if fresh:
            accepted_longs, accepted_shorts = b_longs, b_shorts
            decision = "fresh_accept"
        elif not changed:
            accepted_longs, accepted_shorts = prior_longs, prior_shorts
            decision = "unchanged_m1_reset"
        elif config.multiplier == 0:
            accepted_longs, accepted_shorts = b_longs, b_shorts
            decision = "control_accept"
        else:
            a_weights = equal_targets(prior_longs, prior_shorts, 4, active=active)
            metrics = hurdle_metrics(ledgers, a_weights, b_weights, routes, signal.opens, schedule)
            threshold = config.multiplier*metrics["K"]
            accepted = metrics["G"] >= threshold
            accepted_longs, accepted_shorts = ((b_longs, b_shorts) if accepted
                                                else (prior_longs, prior_shorts))
            decision = "hurdle_accept" if accepted else "hurdle_veto"
        weights = equal_targets(accepted_longs, accepted_shorts, 4, active=active)
        hurdle = None if metrics is None else {
            "dc": {str(d): metrics["dc"][d] for d in (360, 365)},
            "financing": {str(d): metrics["financing"][d] for d in (360, 365)},
            "G": metrics["G"], "K": metrics["K"],
            "threshold": config.multiplier*metrics["K"],
        }
        steps.append(CadenceStep(signal.timestamp, weights, signal.opens, signal.kind, True))
        records.append({"h2": h2, "hurdle_applied": metrics is not None, "decision": decision,
            "accepted_longs": [c for c in order if c in accepted_longs],
            "accepted_shorts": [c for c in order if c in accepted_shorts], "hurdle": hurdle})
        for d, ledger in ledgers.items():
            _execute_denominator(ledger, d, weights, routes, signal.opens, by_step.get(i, ()))
        prior_longs, prior_shorts = set(accepted_longs), set(accepted_shorts)
        evaluable_index += 1
    if require_full and evaluable_index != 157:
        raise IntegrityError("Family-6 requires 157 evaluable decisions")
    return tuple(steps), tuple(records)


@contextmanager
def offline():
    def denied(*args, **kwargs):
        raise PermissionError("Family-6 prohibits network access")
    saved = (socket.socket.connect, socket.socket.connect_ex,
             socket.create_connection, socket.getaddrinfo)
    socket.socket.connect = socket.socket.connect_ex = denied
    socket.create_connection = socket.getaddrinfo = denied
    try:
        yield
    finally:
        (socket.socket.connect, socket.socket.connect_ex,
         socket.create_connection, socket.getaddrinfo) = saved


def immutable_sources(root):
    root = Path(root)
    if _sha256(root/PREREG_REL) != PREREG_SHA256:
        raise IntegrityError("frozen Family-6 preregistration changed")
    sources = dict(f5_immutable_sources(root))
    sources[str(PREREG_REL).replace(chr(92), "/")] = PREREG_SHA256
    for rel, digest in F5_HASHES.items():
        if not (root/rel).is_file() or _sha256(root/rel) != digest:
            raise IntegrityError("immutable Family-5 evidence changed: " + rel)
        sources[str(Path(rel)).replace(chr(92), "/")] = digest
    for rel in SOURCE_PATHS:
        if not (root/rel).is_file():
            raise IntegrityError("Family-6 source missing: " + rel)
        sources[rel] = _sha256(root/rel)
    return dict(sorted(sources.items()))


def _f5_reuse(root):
    readiness = _json(Path(root)/F5_READINESS)
    parity = _json(Path(root)/F5_PARITY)
    control = _json(Path(root)/F5_CONTROL)["control_study"]
    if (parity.get("status") != "K4_CONTROL_PARITY_PASSED"
            or parity.get("parity", {}).get("mismatch_count") != 0):
        raise IntegrityError("immutable Family-5 parity is not valid")
    if parity.get("ic_sha256") != readiness.get("ic_sha256"):
        raise IntegrityError("Family-5 IC evidence identity mismatch")
    ic_sha = _canonical_sha(control["ic"])
    if ic_sha != readiness["ic_sha256"]:
        raise IntegrityError("Family-5 control IC payload mismatch")
    case_hashes = {}
    for omitted in (None, *U14.currencies):
        key = omitted or "FULL"
        stored = control if omitted is None else control["loco"][omitted]
        expected = readiness["configurations"]["K4_CONTROL"]["cases"][key]["benchmark_books_sha256"]
        if stored["benchmark_books_sha256"] != expected:
            raise IntegrityError("Family-5 benchmark identity mismatch: " + key)
        case_hashes[key] = {
            "books_sha256": expected,
            "benchmark_payload_sha256": _canonical_sha(stored["benchmark"]),
        }
    return readiness, parity, control, ic_sha, case_hashes


def build_readiness(root):
    root = Path(root)
    with offline():
        sources = immutable_sources(root)
        f5_ready, f5_parity, _, ic_sha, case_hashes = _f5_reuse(root)
        context = load_frozen_context(root)
        inputs = prepare_candidate(context, U14)
        schedules = causal_schedules(context)
        schedule_payload = [None if s is None else {
            "valid_from": s.valid_from.isoformat(), "valid_to": s.valid_to.isoformat(),
            "rates": {p: list(v) for p, v in sorted(s.rates.items())}}
            for s in schedules]
        configs = {cid: {"multiplier": multiplier, "h": 2, "k": 4, "m": 1,
            "weighting": "EQ", "forecast_days": 7, "historical_economics_computed": False}
            for cid, multiplier in CANDIDATES.items()}
        return {
            "schema_version": 1, "status": "FAMILY6_READINESS_PASSED",
            "freeze_commit": FREEZE_COMMIT, "preregistration_sha256": PREREG_SHA256,
            "source_sha256": sources,
            "cache_sha256": dict(sorted(context.cache_sha256.items())),
            "transaction_mapping_sha256": _canonical_sha(context.transaction_mapping),
            "signals_sha256": _canonical_sha([{"timestamp": s.timestamp, "kind": s.kind,
                "scores": s.scores} for s in inputs.signal_steps]),
            "routes_sha256": _canonical_sha(inputs.routes),
            "financing_event_sha256": _canonical_sha(event_identity(inputs.financing_events)),
            "causal_schedule_sha256": _canonical_sha(schedule_payload),
            "signal_count": len(inputs.signal_steps), "evaluable_count": 157,
            "forecast_semantics": {"days": 7, "schedule_held_fixed": True,
                "future_schedules_events_prices_quotes_read": False,
                "denominators": [360, 365], "K": "max(0,dc360,dc365)",
                "G": "min(f360(B)-f360(A),f365(B)-f365(A))"},
            "configurations": configs, "benchmark_reuse": case_hashes,
            "ic_sha256": ic_sha, "family5_readiness_sha256": F5_HASHES[str(F5_READINESS)],
            "family5_parity_sha256": F5_HASHES[str(F5_PARITY)],
            "family5_control_sha256": F5_HASHES[str(F5_CONTROL)],
            "family5_parity_mismatch_count": f5_parity["parity"]["mismatch_count"],
            "family5_ic_sha256": f5_ready["ic_sha256"],
            "performance_computed": False, "noncontrol_historical_economics_computed": False,
            "network_accessed": False, "stage_b_accessed": False,
        }


def emit_readiness(root):
    root = Path(root)
    value = build_readiness(root)
    path = root/READINESS_REL
    if path.exists():
        if _canonical_bytes(_json(path)) != _canonical_bytes(value):
            raise IntegrityError("existing Family-6 readiness differs")
        return path
    exclusive_json(path, value)
    return path


def validate_readiness(root):
    path = Path(root)/READINESS_REL
    if not path.is_file():
        raise IntegrityError("Family-6 readiness required")
    actual = _json(path)
    if _canonical_bytes(actual) != _canonical_bytes(build_readiness(root)):
        raise IntegrityError("Family-6 readiness/source/input hashes are stale")
    return actual


def run_control_parity(root):
    """Recompute CONTROL strategy evidence only; benchmark/IC economics are hash-reused."""
    root = Path(root)
    with offline():
        readiness = validate_readiness(root)
        if (root/PARITY_REL).exists():
            raise PermissionError("Family-6 CONTROL parity already exists")
        context = load_frozen_context(root)
        inputs = prepare_candidate(context, U14)
        schedules = causal_schedules(context)
        _, f5_parity, _, ic_sha, case_hashes = _f5_reuse(root)
        accumulator = ParityAccumulator()
        signal_values = [currency_usd_values(s.opens) for s in inputs.signal_steps]
        event_values = [currency_usd_values(e.opens) for e in inputs.financing_events]
        for omitted in (None, *U14.currencies):
            actual_steps, records = hurdle_accounting_steps(
                inputs.signal_steps, schedules, inputs.financing_events, inputs.routes,
                HurdleConfig("HURDLE_OFF_CONTROL"), omitted=omitted)
            expected_steps, expected_records = breadth_accounting_steps(
                inputs.signal_steps, 4, omitted=omitted)
            _assert_equal(expected_records, tuple(r["h2"] for r in records), accumulator,
                          "membership_state_records", discrete=True)
            _assert_equal([s.__dict__ | {"opens": None} for s in expected_steps],
                          [s.__dict__ | {"opens": None} for s in actual_steps],
                          accumulator, "strategy_targets_actions", discrete=True)
            expected_paths = _scenario_paths(
                _accounting_view(expected_steps), inputs.financing_events, inputs.routes)
            actual_paths = _scenario_paths(
                _accounting_view(actual_steps), inputs.financing_events, inputs.routes)
            for scenario in SCENARIOS:
                for denominator in (360, 365):
                    expected = _payload(expected_paths[scenario][denominator], inputs, scenario,
                                        signal_values, event_values)
                    actual = _payload(actual_paths[scenario][denominator], inputs, scenario,
                                      signal_values, event_values)
                    _assert_equal(_discrete_path(expected), _discrete_path(actual), accumulator,
                                  "strategy_discrete_paths", discrete=True)
                    _assert_equal(expected, actual, accumulator,
                                  "strategy_full_paths_and_components")
        _assert_equal(readiness["benchmark_reuse"], case_hashes, accumulator,
                      "benchmark_reuse_hashes", discrete=True)
        _assert_equal(readiness["ic_sha256"], ic_sha, accumulator,
                      "ic_reuse_hash", discrete=True)
        if immutable_sources(root) != readiness["source_sha256"]:
            raise IntegrityError("source changed during Family-6 parity")
        report = accumulator.report()
        totals = {key: sum(int(cell[key]) for cell in report["cells"].values()) for key in
                  ("numeric_values_compared", "discrete_values_compared",
                   "numeric_mismatch_count", "discrete_mismatch_count",
                   "shape_mismatch_count")}
        artifact = {
            "schema_version": 1, "status": "FAMILY6_CONTROL_PARITY_PASSED",
            "freeze_commit": FREEZE_COMMIT, "preregistration_sha256": PREREG_SHA256,
            "readiness_sha256": _sha256(root/READINESS_REL),
            "source_sha256": readiness["source_sha256"],
            "scope": {"candidate": "HURDLE_OFF_CONTROL", "full_cases": 1,
                "loco_cases": 14, "scenarios": list(SCENARIOS),
                "denominators": [360, 365], "strategy_paths": 90,
                "noncontrol_historical_paths": 0,
                "benchmark_economics": "HASH_REUSED_IMMUTABLE_FAMILY5_K4",
                "ic_evidence": "HASH_REUSED_IMMUTABLE_FAMILY5_K4"},
            "parity": {**report, **totals},
            "benchmark_reuse": case_hashes, "ic_sha256": ic_sha,
            "family5_parity_sha256": F5_HASHES[str(F5_PARITY)],
            "family5_parity_counts": {key: f5_parity["parity"][key] for key in
                ("numeric_values_compared", "discrete_values_compared", "mismatch_count",
                 "max_abs_difference")},
            "noncontrol_historical_economics_computed": False,
            "network_accessed": False, "stage_b_accessed": False,
        }
        if report["mismatch_count"] or report["max_abs_difference"] > NUMERIC_TOLERANCE:
            raise IntegrityError("Family-6 CONTROL parity failed")
        exclusive_json(root/PARITY_REL, artifact)
        return root/PARITY_REL
