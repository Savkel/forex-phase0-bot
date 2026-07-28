"""Task 11: Phase 1 holdout-only 5-gate acceptance.

Five AND-ed gates on HOLDOUT metrics only (no train metrics): (1) portfolio
holdout exposure-adjusted alpha > 0; (2) primary independent-shift null percentile
>= 90; (3) bot max drawdown >= gross-matched passive (drawdowns <= 0, bot
shallower-or-equal); (4) combined cost-stress alpha > 0; (5) cross-pair robustness
(>= 5/7 pairs positive AND worst >= -0.10). Verdict-first, deterministic; PASS only
if all five pass. Gross-matched is the Gate-3 benchmark; net-matched is diagnostic
only. A zero-exposure/all-flat bot (alpha == 0) cannot pass. Reuses acceptance._check.
"""
import inspect

import pytest

from bot.forex.acceptance_phase1 import phase1_acceptance, REQUIRED_METRICS
import bot.forex.acceptance_phase1 as acc1

PAIRS = ("EUR_USD", "GBP_USD", "USD_JPY", "USD_CHF", "AUD_USD", "USD_CAD", "NZD_USD")


def _pass_metrics():
    return {
        "portfolio_holdout_alpha": 0.05,
        "null_percentile": 93.0,
        "bot_max_drawdown": -0.10,
        "gross_matched_max_drawdown": -0.18,
        "stress_combined_alpha": 0.02,
        "per_pair_holdout_alphas": {  # 6 of 7 positive, worst -0.03 (>= -0.10)
            "EUR_USD": 0.04, "GBP_USD": 0.03, "USD_JPY": 0.01, "USD_CHF": 0.02,
            "AUD_USD": 0.05, "USD_CAD": -0.03, "NZD_USD": 0.02},
    }


# ---- Plan tests (locked Task 11 spec) -------------------------------------------------

def test_all_gates_pass():
    assert phase1_acceptance(_pass_metrics())["overall"] == "PASS"


def test_alpha_gate_fails():
    m = _pass_metrics(); m["portfolio_holdout_alpha"] = -0.01
    assert phase1_acceptance(m)["overall"] == "FAIL"


def test_null_gate_fails():
    m = _pass_metrics(); m["null_percentile"] = 80.0
    assert phase1_acceptance(m)["overall"] == "FAIL"


def test_drawdown_gate_fails_when_bot_deeper():
    m = _pass_metrics(); m["bot_max_drawdown"] = -0.30      # deeper than -0.18
    assert phase1_acceptance(m)["overall"] == "FAIL"


def test_stress_gate_fails():
    m = _pass_metrics(); m["stress_combined_alpha"] = -0.001
    assert phase1_acceptance(m)["overall"] == "FAIL"


def test_cross_pair_count_boundary():
    m = _pass_metrics()
    m["per_pair_holdout_alphas"] = {"A": 0.01, "B": 0.01, "C": 0.01, "D": 0.01,
                                    "E": 0.01, "F": -0.02, "G": -0.02}   # exactly 5 positive
    assert phase1_acceptance(m)["overall"] == "PASS"
    m["per_pair_holdout_alphas"]["E"] = -0.02                            # now 4 positive
    assert phase1_acceptance(m)["overall"] == "FAIL"


def test_cross_pair_worst_floor_boundary():
    m = _pass_metrics()
    m["per_pair_holdout_alphas"] = {"A": 0.05, "B": 0.05, "C": 0.05, "D": 0.05,
                                    "E": 0.05, "F": 0.05, "G": -0.10}    # worst == floor -> pass
    assert phase1_acceptance(m)["overall"] == "PASS"
    m["per_pair_holdout_alphas"]["G"] = -0.11                           # below floor -> fail
    assert phase1_acceptance(m)["overall"] == "FAIL"


def test_missing_metric_raises():
    m = _pass_metrics(); del m["stress_combined_alpha"]
    with pytest.raises(ValueError, match="missing"):
        phase1_acceptance(m)


def test_required_metrics_listed():
    assert "per_pair_holdout_alphas" in REQUIRED_METRICS


# ---- Additive hardening (each maps to a "tests must cover" bullet) ---------------------

def test_null_percentile_exact_boundary():
    m = _pass_metrics(); m["null_percentile"] = 90.0                    # exactly at the gate -> pass
    assert phase1_acceptance(m)["overall"] == "PASS"
    m["null_percentile"] = 89.999                                      # a hair below -> fail
    assert phase1_acceptance(m)["overall"] == "FAIL"


def test_alpha_and_stress_exact_zero_fail():
    m = _pass_metrics(); m["portfolio_holdout_alpha"] = 0.0            # exactly 0 -> not > 0 -> fail
    assert phase1_acceptance(m)["overall"] == "FAIL"
    m = _pass_metrics(); m["stress_combined_alpha"] = 0.0             # exactly 0 -> not > 0 -> fail
    assert phase1_acceptance(m)["overall"] == "FAIL"


def test_drawdown_direction_equal_and_shallower_pass():
    # drawdowns are negative; bot must be shallower-or-equal (>=) than gross-matched
    m = _pass_metrics()
    m["bot_max_drawdown"] = -0.18; m["gross_matched_max_drawdown"] = -0.18   # equal -> pass
    assert phase1_acceptance(m)["overall"] == "PASS"
    m["bot_max_drawdown"] = -0.05                                            # shallower -> pass
    assert phase1_acceptance(m)["overall"] == "PASS"
    m["bot_max_drawdown"] = -0.19                                            # a hair deeper -> fail
    assert phase1_acceptance(m)["overall"] == "FAIL"


def test_each_gate_fails_independently_all_anded():
    assert phase1_acceptance(_pass_metrics())["overall"] == "PASS"     # baseline all-pass
    breakers = [
        ("portfolio_holdout_alpha", -0.01),
        ("null_percentile", 89.0),
        ("bot_max_drawdown", -0.30),
        ("stress_combined_alpha", -0.01),
    ]
    for key, bad in breakers:
        m = _pass_metrics(); m[key] = bad
        res = phase1_acceptance(m)
        assert res["overall"] == "FAIL", f"breaking {key} must FAIL the whole verdict"
        assert any(not c["passed"] for c in res["checks"])
    # breaking gate 5 (robustness) alone also fails the AND
    m = _pass_metrics()
    m["per_pair_holdout_alphas"] = {p: -0.02 for p in PAIRS}           # 0 positive, worst -0.02
    assert phase1_acceptance(m)["overall"] == "FAIL"


def test_zero_exposure_flat_bot_cannot_pass():
    # an all-flat bot: zero alpha, zero drawdown, zero stress, zero per-pair alphas.
    # gross-matched is the Task-8 zero-notional convention (G=0 -> dd 0). It must FAIL
    # (gate 1 alpha 0 not > 0; gate 4 stress 0 not > 0; gate 5 has 0 positive pairs).
    flat = {
        "portfolio_holdout_alpha": 0.0,
        "null_percentile": 95.0,
        "bot_max_drawdown": 0.0,
        "gross_matched_max_drawdown": 0.0,
        "stress_combined_alpha": 0.0,
        "per_pair_holdout_alphas": {p: 0.0 for p in PAIRS},
    }
    assert phase1_acceptance(flat)["overall"] == "FAIL"
    # even if the other gates are handed favorable values, alpha == 0 still cannot pass
    manufactured = dict(flat)
    manufactured["null_percentile"] = 99.0
    manufactured["gross_matched_max_drawdown"] = -0.25    # bot 0 >= -0.25 (gate 3 would pass)
    res = phase1_acceptance(manufactured)
    assert res["overall"] == "FAIL"
    assert "portfolio_holdout_alpha_positive" in res["failed"]   # zero exposure can't manufacture alpha


def test_non_finite_metric_fails_clearly():
    for bad in (float("nan"), float("inf"), float("-inf")):
        m = _pass_metrics(); m["portfolio_holdout_alpha"] = bad
        with pytest.raises(ValueError, match="finite"):
            phase1_acceptance(m)
    m = _pass_metrics(); m["null_percentile"] = float("inf")           # inf must not slip through a >= gate
    with pytest.raises(ValueError, match="finite"):
        phase1_acceptance(m)
    m = _pass_metrics(); m["per_pair_holdout_alphas"]["EUR_USD"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        phase1_acceptance(m)


def test_malformed_metric_raises():
    m = _pass_metrics(); m["portfolio_holdout_alpha"] = "oops"
    with pytest.raises(ValueError):
        phase1_acceptance(m)
    m = _pass_metrics(); m["per_pair_holdout_alphas"]["EUR_USD"] = "oops"
    with pytest.raises(ValueError):
        phase1_acceptance(m)


def test_gate2_uses_primary_null_only():
    # acceptance consults ONLY `null_percentile` (the primary independent-shift null).
    # Diagnostic null keys must be ignored: a failing primary still FAILS even with
    # passing diagnostics, and a passing primary still PASSES with failing diagnostics.
    m = _pass_metrics()
    m["null_percentile"] = 80.0                                        # primary fails
    m["null_percentile_common_shift"] = 99.0                          # diagnostics (ignored)
    m["null_percentile_block_shuffle"] = 99.0
    assert phase1_acceptance(m)["overall"] == "FAIL"
    m["null_percentile"] = 95.0                                       # primary passes
    m["null_percentile_common_shift"] = 1.0                           # diagnostics (ignored)
    m["null_percentile_block_shuffle"] = 1.0
    assert phase1_acceptance(m)["overall"] == "PASS"


def test_holdout_only_ignores_train_metrics():
    # no train metric feeds acceptance; a wildly good train number cannot rescue a failing holdout
    m = _pass_metrics(); m["portfolio_holdout_alpha"] = -0.01
    m["portfolio_train_alpha"] = 999.0                                # train metric (must be ignored)
    assert phase1_acceptance(m)["overall"] == "FAIL"
    assert not any("train" in k for k in REQUIRED_METRICS)


def test_each_check_reports_value_threshold_bool_and_reason():
    m = _pass_metrics(); m["portfolio_holdout_alpha"] = -0.01          # make gate 1 fail
    res = phase1_acceptance(m)
    for c in res["checks"]:
        assert {"rule", "value", "threshold", "passed", "reason"} <= set(c)
        assert isinstance(c["passed"], bool)
    failed = [c for c in res["checks"] if not c["passed"]]
    assert failed and all(c["reason"] for c in failed)                # failing gates carry a concise reason
    assert all(c["reason"] == "" for c in res["checks"] if c["passed"])


def test_verdict_first_and_deterministic():
    res = phase1_acceptance(_pass_metrics())
    assert next(iter(res)) == "overall"                               # verdict-first
    assert res["overall"] == "PASS"
    assert phase1_acceptance(_pass_metrics()) == res                  # deterministic


def test_net_matched_is_not_a_gate():
    # gross-matched is the Gate-3 benchmark; net-matched must never be consulted
    assert not any("net_matched" in k for k in REQUIRED_METRICS)
    m = _pass_metrics(); m["net_matched_max_drawdown"] = 0.99          # diagnostic (ignored)
    assert phase1_acceptance(m)["overall"] == "PASS"


def test_no_selection_runner_report_or_oanda_code():
    banned = ("simulate", "run_phase1", "oanda", "candidate_decisions",
              "load_universe", "to_markdown", "fetch_candles", "split_common_window")
    src = inspect.getsource(acc1)
    for term in banned:
        assert term not in src, f"acceptance_phase1 must not contain {term!r}"
