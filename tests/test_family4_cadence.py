from __future__ import annotations

from bot.forex.family1_universe import SignalStep, U14
from bot.forex.family2_hysteresis import hysteresis_accounting_steps
from bot.forex.family4_cadence import (
    CadenceStep, _accounting_view, cadence_accounting_steps, run_cadence_accounting_path,
    static_cadence_steps,
)
from bot.forex.stage_a_carry import OpenQuote


def _signals(*, gap_after=None):
    scores = {c: float(14-i) for i, c in enumerate(U14.currencies)}
    out = []; timestamp = 1_700_000_000_000
    for i in range(157):
        if gap_after is not None and i == gap_after:
            out.append(SignalStep(timestamp, None, {}, "gap_exit")); timestamp += 1
        kind = "gap_reentry" if gap_after is not None and i == gap_after else "rebalance"
        shifted = {c: scores[U14.currencies[(j+i) % 14]] for j, c in enumerate(U14.currencies)}
        out.append(SignalStep(timestamp, shifted, {}, kind)); timestamp += 1
    out.append(SignalStep(timestamp, None, {}, "terminal"))
    return tuple(out)


def test_frozen_candidate_action_schedules_and_anchor():
    signals = _signals()
    for m in (1, 2, 4):
        steps, records = cadence_accounting_steps(signals, m)
        actions = [step.execute for step in steps[:-1]]
        assert actions == [i % m == 0 for i in range(157)]
        assert records[0]["segment_index"] == 0 and records[0]["state_reset"]
        assert sum(abs(x) for x in steps[0].target_weights.values()) == 2


def test_skips_freeze_h2_state_and_membership():
    signals = list(_signals())
    reversed_scores = {c: float(i) for i, c in enumerate(U14.currencies)}
    signals[1] = SignalStep(signals[1].timestamp, reversed_scores, {}, "rebalance")
    steps, records = cadence_accounting_steps(signals, 2)
    assert not steps[1].execute and steps[1].kind == "hold_mark"
    assert steps[1].target_weights == steps[0].target_weights
    assert records[1]["final_longs"] == records[1]["prior_longs"]
    assert set(records[2]["prior_longs"]) == {c for c, w in steps[0].target_weights.items() if w > 0}


def test_gap_exit_reentry_resets_anchor_and_terminal_is_immediate():
    steps, records = cadence_accounting_steps(_signals(gap_after=3), 4)
    gap_index = next(i for i, step in enumerate(steps) if step.kind == "gap_exit")
    assert steps[gap_index].execute and not any(steps[gap_index].target_weights.values())
    assert steps[gap_index+1].kind == "gap_reentry" and steps[gap_index+1].execute
    assert records[gap_index+1]["segment_index"] == 0 and records[gap_index+1]["state_reset"]
    assert steps[-1].kind == "terminal" and steps[-1].execute and not any(steps[-1].target_weights.values())


def test_hold_mark_keeps_exact_units_has_no_fill_cost_and_closes_week():
    quote = OpenQuote(0.999, 1.001); opens = {"AUDUSD.pro": quote}
    weights = {"AUD": 1.0, "USD": -1.0}; flat = {"AUD": 0.0, "USD": 0.0}
    steps = (CadenceStep(1, weights, opens, "rebalance", True),
             CadenceStep(2, weights, opens, "hold_mark", False),
             CadenceStep(3, flat, opens, "terminal", True))
    path = run_cadence_accounting_path(1.0, steps, (), {"AUD": [["AUDUSD.pro", 1]], "USD": []}, 360)
    assert path.trades[1].target_units == path.trades[0].target_units
    assert path.trades[1].fills == {} and path.trades[1].spread_cost == 0
    assert len(path.period_returns) == 2


def test_static_benchmark_uses_matched_cadence_without_h2_membership_changes():
    signals = _signals(gap_after=5); book = {"longs": U14.currencies[:4], "shorts": U14.currencies[-4:]}
    steps = static_cadence_steps(signals, book, 4)
    active = steps[0].target_weights
    assert all(step.target_weights == active for step in steps if step.kind not in ("gap_exit", "terminal"))
    gap = next(i for i, step in enumerate(steps) if step.kind == "gap_exit")
    assert steps[gap+1].execute and steps[gap+1].kind == "gap_reentry"
    segment = steps[:gap]
    assert [i for i, step in enumerate(segment) if step.execute] == [0, 4]


def test_m1_target_and_discrete_h2_paths_are_exact():
    signals = _signals(gap_after=63)
    expected_steps, expected_records = hysteresis_accounting_steps(signals, 2)
    actual_steps, actual_records = cadence_accounting_steps(signals, 1)
    assert _accounting_view(actual_steps) == expected_steps
    drop = {"segment_index", "action", "execute", "source_kind"}
    cleaned = tuple({k: v for k, v in row.items() if k not in drop} for row in actual_records)
    assert cleaned == expected_records
