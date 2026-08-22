from __future__ import annotations

from pathlib import Path

import pytest

from bot.forex.family1_study import concentration_diagnostics
from bot.forex.family1_universe import U14, CandidateInputs, SignalStep, candidate_accounting_steps
from bot.forex.family2_hysteresis import (
    H_VALUES, _concentration, build_readiness, hysteresis_accounting_steps,
)


ROOT = Path(__file__).resolve().parents[1]


def _scores(order):
    return {currency: float(len(order) - index) for index, currency in enumerate(order)}


def _signals(orders, *, gap_after: int | None = None):
    result = []
    evaluable = 0
    for index, order in enumerate(orders):
        result.append(SignalStep(index + 1, _scores(order), {}, "gap_reentry" if gap_after == index - 1 else "rebalance"))
        evaluable += 1
        if gap_after == index:
            result.append(SignalStep(index + 1000, None, {}, "gap_exit"))
    while evaluable < 157:
        result.append(SignalStep(2000 + evaluable, _scores(orders[-1]), {}, "rebalance"))
        evaluable += 1
    result.append(SignalStep(9999, None, {}, "terminal"))
    return tuple(result)


def _move_first_long_to_rank(rank):
    base = list(U14.currencies); currency = base.pop(0); base.insert(rank - 1, currency); return tuple(base)


def test_frozen_h_values_and_h0_exact_control_memberships():
    signals = _signals((U14.currencies, tuple(reversed(U14.currencies))))
    actual, _ = hysteresis_accounting_steps(signals, 0)
    assert H_VALUES == (0, 1, 2, 3)
    assert actual == tuple(candidate_accounting_steps(signals, U14))
    for step in actual:
        if step.kind not in ("gap_exit", "terminal"):
            assert sum(step.target_weights.values()) == 0
            assert sum(map(abs, step.target_weights.values())) == 2
            assert sorted(abs(x) for x in step.target_weights.values() if x) == [0.25] * 8


@pytest.mark.parametrize("h,rank,retained", ((1, 5, True), (1, 6, False), (2, 6, True), (3, 7, True)))
def test_rank_exit_buffers_are_mechanical(h, rank, retained):
    moved = _move_first_long_to_rank(rank)
    _, records = hysteresis_accounting_steps(_signals((U14.currencies, moved)), h)
    decision = records[1]
    assert ("AUD" in decision["final_longs"]) is retained
    assert decision["suppressed_long_replacements"] == int(retained)
    assert decision["avoided_long_replacements"] == int(retained)
    assert len(decision["final_longs"]) == len(decision["final_shorts"]) == 4


def test_gap_reentry_resets_hysteresis_to_current_extremes():
    moved = _move_first_long_to_rank(7)
    steps, records = hysteresis_accounting_steps(_signals((U14.currencies, moved, moved), gap_after=1), 3)
    before_gap = next(record for record in records if record["timestamp"] == 2)
    reentry = next(record for record in records if record["kind"] == "gap_reentry")
    assert "AUD" in before_gap["final_longs"]
    assert reentry["state_reset"] is True and "AUD" not in reentry["final_longs"]
    gap = next(step for step in steps if step.kind == "gap_exit")
    assert sum(map(abs, gap.target_weights.values())) == 0


def test_loco_h3_overlap_is_disjoint_and_keeps_scale():
    steps, _ = hysteresis_accounting_steps(_signals((U14.currencies, _move_first_long_to_rank(7))), 3, omitted="ZAR")
    for step in steps:
        if step.kind not in ("gap_exit", "terminal"):
            assert step.target_weights["ZAR"] == 0
            assert sum(map(abs, step.target_weights.values())) == 2
            assert sum(value > 0 for value in step.target_weights.values()) == 4
            assert sum(value < 0 for value in step.target_weights.values()) == 4


def test_h0_concentration_matches_frozen_family1_definition():
    signals = _signals((U14.currencies, tuple(reversed(U14.currencies))))
    steps, _ = hysteresis_accounting_steps(signals, 0)
    inputs = CandidateInputs(U14, signals, {}, {}, (), ())
    assert _concentration(steps) == concentration_diagnostics(inputs)


def test_readiness_is_hash_bound_and_non_economic():
    readiness = build_readiness(ROOT)
    assert readiness["status"] == "FAMILY2_READINESS_PASSED"
    assert readiness["h_values"] == [0, 1, 2, 3]
    assert readiness["performance_computed"] is False
    assert readiness["nonzero_h_economics_authorized"] is False
    assert readiness["family1_parity_status"] == "U14_PARITY_PASSED"
    assert set(readiness["configuration_paths"]) == {"0", "1", "2", "3"}


def test_runner_exposes_fail_closed_modes_without_execution():
    source = (ROOT / "run_family2_hysteresis.py").read_text(encoding="utf-8")
    module = (ROOT / "bot/forex/family2_hysteresis.py").read_text(encoding="utf-8")
    assert '"h0-parity"' in source and '"execute-candidates"' in source
    assert "ECONOMICS_STARTED" in module and "consumption_count" in module
    assert "PENDING_EXTERNAL_ADJUDICATION" in module
