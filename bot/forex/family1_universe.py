"""Family-1 universe infrastructure.

This module parameterizes the frozen Stage-A carry mechanics without modifying them.  Candidate
preflight reads only frozen financing metadata and existing H1 caches.  The only economic entry
point is :func:`run_u14_parity`; G10/U8 economic execution is intentionally absent.
"""
from __future__ import annotations

import bisect
import hashlib
import itertools
import json
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal, ROUND_HALF_UP
from math import comb, isfinite
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from bot.forex.stage_a_carry import (
    AccountingPath,
    AccountingStep,
    FinancingEvent,
    FinancingSchedule,
    FrozenDecision,
    OpenQuote,
    SignalStep,
    accounting_steps_from_signals,
    benchmark_books,
    build_causal_signal_steps,
    build_financing_events,
    currency_spot_log_returns,
    currency_usd_values,
    currency_targets,
    max_drawdown_from_returns,
    pair_positions,
    position_financing_cashflow_usd,
    rap,
    run_adverse_dual_accounting_paths,
    run_dual_accounting_paths,
    run_spread3_sensitivity_paths,
    select_signal,
    spearman_ic,
    spot_ic_series,
    stationary_bootstrap_lower_bound,
    rollover_multiplier,
)
from bot.forex.stage_a_orchestration import IntegrityError, _required_financing_open_days
from bot.forex.stage_a_preflight import FROZEN_SHA256, project_preflight


PREREG_REL = Path("prereg/2026-08-21-tms-carry-unlevered-family-1-universe-prereg.md")
STAGE_A_UNIVERSE_REL = Path("prereg/2026-08-14-tms-carry-no-try-direct-gbp-universe.json")
STAGE_A_MASK_REL = Path("prereg/2026-08-14-tms-carry-no-try-direct-gbp-mask.json")
STAGE_A_READINESS_REL = Path("prereg/2026-08-14-tms-carry-no-try-direct-gbp-price-readiness.json")
STAGE_A_FINANCING_REL = Path("data/tms_swap_archive/derived/parsed_all.json")
STAGE_A_FINANCING_READINESS_REL = Path("prereg/2026-08-14-tms-carry-financing-readiness.json")
STAGE_A_RESULT_REL = Path(
    "reports/forex/stage_a/"
    "stage-a-bd220eee501ac81388c78d64878458d2393718e4e458c04d8aafaae945a180f6."
    "attempt-03.result.json"
)
UNIVERSE_ARTIFACT_REL = Path("prereg/2026-08-21-tms-carry-unlevered-family-1-universe.json")
READINESS_ARTIFACT_REL = Path("prereg/2026-08-21-tms-carry-unlevered-family-1-readiness.json")
PARITY_ARTIFACT_REL = Path("prereg/2026-08-21-tms-carry-unlevered-family-1-u14-parity.json")
EXECUTION_ARTIFACT_REL = Path("prereg/2026-08-21-tms-carry-unlevered-family-1-execution.json")
RESULT_ARTIFACT_REL = Path("reports/forex/family1/family1-universe-result.json")
COMPLETION_ARTIFACT_REL = Path("reports/forex/family1/family1-universe-completion.json")

BENCHMARK_SEED = 20260809
BOOTSTRAP_SEED = 20260808
NUMERIC_TOLERANCE = 1e-12
ANNUALIZATION_DAYS = 365.25


@dataclass(frozen=True)
class UniverseDefinition:
    candidate_id: str
    currencies: tuple[str, ...]
    k: int

    def validate(self) -> None:
        if tuple(sorted(self.currencies)) != self.currencies:
            raise ValueError(f"{self.candidate_id}: currencies must be ISO sorted")
        if self.k != len(self.currencies) // 3 or 2 * self.k > len(self.currencies):
            raise ValueError(f"{self.candidate_id}: frozen floor(N/3) rule violated")
        if "TRY" in self.currencies:
            raise ValueError(f"{self.candidate_id}: TRY is excluded")


U14 = UniverseDefinition(
    "U14_CONTROL",
    ("AUD", "CAD", "CHF", "CZK", "EUR", "GBP", "HUF", "JPY", "NOK", "NZD", "PLN", "SEK", "USD", "ZAR"),
    4,
)
G10 = UniverseDefinition(
    "G10", ("AUD", "CAD", "CHF", "EUR", "GBP", "JPY", "NOK", "NZD", "SEK", "USD"), 3
)
U8 = UniverseDefinition(
    "U8_LIQUID_MAJORS", ("AUD", "CAD", "CHF", "EUR", "GBP", "JPY", "NZD", "USD"), 2
)
UNIVERSES = {item.candidate_id: item for item in (U14, G10, U8)}

BLOCKS = (
    {"block_id": "B1", "start": 0, "stop": 52,
     "nominal_start": "2023-04-03T00:00:00Z", "nominal_stop": "2024-06-03T00:00:00Z"},
    {"block_id": "B2", "start": 52, "stop": 104,
     "nominal_start": "2024-06-03T00:00:00Z", "nominal_stop": "2025-06-23T00:00:00Z"},
    {"block_id": "B3", "start": 104, "stop": 157,
     "nominal_start": "2025-06-23T00:00:00Z", "nominal_stop": "2026-08-03T00:00:00Z"},
)


@dataclass(frozen=True)
class FrozenContext:
    root: Path
    universe: Mapping[str, object]
    mask: Mapping[str, object]
    readiness: Mapping[str, object]
    schedules: tuple[FinancingSchedule, ...]
    u14_signals: tuple[SignalStep, ...]
    routes: Mapping[str, object]
    availability: Mapping[str, set[int]]
    transaction_mapping: tuple[tuple[int, int], ...]
    cache_paths: Mapping[str, Path]
    cache_sha256: Mapping[str, str]
    opens_at: Callable[[int, set[str] | None], Mapping[str, OpenQuote]]


@dataclass(frozen=True)
class CandidateInputs:
    definition: UniverseDefinition
    signal_steps: tuple[SignalStep, ...]
    routes: Mapping[str, object]
    financing_days: Mapping[date, Mapping[str, OpenQuote]]
    financing_events: tuple[FinancingEvent, ...]
    financing_records: tuple[Mapping[str, object], ...]


def _json(path: Path) -> object:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _pair_currencies(pair: str) -> tuple[str, str]:
    symbol = pair.split(".")[0].replace("_", "")
    if len(symbol) != 6:
        raise ValueError(f"invalid FX pair: {pair}")
    return symbol[:3], symbol[3:]


def benchmark_space_size(n: int, k: int) -> int:
    if n < 1 or k < 1 or 2 * k > n:
        raise ValueError("invalid benchmark N/k")
    return comb(n, k) * comb(n - k, k)


def family1_benchmark_books(currencies: Sequence[str], k: int) -> list[dict[str, tuple[str, ...]]]:
    ordered = tuple(sorted(currencies))
    if len(set(ordered)) != len(ordered):
        raise ValueError("benchmark currencies must be unique")
    size = benchmark_space_size(len(ordered), k)
    if size <= 1000:
        books = []
        for longs in itertools.combinations(ordered, k):
            remaining = tuple(c for c in ordered if c not in longs)
            for shorts in itertools.combinations(remaining, k):
                books.append({"longs": longs, "shorts": shorts})
        if len(books) != size or len({(x["longs"], x["shorts"]) for x in books}) != size:
            raise AssertionError("exhaustive benchmark enumeration is incomplete")
        return books
    return benchmark_books(ordered, k, 1000, BENCHMARK_SEED)


def validate_blocks(mask: Mapping[str, object]) -> tuple[dict[str, object], ...]:
    rows = list(mask["evaluable_rebalances"])
    if len(rows) != 157:
        raise IntegrityError("Family-1 requires exactly 157 evaluable periods")
    result = []
    for raw in BLOCKS:
        start, stop = int(raw["start"]), int(raw["stop"])
        if rows[start]["decision_utc"] != raw["nominal_start"] or rows[stop - 1]["hold_end_utc"] != raw["nominal_stop"]:
            raise IntegrityError(f"{raw['block_id']}: frozen chronological boundary mismatch")
        result.append({**raw, "count": stop - start})
    if [x for block in result for x in range(block["start"], block["stop"])] != list(range(157)):
        raise IntegrityError("chronological blocks do not partition all periods")
    return tuple(result)


def period_bounds(signals: Sequence[SignalStep]) -> tuple[tuple[int, int], ...]:
    bounds = tuple((start.timestamp, end.timestamp)
                   for start, end in zip(signals, signals[1:]) if start.scores is not None)
    if len(bounds) != 157 or any(start >= stop for start, stop in bounds):
        raise IntegrityError("Family-1 period bounds must contain 157 ordered evaluable intervals")
    return bounds


def path_block_diagnostics(path: AccountingPath, signals: Sequence[SignalStep]) -> tuple[dict[str, object], ...]:
    if len(path.period_returns) != 157:
        raise IntegrityError("Family-1 block diagnostics require 157 accounting returns")
    bounds = period_bounds(signals)
    result = []
    for block in BLOCKS:
        start, stop = int(block["start"]), int(block["stop"])
        returns = tuple(float(x) for x in path.period_returns[start:stop])
        years = (bounds[stop - 1][1] - bounds[start][0]) / 1000 / (ANNUALIZATION_DAYS * 24 * 60 * 60)
        total_return = float(np.prod(1 + np.asarray(returns, dtype=float)) - 1)
        result.append({
            "block_id": block["block_id"], "count": len(returns),
            "start_timestamp": bounds[start][0], "stop_timestamp": bounds[stop - 1][1],
            "elapsed_years": years, "total_return": total_return,
            "cagr": (1 + total_return) ** (1 / years) - 1,
            "rap": rap(returns), "max_drawdown": max_drawdown_from_returns(returns),
        })
    return tuple(result)


def benchmark_block_medians(
    paths: Sequence[AccountingPath], signals: Sequence[SignalStep]
) -> tuple[dict[str, object], ...]:
    if not paths:
        raise ValueError("at least one benchmark path is required")
    diagnostics = [path_block_diagnostics(path, signals) for path in paths]
    return tuple({
        "block_id": BLOCKS[index]["block_id"], "path_count": len(paths),
        "median_rap": float(np.median([item[index]["rap"] for item in diagnostics])),
        "median_max_drawdown": float(np.median([item[index]["max_drawdown"] for item in diagnostics])),
    } for index in range(len(BLOCKS)))


def _cache_paths(root: Path, readiness: Mapping[str, object]) -> dict[str, Path]:
    start = pd.Timestamp(readiness["required_window_utc"][0]).value // 10**6
    end = pd.Timestamp(readiness["required_window_utc"][1]).value // 10**6
    return {
        leg["v20_instrument"]: root / "data/forex_ohlcv" / f"{leg['v20_instrument']}__H1__BA__a0__w{start}-{end}.csv"
        for leg in readiness["routed_legs"]
    }


def load_frozen_context(root: Path) -> FrozenContext:
    """Load frozen sources and existing caches without computing any economic quantity."""
    root = Path(root)
    preflight = project_preflight(root)
    if preflight.get("performance_computed") is not False or preflight.get("execution_eligible") is not False:
        raise IntegrityError("Stage-A metadata preflight crossed an economic boundary")
    universe = _json(root / STAGE_A_UNIVERSE_REL)
    mask = _json(root / STAGE_A_MASK_REL)
    readiness = _json(root / STAGE_A_READINESS_REL)
    parsed = _json(root / STAGE_A_FINANCING_REL)
    validate_blocks(mask)
    for item in UNIVERSES.values():
        item.validate()
    if tuple(universe["currencies"]) != U14.currencies or universe["k_per_leg"] != U14.k:
        raise IntegrityError("frozen Stage-A universe differs from Family-1 U14 control")

    schedules = []
    for record in parsed.values():
        schedules.append(FinancingSchedule(
            date.fromisoformat(record["valid_from"]), date.fromisoformat(record["valid_to"]),
            {pair: (float(values[0]), float(values[1])) for pair, values in record["rows"].items()},
        ))

    paths = _cache_paths(root, readiness)
    frames: dict[str, pd.DataFrame] = {}
    hashes = {}
    timestamp_sets = []
    for leg in readiness["routed_legs"]:
        name, path = leg["v20_instrument"], paths[leg["v20_instrument"]]
        if not path.is_file() or _sha256(path) != leg["sha256"]:
            raise IntegrityError(f"{name}: frozen cache identity mismatch")
        frame = pd.read_csv(path, usecols=["open_time", "complete", "bid_o", "ask_o"])
        frame = frame[frame["complete"].astype(str).str.lower().eq("true")].set_index("open_time")
        if not frame.index.is_unique:
            raise IntegrityError(f"{name}: duplicate complete H1 timestamps")
        frame.index = frame.index.astype("int64")
        frames[name] = frame
        hashes[name] = leg["sha256"]
        timestamp_sets.append(set(map(int, frame.index)))

    targets = sorted({
        int(pd.Timestamp(row[key]).value // 10**6)
        for row in mask["evaluable_rebalances"] for key in ("decision_utc", "hold_end_utc")
    })
    if len(targets) != 168:
        raise IntegrityError("frozen mask must resolve to 168 transaction targets")
    common = sorted(set.intersection(*timestamp_sets))
    mapping = []
    for target in targets:
        index = bisect.bisect_left(common, target)
        if index == len(common) or common[index] - target > 48 * 3_600_000:
            raise IntegrityError("missing frozen common execution timestamp")
        mapping.append((target, common[index]))
    resolved = dict(mapping)
    tms_by_v20 = {x["v20_instrument"]: x["tms_instrument"] for x in readiness["routed_legs"]}

    def opens_at(timestamp: int, required: set[str] | None = None) -> dict[str, OpenQuote]:
        result = {}
        for name, frame in frames.items():
            tms = tms_by_v20[name]
            if required is not None and tms not in required:
                continue
            if timestamp not in frame.index:
                raise IntegrityError(f"missing H1 OPEN: {name}/{timestamp}")
            row = frame.loc[timestamp]
            result[tms] = OpenQuote(float(row["bid_o"]), float(row["ask_o"]))
        return result

    evaluable = {int(pd.Timestamp(x["decision_utc"]).value // 10**6): x for x in mask["evaluable_rebalances"]}
    excluded = {int(pd.Timestamp(x).value // 10**6) for x in mask["excluded_rebalances"]}
    decisions = []
    for target in sorted(set(evaluable) | excluded):
        execution = resolved[target]
        dt = datetime.fromtimestamp(target / 1000, tz=timezone.utc)
        is_evaluable = target in evaluable
        if is_evaluable and datetime.fromtimestamp(execution / 1000, tz=timezone.utc).date() <= select_signal(schedules, dt).valid_to:
            raise IntegrityError("Family-1 signal/fill look-ahead violation")
        decisions.append(FrozenDecision(dt, is_evaluable, [{execution} for _ in frames], {execution: opens_at(execution)}))
    terminal_target = int(pd.Timestamp(mask["last_hold_end_utc"]).value // 10**6)
    terminal_execution = resolved[terminal_target]
    decisions.append(FrozenDecision(
        datetime.fromtimestamp(terminal_target / 1000, tz=timezone.utc), False,
        [{terminal_execution} for _ in frames], {terminal_execution: opens_at(terminal_execution)}, terminal=True,
    ))
    subgraph = universe["representation_gate"]["over_identified_subgraph"]["currency_list"]
    signals = build_causal_signal_steps(
        decisions, schedules, universe["currencies"], universe["investable_financing_pairs"], subgraph, k=4
    )
    availability = {tms_by_v20[name]: set(map(int, frame.index)) for name, frame in frames.items()}
    return FrozenContext(
        root, universe, mask, readiness, tuple(schedules), tuple(signals), universe["routes"], availability,
        tuple(mapping), paths, hashes, opens_at,
    )


def candidate_signal_steps(signals: Sequence[SignalStep], definition: UniverseDefinition) -> tuple[SignalStep, ...]:
    definition.validate()
    result = []
    for step in signals:
        scores = None if step.scores is None else {c: float(step.scores[c]) for c in definition.currencies}
        if scores is not None:
            weights = currency_targets(scores, definition.k)
            if abs(sum(weights.values())) > NUMERIC_TOLERANCE or abs(sum(map(abs, weights.values())) - 2) > NUMERIC_TOLERANCE:
                raise IntegrityError(f"{definition.candidate_id}: weight/gross invariant failed")
        result.append(SignalStep(step.timestamp, scores, step.opens, step.kind))
    return tuple(result)


def candidate_routes(routes: Mapping[str, object], definition: UniverseDefinition) -> dict[str, object]:
    result = {currency: routes[currency] for currency in definition.currencies}
    if result.get("GBP", {}).get("legs") != [["GBPUSD.pro", 1]]:
        raise IntegrityError("Family-1 GBP route is not direct/exclusive")
    return result


def candidate_accounting_steps(signals: Sequence[SignalStep], definition: UniverseDefinition) -> tuple[AccountingStep, ...]:
    steps = []
    for signal in signals:
        weights = ({c: 0.0 for c in definition.currencies} if signal.scores is None
                   else currency_targets(signal.scores, definition.k))
        steps.append(AccountingStep(signal.timestamp, weights, signal.opens, signal.kind))
    return tuple(steps)


def _financing_requirements(
    signals: Sequence[SignalStep], definition: UniverseDefinition, routes: Mapping[str, object],
    availability: Mapping[str, set[int]], opens_at: Callable[[int, set[str] | None], Mapping[str, OpenQuote]],
) -> tuple[dict[date, Mapping[str, OpenQuote]], tuple[dict[str, object], ...]]:
    days: dict[date, Mapping[str, OpenQuote]] = {}
    records = []
    for after_step, (start, end) in enumerate(zip(signals, signals[1:])):
        if start.scores is None:
            continue
        weights = currency_targets(start.scores, definition.k)
        held = set(pair_positions(weights, routes))
        union = set().union(*(availability[p] for p in held)) if held else set()
        for timestamp in sorted(union):
            instant = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
            if not (start.timestamp <= timestamp < end.timestamp and instant.time() == time(21) and instant.weekday() < 5):
                continue
            eligible = {p for p in held if timestamp in availability[p]}
            conversions = {"EURUSD.pro"} if any(p.startswith("EUR") and p != "EURUSD.pro" for p in eligible) else set()
            required = eligible | conversions
            missing = sorted(p for p in required if timestamp not in availability[p])
            if missing:
                raise IntegrityError(f"missing required financing OPEN at {timestamp}: {missing[0]}")
            day = instant.date()
            payload = opens_at(timestamp, required)
            days[day] = payload
            records.append({
                "after_step": after_step, "day": day.isoformat(), "timestamp": timestamp,
                "held_routes": sorted(held), "venue_evidenced_routes": sorted(eligible),
                "conversion_routes": sorted(conversions), "required_routes": sorted(required),
            })
    return days, tuple(records)


def prepare_candidate(context: FrozenContext, definition: UniverseDefinition) -> CandidateInputs:
    signals = candidate_signal_steps(context.u14_signals, definition)
    routes = candidate_routes(context.routes, definition)
    days, records = _financing_requirements(signals, definition, routes, context.availability, context.opens_at)
    events = tuple(build_financing_events(signals, context.schedules, days))
    return CandidateInputs(definition, signals, routes, days, events, records)


def membership_records(inputs: CandidateInputs) -> tuple[dict[str, object], ...]:
    result = []
    for step in inputs.signal_steps:
        if step.scores is None:
            continue
        weights = currency_targets(step.scores, inputs.definition.k)
        result.append({
            "timestamp": step.timestamp,
            "longs": sorted(c for c, value in weights.items() if value > 0),
            "shorts": sorted(c for c, value in weights.items() if value < 0),
        })
    return tuple(result)


def accounting_membership_records(steps: Sequence[AccountingStep]) -> tuple[dict[str, object], ...]:
    result = []
    for step in steps:
        longs = sorted(c for c, value in step.target_weights.items() if value > 0)
        shorts = sorted(c for c, value in step.target_weights.items() if value < 0)
        if longs or shorts:
            result.append({"timestamp": step.timestamp, "longs": longs, "shorts": shorts})
    return tuple(result)


def event_identity(events: Sequence[FinancingEvent]) -> tuple[dict[str, object], ...]:
    return tuple({
        "after_step": event.after_step, "day": event.day.isoformat(),
        "schedule_valid_from": event.schedule.valid_from.isoformat(),
        "schedule_valid_to": event.schedule.valid_to.isoformat(),
        "open_routes": sorted(event.opens), "days_charged": event.days_charged,
        "effective_days_charged_by_open_route": {
            pair: (rollover_multiplier(event.day, pair) if event.days_charged is None else event.days_charged)
            for pair in sorted(event.opens)
        },
    } for event in events)


def loco_definitions(definition: UniverseDefinition) -> tuple[dict[str, object], ...]:
    k = (len(definition.currencies) - 1) // 3
    return tuple({
        "omitted": omitted,
        "rankable": [c for c in definition.currencies if c != omitted],
        "latent_columns": list(U14.currencies),
        "N": len(definition.currencies) - 1,
        "k": k,
        "benchmark_space": benchmark_space_size(len(definition.currencies) - 1, k),
        "benchmark_rule": "EXHAUSTIVE" if benchmark_space_size(len(definition.currencies) - 1, k) <= 1000 else "SEEDED_1000",
    } for omitted in definition.currencies)


def _source_hashes(root: Path) -> dict[str, str]:
    paths = (
        PREREG_REL, STAGE_A_UNIVERSE_REL, STAGE_A_MASK_REL, STAGE_A_READINESS_REL,
        STAGE_A_FINANCING_REL, STAGE_A_FINANCING_READINESS_REL,
        Path("bot/forex/family1_universe.py"), Path("bot/forex/family1_study.py"), Path("run_family1_universe.py"),
        Path("requirements.txt"),
    )
    return {str(path).replace("\\", "/"): _sha256(root / path) for path in paths}


def build_universe_artifact(root: Path) -> dict[str, object]:
    root = Path(root)
    mask = _json(root / STAGE_A_MASK_REL)
    return {
        "schema_version": 1,
        "status": "FAMILY1_UNIVERSE_FROZEN",
        "preregistration": str(PREREG_REL).replace("\\", "/"),
        "preregistration_sha256": _sha256(root / PREREG_REL),
        "stage_a_source_sha256": {key: FROZEN_SHA256[key] for key in ("universe", "mask", "readiness", "financing")},
        "annualization_days": ANNUALIZATION_DAYS,
        "currency_gross": 2,
        "candidates": {
            item.candidate_id: {
                "currencies": list(item.currencies), "N": len(item.currencies), "k": item.k,
                "weight_per_selected_currency": 1 / item.k,
                "benchmark_space": benchmark_space_size(len(item.currencies), item.k),
                "benchmark_rule": "EXHAUSTIVE" if benchmark_space_size(len(item.currencies), item.k) <= 1000 else "SEEDED_1000",
                "loco": list(loco_definitions(item)),
            } for item in UNIVERSES.values()
        },
        "chronological_blocks": list(validate_blocks(mask)),
        "economic_execution_authorized": False,
        "candidate_disposition": "PENDING_EXTERNAL_ADJUDICATION",
    }


def build_readiness_artifact(root: Path, context: FrozenContext | None = None) -> dict[str, object]:
    root = Path(root)
    context = context or load_frozen_context(root)
    candidates = {}
    for definition in UNIVERSES.values():
        inputs = prepare_candidate(context, definition)
        memberships = membership_records(inputs)
        identities = event_identity(inputs.financing_events)
        candidates[definition.candidate_id] = {
            "N": len(definition.currencies), "k": definition.k,
            "routes": {c: inputs.routes[c] for c in definition.currencies},
            "signal_membership_count": len(memberships),
            "signal_membership_sha256": _canonical_sha(memberships),
            "financing_event_count": len(identities),
            "financing_event_identity_sha256": _canonical_sha(identities),
            "venue_evidenced_held_pair_events": sum(len(x["venue_evidenced_routes"]) for x in inputs.financing_records),
            "required_input_missing_count": 0,
            "benchmark_space": benchmark_space_size(len(definition.currencies), definition.k),
            "benchmark_rule": "EXHAUSTIVE" if benchmark_space_size(len(definition.currencies), definition.k) <= 1000 else "SEEDED_1000",
        }
    universe_artifact = build_universe_artifact(root)
    return {
        "schema_version": 1,
        "status": "FAMILY1_READINESS_PASSED",
        "performance_computed": False,
        "network_accessed": False,
        "preregistration_sha256": _sha256(root / PREREG_REL),
        "universe_artifact_sha256": _canonical_sha(universe_artifact),
        "source_sha256": _source_hashes(root),
        "cache_sha256": dict(sorted(context.cache_sha256.items())),
        "transaction_count": len(context.transaction_mapping),
        "transaction_mapping_sha256": _canonical_sha(context.transaction_mapping),
        "candidates": candidates,
        "candidate_economics_authorized": False,
    }


def write_artifact(path: Path, value: object) -> None:
    path = Path(path)
    payload = json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != payload:
        raise FileExistsError(f"refusing to overwrite differing artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8", newline="\n")


def emit_readiness_artifacts(root: Path) -> tuple[Path, Path]:
    root = Path(root)
    context = load_frozen_context(root)
    universe = build_universe_artifact(root)
    readiness = build_readiness_artifact(root, context)
    universe_path, readiness_path = root / UNIVERSE_ARTIFACT_REL, root / READINESS_ARTIFACT_REL
    write_artifact(universe_path, universe)
    write_artifact(readiness_path, readiness)
    return universe_path, readiness_path


def validate_readiness_artifacts(root: Path) -> dict[str, object]:
    root = Path(root)
    universe_path, readiness_path = root / UNIVERSE_ARTIFACT_REL, root / READINESS_ARTIFACT_REL
    if not universe_path.is_file() or not readiness_path.is_file():
        raise IntegrityError("Family-1 universe/readiness artifacts are missing")
    expected_universe = build_universe_artifact(root)
    actual_universe = _json(universe_path)
    if _canonical_bytes(actual_universe) != _canonical_bytes(expected_universe):
        raise IntegrityError("Family-1 universe artifact identity mismatch")
    context = load_frozen_context(root)
    expected_readiness = build_readiness_artifact(root, context)
    actual_readiness = _json(readiness_path)
    if _canonical_bytes(actual_readiness) != _canonical_bytes(expected_readiness):
        raise IntegrityError("Family-1 readiness artifact identity mismatch")
    return {
        "status": "FAMILY1_ARTIFACT_INTEGRITY_PASSED",
        "universe_sha256": _sha256(universe_path),
        "readiness_sha256": _sha256(readiness_path),
        "performance_computed": False,
    }


def _book_weights(columns: Sequence[str], book: Mapping[str, Sequence[str]]) -> dict[str, float]:
    longs, shorts = set(book["longs"]), set(book["shorts"])
    if len(longs) != len(shorts) or not longs or longs & shorts:
        raise ValueError("invalid static book")
    k = len(longs)
    return {c: (1 / k if c in longs else -1 / k if c in shorts else 0.0) for c in columns}


def _static_steps(signals: Sequence[SignalStep], columns: Sequence[str], book: Mapping[str, Sequence[str]]) -> tuple[AccountingStep, ...]:
    active = _book_weights(columns, book)
    return tuple(AccountingStep(
        step.timestamp,
        {c: 0.0 for c in columns} if step.kind in ("gap_exit", "terminal") else active,
        step.opens, step.kind,
    ) for step in signals)


def _candidate_ic(signals: Sequence[SignalStep], definition: UniverseDefinition, routes: Mapping[str, object]) -> list[float]:
    route_pairs = {leg[0] for route in routes.values() for leg in route.get("legs", [])}
    result = []
    for current, nxt in zip(signals, signals[1:]):
        if current.scores is None:
            continue
        common = route_pairs & set(current.opens) & set(nxt.opens)
        pair_returns = {p: float(np.log(nxt.opens[p].mid / current.opens[p].mid)) for p in common}
        spot = currency_spot_log_returns(pair_returns, definition.currencies)
        result.append(spearman_ic(
            [current.scores[c] for c in definition.currencies], [spot[c] for c in definition.currencies]
        ))
    if len(result) != 157:
        raise IntegrityError(f"{definition.candidate_id}: IC period count mismatch")
    return result


def stationary_bootstrap_evidence(
    series: Sequence[float], *, lower_quantile: float, reps: int = 10_000, seed: int = BOOTSTRAP_SEED,
    block_selector: Callable[[np.ndarray], float] | None = None,
) -> tuple[dict[str, object], list[float]]:
    values = np.asarray(series, dtype=float)
    if values.ndim != 1 or len(values) < 2 or not np.isfinite(values).all():
        raise ValueError("invalid Family-1 IC bootstrap input")
    if not (0 < lower_quantile < 0.5) or reps < 1:
        raise ValueError("invalid Family-1 bootstrap quantile/replicate count")
    try:
        from arch.bootstrap import StationaryBootstrap, optimal_block_length
    except ImportError as exc:
        raise RuntimeError("frozen inference requires arch>=7.2,<8") from exc
    selected = float(optimal_block_length(values)["stationary"].iloc[0]) if block_selector is None else float(block_selector(values))
    block = int(Decimal(str(selected)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) if isfinite(selected) else 0
    if block < 1 or block > len(values) / 2:
        raise ValueError("degenerate Family-1 stationary-bootstrap block length")
    rng = np.random.Generator(np.random.PCG64(seed))
    bootstrap = StationaryBootstrap(block, values, seed=rng)
    means = [float(np.mean(data[0][0])) for data in bootstrap.bootstrap(reps)]
    evidence = {
        "mean_ic": float(np.mean(values)),
        "lower_bound": float(np.percentile(np.asarray(means), lower_quantile * 100)),
        "one_sided_confidence": 1 - lower_quantile,
        "lower_bound_quantile": lower_quantile,
        "bootstrap_block_length": block,
        "bootstrap_replicates": reps,
        "bootstrap_seed": seed,
    }
    return evidence, means


def _path_payload(path: AccountingPath) -> dict[str, object]:
    return {
        "denominator": path.denominator,
        "equities": list(path.equities),
        "period_returns": list(path.period_returns),
        "trades": [{
            "timestamp": trade.timestamp, "kind": trade.kind,
            "target_weights": dict(sorted(trade.target_weights.items())),
            "target_units": dict(sorted(trade.target_units.items())),
            "fills": dict(sorted(trade.fills.items())), "spread_cost": trade.spread_cost,
        } for trade in path.trades],
        "total_spread_cost": path.total_spread_cost,
        "total_financing": path.total_financing,
    }


def _numeric_diff(left: object, right: object, path: str = "root") -> tuple[float, int]:
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        if set(left) != set(right):
            raise IntegrityError(f"{path}: mapping keys differ")
        values = [_numeric_diff(left[key], right[key], f"{path}.{key}") for key in left]
    elif isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        if len(left) != len(right):
            raise IntegrityError(f"{path}: sequence lengths differ")
        values = [_numeric_diff(a, b, f"{path}[{i}]") for i, (a, b) in enumerate(zip(left, right))]
    elif isinstance(left, bool) or isinstance(right, bool) or isinstance(left, str) or isinstance(right, str) or left is None or right is None:
        if left != right:
            raise IntegrityError(f"{path}: discrete values differ")
        return 0.0, 0
    elif isinstance(left, (int, float)) and isinstance(right, (int, float)):
        if not (isfinite(float(left)) and isfinite(float(right))):
            raise IntegrityError(f"{path}: non-finite numeric value")
        difference = abs(float(left) - float(right))
        if difference > NUMERIC_TOLERANCE:
            raise IntegrityError(f"{path}: numerical parity difference {difference} exceeds 1e-12")
        return difference, 1
    else:
        if left != right:
            raise IntegrityError(f"{path}: values differ")
        return 0.0, 0
    return (max((item[0] for item in values), default=0.0), sum(item[1] for item in values))


def _shape_summary(value: object) -> dict[str, int]:
    result = {"mappings": 0, "sequences": 0, "numeric_scalars": 0, "discrete_scalars": 0}

    def visit(item: object) -> None:
        if isinstance(item, Mapping):
            result["mappings"] += 1
            for child in item.values():
                visit(child)
        elif isinstance(item, (list, tuple)):
            result["sequences"] += 1
            for child in item:
                visit(child)
        elif isinstance(item, (int, float)) and not isinstance(item, bool):
            result["numeric_scalars"] += 1
        else:
            result["discrete_scalars"] += 1

    visit(value)
    return result


def _comparison_stats(expected: object, actual: object) -> dict[str, object]:
    stats = {
        "numeric_values_compared": 0, "discrete_values_compared": 0,
        "shape_mismatch_count": 0, "numeric_mismatch_count": 0,
        "discrete_mismatch_count": 0, "max_abs_difference": 0.0,
    }

    def compare(left: object, right: object) -> None:
        if isinstance(left, Mapping) and isinstance(right, Mapping):
            if set(left) != set(right):
                stats["shape_mismatch_count"] += 1
            for key in set(left) & set(right):
                compare(left[key], right[key])
            return
        if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
            if len(left) != len(right):
                stats["shape_mismatch_count"] += 1
            for left_item, right_item in zip(left, right):
                compare(left_item, right_item)
            return
        left_numeric = isinstance(left, (int, float)) and not isinstance(left, bool)
        right_numeric = isinstance(right, (int, float)) and not isinstance(right, bool)
        if left_numeric and right_numeric:
            stats["numeric_values_compared"] += 1
            if not (isfinite(float(left)) and isfinite(float(right))):
                stats["numeric_mismatch_count"] += 1
                return
            difference = abs(float(left) - float(right))
            stats["max_abs_difference"] = max(stats["max_abs_difference"], difference)
            if difference > NUMERIC_TOLERANCE:
                stats["numeric_mismatch_count"] += 1
            return
        stats["discrete_values_compared"] += 1
        if left != right:
            stats["discrete_mismatch_count"] += 1

    compare(expected, actual)
    stats["mismatch_count"] = (
        stats["shape_mismatch_count"] + stats["numeric_mismatch_count"] +
        stats["discrete_mismatch_count"]
    )
    stats["expected_shape"] = _shape_summary(expected)
    stats["actual_shape"] = _shape_summary(actual)
    return stats


class ParityAccumulator:
    def __init__(self) -> None:
        self._cells: dict[str, dict[str, object]] = {}

    def add(self, cell_id: str, expected: object, actual: object) -> None:
        observed = _comparison_stats(expected, actual)
        cell = self._cells.setdefault(cell_id, {
            "instances": 0, "numeric_values_compared": 0, "discrete_values_compared": 0,
            "shape_mismatch_count": 0, "numeric_mismatch_count": 0,
            "discrete_mismatch_count": 0, "mismatch_count": 0,
            "max_abs_difference": 0.0, "expected_shapes": {}, "actual_shapes": {},
        })
        cell["instances"] += 1
        for key in (
            "numeric_values_compared", "discrete_values_compared", "shape_mismatch_count",
            "numeric_mismatch_count", "discrete_mismatch_count", "mismatch_count",
        ):
            cell[key] += observed[key]
        cell["max_abs_difference"] = max(cell["max_abs_difference"], observed["max_abs_difference"])
        for side in ("expected", "actual"):
            shape = observed[f"{side}_shape"]
            identity = json.dumps(shape, sort_keys=True, separators=(",", ":"))
            cell[f"{side}_shapes"][identity] = cell[f"{side}_shapes"].get(identity, 0) + 1

    def report(self) -> dict[str, object]:
        cells = dict(sorted(self._cells.items()))
        mismatch_count = sum(int(cell["mismatch_count"]) for cell in cells.values())
        return {
            "tolerance": NUMERIC_TOLERANCE,
            "cell_count": len(cells),
            "mismatch_count": mismatch_count,
            "max_abs_difference": max((float(x["max_abs_difference"]) for x in cells.values()), default=0.0),
            "cells": cells,
        }


def _path_component_payload(
    path: AccountingPath, signals: Sequence[SignalStep], events: Sequence[FinancingEvent],
    routes: Mapping[str, object], *, adverse_financing: bool = False,
    signal_currency_values: Sequence[Mapping[str, float]] | None = None,
    event_currency_values: Sequence[Mapping[str, float]] | None = None,
) -> dict[str, object]:
    spot_cashflows = [0.0]
    for index in range(1, len(path.trades)):
        previous = path.trades[index - 1].target_units
        prior_opens, current_opens = signals[index - 1].opens, signals[index].opens
        currency_values = (
            signal_currency_values[index] if signal_currency_values is not None
            else currency_usd_values(current_opens)
        )
        cash = 0.0
        for pair, units in previous.items():
            _, quote = _pair_currencies(pair)
            cash += units * (current_opens[pair].mid - prior_opens[pair].mid) * currency_values[quote]
        spot_cashflows.append(cash)
    financing_cashflows = []
    for event_index, event in enumerate(events):
        positions = path.trades[event.after_step].target_units
        currency_values = (
            event_currency_values[event_index] if event_currency_values is not None
            else currency_usd_values(event.opens)
        )
        cash = 0.0
        for pair, units in positions.items():
            if pair not in event.opens or units == 0:
                continue
            _, quote = _pair_currencies(pair)
            item = position_financing_cashflow_usd(
                event.schedule, pair, units, event.opens[pair].mid, path.denominator,
                rollover_multiplier(event.day, pair) if event.days_charged is None else event.days_charged,
                currency_values[quote],
            )
            if adverse_financing:
                from bot.forex.stage_a_carry import apply_financing_stress
                item = apply_financing_stress(item)
            cash += item
        financing_cashflows.append(cash)
    return {
        "path": _path_payload(path),
        "spot_cashflows_by_step": spot_cashflows,
        "financing_cashflows_by_event": financing_cashflows,
        "spread_costs_by_trade": [trade.spread_cost for trade in path.trades],
    }


def _posthoc(strategy: Mapping[int, AccountingPath], signals: Sequence[SignalStep]) -> dict[str, object]:
    years = (signals[-1].timestamp - signals[0].timestamp) / 1000 / (ANNUALIZATION_DAYS * 24 * 60 * 60)
    result = {"elapsed_years": years, "accounting_periods": len(strategy[360].period_returns), "scenarios": {}}
    for denominator in (360, 365):
        path = strategy[denominator]
        final = path.equities[-1]
        result["scenarios"][str(denominator)] = {
            "final_equity": final,
            "total_return": final - 1,
            "cagr": final ** (1 / years) - 1,
            "total_spread_cost": path.total_spread_cost,
            "total_financing": path.total_financing,
        }
    return result


def _published_posthoc_match(value: Mapping[str, object]) -> dict[str, bool]:
    expected = {
        "elapsed_years": 3.334702,
        "360": {"final_equity": 1.0801650638, "total_return_pct": 8.016506, "cagr_pct": 2.339411,
                "total_spread_cost": 0.0264791950, "total_financing": 0.0621592826},
        "365": {"final_equity": 1.0792625720, "total_return_pct": 7.926257, "cagr_pct": 2.313762,
                "total_spread_cost": 0.0264683925, "total_financing": 0.0612822888},
    }
    checks = {"elapsed_years": round(float(value["elapsed_years"]), 6) == expected["elapsed_years"]}
    for denominator in ("360", "365"):
        actual = value["scenarios"][denominator]
        checks[denominator] = (
            round(actual["final_equity"], 10) == expected[denominator]["final_equity"] and
            round(actual["total_return"] * 100, 6) == expected[denominator]["total_return_pct"] and
            round(actual["cagr"] * 100, 6) == expected[denominator]["cagr_pct"] and
            round(actual["total_spread_cost"], 10) == expected[denominator]["total_spread_cost"] and
            round(actual["total_financing"], 10) == expected[denominator]["total_financing"]
        )
    return checks


def _membership_steps(signals: Sequence[SignalStep], definition: UniverseDefinition, omitted: str | None = None) -> tuple[AccountingStep, ...]:
    active = tuple(c for c in definition.currencies if c != omitted)
    k = len(active) // 3
    result = []
    for signal in signals:
        if signal.scores is None:
            weights = {c: 0.0 for c in definition.currencies}
        else:
            selected = currency_targets({c: signal.scores[c] for c in active}, k)
            weights = {c: (0.0 if c == omitted else selected[c]) for c in definition.currencies}
        result.append(AccountingStep(signal.timestamp, weights, signal.opens, signal.kind))
    return tuple(result)


def _stream_u14_economics(
    inputs: CandidateInputs, legacy_signals: Sequence[SignalStep], legacy_steps: Sequence[AccountingStep],
    legacy_events: Sequence[FinancingEvent], legacy_routes: Mapping[str, object],
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    """Compute U14 only while streaming complete legacy/parameterized parity cells."""
    if inputs.definition != U14:
        raise PermissionError("G10/U8 economics are not implemented or authorized")
    parity = ParityAccumulator()
    legacy_signal_values = tuple(currency_usd_values(signal.opens) for signal in legacy_signals)
    actual_signal_values = tuple(currency_usd_values(signal.opens) for signal in inputs.signal_steps)
    legacy_event_values = tuple(currency_usd_values(event.opens) for event in legacy_events)
    actual_event_values = tuple(currency_usd_values(event.opens) for event in inputs.financing_events)

    def legacy_component(path: AccountingPath, *, adverse: bool = False) -> dict[str, object]:
        return _path_component_payload(
            path, legacy_signals, legacy_events, legacy_routes, adverse_financing=adverse,
            signal_currency_values=legacy_signal_values, event_currency_values=legacy_event_values,
        )

    def actual_component(path: AccountingPath, *, adverse: bool = False) -> dict[str, object]:
        return _path_component_payload(
            path, inputs.signal_steps, inputs.financing_events, inputs.routes, adverse_financing=adverse,
            signal_currency_values=actual_signal_values, event_currency_values=actual_event_values,
        )
    steps = candidate_accounting_steps(inputs.signal_steps, U14)
    strategy = run_dual_accounting_paths(1.0, steps, inputs.financing_events, inputs.routes)
    adverse = run_adverse_dual_accounting_paths(1.0, steps, inputs.financing_events, inputs.routes)
    spread3 = run_spread3_sensitivity_paths(1.0, steps, inputs.financing_events, inputs.routes)
    legacy_strategy = run_dual_accounting_paths(1.0, legacy_steps, legacy_events, legacy_routes)
    legacy_adverse = run_adverse_dual_accounting_paths(1.0, legacy_steps, legacy_events, legacy_routes)
    legacy_spread3 = run_spread3_sensitivity_paths(1.0, legacy_steps, legacy_events, legacy_routes)
    for denominator in (360, 365):
        parity.add(
            "strategy_base_full_path_and_components",
            legacy_component(legacy_strategy[denominator]), actual_component(strategy[denominator]),
        )
        parity.add(
            "strategy_adverse_full_path_and_components",
            legacy_component(legacy_adverse[denominator], adverse=True),
            actual_component(adverse[denominator], adverse=True),
        )
        parity.add(
            "strategy_spread_x3_full_path_and_components",
            legacy_component(legacy_spread3[denominator]), actual_component(spread3[denominator]),
        )

    benchmark_rap = {360: [], 365: []}
    benchmark_mdd = {360: [], 365: []}
    benchmark_total_return = {360: [], 365: []}
    benchmark_adverse_return = {360: [], 365: []}
    benchmark_spread3_return = {360: [], 365: []}
    benchmark_blocks = {d: {block["block_id"]: {"rap": [], "max_drawdown": [], "total_return": []} for block in BLOCKS} for d in (360, 365)}
    benchmark_hash = hashlib.sha256()
    books = family1_benchmark_books(U14.currencies, U14.k)
    for book in books:
        actual_steps = _static_steps(inputs.signal_steps, U14.currencies, book)
        expected_steps = _static_steps(legacy_signals, U14.currencies, book)
        actual_scenarios = {
            "base": run_dual_accounting_paths(1.0, actual_steps, inputs.financing_events, inputs.routes),
            "adverse": run_adverse_dual_accounting_paths(1.0, actual_steps, inputs.financing_events, inputs.routes),
            "spread_x3": run_spread3_sensitivity_paths(1.0, actual_steps, inputs.financing_events, inputs.routes),
        }
        expected_scenarios = {
            "base": run_dual_accounting_paths(1.0, expected_steps, legacy_events, legacy_routes),
            "adverse": run_adverse_dual_accounting_paths(1.0, expected_steps, legacy_events, legacy_routes),
            "spread_x3": run_spread3_sensitivity_paths(1.0, expected_steps, legacy_events, legacy_routes),
        }
        for denominator in (360, 365):
            for scenario in ("base", "adverse", "spread_x3"):
                parity.add(
                    f"benchmark_{scenario}_full_paths_and_components",
                    legacy_component(expected_scenarios[scenario][denominator], adverse=scenario == "adverse"),
                    actual_component(actual_scenarios[scenario][denominator], adverse=scenario == "adverse"),
                )
            paths = actual_scenarios["base"]
            benchmark_rap[denominator].append(rap(paths[denominator].period_returns))
            benchmark_mdd[denominator].append(max_drawdown_from_returns(paths[denominator].period_returns))
            benchmark_total_return[denominator].append(paths[denominator].equities[-1] - 1)
            benchmark_adverse_return[denominator].append(actual_scenarios["adverse"][denominator].equities[-1] - 1)
            benchmark_spread3_return[denominator].append(actual_scenarios["spread_x3"][denominator].equities[-1] - 1)
            for block in path_block_diagnostics(paths[denominator], inputs.signal_steps):
                target = benchmark_blocks[denominator][block["block_id"]]
                for key in target:
                    target[key].append(block[key])
            benchmark_hash.update(_canonical_bytes(_path_payload(paths[denominator])))

    loco_excess = {360: {}, 365: {}}
    loco_diagnostics = {}
    loco_hash = hashlib.sha256()
    for omitted in U14.currencies:
        active = tuple(c for c in U14.currencies if c != omitted)
        k = len(active) // 3
        loco_strategy = run_dual_accounting_paths(
            1.0, _membership_steps(inputs.signal_steps, U14, omitted), inputs.financing_events, inputs.routes
        )
        expected_loco_strategy = run_dual_accounting_paths(
            1.0, _membership_steps(legacy_signals, U14, omitted), legacy_events, legacy_routes
        )
        loco_adverse = run_adverse_dual_accounting_paths(
            1.0, _membership_steps(inputs.signal_steps, U14, omitted), inputs.financing_events, inputs.routes
        )
        expected_loco_adverse = run_adverse_dual_accounting_paths(
            1.0, _membership_steps(legacy_signals, U14, omitted), legacy_events, legacy_routes
        )
        loco_spread3 = run_spread3_sensitivity_paths(
            1.0, _membership_steps(inputs.signal_steps, U14, omitted), inputs.financing_events, inputs.routes
        )
        expected_loco_spread3 = run_spread3_sensitivity_paths(
            1.0, _membership_steps(legacy_signals, U14, omitted), legacy_events, legacy_routes
        )
        braps = {360: [], 365: []}; bmdds = {360: [], 365: []}
        badverse = {360: [], 365: []}; bspread3 = {360: [], 365: []}
        bblocks = {d: {block["block_id"]: {"rap": [], "max_drawdown": [], "total_return": []} for block in BLOCKS} for d in (360, 365)}
        for book in family1_benchmark_books(active, k):
            actual_steps = _static_steps(inputs.signal_steps, U14.currencies, book)
            expected_steps = _static_steps(legacy_signals, U14.currencies, book)
            actual_scenarios = {
                "base": run_dual_accounting_paths(1.0, actual_steps, inputs.financing_events, inputs.routes),
                "adverse": run_adverse_dual_accounting_paths(1.0, actual_steps, inputs.financing_events, inputs.routes),
                "spread_x3": run_spread3_sensitivity_paths(1.0, actual_steps, inputs.financing_events, inputs.routes),
            }
            expected_scenarios = {
                "base": run_dual_accounting_paths(1.0, expected_steps, legacy_events, legacy_routes),
                "adverse": run_adverse_dual_accounting_paths(1.0, expected_steps, legacy_events, legacy_routes),
                "spread_x3": run_spread3_sensitivity_paths(1.0, expected_steps, legacy_events, legacy_routes),
            }
            for denominator in (360, 365):
                for scenario in ("base", "adverse", "spread_x3"):
                    parity.add(
                        f"loco_benchmark_{scenario}_full_paths_and_components",
                        legacy_component(expected_scenarios[scenario][denominator], adverse=scenario == "adverse"),
                        actual_component(actual_scenarios[scenario][denominator], adverse=scenario == "adverse"),
                    )
                paths = actual_scenarios["base"]
                braps[denominator].append(rap(paths[denominator].period_returns))
                bmdds[denominator].append(max_drawdown_from_returns(paths[denominator].period_returns))
                badverse[denominator].append(actual_scenarios["adverse"][denominator].equities[-1] - 1)
                bspread3[denominator].append(actual_scenarios["spread_x3"][denominator].equities[-1] - 1)
                for block in path_block_diagnostics(paths[denominator], inputs.signal_steps):
                    target = bblocks[denominator][block["block_id"]]
                    for key in target:
                        target[key].append(block[key])
                loco_hash.update(_canonical_bytes(_path_payload(paths[denominator])))
        for denominator in (360, 365):
            parity.add(
                "loco_strategy_base_full_paths_and_components",
                legacy_component(expected_loco_strategy[denominator]), actual_component(loco_strategy[denominator]),
            )
            parity.add(
                "loco_strategy_adverse_full_paths_and_components",
                legacy_component(expected_loco_adverse[denominator], adverse=True),
                actual_component(loco_adverse[denominator], adverse=True),
            )
            parity.add(
                "loco_strategy_spread_x3_full_paths_and_components",
                legacy_component(expected_loco_spread3[denominator]), actual_component(loco_spread3[denominator]),
            )
            loco_hash.update(_canonical_bytes(_path_payload(loco_strategy[denominator])))
            loco_excess[denominator][omitted] = (
                rap(loco_strategy[denominator].period_returns) - float(np.median(braps[denominator]))
            )
        from bot.forex.family1_study import path_diagnostics
        loco_diagnostics[omitted] = {
            "N": len(active), "k": k,
            "denominators": {str(d): {
                "base": path_diagnostics(loco_strategy[d], inputs.signal_steps, inputs.financing_events, inputs.routes),
                "adverse_total_return": loco_adverse[d].equities[-1] - 1,
                "spread_x3_total_return": loco_spread3[d].equities[-1] - 1,
                "benchmark_rap": float(np.median(braps[d])),
                "benchmark_max_drawdown": float(np.median(bmdds[d])),
                "benchmark_adverse_total_return": float(np.median(badverse[d])),
                "benchmark_spread_x3_total_return": float(np.median(bspread3[d])),
                "benchmark_rap_excess": loco_excess[d][omitted],
                "benchmark_blocks": {
                    block_id: {key: float(np.median(values)) for key, values in cell.items()}
                    for block_id, cell in bblocks[d].items()
                },
            } for d in (360, 365)},
        }

    expected_ic = spot_ic_series(legacy_signals, U14.currencies)
    ic = _candidate_ic(inputs.signal_steps, U14, inputs.routes)
    parity.add("ic_period_array", expected_ic, ic)
    ic_evidence, bootstrap_means = stationary_bootstrap_evidence(ic, lower_quantile=0.05)
    expected_ic_evidence, expected_bootstrap_means = stationary_bootstrap_evidence(
        expected_ic, lower_quantile=0.05
    )
    lower, block = ic_evidence["lower_bound"], ic_evidence["bootstrap_block_length"]
    parity.add("ic_bootstrap_mean_array", expected_bootstrap_means, bootstrap_means)
    parity.add("ic_bootstrap_scalars", expected_ic_evidence, ic_evidence)
    metrics = {}
    scenarios = {}
    for denominator in (360, 365):
        srap = rap(strategy[denominator].period_returns)
        brap = float(np.median(benchmark_rap[denominator]))
        smdd = max_drawdown_from_returns(strategy[denominator].period_returns)
        bmdd = float(np.median(benchmark_mdd[denominator]))
        stressed = adverse[denominator].equities[-1] - 1
        worst_currency, worst_excess = min(loco_excess[denominator].items(), key=lambda item: (item[1], item[0]))
        metrics[str(denominator)] = {
            "G1": {"strategy_rap": srap, "benchmark_median_rap": brap, "excess": srap - brap},
            "G3": {"strategy_mdd": smdd, "benchmark_median_mdd": bmdd},
            "G4": {"stressed_total_return": stressed},
            "G5": {"loco_excesses": loco_excess[denominator],
                   "pass_count": sum(value > 0 for value in loco_excess[denominator].values()),
                   "worst_currency": worst_currency, "worst_excess": worst_excess},
        }
        scenarios[str(denominator)] = {
            "G1": srap > brap, "G3": smdd >= bmdd, "G4": stressed > 0,
            "G5": all(value > 0 for value in loco_excess[denominator].values()),
        }
    gates = {
        "G1": all(scenarios[d]["G1"] for d in scenarios), "G2": lower > 0,
        "G3": all(scenarios[d]["G3"] for d in scenarios),
        "G4": all(scenarios[d]["G4"] for d in scenarios),
        "G5": all(scenarios[d]["G5"] for d in scenarios),
    }
    results = {
        "G2_block_length": block,
        "G2_metrics": {**ic_evidence, "threshold": 0.0},
        "gates": gates,
        "non_gating_sensitivities": {"spread_x3_total_return": {
            "360": spread3[360].equities[-1] - 1, "365": spread3[365].equities[-1] - 1}},
        "scenario_metrics": metrics,
        "scenarios": scenarios,
        "terminal_verdict": "SURVIVES_KILL_TEST" if all(gates.values()) else "CLOSED_FAIL",
    }
    vectors = {
        "strategy": {str(d): _path_payload(strategy[d]) for d in (360, 365)},
        "adverse": {str(d): _path_payload(adverse[d]) for d in (360, 365)},
        "spread3": {str(d): _path_payload(spread3[d]) for d in (360, 365)},
        "benchmark_path_sha256": benchmark_hash.hexdigest(),
        "loco_path_sha256": loco_hash.hexdigest(),
    }
    from bot.forex.family1_study import concentration_diagnostics, path_diagnostics
    control_denominators = {str(d): {
        "base": path_diagnostics(strategy[d], inputs.signal_steps, inputs.financing_events, inputs.routes),
        "benchmark": {
            "rap": float(np.median(benchmark_rap[d])),
            "max_drawdown": float(np.median(benchmark_mdd[d])),
            "total_return": float(np.median(benchmark_total_return[d])),
            "adverse_total_return": float(np.median(benchmark_adverse_return[d])),
            "spread_x3_total_return": float(np.median(benchmark_spread3_return[d])),
            "blocks": {
                block_id: {key: float(np.median(values)) for key, values in cell.items()}
                for block_id, cell in benchmark_blocks[d].items()
            },
        },
        "benchmark_rap_excess": rap(strategy[d].period_returns) - float(np.median(benchmark_rap[d])),
        "benchmark_mdd_difference": max_drawdown_from_returns(strategy[d].period_returns) - float(np.median(benchmark_mdd[d])),
        "adverse_total_return": adverse[d].equities[-1] - 1,
        "spread_x3_total_return": spread3[d].equities[-1] - 1,
    } for d in (360, 365)}
    difference_keys = (
        "final_equity", "total_return", "cagr", "rap", "max_drawdown", "currency_turnover",
        "annualized_currency_turnover", "routed_usd_turnover", "annualized_routed_usd_turnover",
        "mean_routed_usd_gross", "total_spread_cost", "total_financing", "spot_pnl",
    )
    control_diagnostics = {
        "candidate_id": U14.candidate_id, "N": 14, "k": 4, "currencies": list(U14.currencies),
        "benchmark_books_sha256": _canonical_sha(books), "benchmark_book_count": len(books),
        "ic": {**ic_evidence, "period_count": len(ic), "series": ic},
        "concentration": concentration_diagnostics(inputs),
        "denominators": control_denominators,
        "D365_MINUS_D360": {
            **{key: control_denominators["365"]["base"][key] - control_denominators["360"]["base"][key] for key in difference_keys},
            "benchmark_rap_excess": control_denominators["365"]["benchmark_rap_excess"] - control_denominators["360"]["benchmark_rap_excess"],
            "benchmark_mdd_difference": control_denominators["365"]["benchmark_mdd_difference"] - control_denominators["360"]["benchmark_mdd_difference"],
            "adverse_total_return": control_denominators["365"]["adverse_total_return"] - control_denominators["360"]["adverse_total_return"],
            "spread_x3_total_return": control_denominators["365"]["spread_x3_total_return"] - control_denominators["360"]["spread_x3_total_return"],
        },
        "loco": loco_diagnostics,
        "candidate_disposition": "PENDING_EXTERNAL_ADJUDICATION",
    }
    return {
        "results": results, "posthoc": _posthoc(strategy, inputs.signal_steps),
        "control_diagnostics": control_diagnostics,
    }, vectors, parity.report()


def run_u14_parity(root: Path) -> dict[str, object]:
    root = Path(root)
    artifact_integrity = validate_readiness_artifacts(root)
    context = load_frozen_context(root)
    family = prepare_candidate(context, U14)

    legacy_days = _required_financing_open_days(context.u14_signals, context.availability, context.routes, context.opens_at)
    _, legacy_financing_records = _financing_requirements(
        context.u14_signals, U14, context.routes, context.availability, context.opens_at
    )
    legacy_events = tuple(build_financing_events(context.u14_signals, context.schedules, legacy_days))
    legacy_steps = tuple(accounting_steps_from_signals(context.u14_signals, U14.currencies, k=4))
    family_steps = candidate_accounting_steps(family.signal_steps, U14)
    financing_readiness = _json(root / STAGE_A_FINANCING_READINESS_REL)
    closed_market_identity = {
        "records_sha256": financing_readiness["records_sha256"],
        "closed_market_no_event_records": financing_readiness["summary"]["closed_market_no_event_records"],
        "potential_held_route_records": financing_readiness["summary"]["potential_held_route_records"],
    }

    discrete_left = {
        "transaction_mapping": context.transaction_mapping,
        "evaluable_periods": context.mask["evaluable_rebalances"],
        "excluded_periods": context.mask["excluded_rebalances"],
        "signal_timestamps": [x.timestamp for x in context.u14_signals],
        "signal_kinds": [x.kind for x in context.u14_signals],
        "memberships": accounting_membership_records(legacy_steps),
        "routes": context.routes,
        "events": event_identity(legacy_events),
        "held_leg_and_conversion_records": legacy_financing_records,
        "benchmark_books": family1_benchmark_books(U14.currencies, U14.k),
        "loco": [{"omitted": x["omitted"], "rankable": x["rankable"], "N": x["N"], "k": x["k"]}
                 for x in loco_definitions(U14)],
        "blocks": validate_blocks(context.mask),
        "stress_cells": ["base", "adverse_spread_x2_debit_x1.25_days_x1.10_credit_x0.80", "spread_x3"],
        "denominators": [360, 365],
        "closed_market_non_events": closed_market_identity,
    }
    discrete_right = {
        "transaction_mapping": context.transaction_mapping,
        "evaluable_periods": context.mask["evaluable_rebalances"],
        "excluded_periods": context.mask["excluded_rebalances"],
        "signal_timestamps": [x.timestamp for x in family.signal_steps],
        "signal_kinds": [x.kind for x in family.signal_steps],
        "memberships": accounting_membership_records(family_steps),
        "routes": family.routes,
        "events": event_identity(family.financing_events),
        "held_leg_and_conversion_records": family.financing_records,
        "benchmark_books": benchmark_books(U14.currencies, 4, 1000, BENCHMARK_SEED),
        "loco": [{"omitted": c, "rankable": [x for x in U14.currencies if x != c], "N": 13, "k": 4}
                 for c in U14.currencies],
        "blocks": validate_blocks(context.mask),
        "stress_cells": ["base", "adverse_spread_x2_debit_x1.25_days_x1.10_credit_x0.80", "spread_x3"],
        "denominators": [360, 365],
        "closed_market_non_events": closed_market_identity,
    }
    discrete_comparison = _comparison_stats(discrete_left, discrete_right)
    if discrete_comparison["mismatch_count"]:
        raise IntegrityError("U14 discrete parity failed")

    computed, vectors, section12 = _stream_u14_economics(
        family, context.u14_signals, legacy_steps, legacy_events, context.routes
    )
    path_shape = {"equities": [168], "period_returns": [157], "trades": [168]}
    component_shape = {
        **path_shape, "spot_cashflows_by_step": [168],
        "financing_cashflows_by_event": [len(legacy_events)], "spread_costs_by_trade": [168],
    }
    declared = {}
    for cell_id, cell in section12["cells"].items():
        if cell_id == "ic_period_array":
            shape = {"series": [157]}
        elif cell_id == "ic_bootstrap_mean_array":
            shape = {"bootstrap_means": [10_000]}
        elif cell_id == "ic_bootstrap_scalars":
            shape = {"scalar_mapping_fields": 7}
        elif "components" in cell_id:
            shape = component_shape
        else:
            shape = path_shape
        declared[cell_id] = {
            "expected": {"instances": cell["instances"], **shape},
            "actual": {"instances": cell["instances"], **shape},
        }
    section12["expected_actual_shapes"] = declared
    if section12["mismatch_count"]:
        raise IntegrityError("U14 Section-12 floating/structure parity failed")
    attempt3 = _json(root / STAGE_A_RESULT_REL)["result"]["results"]
    metric_max, metric_count = _numeric_diff(attempt3, computed["results"], "attempt3")
    published = _published_posthoc_match(computed["posthoc"])
    if not all(published.values()):
        raise IntegrityError(f"U14 published post-hoc parity failed: {published}")

    readiness_path = root / READINESS_ARTIFACT_REL
    readiness_sha = _sha256(readiness_path) if readiness_path.is_file() else None
    return {
        "schema_version": 2,
        "status": "U14_PARITY_PASSED",
        "candidate_economics_computed": False,
        "network_accessed": False,
        "preregistration_sha256": _sha256(root / PREREG_REL),
        "readiness_artifact_sha256": readiness_sha,
        "readiness_integrity": artifact_integrity,
        "implementation_sha256": _canonical_sha(_source_hashes(root)),
        "attempt3_result_sha256": _sha256(root / STAGE_A_RESULT_REL),
        "discrete": {
            "exact": True, "canonical_sha256": _canonical_sha(discrete_left),
            "comparison": discrete_comparison,
            "transaction_count": len(context.transaction_mapping),
            "signal_step_count": len(family.signal_steps),
            "membership_count": len(membership_records(family)),
            "financing_event_count": len(family.financing_events),
            "held_leg_record_count": len(family.financing_records),
            "closed_market_non_event_count": closed_market_identity["closed_market_no_event_records"],
            "benchmark_book_count": len(discrete_left["benchmark_books"]),
            "loco_case_count": len(discrete_left["loco"]),
        },
        "floating": {
            "tolerance": NUMERIC_TOLERANCE,
            "section12_values_compared": sum(
                int(cell["numeric_values_compared"]) for cell in section12["cells"].values()
            ),
            "section12_max_abs_diff": section12["max_abs_difference"],
            "attempt3_scalars_compared": metric_count,
            "attempt3_max_abs_diff": metric_max,
            "benchmark_path_sha256": vectors["benchmark_path_sha256"],
            "loco_path_sha256": vectors["loco_path_sha256"],
        },
        "section12_parity": section12,
        "posthoc": computed["posthoc"],
        "control_diagnostics": computed["control_diagnostics"],
        "published_posthoc_match": published,
        "results": computed["results"],
        "candidate_disposition": "PENDING_EXTERNAL_ADJUDICATION",
    }


def emit_u14_parity_artifact(root: Path) -> Path:
    root = Path(root)
    value = run_u14_parity(root)
    path = root / PARITY_ARTIFACT_REL
    write_artifact(path, value)
    return path
