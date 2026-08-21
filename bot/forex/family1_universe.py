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
    currency_targets,
    max_drawdown_from_returns,
    pair_positions,
    rap,
    run_adverse_dual_accounting_paths,
    run_dual_accounting_paths,
    run_spread3_sensitivity_paths,
    select_signal,
    spearman_ic,
    stationary_bootstrap_lower_bound,
)
from bot.forex.stage_a_orchestration import IntegrityError, _required_financing_open_days
from bot.forex.stage_a_preflight import FROZEN_SHA256, project_preflight


PREREG_REL = Path("prereg/2026-08-21-tms-carry-unlevered-family-1-universe-prereg.md")
STAGE_A_UNIVERSE_REL = Path("prereg/2026-08-14-tms-carry-no-try-direct-gbp-universe.json")
STAGE_A_MASK_REL = Path("prereg/2026-08-14-tms-carry-no-try-direct-gbp-mask.json")
STAGE_A_READINESS_REL = Path("prereg/2026-08-14-tms-carry-no-try-direct-gbp-price-readiness.json")
STAGE_A_FINANCING_REL = Path("data/tms_swap_archive/derived/parsed_all.json")
STAGE_A_RESULT_REL = Path(
    "reports/forex/stage_a/"
    "stage-a-bd220eee501ac81388c78d64878458d2393718e4e458c04d8aafaae945a180f6."
    "attempt-03.result.json"
)
UNIVERSE_ARTIFACT_REL = Path("prereg/2026-08-21-tms-carry-unlevered-family-1-universe.json")
READINESS_ARTIFACT_REL = Path("prereg/2026-08-21-tms-carry-unlevered-family-1-readiness.json")
PARITY_ARTIFACT_REL = Path("prereg/2026-08-21-tms-carry-unlevered-family-1-u14-parity.json")

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
        STAGE_A_FINANCING_REL, Path("bot/forex/family1_universe.py"), Path("run_family1_universe.py"),
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


def _stream_u14_economics(inputs: CandidateInputs) -> tuple[dict[str, object], dict[str, object]]:
    """Compute U14 only, streaming benchmark/LOCO paths to bound memory."""
    if inputs.definition != U14:
        raise PermissionError("G10/U8 economics are not implemented or authorized")
    steps = candidate_accounting_steps(inputs.signal_steps, U14)
    strategy = run_dual_accounting_paths(1.0, steps, inputs.financing_events, inputs.routes)
    adverse = run_adverse_dual_accounting_paths(1.0, steps, inputs.financing_events, inputs.routes)
    spread3 = run_spread3_sensitivity_paths(1.0, steps, inputs.financing_events, inputs.routes)

    benchmark_rap = {360: [], 365: []}
    benchmark_mdd = {360: [], 365: []}
    benchmark_hash = hashlib.sha256()
    books = family1_benchmark_books(U14.currencies, U14.k)
    for book in books:
        paths = run_dual_accounting_paths(1.0, _static_steps(inputs.signal_steps, U14.currencies, book),
                                          inputs.financing_events, inputs.routes)
        for denominator in (360, 365):
            benchmark_rap[denominator].append(rap(paths[denominator].period_returns))
            benchmark_mdd[denominator].append(max_drawdown_from_returns(paths[denominator].period_returns))
            benchmark_hash.update(_canonical_bytes(_path_payload(paths[denominator])))

    loco_excess = {360: {}, 365: {}}
    loco_hash = hashlib.sha256()
    for omitted in U14.currencies:
        active = tuple(c for c in U14.currencies if c != omitted)
        k = len(active) // 3
        loco_strategy = run_dual_accounting_paths(
            1.0, _membership_steps(inputs.signal_steps, U14, omitted), inputs.financing_events, inputs.routes
        )
        braps = {360: [], 365: []}
        for book in family1_benchmark_books(active, k):
            paths = run_dual_accounting_paths(
                1.0, _static_steps(inputs.signal_steps, U14.currencies, book), inputs.financing_events, inputs.routes
            )
            for denominator in (360, 365):
                braps[denominator].append(rap(paths[denominator].period_returns))
                loco_hash.update(_canonical_bytes(_path_payload(paths[denominator])))
        for denominator in (360, 365):
            loco_hash.update(_canonical_bytes(_path_payload(loco_strategy[denominator])))
            loco_excess[denominator][omitted] = (
                rap(loco_strategy[denominator].period_returns) - float(np.median(braps[denominator]))
            )

    ic = _candidate_ic(inputs.signal_steps, U14, inputs.routes)
    lower, block = stationary_bootstrap_lower_bound(ic, 10_000, BOOTSTRAP_SEED)
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
        "G2_metrics": {"mean_ic": float(np.mean(ic)), "lower_bound": lower,
                       "one_sided_confidence": 0.95, "lower_bound_quantile": 0.05,
                       "threshold": 0.0, "bootstrap_block_length": block,
                       "bootstrap_replicates": 10000, "bootstrap_seed": BOOTSTRAP_SEED},
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
    return {"results": results, "posthoc": _posthoc(strategy, inputs.signal_steps)}, vectors


def run_u14_parity(root: Path) -> dict[str, object]:
    root = Path(root)
    artifact_integrity = validate_readiness_artifacts(root)
    context = load_frozen_context(root)
    family = prepare_candidate(context, U14)

    legacy_days = _required_financing_open_days(context.u14_signals, context.availability, context.routes, context.opens_at)
    legacy_events = tuple(build_financing_events(context.u14_signals, context.schedules, legacy_days))
    legacy_steps = tuple(accounting_steps_from_signals(context.u14_signals, U14.currencies, k=4))
    family_steps = candidate_accounting_steps(family.signal_steps, U14)

    discrete_left = {
        "transaction_mapping": context.transaction_mapping,
        "signal_timestamps": [x.timestamp for x in context.u14_signals],
        "signal_kinds": [x.kind for x in context.u14_signals],
        "memberships": accounting_membership_records(legacy_steps),
        "routes": context.routes,
        "events": event_identity(legacy_events),
        "benchmark_books": family1_benchmark_books(U14.currencies, U14.k),
        "loco": [{"omitted": x["omitted"], "rankable": x["rankable"], "N": x["N"], "k": x["k"]}
                 for x in loco_definitions(U14)],
        "blocks": validate_blocks(context.mask),
    }
    discrete_right = {
        "transaction_mapping": context.transaction_mapping,
        "signal_timestamps": [x.timestamp for x in family.signal_steps],
        "signal_kinds": [x.kind for x in family.signal_steps],
        "memberships": accounting_membership_records(family_steps),
        "routes": family.routes,
        "events": event_identity(family.financing_events),
        "benchmark_books": benchmark_books(U14.currencies, 4, 1000, BENCHMARK_SEED),
        "loco": [{"omitted": c, "rankable": [x for x in U14.currencies if x != c], "N": 13, "k": 4}
                 for c in U14.currencies],
        "blocks": validate_blocks(context.mask),
    }
    if _canonical_bytes(discrete_left) != _canonical_bytes(discrete_right):
        raise IntegrityError("U14 discrete parity failed")

    legacy_base = run_dual_accounting_paths(1.0, legacy_steps, legacy_events, context.routes)
    family_base = run_dual_accounting_paths(1.0, family_steps, family.financing_events, family.routes)
    base_max = 0.0
    compared = 0
    for denominator in (360, 365):
        difference, count = _numeric_diff(_path_payload(legacy_base[denominator]), _path_payload(family_base[denominator]))
        base_max = max(base_max, difference)
        compared += count

    computed, vectors = _stream_u14_economics(family)
    attempt3 = _json(root / STAGE_A_RESULT_REL)["result"]["results"]
    metric_max, metric_count = _numeric_diff(attempt3, computed["results"], "attempt3")
    published = _published_posthoc_match(computed["posthoc"])
    if not all(published.values()):
        raise IntegrityError(f"U14 published post-hoc parity failed: {published}")

    readiness_path = root / READINESS_ARTIFACT_REL
    readiness_sha = _sha256(readiness_path) if readiness_path.is_file() else None
    return {
        "schema_version": 1,
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
            "transaction_count": len(context.transaction_mapping),
            "signal_step_count": len(family.signal_steps),
            "membership_count": len(membership_records(family)),
            "financing_event_count": len(family.financing_events),
            "benchmark_book_count": len(discrete_left["benchmark_books"]),
            "loco_case_count": len(discrete_left["loco"]),
        },
        "floating": {
            "tolerance": NUMERIC_TOLERANCE,
            "baseline_vector_values_compared": compared,
            "baseline_vector_max_abs_diff": base_max,
            "attempt3_scalars_compared": metric_count,
            "attempt3_max_abs_diff": metric_max,
            "benchmark_path_sha256": vectors["benchmark_path_sha256"],
            "loco_path_sha256": vectors["loco_path_sha256"],
        },
        "posthoc": computed["posthoc"],
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
