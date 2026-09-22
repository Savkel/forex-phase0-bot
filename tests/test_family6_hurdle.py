from datetime import date

import pytest

from bot.forex.family1_universe import U14
from bot.forex.family4_cadence import run_cadence_accounting_path
from bot.forex.family5_breadth import breadth_accounting_steps, equal_targets, select_memberships
from bot.forex.family6_hurdle import (
    HurdleConfig, _Ledger, _target_cost, hurdle_accounting_steps, hurdle_metrics,
)
from bot.forex.stage_a_carry import FinancingSchedule, OpenQuote, SignalStep


def routes_quotes(mid=1.0, spread=.002):
    routes, quotes = {}, {}
    for currency in U14.currencies:
        if currency == "USD":
            routes[currency] = {"legs": []}
            continue
        pair = currency+"USD.pro"
        routes[currency] = {"legs": [(pair, 1.0)]}
        quotes[pair] = OpenQuote(mid-spread/2, mid+spread/2)
    return routes, quotes


def score(order):
    return {currency: float(len(order)-i) for i, currency in enumerate(order)}


ORDER_A = list(U14.currencies)
ORDER_B = ["EUR", "CAD", "CHF", "CZK", "GBP", "HUF", "AUD",
           "JPY", "NOK", "NZD", "PLN", "SEK", "USD", "ZAR"]


def schedule(routes, *, eur=1000.0, aud=0.0):
    rates = {}
    for raw in routes.values():
        for pair, _ in raw["legs"]:
            rates[pair] = (0.0, 0.0)
    rates["EURUSD.pro"] = (eur, -eur)
    rates["AUDUSD.pro"] = (aud, -aud)
    return FinancingSchedule(date(2025, 1, 1), date(2025, 1, 7), rates)


def signals(second=ORDER_B, *, future_mid=1.02):
    routes, q1 = routes_quotes()
    _, q2 = routes_quotes(1.01)
    _, q3 = routes_quotes(future_mid)
    return routes, (
        SignalStep(1, score(ORDER_A), q1, "rebalance"),
        SignalStep(2, score(second), q2, "rebalance"),
        SignalStep(3, score(second), q3, "rebalance"),
        SignalStep(4, None, q3, "terminal"),
    )


@pytest.mark.parametrize("value", [
    {"candidate_id": "BAD"}, {"candidate_id": "HURDLE_1X", "h": 1},
    {"candidate_id": "HURDLE_1X", "k": 3},
    {"candidate_id": "HURDLE_1X", "forecast_days": 8},
    {"candidate_id": "HURDLE_1X", "extra": 1},
])
def test_config_rejects_every_nonfrozen_dimension(value):
    with pytest.raises(ValueError):
        HurdleConfig.from_mapping(value)


def test_unchanged_membership_bypasses_hurdle_but_executes_m1_reset():
    routes, sig = signals(ORDER_A)
    s = schedule(routes)
    steps, records = hurdle_accounting_steps(
        sig, (s, s, s, None), (), routes, HurdleConfig("HURDLE_1X"),
        require_full=False)
    assert records[1]["decision"] == "unchanged_m1_reset"
    assert not records[1]["hurdle_applied"]
    path = run_cadence_accounting_path(1.0, steps, (), routes, 360)
    assert path.trades[1].fills


def test_veto_executes_a_reset_never_passive_hold():
    routes, sig = signals()
    s = schedule(routes, eur=-1000, aud=1000)
    steps, records = hurdle_accounting_steps(
        sig, (s, s, s, None), (), routes, HurdleConfig("HURDLE_1X"),
        require_full=False)
    assert records[1]["decision"] == "hurdle_veto"
    assert records[1]["accepted_longs"] == [c for c in ORDER_B if c in set(ORDER_A[:4])]
    path = run_cadence_accounting_path(1.0, steps, (), routes, 360)
    assert path.trades[1].fills


def test_candidate_formulas_control_one_x_and_two_x():
    routes, sig = signals()
    bad = schedule(routes, eur=-1000, aud=1000)
    good = schedule(routes, eur=1000, aud=-1000)
    decisions = {}
    for cid, current in (("HURDLE_OFF_CONTROL", bad), ("HURDLE_1X", good),
                         ("HURDLE_2X", good)):
        _, records = hurdle_accounting_steps(
            sig, (current, current, current, None), (), routes, HurdleConfig(cid),
            require_full=False)
        decisions[cid] = records[1]["decision"]
    assert decisions == {"HURDLE_OFF_CONTROL": "control_accept",
                         "HURDLE_1X": "hurdle_accept",
                         "HURDLE_2X": "hurdle_accept"}


def test_k_clamps_nonpositive_cost_and_uses_max_denominator():
    routes, quotes = routes_quotes()
    active = U14.currencies
    a = equal_targets(set(ORDER_A[:4]), set(ORDER_A[-4:]), 4, active=active)
    longs, shorts, _, _ = select_memberships(
        ORDER_B, 4, set(ORDER_A[:4]), set(ORDER_A[-4:]), fresh=False)
    b = equal_targets(longs, shorts, 4, active=active)
    base = _Ledger()
    b_target, _ = _target_cost(base, b, routes, quotes)
    a_target, _ = _target_cost(base, a, routes, quotes)
    s = schedule(routes)
    ledgers = {360: _Ledger(positions=dict(b_target.units)),
               365: _Ledger(positions=dict(b_target.units))}
    metrics = hurdle_metrics(ledgers, a, b, routes, quotes, s)
    assert metrics["dc"][360] < 0 and metrics["dc"][365] < 0 and metrics["K"] == 0
    ledgers[365].positions = dict(a_target.units)
    metrics = hurdle_metrics(ledgers, a, b, routes, quotes, s)
    assert metrics["K"] == pytest.approx(metrics["dc"][365])
    assert metrics["K"] > 0


def test_future_schedules_and_quotes_cannot_change_earlier_decisions():
    routes, left = signals(future_mid=1.02)
    _, right = signals(future_mid=9.0)
    current = schedule(routes, eur=-1000, aud=1000)
    future_a = schedule(routes, eur=1000, aud=-1000)
    future_b = schedule(routes, eur=-9999, aud=9999)
    _, lr = hurdle_accounting_steps(
        left, (current, current, future_a, None), (), routes,
        HurdleConfig("HURDLE_1X"), require_full=False)
    _, rr = hurdle_accounting_steps(
        right, (current, current, future_b, None), (), routes,
        HurdleConfig("HURDLE_1X"), require_full=False)
    assert lr[:2] == rr[:2]


def test_gap_exit_reentry_and_terminal_are_forced_and_fresh():
    routes, q = routes_quotes()
    s = schedule(routes)
    sig = (
        SignalStep(1, score(ORDER_A), q, "rebalance"),
        SignalStep(2, None, q, "gap_exit"),
        SignalStep(3, score(ORDER_B), q, "gap_reentry"),
        SignalStep(4, None, q, "terminal"),
    )
    _, records = hurdle_accounting_steps(
        sig, (s, None, s, None), (), routes, HurdleConfig("HURDLE_2X"),
        require_full=False)
    assert [r["decision"] for r in records] == [
        "fresh_accept", "gap_exit", "fresh_accept", "terminal"]
    assert not any(r["hurdle_applied"] for r in records)


def test_control_exact_membership_target_and_record_parity():
    routes, q = routes_quotes(spread=.0001)
    s = schedule(routes)
    sig = [SignalStep(i+1, score(ORDER_A if i == 0 else ORDER_B), q, "rebalance")
           for i in range(157)]
    sig.append(SignalStep(158, None, q, "terminal"))
    actual_steps, records = hurdle_accounting_steps(
        tuple(sig), tuple([s]*157+[None]), (), routes,
        HurdleConfig("HURDLE_OFF_CONTROL"))
    expected_steps, expected_records = breadth_accounting_steps(tuple(sig), 4)
    assert actual_steps == expected_steps
    assert tuple(r["h2"] for r in records) == expected_records
