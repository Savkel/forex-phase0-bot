from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from bot.forex.family1_universe import (
    ANNUALIZATION_DAYS,
    BLOCKS,
    G10,
    NUMERIC_TOLERANCE,
    U14,
    U8,
    UNIVERSES,
    _numeric_diff,
    benchmark_space_size,
    accounting_membership_records,
    benchmark_block_medians,
    build_universe_artifact,
    candidate_accounting_steps,
    candidate_routes,
    candidate_signal_steps,
    event_identity,
    family1_benchmark_books,
    loco_definitions,
    path_block_diagnostics,
    validate_blocks,
)
from bot.forex.stage_a_carry import (
    AccountingPath,
    FinancingEvent,
    FinancingSchedule,
    OpenQuote,
    SignalStep,
    accounting_steps_from_signals,
    benchmark_books,
    currency_targets,
    run_dual_accounting_paths,
)
from bot.forex.stage_a_orchestration import IntegrityError


ROOT = Path(__file__).resolve().parents[1]


def test_frozen_universes_k_and_weight_gross():
    assert tuple(UNIVERSES) == ("U14_CONTROL", "G10", "U8_LIQUID_MAJORS")
    assert [(len(x.currencies), x.k) for x in UNIVERSES.values()] == [(14, 4), (10, 3), (8, 2)]
    for definition in UNIVERSES.values():
        definition.validate()
        weights = currency_targets({c: float(i) for i, c in enumerate(definition.currencies)}, definition.k)
        assert sum(weights.values()) == pytest.approx(0, abs=1e-15)
        assert sum(map(abs, weights.values())) == pytest.approx(2, abs=1e-15)
        assert all(abs(x) == pytest.approx(1 / definition.k) for x in weights.values() if x)


def test_u8_benchmark_is_exhaustive_unique_and_deterministic():
    assert benchmark_space_size(8, 2) == 420
    first = family1_benchmark_books(U8.currencies, U8.k)
    second = family1_benchmark_books(tuple(reversed(U8.currencies)), U8.k)
    assert first == second and len(first) == 420
    assert len({(x["longs"], x["shorts"]) for x in first}) == 420
    assert first[0] == {"longs": ("AUD", "CAD"), "shorts": ("CHF", "EUR")}
    assert all(set(x["longs"]).isdisjoint(x["shorts"]) for x in first)


def test_large_benchmark_spaces_reuse_stage_a_seeded_sampling():
    assert benchmark_space_size(10, 3) == 4200
    assert benchmark_space_size(14, 4) == 210210
    assert family1_benchmark_books(G10.currencies, 3) == benchmark_books(G10.currencies, 3, 1000, 20260809)
    assert family1_benchmark_books(U14.currencies, 4) == benchmark_books(U14.currencies, 4, 1000, 20260809)


def test_loco_space_rule_and_full_latent_columns():
    g10 = loco_definitions(G10)
    u8 = loco_definitions(U8)
    assert len(g10) == 10 and all(x["N"] == 9 and x["k"] == 3 and x["benchmark_space"] == 1680 for x in g10)
    assert len(u8) == 8 and all(x["N"] == 7 and x["k"] == 2 and x["benchmark_space"] == 210 for x in u8)
    assert all(x["benchmark_rule"] == "EXHAUSTIVE" for x in u8)
    assert all(tuple(x["latent_columns"]) == U14.currencies for x in (*g10, *u8))


def test_frozen_chronological_blocks_match_mask_exactly():
    import json

    mask = json.loads((ROOT / "prereg/2026-08-14-tms-carry-no-try-direct-gbp-mask.json").read_text())
    blocks = validate_blocks(mask)
    assert [(x["start"], x["stop"], x["count"]) for x in blocks] == [(0, 52, 52), (52, 104, 52), (104, 157, 53)]
    assert tuple(x["block_id"] for x in blocks) == tuple(x["block_id"] for x in BLOCKS)


def test_block_diagnostics_slice_52_52_53_and_benchmark_medians():
    day = 86_400_000
    scores = {c: float(i) for i, c in enumerate(U8.currencies)}
    signals = tuple(SignalStep(i * day, scores, {}) for i in range(157)) + (
        SignalStep(157 * day, None, {}, "terminal"),
    )
    returns = tuple(0.001 if i % 2 else 0.002 for i in range(157))
    path = AccountingPath(360, tuple(range(158)), returns, (), 0.0, 0.0)
    blocks = path_block_diagnostics(path, signals)
    assert [x["count"] for x in blocks] == [52, 52, 53]
    assert all(x["total_return"] > 0 and x["rap"] > 0 for x in blocks)
    medians = benchmark_block_medians([path, path], signals)
    assert [x["path_count"] for x in medians] == [2, 2, 2]
    assert [x["median_rap"] for x in medians] == pytest.approx([x["rap"] for x in blocks])


def test_candidate_signal_and_routing_preserve_u14_discrete_state():
    import json

    routes = json.loads((ROOT / "prereg/2026-08-14-tms-carry-no-try-direct-gbp-universe.json").read_text())["routes"]
    quotes = {leg[0]: OpenQuote(1, 1) for route in routes.values() for leg in route["legs"]}
    scores = {c: float(i) for i, c in enumerate(U14.currencies)}
    signals = (SignalStep(1, scores, quotes), SignalStep(2, None, quotes, "terminal"))
    family = candidate_signal_steps(signals, U14)
    assert [x.timestamp for x in family] == [1, 2]
    assert [x.kind for x in family] == ["rebalance", "terminal"]
    assert family[0].scores == scores
    assert candidate_routes(routes, U14) == routes
    assert candidate_routes(routes, U8)["GBP"]["legs"] == [["GBPUSD.pro", 1]]


def test_u14_accounting_steps_and_dual_paths_are_exactly_legacy():
    quotes = {f"{c}USD.pro": OpenQuote(1, 1) for c in U14.currencies if c != "USD"}
    routes = {c: ({"legs": [[f"{c}USD.pro", 1]]} if c != "USD" else {"legs": []}) for c in U14.currencies}
    scores = {c: float(i) for i, c in enumerate(U14.currencies)}
    signals = (SignalStep(1, scores, quotes), SignalStep(2, None, quotes, "terminal"))
    legacy_steps = accounting_steps_from_signals(signals, U14.currencies, k=4)
    family_steps = candidate_accounting_steps(candidate_signal_steps(signals, U14), U14)
    assert legacy_steps == list(family_steps)
    assert accounting_membership_records(legacy_steps) == accounting_membership_records(family_steps)
    legacy = run_dual_accounting_paths(1, legacy_steps, [], routes)
    family = run_dual_accounting_paths(1, family_steps, [], routes)
    assert legacy == family and legacy[360] is not legacy[365]


def test_event_identity_binds_financing_discrete_state():
    schedule = FinancingSchedule(date(2025, 1, 1), date(2025, 1, 7), {"GBPUSD.pro": (1, -1)})
    event = FinancingEvent(date(2025, 1, 2), schedule, {"GBPUSD.pro": OpenQuote(1, 1)}, None, 3)
    assert event_identity([event]) == ({
        "after_step": 3,
        "day": "2025-01-02",
        "schedule_valid_from": "2025-01-01",
        "schedule_valid_to": "2025-01-07",
        "open_routes": ["GBPUSD.pro"],
        "days_charged": None,
    },)


def test_numeric_parity_tolerance_is_absolute_and_fail_closed():
    maximum, count = _numeric_diff({"x": [1.0, 2.0]}, {"x": [1.0 + 5e-13, 2.0]})
    assert maximum <= NUMERIC_TOLERANCE and count == 2
    with pytest.raises(IntegrityError, match="exceeds"):
        _numeric_diff([1.0], [1.0 + 2e-12])
    with pytest.raises(IntegrityError, match="keys"):
        _numeric_diff({"a": 1}, {"b": 1})


def test_universe_artifact_is_non_economic_and_hash_bound():
    artifact = build_universe_artifact(ROOT)
    assert artifact["annualization_days"] == ANNUALIZATION_DAYS == 365.25
    assert artifact["economic_execution_authorized"] is False
    assert artifact["candidate_disposition"] == "PENDING_EXTERNAL_ADJUDICATION"
    assert artifact["candidates"]["U8_LIQUID_MAJORS"]["benchmark_space"] == 420
    assert len(artifact["preregistration_sha256"]) == 64


def test_emitted_readiness_and_parity_artifacts_are_hash_bound():
    import hashlib
    import json

    readiness_path = ROOT / "prereg/2026-08-21-tms-carry-unlevered-family-1-readiness.json"
    parity_path = ROOT / "prereg/2026-08-21-tms-carry-unlevered-family-1-u14-parity.json"
    if not readiness_path.is_file() or not parity_path.is_file():
        pytest.skip("generated integration artifacts not emitted yet")
    readiness = json.loads(readiness_path.read_text())
    parity = json.loads(parity_path.read_text())
    module_path = ROOT / "bot/forex/family1_universe.py"
    assert readiness["source_sha256"]["bot/forex/family1_universe.py"] == hashlib.sha256(module_path.read_bytes()).hexdigest()
    assert parity["readiness_artifact_sha256"] == hashlib.sha256(readiness_path.read_bytes()).hexdigest()
    assert parity["status"] == "U14_PARITY_PASSED"
    assert parity["candidate_economics_computed"] is False and parity["network_accessed"] is False
    assert parity["discrete"]["exact"] is True
    assert parity["floating"]["attempt3_max_abs_diff"] <= 1e-12
    assert parity["floating"]["baseline_vector_max_abs_diff"] <= 1e-12
    assert all(parity["published_posthoc_match"].values())


def test_runner_exposes_no_candidate_economic_mode():
    source = (ROOT / "run_family1_universe.py").read_text(encoding="utf-8")
    assert '"preflight", "emit-readiness", "u14-parity"' in source
    assert "g10" not in source.lower() and "u8" not in source.lower()
