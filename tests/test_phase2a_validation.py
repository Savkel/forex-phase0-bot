"""Phase 2A validation runner: one segment, one run, one door.

The runner exists to make the single validation pass unrepeatable-by-accident and
confirmation-proof: it refuses frames carrying a bar from any other segment, it fingerprints
its frozen inputs and refuses to run against a changed fingerprint, and it never opens the
confirmation segment whatever the outcome.

The measurement and null functions are injected so these tests exercise the ORCHESTRATION
without running a thousand permutations.
"""
import json

import numpy as np
import pandas as pd
import pytest

from bot.forex.phase2a_validation import (
    CONFIRMATION,
    DEVELOPMENT,
    VALIDATION,
    fingerprint,
    assert_validation_only,
    render_markdown,
    run_validation,
)

M15 = 900_000


def _ms(s):
    return int(pd.Timestamp(s, tz="UTC").value // 10 ** 6)


def _frames(start=None, extra=(), px=1.0):
    start = start if start is not None else VALIDATION[0] + 10 * M15
    ts = [start + i * M15 for i in range(20)] + list(extra)
    return {p: pd.DataFrame({"open_time": ts, "volume": [100] * len(ts),
                             "complete": [True] * len(ts),
                             "bid_c": [px] * len(ts), "ask_c": [px] * len(ts)})
            for p in ("AUD_USD", "EUR_USD", "GBP_USD", "USD_JPY")}


def _measurement(name, **over):
    per_pair = {"AUD_USD": 0.2, "EUR_USD": 0.2, "GBP_USD": 0.2, "USD_JPY": 0.2}
    base = {"name": name, "alpha": 0.05, "k": 1.0, "benchmark_status": "OK",
            "stressed_alpha": 0.01, "per_pair_alpha": {"EUR_USD": 0.03, "GBP_USD": 0.02},
            "positive_pairs": 4, "worst_pair_alpha": -0.05,
            "participation": dict(per_pair),
            "trades_per_pair": {k: 100 for k in per_pair},
            "active_month_ratio": {k: 0.9 for k in per_pair}, "n_trades": 100,
            "null_percentile": 95.0}
    base.update(over)
    return base


def _run(measurements, **kw):
    def measure_fn(frames, spec, **_):
        return dict(measurements[spec.name])

    def null_fn(frames, spec, **_):
        return {"real": 0.0, "runs": 1000, "seed": 20260806,
                "percentile_rank": measurements[spec.name]["null_percentile"]}

    return run_validation(_frames(), expected=np.array([], dtype="int64"),
                          measure_fn=measure_fn, null_fn=null_fn, **kw)


# --- segment isolation ------------------------------------------------------------------

def test_a_confirmation_bar_anywhere_in_the_frames_is_refused():
    frames = _frames(extra=[CONFIRMATION[0]])
    with pytest.raises(ValueError, match="confirmation"):
        assert_validation_only(frames)

def test_a_development_bar_anywhere_in_the_frames_is_refused():
    frames = _frames(extra=[DEVELOPMENT[0] + M15])
    with pytest.raises(ValueError, match="outside the validation segment"):
        assert_validation_only(frames)

def test_frames_wholly_inside_the_validation_segment_are_accepted():
    assert assert_validation_only(_frames()) is None

def test_the_runner_itself_refuses_out_of_segment_frames():
    def boom(*a, **k):                      # must never be reached
        raise AssertionError("measurement ran on out-of-segment data")
    with pytest.raises(ValueError, match="confirmation"):
        run_validation(_frames(extra=[CONFIRMATION[0]]),
                       expected=np.array([], dtype="int64"),
                       measure_fn=boom, null_fn=boom)


# --- fingerprint ------------------------------------------------------------------------

def test_the_fingerprint_is_deterministic_and_content_sensitive():
    a = fingerprint(_frames())
    assert a == fingerprint(_frames()) and len(a) == 64
    assert fingerprint(_frames(start=VALIDATION[0] + 50 * M15)) != a   # timestamps
    assert fingerprint(_frames(px=1.5)) != a                            # bar VALUES
    assert fingerprint(_frames(), np.array([1, 2, 3], dtype="int64")) != a

def test_a_fingerprint_mismatch_refuses_to_run():
    with pytest.raises(ValueError, match="fingerprint"):
        _run({n: _measurement(n) for n in ("c1_asia_london", "c2_london_orb",
                                           "c3_london_ny")},
             expected_fingerprint="0" * 64)


# --- verdicts ---------------------------------------------------------------------------

def test_no_eligible_candidate_closes_the_family_and_seals_confirmation():
    out = _run({n: _measurement(n, alpha=-0.01)
                for n in ("c1_asia_london", "c2_london_orb", "c3_london_ny")})
    assert out["verdict"] == "CLOSED_FAIL"
    assert out["selected"] is None
    assert out["confirmation"]["opened"] is False
    assert "alpha_not_positive" in out["candidates"][0]["failed"]

def test_one_eligible_candidate_is_frozen_but_confirmation_stays_shut():
    out = _run({"c1_asia_london": _measurement("c1_asia_london", alpha=-0.01),
                "c2_london_orb": _measurement("c2_london_orb", alpha=0.05),
                "c3_london_ny": _measurement("c3_london_ny", null_percentile=10.0)})
    assert out["verdict"] == "PROCEED" and out["selected"] == "c2_london_orb"
    assert out["frozen"] == ["c2_london_orb"]
    assert out["confirmation"]["opened"] is False
    assert out["confirmation"]["unlocks"] == "c2_london_orb"

def test_selection_is_deterministic_on_alpha_then_trades_then_listed_order():
    out = _run({"c1_asia_london": _measurement("c1_asia_london", alpha=0.05, n_trades=120),
                "c2_london_orb": _measurement("c2_london_orb", alpha=0.05, n_trades=100),
                "c3_london_ny": _measurement("c3_london_ny", alpha=0.05, n_trades=100)})
    assert out["selected"] == "c2_london_orb"

def test_the_runner_passes_the_locked_null_settings_and_they_are_not_overridable():
    # Asserting on what the RUNNER handed the null, not on what a stub chose to echo.
    seen = []

    def null_fn(frames, spec, **kw):
        seen.append((kw["runs"], kw["seed"]))
        return {"real": 0.0, "runs": kw["runs"], "seed": kw["seed"],
                "percentile_rank": 95.0}

    run_validation(_frames(), expected=np.array([], dtype="int64"),
                   measure_fn=lambda f, s, **k: dict(_measurement(s.name)),
                   null_fn=null_fn)
    assert seen == [(1000, 20260806)] * 3
    with pytest.raises(TypeError):
        run_validation(_frames(), expected=np.array([], dtype="int64"),
                       runs=10, measure_fn=null_fn, null_fn=null_fn)

def test_a_measurement_missing_a_pair_is_refused_rather_than_gated_vacuously():
    bad = {n: _measurement(n) for n in ("c1_asia_london", "c2_london_orb", "c3_london_ny")}
    bad["c1_asia_london"]["participation"] = {"EUR_USD": 0.2}
    with pytest.raises(ValueError, match="locked universe"):
        _run(bad)

def test_a_universe_with_a_pair_removed_is_refused():
    frames = _frames()
    frames.pop("USD_JPY")
    with pytest.raises(ValueError, match="universe mismatch"):
        run_validation(frames, expected=np.array([], dtype="int64"),
                       measure_fn=lambda *a, **k: {}, null_fn=lambda *a, **k: {})


# --- report -----------------------------------------------------------------------------

def test_the_report_leads_with_the_verdict():
    out = _run({n: _measurement(n, alpha=-0.01)
                for n in ("c1_asia_london", "c2_london_orb", "c3_london_ny")})
    assert list(out)[0] == "verdict"
    md = render_markdown(out)
    assert md.splitlines()[0].startswith("# ")
    assert "CLOSED_FAIL" in md.splitlines()[0] or "CLOSED_FAIL" in md.splitlines()[1]
    assert "confirmation" in md.lower()
    json.dumps(out)                                    # must be serialisable as-is
