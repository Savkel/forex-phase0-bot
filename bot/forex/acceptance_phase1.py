"""Phase 1 holdout-only 5-gate PASS/FAIL. Structure adapted from the Phase 0 gate;
reuses acceptance._check for the value/op/threshold/passed record. The verdict is
HOLDOUT-ONLY (no in-sample rescue, no threshold change, no averaging of failed
gates, no discretionary override). All five gates are AND-ed and the verdict is
deterministic and verdict-first: PASS only if all five pass, otherwise FAIL. A
missing required metric raises; a non-finite/non-numeric metric raises (so a
malformed +inf can never slip through a > / >= gate).

Drawdowns are <= 0; the bot must be shallower-or-equal than the GROSS-MATCHED
passive (Gate 3): numerically bot_max_drawdown >= gross_matched_max_drawdown
(e.g. -0.10 >= -0.18 passes; -0.30 >= -0.18 fails). Gross-matched is the Gate-3
benchmark; net-matched is diagnostic only and is never consulted here.

Zero-exposure convention (unified with Task 8): an all-flat bot has zero net and
zero return, so its exposure-adjusted alpha is exactly 0 -> Gate 1 (alpha > 0)
rejects it. It cannot manufacture alpha or pass. The Gate-3 gross-matched drawdown
is supplied upstream by portfolio.gross_matched_basket, which at measured G=0 uses
f=0.0 (a zero-notional benchmark) -- the same zero-notional convention as Task 8.
The legacy evaluate.matched_gross `... or 1.0` fallback is shared Phase 0 code and
is intentionally NOT on this path (left deferred; not edited here)."""
from __future__ import annotations
import math
from typing import Any, Dict, List
from bot.forex.acceptance import _check

REQUIRED_METRICS = ("portfolio_holdout_alpha", "null_percentile", "bot_max_drawdown",
                    "gross_matched_max_drawdown", "stress_combined_alpha",
                    "per_pair_holdout_alphas")

def _finite(name: str, v: Any) -> float:
    """Coerce a scalar metric to a finite float or raise. A non-numeric value or a
    NaN/inf is a deterministic error -- it is never defaulted to a passing value and
    never allowed to slip through a comparison gate."""
    try:
        fv = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"acceptance_phase1: metric {name!r} is not numeric: {v!r}")
    if not math.isfinite(fv):
        raise ValueError(f"acceptance_phase1: metric {name!r} is not finite: {v!r}")
    return fv

def _gate(name: str, value: float, op: str, threshold: float) -> Dict[str, Any]:
    """A single gate: the reused acceptance._check (value/op/threshold/passed/status)
    plus a concise human-readable failure reason ("" when the gate passes)."""
    c = _check(name, value, op, threshold)
    c["reason"] = "" if c["passed"] else f"{name}: {c['value']} not {op} {c['threshold']}"
    return c

def phase1_acceptance(m: Dict[str, Any], *, null_percentile_gate: float = 90.0,
                      min_positive_pairs: int = 5, per_pair_floor: float = -0.10) -> Dict[str, Any]:
    """Holdout-only five-gate verdict. Returns PASS only if ALL five gates pass; FAIL
    if any one fails. Raises ValueError (deterministically) if a required metric is
    missing or non-finite/non-numeric -- never defaulting it to a passing value."""
    missing = sorted(k for k in REQUIRED_METRICS if k not in m)
    if missing:
        raise ValueError(f"acceptance_phase1: missing required metric(s) {missing}; "
                         f"a missing metric is never defaulted to a passing value")
    # finiteness / numeric guard on every consumed metric (malformed inputs fail clearly)
    alpha = _finite("portfolio_holdout_alpha", m["portfolio_holdout_alpha"])
    null_pct = _finite("null_percentile", m["null_percentile"])
    bot_dd = _finite("bot_max_drawdown", m["bot_max_drawdown"])
    gm_dd = _finite("gross_matched_max_drawdown", m["gross_matched_max_drawdown"])
    stress = _finite("stress_combined_alpha", m["stress_combined_alpha"])
    ppa = m["per_pair_holdout_alphas"]
    items = list(ppa.items()) if isinstance(ppa, dict) else list(enumerate(ppa))
    alphas: List[float] = [_finite(f"per_pair_holdout_alphas[{k}]", v) for k, v in items]
    n_positive = sum(1 for a in alphas if a > 0.0)
    worst = min(alphas, default=0.0)

    checks = [
        _gate("portfolio_holdout_alpha_positive", alpha, ">", 0.0),
        _gate("null_percentile", null_pct, ">=", null_percentile_gate),
        # both drawdowns are <= 0; bot must be shallower-or-equal (>=) than the gross-matched passive
        _gate("drawdown_le_gross_matched_passive", bot_dd, ">=", gm_dd),
        _gate("cost_stress_combined_alpha_positive", stress, ">", 0.0),
        _gate("cross_pair_positive_count", n_positive, ">=", min_positive_pairs),
        _gate("cross_pair_worst_floor", worst, ">=", per_pair_floor),
    ]
    failed = [c["rule"] for c in checks if not c["passed"]]
    return {
        "overall": "FAIL" if failed else "PASS",
        "verdict_note": ("H4 mean-reversion on the major-pair universe KILLED for Phase 1 — no rescue."
                         if failed else
                         "Mean-reversion portfolio cleared all 5 holdout gates."),
        "failed": failed,
        "checks": checks,
        "cross_pair": {"n_positive": n_positive, "min_positive_pairs": int(min_positive_pairs),
                       "worst_alpha": round(worst, 6), "per_pair_floor": float(per_pair_floor),
                       "n_pairs": len(alphas)},
        "drawdown": {"bot_max_drawdown": round(bot_dd, 6),
                     "gross_matched_max_drawdown": round(gm_dd, 6),
                     "convention": "drawdowns <= 0; PASS requires bot >= gross_matched (shallower-or-equal)"},
    }
