from __future__ import annotations

from pathlib import Path

import pytest

from bot.forex.family1_universe import U14, SignalStep, accounting_membership_records
from bot.forex.family2_hysteresis import hysteresis_accounting_steps
from bot.forex.family3_weighting import (
    CANDIDATE_TAUS, WEIGHT_BOUNDS, build_readiness, strength_weight_targets,
    weight_turnover_diagnostics, weighted_h2_accounting_steps, weighted_static_accounting_steps,
)


ROOT = Path(__file__).resolve().parents[1]


def _scores(order):
    return {currency: float(len(order) - index) for index, currency in enumerate(order)}


def _signals(orders, *, gap_after: int | None = None):
    result = []; evaluable = 0
    for index, order in enumerate(orders):
        result.append(SignalStep(index + 1, _scores(order), {}, "gap_reentry" if gap_after == index - 1 else "rebalance"))
        evaluable += 1
        if gap_after == index:
            result.append(SignalStep(index + 1000, None, {}, "gap_exit"))
    while evaluable < 157:
        result.append(SignalStep(2000 + evaluable, _scores(orders[-1]), {}, "rebalance")); evaluable += 1
    result.append(SignalStep(9999, None, {}, "terminal"))
    return tuple(result)


def test_frozen_candidates_and_formula_invariants():
    assert CANDIDATE_TAUS == {"EQ_H2": 0.0, "CS_MILD": 0.10, "CS_STRONG": 0.20}
    assert WEIGHT_BOUNDS == {"EQ_H2": (0.25, 0.25), "CS_MILD": (0.20, 0.30), "CS_STRONG": (0.15, 0.35)}
    scores = _scores(U14.currencies); longs, shorts = U14.currencies[:4], U14.currencies[-4:]
    for candidate, tau in CANDIDATE_TAUS.items():
        weights = strength_weight_targets(scores, longs, shorts, tau, active=U14.currencies)
        assert sum(weights[c] for c in longs) == pytest.approx(1, abs=1e-12)
        assert sum(weights[c] for c in shorts) == pytest.approx(-1, abs=1e-12)
        assert sum(map(abs, weights.values())) == pytest.approx(2, abs=1e-12)
        assert all(WEIGHT_BOUNDS[candidate][0] - 1e-12 <= abs(weights[c]) <= WEIGHT_BOUNDS[candidate][1] + 1e-12 for c in (*longs, *shorts))


def test_ties_and_zero_dispersion_fall_back_safely():
    active = U14.currencies; longs, shorts = active[:4], active[-4:]
    zero = {currency: 7.0 for currency in active}
    assert sorted(abs(x) for x in strength_weight_targets(zero, longs, shorts, 0.20, active=active).values() if x) == [0.25] * 8
    tied = _scores(active); tied[longs[0]] = tied[longs[1]]
    weights = strength_weight_targets(tied, longs, shorts, 0.20, active=active)
    assert weights[longs[0]] == weights[longs[1]]


def test_h2_membership_gap_and_eq_exact_parity_are_preserved():
    moved = tuple(reversed(U14.currencies)); signals = _signals((U14.currencies, moved, moved), gap_after=1)
    expected, _ = hysteresis_accounting_steps(signals, 2)
    eq, _ = weighted_h2_accounting_steps(signals, 0.0)
    assert eq == expected
    for tau in CANDIDATE_TAUS.values():
        actual, _ = weighted_h2_accounting_steps(signals, tau)
        assert accounting_membership_records(actual) == accounting_membership_records(expected)
        assert next(step for step in actual if step.kind == "gap_exit").target_weights == {c: 0.0 for c in U14.currencies}


def test_static_books_never_apply_h2_logic_and_capture_weight_turnover():
    signals = _signals((U14.currencies, tuple(reversed(U14.currencies))))
    book = {"longs": U14.currencies[:4], "shorts": U14.currencies[-4:]}
    steps = weighted_static_accounting_steps(signals, book, 0.20, active=U14.currencies)
    for step in steps:
        if step.kind not in ("gap_exit", "terminal"):
            assert {c for c, value in step.target_weights.items() if value > 0} == set(book["longs"])
            assert {c for c, value in step.target_weights.items() if value < 0} == set(book["shorts"])
    diagnostics = weight_turnover_diagnostics(steps, signals)
    assert diagnostics["totals"]["weight_only_currency_turnover"] > 0
    assert diagnostics["totals"]["total_currency_turnover"] == pytest.approx(
        diagnostics["totals"]["weight_only_currency_turnover"] + diagnostics["totals"]["membership_or_sign_currency_turnover"]
    )


def test_readiness_is_hash_bound_and_non_economic():
    readiness = build_readiness(ROOT)
    assert readiness["status"] == "FAMILY3_READINESS_PASSED"
    assert readiness["performance_computed"] is False and readiness["nonzero_tau_economics_authorized"] is False
    assert readiness["selected_base"] == "H2" and readiness["h"] == 2
    assert set(readiness["configurations"]) == set(CANDIDATE_TAUS)
    assert readiness["ic_reuse_only"] is True and readiness["static_memberships_candidate_weights"] is True


def test_runner_is_fail_closed():
    source = (ROOT / "run_family3_weighting.py").read_text(encoding="utf-8")
    module = (ROOT / "bot/forex/family3_weighting.py").read_text(encoding="utf-8")
    assert '"eq-h2-parity"' in source and '"execute-candidates"' in source
    assert "ECONOMICS_STARTED" in module and "consumption_count" in module
    assert "PENDING_EXTERNAL_ADJUDICATION" in module
