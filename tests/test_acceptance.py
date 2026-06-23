import pytest
from bot.forex.acceptance import phase0_acceptance


def _pass_metrics():
    # a clean all-pass holdout metrics dict
    return {"holdout_alpha": 0.05, "null_percentile": 93.0,
            "bot_max_drawdown": -0.10, "gross_matched_max_drawdown": -0.18,
            "stress_combined_alpha": 0.02}


# --- all four pass -> PASS (AND logic) ---

def test_all_four_checks_pass_returns_pass():
    r = phase0_acceptance(_pass_metrics())
    assert r["overall"] == "PASS"
    assert r["failed"] == []
    assert len(r["checks"]) == 4
    assert all(c["passed"] is True for c in r["checks"])


# --- each individual failed check -> FAIL ---

def test_negative_holdout_alpha_fails():
    m = _pass_metrics(); m["holdout_alpha"] = -0.01
    r = phase0_acceptance(m)
    assert r["overall"] == "FAIL" and "holdout_alpha_positive" in r["failed"]


def test_zero_holdout_alpha_fails_strict_gt():
    m = _pass_metrics(); m["holdout_alpha"] = 0.0
    assert phase0_acceptance(m)["overall"] == "FAIL"        # check is strict > 0


def test_weak_null_percentile_fails():
    m = _pass_metrics(); m["null_percentile"] = 80.0
    r = phase0_acceptance(m)
    assert r["overall"] == "FAIL" and "null_percentile" in r["failed"]


def test_cost_stress_combined_failure_fails():
    m = _pass_metrics(); m["stress_combined_alpha"] = -0.001
    r = phase0_acceptance(m)
    assert r["overall"] == "FAIL" and "cost_stress_combined_alpha_positive" in r["failed"]


def test_zero_stress_alpha_fails_strict_gt():
    m = _pass_metrics(); m["stress_combined_alpha"] = 0.0
    assert phase0_acceptance(m)["overall"] == "FAIL"        # strict > 0


# --- drawdown sign convention (drawdowns are <= 0; bot must be shallower-or-equal) ---

def test_drawdown_shallower_passes_deeper_fails():
    ok = _pass_metrics(); ok["bot_max_drawdown"] = -0.10; ok["gross_matched_max_drawdown"] = -0.20
    assert phase0_acceptance(ok)["overall"] == "PASS"       # -0.10 >= -0.20  (shallower)
    bad = _pass_metrics(); bad["bot_max_drawdown"] = -0.30; bad["gross_matched_max_drawdown"] = -0.20
    r = phase0_acceptance(bad)
    assert r["overall"] == "FAIL"                           # -0.30 >= -0.20 is False (deeper)
    assert "drawdown_le_gross_matched_passive" in r["failed"]


def test_drawdown_equality_passes():
    m = _pass_metrics(); m["bot_max_drawdown"] = -0.20; m["gross_matched_max_drawdown"] = -0.20
    assert phase0_acceptance(m)["overall"] == "PASS"        # equal -> shallower-or-equal -> pass


# --- null percentile equality to the gate passes (>=) ---

def test_null_percentile_equal_to_gate_passes():
    m = _pass_metrics(); m["null_percentile"] = 90.0
    assert phase0_acceptance(m, null_percentile_gate=90.0)["overall"] == "PASS"


# --- missing required metric: deterministic error, never silently passed ---

def test_missing_required_metric_raises_deterministic_error():
    m = _pass_metrics(); del m["holdout_alpha"]
    with pytest.raises(ValueError, match="holdout_alpha"):
        phase0_acceptance(m)


def test_missing_metric_is_not_silently_defaulted_to_pass():
    for key in ("holdout_alpha", "null_percentile", "bot_max_drawdown",
                "gross_matched_max_drawdown", "stress_combined_alpha"):
        m = _pass_metrics(); del m[key]
        with pytest.raises(ValueError, match=key):           # never returns PASS by defaulting
            phase0_acceptance(m)


# --- no rescue/override/manual-pass can flip a genuine FAIL into PASS ---

def test_rescue_or_override_fields_cannot_flip_fail_to_pass():
    m = _pass_metrics(); m["holdout_alpha"] = -0.01          # a real failure
    m.update({"override": True, "rescue": "please", "manual_pass": True, "force_pass": 1, "weight": 99})
    r = phase0_acceptance(m)
    assert r["overall"] == "FAIL"                            # extra fields are inert


# --- structure: each check carries a boolean + raw value; drawdowns echoed with convention ---

def test_each_check_includes_boolean_and_raw_value():
    r = phase0_acceptance(_pass_metrics())
    for c in r["checks"]:
        assert isinstance(c["passed"], bool)
        for field in ("rule", "value", "op", "threshold", "status"):
            assert field in c


def test_result_echoes_drawdowns_with_sign_convention():
    r = phase0_acceptance(_pass_metrics())
    dd = r["drawdown"]
    assert dd["bot_max_drawdown"] == -0.10
    assert dd["gross_matched_max_drawdown"] == -0.18
    assert "convention" in dd and "<= 0" in dd["convention"]
