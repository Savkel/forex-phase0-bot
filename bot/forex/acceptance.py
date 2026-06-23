"""Phase 0 holdout-only PASS/FAIL gate (spec §8). Structure adapted from the
crypto acceptance module; the perp-specific rules are removed. The verdict is
HOLDOUT-ONLY — there is no train/in-sample rescue, no parameter tuning, no score
weighting, no near-pass or manual override. All four conditions must pass (AND)
or the trend family is killed for Phase 0.

Drawdown sign convention: drawdowns are reported as a NEGATIVE fraction (or 0).
"bot DD no worse than the gross-matched passive" therefore means the bot's
drawdown is SHALLOWER-OR-EQUAL, i.e. numerically `bot_max_drawdown >=
gross_matched_max_drawdown` (e.g. -0.10 >= -0.20 passes; -0.30 >= -0.20 fails)."""
from __future__ import annotations
from typing import Any, Dict

# The exact metrics the gate consumes. A missing metric is a deterministic error,
# never silently defaulted to a passing value.
REQUIRED_METRICS = ("holdout_alpha", "null_percentile", "bot_max_drawdown",
                    "gross_matched_max_drawdown", "stress_combined_alpha")

def _check(name: str, value: float, op: str, threshold: float) -> Dict[str, Any]:
    v = float(value); t = float(threshold)
    ok = {">": v > t, ">=": v >= t}[op]      # only strict-gt and ge are used; compared at full precision
    return {"rule": name, "passed": bool(ok), "value": round(v, 6), "op": op,
            "threshold": round(t, 6), "status": "PASS" if ok else "FAIL"}

def phase0_acceptance(m: Dict[str, Any], null_percentile_gate: float = 90.0) -> Dict[str, Any]:
    """Holdout-only four-gate verdict. Returns PASS only if ALL four checks pass;
    FAIL if any one fails. Raises ValueError (deterministically) if any required
    metric is missing — it never defaults a missing metric to a passing value."""
    missing = sorted(k for k in REQUIRED_METRICS if k not in m)
    if missing:
        raise ValueError(f"acceptance: missing required metric(s) {missing}; "
                         f"a missing metric is never defaulted to a passing value")

    checks = [
        _check("holdout_alpha_positive", m["holdout_alpha"], ">", 0.0),
        _check("null_percentile", m["null_percentile"], ">=", null_percentile_gate),
        # both drawdowns are <= 0; bot must be shallower-or-equal (>=) than the gross-matched passive
        _check("drawdown_le_gross_matched_passive",
               m["bot_max_drawdown"], ">=", m["gross_matched_max_drawdown"]),
        _check("cost_stress_combined_alpha_positive", m["stress_combined_alpha"], ">", 0.0),
    ]
    failed = [c["rule"] for c in checks if not c["passed"]]
    return {
        "overall": "FAIL" if failed else "PASS",
        "verdict_note": ("Trend family on EUR/USD 4H KILLED for Phase 0 — no rescue."
                         if failed else
                         "Trend edge cleared all holdout gates — proceed to Phase 1."),
        "failed": failed,
        "checks": checks,
        "drawdown": {
            "bot_max_drawdown": round(float(m["bot_max_drawdown"]), 6),
            "gross_matched_max_drawdown": round(float(m["gross_matched_max_drawdown"]), 6),
            "convention": "drawdowns are <= 0; PASS requires bot_max_drawdown >= "
                          "gross_matched_max_drawdown (bot DD shallower-or-equal)",
        },
    }
