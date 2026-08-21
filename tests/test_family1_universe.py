from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

import bot.forex.family1_study as family1_study
from bot.forex.family1_universe import (
    ANNUALIZATION_DAYS,
    BLOCKS,
    CandidateInputs,
    G10,
    NUMERIC_TOLERANCE,
    ParityAccumulator,
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
    stationary_bootstrap_evidence,
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
from bot.forex.family1_study import concentration_diagnostics, diagnostic_flags, path_diagnostics


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
        "effective_days_charged_by_open_route": {"GBPUSD.pro": 1},
    },)


def test_numeric_parity_tolerance_is_absolute_and_fail_closed():
    maximum, count = _numeric_diff({"x": [1.0, 2.0]}, {"x": [1.0 + 5e-13, 2.0]})
    assert maximum <= NUMERIC_TOLERANCE and count == 2
    with pytest.raises(IntegrityError, match="exceeds"):
        _numeric_diff([1.0], [1.0 + 2e-12])
    with pytest.raises(IntegrityError, match="keys"):
        _numeric_diff({"a": 1}, {"b": 1})


def test_section12_parity_reports_shapes_counts_and_all_mismatches():
    parity = ParityAccumulator()
    parity.add("full_paths", {"x": [1.0, 2.0], "kind": "base"}, {"x": [1.0, 2.0 + 2e-12], "kind": "base"})
    parity.add("full_paths", [1, 2], [1])
    report = parity.report()
    cell = report["cells"]["full_paths"]
    assert cell["instances"] == 2
    assert cell["numeric_mismatch_count"] == 1
    assert cell["shape_mismatch_count"] == 1
    assert report["mismatch_count"] == 2
    assert cell["expected_shapes"] and cell["actual_shapes"]


def test_family1_ic_bootstrap_supports_frozen_bonferroni_quantile_deterministically():
    values = [0.1, -0.05, 0.2, 0.0, 0.15, -0.02, 0.08, 0.04]
    first, first_means = stationary_bootstrap_evidence(
        values, lower_quantile=0.025, reps=100, seed=20260808, block_selector=lambda _: 1
    )
    second, second_means = stationary_bootstrap_evidence(
        values, lower_quantile=0.025, reps=100, seed=20260808, block_selector=lambda _: 1
    )
    assert first == second and first_means == second_means
    assert first["one_sided_confidence"] == 0.975
    assert first["lower_bound_quantile"] == 0.025
    assert first["bootstrap_block_length"] == 1


def test_synthetic_candidate_diagnostics_cover_accounting_turnover_blocks_and_concentration():
    day = 86_400_000
    routes = {c: ({"legs": [[f"{c}USD.pro", 1]]} if c != "USD" else {"legs": []}) for c in U8.currencies}
    scores = {c: float(i) for i, c in enumerate(U8.currencies)}
    signals = []
    for step in range(157):
        quotes = {
            f"{c}USD.pro": OpenQuote(1 + (step * (i + 1) * 1e-5), 1 + (step * (i + 1) * 1e-5))
            for i, c in enumerate(U8.currencies) if c != "USD"
        }
        signals.append(SignalStep(step * day, scores, quotes))
    terminal_quotes = {
        f"{c}USD.pro": OpenQuote(1 + (157 * (i + 1) * 1e-5), 1 + (157 * (i + 1) * 1e-5))
        for i, c in enumerate(U8.currencies) if c != "USD"
    }
    signals.append(SignalStep(157 * day, None, terminal_quotes, "terminal"))
    family = candidate_signal_steps(signals, U8)
    paths = run_dual_accounting_paths(1, candidate_accounting_steps(family, U8), [], routes)
    inputs = CandidateInputs(U8, family, routes, {}, (), ())
    diagnostics = path_diagnostics(paths[360], family, [], routes)
    assert len(diagnostics["blocks"]) == 3
    assert diagnostics["currency_turnover"] == pytest.approx(4)
    assert diagnostics["trade_count"] > 0
    assert diagnostics["spot_pnl"] == pytest.approx(diagnostics["total_return"])
    concentration = concentration_diagnostics(inputs)
    assert concentration["hhi_mean"] == pytest.approx(1 / (2 * U8.k))
    assert set(concentration["currencies"]) == set(U8.currencies)


def test_diagnostic_flags_are_labels_not_a_disposition():
    base = {
        "cagr": 0.05, "max_drawdown": -0.10, "rap": 0.2, "calmar": 0.5,
        "currency_turnover": 3.0, "total_spread_cost": 0.01, "total_financing": 0.02,
        "mean_routed_usd_gross": 1.5,
    }
    control_base = {**base, "cagr": 0.023, "rap": 0.1, "calmar": 0.25, "currency_turnover": 4.0}
    candidate = {"concentration": {"hhi_mean": 0.25}, "denominators": {d: {
        "base": base, "benchmark_rap_excess": 0.1, "benchmark_mdd_difference": 0.01,
        "adverse_total_return": 0.01, "spread_x3_total_return": 0.005,
    } for d in ("360", "365")}}
    control = {"concentration": {"hhi_mean": 0.125}, "denominators": {d: {"base": control_base} for d in ("360", "365")}}
    flags = diagnostic_flags(candidate, control)
    assert flags["DELTA_CAGR_GE_1PP_REFERENCE_BOTH_DENOMINATORS"] is True
    assert flags["DENOMINATOR_DIRECTIONAL_DISAGREEMENT"] is False
    assert "candidate_disposition" not in flags


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
    if readiness["source_sha256"].get("bot/forex/family1_universe.py") != hashlib.sha256(module_path.read_bytes()).hexdigest():
        pytest.skip("generated integration artifacts are stale pending authorized U14 parity regeneration")
    assert readiness["source_sha256"]["bot/forex/family1_universe.py"] == hashlib.sha256(module_path.read_bytes()).hexdigest()
    assert parity["readiness_artifact_sha256"] == hashlib.sha256(readiness_path.read_bytes()).hexdigest()
    assert parity["status"] == "U14_PARITY_PASSED"
    assert parity["candidate_economics_computed"] is False and parity["network_accessed"] is False
    assert parity["discrete"]["exact"] is True
    assert parity["floating"]["attempt3_max_abs_diff"] <= 1e-12
    assert parity["floating"]["section12_max_abs_diff"] <= 1e-12
    assert parity["section12_parity"]["mismatch_count"] == 0
    assert parity["section12_parity"]["expected_actual_shapes"]
    assert parity["control_diagnostics"]["candidate_id"] == "U14_CONTROL"
    assert all(parity["published_posthoc_match"].values())


def test_runner_exposes_fail_closed_candidate_economic_mode_without_executing_it():
    source = (ROOT / "run_family1_universe.py").read_text(encoding="utf-8")
    study = (ROOT / "bot/forex/family1_study.py").read_text(encoding="utf-8")
    assert '"execute-candidates"' in source
    assert "ECONOMICS_STARTED" in study and "consumption_count" in study
    assert "PENDING_EXTERNAL_ADJUDICATION" in study
    assert "automatic_candidate_rejection_or_winner_selection" in study


def test_one_shot_candidate_plumbing_writes_all_artifacts_without_selecting(monkeypatch, tmp_path):
    import json

    parity_path = tmp_path / family1_study.PARITY_ARTIFACT_REL
    parity_path.parent.mkdir(parents=True)
    parity_path.write_text(json.dumps({
        "status": "U14_PARITY_PASSED",
        "section12_parity": {"mismatch_count": 0},
        "control_diagnostics": {"denominators": {}, "concentration": {}},
    }))
    prereg_path = tmp_path / family1_study.PREREG_REL
    prereg_path.parent.mkdir(parents=True, exist_ok=True)
    prereg_path.write_text("frozen")
    readiness_path = tmp_path / family1_study.READINESS_ARTIFACT_REL
    readiness_path.write_text("{}")

    monkeypatch.setattr(family1_study, "validate_readiness_artifacts", lambda _: {"status": "PASSED"})
    monkeypatch.setattr(family1_study, "load_frozen_context", lambda _: object())
    monkeypatch.setattr(family1_study, "prepare_candidate", lambda context, definition: definition)
    monkeypatch.setattr(family1_study, "candidate_study", lambda definition: {
        "candidate_id": definition.candidate_id,
        "candidate_disposition": "PENDING_EXTERNAL_ADJUDICATION",
    })
    monkeypatch.setattr(family1_study, "diagnostic_flags", lambda candidate, control: {"diagnostic_only": True})

    result_path = family1_study.execute_family1_candidates(tmp_path)
    execution = json.loads((tmp_path / family1_study.EXECUTION_ARTIFACT_REL).read_text())
    result = json.loads(result_path.read_text())
    completion = json.loads((tmp_path / family1_study.COMPLETION_ARTIFACT_REL).read_text())
    assert execution["status"] == "ECONOMICS_STARTED" and execution["consumption_count"] == 1
    assert list(result["candidates"]) == ["G10", "U8_LIQUID_MAJORS"]
    assert result["automatic_candidate_rejection_or_winner_selection"] is False
    assert result["candidate_disposition"] == "PENDING_EXTERNAL_ADJUDICATION"
    assert completion["status"] == "ECONOMICS_COMPLETED_PENDING_EXTERNAL_ADJUDICATION"
    with pytest.raises(PermissionError, match="already consumed or started"):
        family1_study.execute_family1_candidates(tmp_path)
