from __future__ import annotations

from dataclasses import replace
from datetime import date
from itertools import combinations
from pathlib import Path
from types import SimpleNamespace
import gzip
import json
import random
import socket

import numpy as np
import pytest

from bot.forex import family5_breadth as f5
from bot.forex import family5_study as study
from bot.forex import family4_cadence as f4
from bot.forex.family1_universe import U14, CandidateInputs, _canonical_sha, _comparison_stats, _json, _sha256
from bot.forex.family1_study import _scenario_paths
from bot.forex.stage_a_carry import SignalStep, OpenQuote, FinancingSchedule, FinancingEvent
from bot.forex.stage_a_orchestration import IntegrityError

ROOT = Path(__file__).resolve().parents[1]


def signals(*, gaps=(61,), scores=None, quotes=False):
    result, timestamp = [], 1_700_000_000_000
    for i in range(157):
        opens = ({c+"USD.pro": OpenQuote(1+i*0.00001-0.00002, 1+i*0.00001+0.00002)
                  for c in U14.currencies if c != "USD"} if quotes else {})
        if i in gaps:
            result.append(SignalStep(timestamp, None, opens, "gap_exit"))
            timestamp += 86400000
        row = scores or {c: float((j+i) % 14) for j, c in enumerate(U14.currencies)}
        result.append(SignalStep(timestamp, row, opens, "gap_reentry" if i in gaps else "rebalance"))
        timestamp += 7*86400000
    result.append(SignalStep(timestamp, None, opens, "terminal"))
    return tuple(result)


def synthetic_inputs():
    rows = signals(quotes=True)
    routes = {c: [[c+"USD.pro", 1]] if c != "USD" else [] for c in U14.currencies}
    schedule = FinancingSchedule(date(2023, 1, 1), date(2030, 1, 1),
                                 {c+"USD.pro": (2.0, -3.0) for c in U14.currencies if c != "USD"})
    events = tuple(FinancingEvent(date(2024, 1, 2), schedule, s.opens, 1.0, i)
                   for i, s in enumerate(rows) if s.scores is not None)
    return CandidateInputs(U14, rows, routes, {}, events, ())


@pytest.mark.parametrize("bad", [True, False, 3.0, 4.5, 0, 1, 2, 6, "4", None])
def test_reject_nonfrozen_k(bad):
    with pytest.raises(ValueError):
        f5.BreadthConfig(bad)


@pytest.mark.parametrize("config", [
    {"k": 4, "other": 1}, {"h": 2}, {"k": 4, "h": 3}, {"k": 4, "h": 2.0},
    {"k": 4, "m": True}, {"k": 4, "m": 2}, {"k": 4, "weighting": "CS"},
    {"k": 4, "currencies": U14.currencies[:-1]}, {"k": 4, "gross": 3},
    {"k": 4, "long_target": True}, {"k": 4, "short_target": -0.5},
])
def test_config_unknown_keys_and_invariants(config):
    with pytest.raises(ValueError):
        f5.BreadthConfig.from_mapping(config)


@pytest.mark.parametrize("k", [3, 4, 5])
def test_all_omissions_fixed_k_scale_and_state(k):
    rows = signals(gaps=(1, 61, 62, 155))
    for omitted in (None, *U14.currencies):
        steps, records = f5.breadth_accounting_steps(rows, k, omitted=omitted)
        for step, record in zip(steps, records):
            if step.kind in ("terminal", "gap_exit"):
                assert not any(step.target_weights.values()) and record["state_reset"]
            else:
                longs = {c for c, w in step.target_weights.items() if w > 0}
                shorts = {c for c, w in step.target_weights.items() if w < 0}
                assert len(longs) == len(shorts) == k and not longs & shorts
                assert longs == set(record["final_longs"]) and shorts == set(record["final_shorts"])
                assert all(abs(w) == 1/k for w in step.target_weights.values() if w)
                assert sum(step.target_weights.values()) == pytest.approx(0, abs=1e-12)
                assert sum(map(abs, step.target_weights.values())) == pytest.approx(2, abs=1e-12)
                if omitted:
                    assert step.target_weights[omitted] == 0
            assert step.execute
        f5.rank7_diagnostics(records, k, omitted)


@pytest.mark.parametrize("n,k", [(n, k) for n in (13, 14) for k in (3, 4, 5)])
@pytest.mark.parametrize("side", ["long", "short"])
def test_inclusive_cutoff_and_one_beyond(n, k, side):
    active = U14.currencies[:n]
    lp, sp = set(active[:k]), set(active[-k:])
    moved = active[0] if side == "long" else active[-1]
    cutoff = k+2 if side == "long" else n-k-1
    for rank, retain in ((cutoff, True), (cutoff+1 if side == "long" else cutoff-1, False)):
        order = [c for c in active if c != moved]
        order.insert(rank-1, moved)
        ls, ss, rl, rs = f5.select_memberships(order, k, lp, sp)
        assert (moved in (rl if side == "long" else rs)) == retain


def _reverse_fill(order, k, rl, rs):
    ls, ss = set(rl), set(rs)
    for c in reversed(order):
        if len(ss) < k and c not in ls | ss:
            ss.add(c)
    for c in order:
        if len(ls) < k and c not in ls | ss:
            ls.add(c)
    return ls, ss


@pytest.mark.parametrize("n,k", [(n, k) for n in (13, 14) for k in (3, 4, 5)])
def test_fill_order_independence_and_opposite_free_ends(n, k):
    rng = random.Random(932)
    order = U14.currencies[:n]
    for i in range(1500):
        prior = rng.sample(order, 2*k)
        lp, sp = set(prior[:k]), set(prior[k:])
        ls, ss, rl, rs = f5.select_memberships(order, k, lp, sp)
        free = [c for c in order if c not in rl | rs]
        a, b = k-len(rl), k-len(rs)
        assert len(free) >= a+b
        assert ls == rl | set(free[:a])
        assert ss == rs | set(free[len(free)-b:] if b else ())
        assert (ls, ss) == _reverse_fill(order, k, rl, rs)
        assert len(ls) == len(ss) == k and not ls & ss
    ls, ss, rl, rs = f5.select_memberships(order, k, order[:k], order[-k:])
    assert len(rl) == len(rs) == k  # zero vacancies on both sides
    assert (ls, ss) == _reverse_fill(order, k, rl, rs)


def test_exhaustive_k5_n13_rank7_all_72072_prior_books():
    order = U14.currencies[:13]
    middle = order[6]
    counts = {"long": 0, "short": 0, "unheld": 0}
    for longs in combinations(order, 5):
        remainder = [c for c in order if c not in longs]
        for shorts in combinations(remainder, 5):
            ls, ss, rl, rs = f5.select_memberships(order, 5, longs, shorts)
            side = "long" if middle in longs else "short" if middle in shorts else "unheld"
            counts[side] += 1
            assert (middle in ls) == (side == "long")
            assert (middle in ss) == (side == "short")
            if side == "unheld":
                upper = [c for c in order[:6] if c not in rl | rs]
                lower = [c for c in order[7:] if c not in rl | rs]
                assert len(upper) == 6-len(rl) >= 5-len(rl)
                assert len(lower) == 6-len(rs) >= 5-len(rs)
            assert (ls, ss) == _reverse_fill(order, 5, rl, rs)
            assert len(ls) == len(ss) == 5 and not ls & ss
    assert sum(counts.values()) == 72072 and all(counts.values())


def test_ties_prefix_causality_opposite_entry_and_reset():
    rows = signals(scores={c: 0.0 for c in reversed(U14.currencies)})
    steps, records = f5.breadth_accounting_steps(rows, 5, omitted="ZAR")
    active = U14.currencies[:-1]
    assert records[0]["final_longs"] == list(active[:5])
    assert records[0]["final_shorts"] == list(active[-5:])
    changed = list(rows)
    for i in range(80, len(changed)):
        if changed[i].scores is not None:
            changed[i] = replace(changed[i], scores={c: float(j) for j, c in enumerate(U14.currencies)},
                                 opens={"AUDUSD.pro": OpenQuote(2, 2)})
    later, later_records = f5.breadth_accounting_steps(changed, 5, omitted="ZAR")
    assert steps[:80] == later[:80] and records[:80] == later_records[:80]
    ls, ss, *_ = f5.select_memberships(tuple(reversed(active)), 5, active[:5], active[-5:])
    assert active[0] in ss and active[-1] in ls
    gap = next(i for i, s in enumerate(steps) if s.kind == "gap_exit")
    assert records[gap+1]["segment_index"] == 0 and records[gap+1]["state_reset"]
    assert records[gap+1]["final_longs"] == list(active[:5])


def test_invalid_membership_scores_and_transitions():
    with pytest.raises(IntegrityError):
        f5.equal_targets(["AUD"]*4, ["JPY"]*4, 4, active=U14.currencies)
    with pytest.raises(IntegrityError):
        f5.select_memberships(U14.currencies, 4, U14.currencies[:4], U14.currencies[:4])
    with pytest.raises(IntegrityError):
        f5.equal_targets(U14.currencies[:4], U14.currencies[-4:], 4, active=U14.currencies[:-1])
    for scores in ({c: 1 for c in U14.currencies[:-1]}, {c: float("nan") for c in U14.currencies}):
        with pytest.raises(IntegrityError):
            f5.breadth_accounting_steps(signals(scores=scores), 4)
    with pytest.raises(ValueError):
        f5.breadth_accounting_steps(signals(), 4, omitted="TRY")
    rows = list(signals())
    rows[0] = replace(rows[0], kind="hold_mark")
    with pytest.raises(IntegrityError):
        f5.breadth_accounting_steps(rows, 4)


def test_k4_exact_frozen_steps_records_and_static_books():
    rows = signals(gaps=(5, 66))
    for omitted in (None, *U14.currencies):
        actual = f5.breadth_accounting_steps(rows, 4, omitted=omitted)
        expected = f4.cadence_accounting_steps(rows, 1, omitted=omitted)
        assert actual == expected
        books = f5.benchmark_books(4, omitted)
        assert books == f4.family1_benchmark_books(f5.active_currencies(omitted), 4)
        for book in books[:3]:
            assert f5.static_breadth_steps(rows, book, 4, omitted=omitted) == f4.static_cadence_steps(rows, book, 1)


@pytest.mark.parametrize("k", [3, 4, 5])
def test_benchmark_rng_membership_and_static_semantics(k):
    rows = signals()
    for omitted in (None, "GBP"):
        active = f5.active_currencies(omitted)
        books = f5.benchmark_books(k, omitted)
        assert len(books) == 1000 and books == f5.benchmark_books(k, omitted)
        rng = np.random.Generator(np.random.PCG64(20260809))
        for book in books:
            draw = rng.choice(np.array(active, dtype=object), size=2*k, replace=False).tolist()
            assert book == {"longs": tuple(sorted(draw[:k])), "shorts": tuple(sorted(draw[k:]))}
        steps = f5.static_breadth_steps(rows, books[0], k, omitted=omitted)
        target = steps[0].target_weights
        assert all(s.execute for s in steps)
        assert all(s.target_weights == target for s in steps if s.kind not in ("gap_exit", "terminal"))
        assert all(not any(s.target_weights.values()) for s in steps if s.kind in ("gap_exit", "terminal"))


@pytest.mark.parametrize("k", [3, 5])
def test_synthetic_dual_accounting_stresses_attribution_and_causal_fills(k, tmp_path):
    inputs = synthetic_inputs()
    steps, _ = f5.breadth_accounting_steps(inputs.signal_steps, k)
    actual = _scenario_paths(f4._accounting_view(steps), inputs.financing_events, inputs.routes)
    expected = f4._scenarios(steps, inputs)
    vals = ([study.currency_usd_values(s.opens) for s in inputs.signal_steps],
            [study.currency_usd_values(e.opens) for e in inputs.financing_events])
    for scenario in study.SCENARIOS:
        for d in (360, 365):
            a = study._payload(actual[scenario][d], inputs, scenario, *vals)
            b = study._payload(expected[scenario][d], inputs, scenario, *vals)
            assert _comparison_stats(b, a)["mismatch_count"] == 0
            assert len(a["blocks"]) == 3 and [b["count"] for b in a["blocks"]] == [52, 52, 53]
            assert not actual[scenario][d].trades[-1].target_units
            for event, legs in zip(inputs.financing_events, a["financing_cashflows_by_event_leg"]):
                assert set(legs) <= set(actual[scenario][d].trades[event.after_step].target_units)
            assert a["path"]["total_spread_cost"] > 0 and len(a["path"]["period_returns"]) == 157
    assert actual["base"][360].total_financing != actual["base"][365].total_financing
    # Fixed membership still resolves units against changed equity/marks every week.
    book = f5.benchmark_books(k)[0]
    static = f5.static_breadth_steps(inputs.signal_steps, book, k)
    path = _scenario_paths(f4._accounting_view(static), inputs.financing_events, inputs.routes)["base"][360]
    assert path.trades[0].target_units != path.trades[1].target_units


def test_archive_exclusive_integrity_and_exact_comparison(tmp_path):
    path = tmp_path/"paths.jsonl.gz"
    sink = study.PathArchive(path)
    sink.append({"role": "test"}, {"values": [1.0, 2.0]})
    info = sink.close()
    assert info["sha256"] == _sha256(path) and info["records"] == 1
    with gzip.open(path, "rt") as handle:
        assert json.loads(handle.readline())["evidence"]["values"] == [1.0, 2.0]
    with pytest.raises(FileExistsError):
        study.PathArchive(path)
    accumulator = study.ParityAccumulator()
    with pytest.raises(IntegrityError):
        study._assert_equal({"x": 1.0}, {"x": 1.0+1e-10}, accumulator, "bad")
    with pytest.raises(IntegrityError):
        study._assert_equal({"rank": 1}, {"rank": 1.0}, accumulator, "bad_discrete", discrete=True)
    marker = tmp_path/"start.json"
    f5.exclusive_json(marker, {"consumption_count": 1})
    with pytest.raises(FileExistsError):
        f5.exclusive_json(marker, {"consumption_count": 1})


def test_network_guard_and_no_authorization_entry_boundary(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        raise AssertionError("historical economics/data unexpectedly entered")
    with f5.offline(), pytest.raises(PermissionError):
        socket.create_connection(("example.invalid", 443))
    monkeypatch.setattr(study, "validate_readiness", forbidden)
    monkeypatch.setattr(study, "breadth_study", forbidden)
    with pytest.raises(PermissionError, match="authorization"):
        study.execute_candidates(tmp_path)
    assert not (tmp_path/f5.EXECUTION_REL).exists()


def test_readiness_non_economic_all_cases_and_frozen_hashes(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("historical accounting or economics in readiness")
    monkeypatch.setattr(study, "breadth_study", forbidden)
    monkeypatch.setattr(study, "_scenario_paths", forbidden)
    monkeypatch.setattr(f4, "_scenarios", forbidden)
    result = f5.build_readiness(ROOT)
    assert result["performance_computed"] is False and result["noncontrol_economics_authorized"] is False
    assert result["preregistration_sha256"] == f5.PREREG_SHA256
    assert result["signal_count"] == 168 and result["evaluable_count"] == 157
    assert result["benchmark_seed"] == 20260809 and result["bootstrap_seed"] == 20260808
    for cid, k in f5.CANDIDATES.items():
        assert len(result["configurations"][cid]["cases"]) == 15
        assert all(case["k"] == k for case in result["configurations"][cid]["cases"].values())


def test_stale_readiness_and_control_fail_closed(monkeypatch, tmp_path):
    readiness = {"source_sha256": {"code": "new"}, "ic_sha256": "ic"}
    path = tmp_path/f5.READINESS_REL
    f5.exclusive_json(path, {"source_sha256": {"code": "old"}})
    monkeypatch.setattr(f5, "build_readiness", lambda root: readiness)
    with pytest.raises(IntegrityError):
        f5.validate_readiness(tmp_path)
    with pytest.raises(IntegrityError):
        study.validate_control(tmp_path, readiness)
    f5.exclusive_json(tmp_path/f5.PARITY_REL, {"status": "K4_CONTROL_PARITY_PASSED", "parity": {"mismatch_count": 1}})
    f5.exclusive_json(tmp_path/f5.CONTROL_REL, {})
    with pytest.raises(IntegrityError):
        study.validate_control(tmp_path, readiness)


def test_runner_default_is_preflight_only(monkeypatch, capsys):
    import run_family5_breadth as runner
    calls = []
    monkeypatch.setattr(runner, "build_readiness", lambda root: calls.append("readiness") or
                        {"status": "FAMILY5_READINESS_PASSED", "configurations": f5.CANDIDATES})
    monkeypatch.setattr(runner, "run_k4_parity", lambda root: pytest.fail("unexpected K4"))
    monkeypatch.setattr(runner, "execute_candidates", lambda root: pytest.fail("unexpected candidates"))
    assert runner.main([]) == 0 and calls == ["readiness"]
    assert json.loads(capsys.readouterr().out)["performance_computed"] is False


def test_benchmark_duplicate_multiplicity_and_cache_isolation(monkeypatch):
    inputs = synthetic_inputs()
    calls = []
    class Sink:
        def append(self, *args):
            pass
    book4 = {"longs": U14.currencies[:4], "shorts": U14.currencies[-4:]}
    book3 = {"longs": U14.currencies[:3], "shorts": U14.currencies[-3:]}
    monkeypatch.setattr(study, "benchmark_books", lambda k, omitted: [book4, book4] if k == 4 else [book3, book3])
    monkeypatch.setattr(study, "_scenario_paths", lambda *args: calls.append("path") or {})
    monkeypatch.setattr(study, "_capture", lambda *args: {})
    item = {str(d): {"rap": 1.0, "max_drawdown": -0.1, "total_return": 0.1,
        "adverse_total_return": -0.01, "spread_x3_total_return": 0.05,
        "blocks": {b["block_id"]: {"rap": 1.0, "max_drawdown": -0.1, "total_return": 0.01}
                   for b in f5.BLOCKS}} for d in (360, 365)}
    monkeypatch.setattr(study, "_book_summary", lambda *args: item)
    _, result = study._benchmark(inputs, 4, None, Sink(), None, None)
    assert calls == ["path"] and result["path_count"] == 2
    assert result["distributions"]["360"]["rap"] == [1.0, 1.0]
    study._benchmark(inputs, 4, "GBP", Sink(), None, None)
    study._benchmark(inputs, 3, None, Sink(), None, None)
    assert len(calls) == 3


def test_k4_rerun_marker_blocks_before_historical_loading(monkeypatch, tmp_path):
    monkeypatch.setattr(study, "validate_readiness", lambda root: {})
    monkeypatch.setattr(study, "load_frozen_context", lambda root: pytest.fail("historical reload"))
    f5.exclusive_json(tmp_path/f5.PARITY_START_REL, {"status": "K4_PARITY_STARTED"})
    with pytest.raises(PermissionError, match="already started"):
        study.run_k4_parity(tmp_path)


def test_valid_marker_stale_hashes_and_archive_tamper_block(monkeypatch, tmp_path):
    readiness = {"source_sha256": {"code": "new"}, "ic_sha256": _canonical_sha({})}
    f5.exclusive_json(tmp_path/f5.READINESS_REL, readiness)
    archive = tmp_path/f5.CONTROL_PATHS_REL
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(b"archive")
    f5.exclusive_json(tmp_path/f5.CONTROL_REL, {"control_study": {"ic": {}}})
    parity = {"status": "K4_CONTROL_PARITY_PASSED", "parity": {"mismatch_count": 0},
        "preregistration_sha256": f5.PREREG_SHA256, "source_sha256": readiness["source_sha256"],
        "readiness_sha256": _sha256(tmp_path/f5.READINESS_REL),
        "control_sha256": _sha256(tmp_path/f5.CONTROL_REL),
        "archive": {"sha256": _sha256(archive)}}
    f5.exclusive_json(tmp_path/f5.PARITY_REL, parity)
    assert study.validate_control(tmp_path, readiness)["control_study"]["ic"] == {}
    with pytest.raises(IntegrityError, match="stale"):
        study.validate_control(tmp_path, {**readiness, "source_sha256": {"code": "changed"}})
    archive.write_bytes(b"tampered")
    with pytest.raises(IntegrityError, match="archive"):
        study.validate_control(tmp_path, readiness)
