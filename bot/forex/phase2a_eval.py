"""Phase 2A evaluation: session-preserving null, session-matched benchmark, gates, selection.

Nothing here opens the confirmation segment. `open_confirmation` is the only door and it
refuses unless exactly one candidate has been frozen by `select_candidate`.

The three moving parts, all locked before any result was seen:

NULL — the permuted object for a pair-day is `None` (NO_TRADE) or `(entry offset,
direction)`. Every ELIGIBLE day takes part, no-trade days included; otherwise the null
would compare an always-invested strategy against an always-invested shadow and lose the
timing question it exists to ask. Permutation runs within same-ISO-weekday days,
independently per pair, and only a globally unchanged mapping is redrawn. On the target
day the entry bar and the stop are rebuilt from THAT day's own prices under the original
candidate rules — no source stop distance travels with the object.

BENCHMARK — candidate-specific and session-matched: always long, on every eligible
pair-day, entering at the first candidate-permitted fill open and exiting at that
candidate's scheduled exit, through the same execution path and therefore the same spread,
slippage and no-overnight rule. It is scaled so its return volatility matches the
strategy's. If that needs k>10, or either volatility is zero, the comparison is UNDEFINED
and the gate FAILS — it is never capped and called matched.

GATES — activity and performance, all AND-ed. No eligible candidate kills the family.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from bot.forex.market_grid import M15_MS
from bot.forex.phase2a import (
    SPECS,
    SessionSpec,
    bar_arrays,
    bar_index,
    eligible_days,
    execute_signal,
    range_extremes,
    run_candidate,
    session_bounds,
)

NULL_SEED = 20260806
NULL_RUNS = 1000
MAX_K = 10.0

GATES = {
    "min_participation": 0.08,
    "min_trades_per_pair": 40,
    "min_active_month_ratio": 0.70,
    "min_null_percentile": 90.0,
    "min_positive_pairs": 3,
    "worst_pair_floor": -0.10,
}


class ConfirmationLocked(RuntimeError):
    """Raised on any attempt to reach the confirmation segment without a frozen selection."""


# --- returns ---------------------------------------------------------------------------

def trade_return(t: Dict[str, Any]) -> float:
    return t["direction"] * (t["exit_px"] - t["entry_px"]) / t["entry_px"]


def daily_series(trades: Sequence[Dict[str, Any]], pairs: Sequence[str],
                 days: Sequence[str]) -> np.ndarray:
    """Equal-weight portfolio return per trading day; a day with no trade contributes 0."""
    by_day: Dict[str, float] = {d: 0.0 for d in days}
    for t in trades:
        if t["trading_day"] in by_day:
            by_day[t["trading_day"]] += trade_return(t) / len(pairs)
    return np.array([by_day[d] for d in days], dtype=float)


# --- benchmark ---------------------------------------------------------------------------

def session_matched_benchmark(df: pd.DataFrame, spec: SessionSpec, *, pair: str,
                              expected: np.ndarray, pip: float = 0.0001,
                              slippage_pips: float = 0.0) -> List[Dict[str, Any]]:
    """Always long on every eligible pair-day, same schedule and same execution path."""
    slip = float(slippage_pips) * float(pip)
    A = bar_arrays(df)
    idx = bar_index(A)
    out: List[Dict[str, Any]] = []
    for day in eligible_days(df, spec, expected):
        b = session_bounds(spec, day)
        if b["entry_start_ms"] not in idx:
            continue
        t = execute_signal(A, idx, b, spec=spec, pair=pair, day=day,
                           signal_ms=b["entry_start_ms"], direction=1,
                           stop_px=None, slip=slip)
        if t is not None:
            out.append(t)
    return out


def volatility_scale(strategy: np.ndarray, benchmark: np.ndarray) -> Dict[str, Any]:
    """k = sigma_strategy / sigma_benchmark, or UNDEFINED. Never capped."""
    s, b = float(np.std(strategy)), float(np.std(benchmark))
    if s == 0.0 or b == 0.0:
        return {"k": float("nan"), "sigma_strategy": s, "sigma_benchmark": b,
                "status": "UNDEFINED", "reason": "zero volatility"}
    k = s / b
    if k > MAX_K:
        return {"k": k, "sigma_strategy": s, "sigma_benchmark": b,
                "status": "UNDEFINED", "reason": f"k {k:.3f} > {MAX_K}"}
    return {"k": k, "sigma_strategy": s, "sigma_benchmark": b, "status": "OK"}


# --- null -------------------------------------------------------------------------------

def day_objects(df: pd.DataFrame, spec: SessionSpec, *, pair: str, expected: np.ndarray,
                pip: float = 0.0001) -> Dict[pd.Timestamp, Optional[Tuple[int, int]]]:
    """One object per ELIGIBLE day: None, or `(entry offset in bars, direction)`."""
    trades = {t["trading_day"]: t
              for t in run_candidate(df, spec, pair=pair, expected=expected, pip=pip)}
    out: Dict[pd.Timestamp, Optional[Tuple[int, int]]] = {}
    for day in eligible_days(df, spec, expected):
        key = str(pd.Timestamp(day).date())
        t = trades.get(key)
        if t is None:
            out[day] = None
        else:
            b = session_bounds(spec, day)
            out[day] = (int((t["signal_ms"] - b["entry_start_ms"]) // M15_MS),
                        int(t["direction"]))
    return out


def permute_objects(objects: Dict[str, Dict[Any, Any]], rng: np.random.Generator,
                    max_tries: int = 50) -> Dict[str, Dict[Any, Any]]:
    """Shuffle day objects within same-ISO-weekday groups, independently per pair.

    Only a GLOBALLY unchanged mapping is rejected: an individual day mapping to itself is
    a legitimate draw, and forbidding it would bias the null.
    """
    for _ in range(max_tries):
        out: Dict[str, Dict[Any, Any]] = {}
        for pair, by_day in objects.items():
            out[pair] = {}
            groups: Dict[int, List[Any]] = {}
            for day in by_day:
                groups.setdefault(pd.Timestamp(day).weekday(), []).append(day)
            for _wd, days in groups.items():
                vals = [by_day[d] for d in days]
                order = rng.permutation(len(vals))
                for d, j in zip(days, order):
                    out[pair][d] = vals[int(j)]
        if any(out[p][d] != objects[p][d] for p in objects for d in objects[p]):
            return out
    raise ValueError("permutation left the mapping globally unchanged after "
                     f"{max_tries} tries; the day set is too small to permute")


def day_cache(A: Dict[str, np.ndarray], spec: SessionSpec,
              days: Sequence[Any]) -> Dict[Any, Any]:
    """Per-day bounds and range extremes, computed ONCE and reused by every null run."""
    return {day: (session_bounds(spec, day), range_extremes(A, session_bounds(spec, day)))
            for day in days}


def apply_objects(df: pd.DataFrame, spec: SessionSpec, *, pair: str, expected: np.ndarray,
                  objects: Dict[Any, Any], pip: float = 0.0001,
                  slippage_pips: float = 0.0, A: Optional[Dict[str, np.ndarray]] = None,
                  idx: Optional[Dict[int, int]] = None,
                  cache: Optional[Dict[Any, Any]] = None) -> List[Dict[str, Any]]:
    """Re-run the engine with permuted decisions, rebuilding everything on the target day.

    `A`/`idx`/`cache` are pure memoisation of day-invariant work; passing them changes
    nothing about the result, only how often it is recomputed.
    """
    slip = float(slippage_pips) * float(pip)
    if A is None:
        A = bar_arrays(df)
    if idx is None:
        idx = bar_index(A)
    if cache is None:
        cache = day_cache(A, spec, list(objects))
    out: List[Dict[str, Any]] = []
    for day, obj in objects.items():
        if obj is None:
            continue
        offset, direction = obj
        b, extremes = cache[day]
        signal_ms = b["entry_start_ms"] + int(offset) * M15_MS
        if signal_ms > b["last_signal_open_ms"] or signal_ms not in idx:
            continue                      # the target day's window is shorter: NO_TRADE
        if extremes is None:
            continue
        hi, lo = extremes                 # the TARGET day's own range builds the stop
        t = execute_signal(A, idx, b, spec=spec, pair=pair, day=day,
                           signal_ms=signal_ms, direction=int(direction),
                           stop_px=lo if direction == 1 else hi, slip=slip,
                           range_high=hi, range_low=lo)
        if t is not None:
            out.append(t)
    return out


def run_null(frames: Dict[str, pd.DataFrame], *, spec: SessionSpec, expected: np.ndarray,
             runs: int = NULL_RUNS, seed: int = NULL_SEED,
             pips: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """`runs` deterministic full-engine reruns on permuted decisions."""
    pips = pips or {}
    pairs = sorted(frames)
    objects = {p: day_objects(frames[p], spec, pair=p, expected=expected,
                              pip=pips.get(p, 0.0001)) for p in pairs}
    days = sorted({str(pd.Timestamp(d).date()) for p in pairs for d in objects[p]})

    real = [t for p in pairs
            for t in run_candidate(frames[p], spec, pair=p, expected=expected,
                                   pip=pips.get(p, 0.0001))]
    real_alpha = float(daily_series(real, pairs, days).sum())

    arrays = {p: bar_arrays(frames[p]) for p in pairs}
    indexes = {p: bar_index(arrays[p]) for p in pairs}
    caches = {p: day_cache(arrays[p], spec, list(objects[p])) for p in pairs}

    alphas: List[float] = []
    for i in range(int(runs)):
        rng = np.random.default_rng(int(seed) + i)
        perm = permute_objects(objects, rng)
        trades = [t for p in pairs
                  for t in apply_objects(frames[p], spec, pair=p, expected=expected,
                                         objects=perm[p], pip=pips.get(p, 0.0001),
                                         A=arrays[p], idx=indexes[p], cache=caches[p])]
        alphas.append(float(daily_series(trades, pairs, days).sum()))
    arr = np.array(alphas)
    return {"real": real_alpha, "alphas": alphas, "runs": int(runs), "seed": int(seed),
            "percentile_rank": float(100.0 * (arr < real_alpha).mean()) if len(arr) else 0.0}


# --- gates and selection ------------------------------------------------------------------

def stress_frames(frames: Dict[str, pd.DataFrame], spread_mult: float
                  ) -> Dict[str, pd.DataFrame]:
    """Widen every bar's bid/ask symmetrically about its mid — the locked stress cell."""
    out: Dict[str, pd.DataFrame] = {}
    for pair, df in frames.items():
        w = df.copy()
        for f in ("o", "h", "l", "c"):
            mid = (w[f"bid_{f}"] + w[f"ask_{f}"]) / 2.0
            half = (w[f"ask_{f}"] - w[f"bid_{f}"]) / 2.0 * float(spread_mult)
            w[f"bid_{f}"], w[f"ask_{f}"] = mid - half, mid + half
        out[pair] = w
    return out


def _alpha_block(frames, spec, expected, pips, slippage_pips) -> Dict[str, Any]:
    """Strategy vs its session-matched benchmark, volatility-scaled. One shared k."""
    pairs = sorted(frames)
    strat = {p: run_candidate(frames[p], spec, pair=p, expected=expected,
                              pip=pips.get(p, 0.0001), slippage_pips=slippage_pips)
             for p in pairs}
    bench = {p: session_matched_benchmark(frames[p], spec, pair=p, expected=expected,
                                          pip=pips.get(p, 0.0001),
                                          slippage_pips=slippage_pips) for p in pairs}
    elig = {p: [str(pd.Timestamp(d).date())
                for d in eligible_days(frames[p], spec, expected)] for p in pairs}
    days = sorted({d for p in pairs for d in elig[p]})
    S = daily_series([t for p in pairs for t in strat[p]], pairs, days)
    B = daily_series([t for p in pairs for t in bench[p]], pairs, days)
    vs = volatility_scale(S, B)
    k = vs["k"] if vs["status"] == "OK" else 0.0
    # Per-pair alphas use the SAME portfolio k, so they decompose exactly into the
    # portfolio alpha and never go undefined for one thin pair alone.
    per_pair = {p: float(daily_series(strat[p], pairs, days).sum()
                         - k * daily_series(bench[p], pairs, days).sum()) for p in pairs}
    return {"alpha": float(S.sum() - k * B.sum()), "k": vs["k"],
            "benchmark_status": vs["status"], "per_pair_alpha": per_pair,
            "strat": strat, "eligible": elig, "days": days}


def measure_candidate(frames: Dict[str, pd.DataFrame], spec: SessionSpec, *,
                      expected: np.ndarray, pips: Optional[Dict[str, float]] = None,
                      null_percentile: Optional[float] = None,
                      spread_mult: float = 2.0,
                      stress_slippage_pips: float = 0.5) -> Dict[str, Any]:
    """Assemble one candidate's gate inputs. Measures; decides nothing."""
    pips = pips or {}
    base = _alpha_block(frames, spec, expected, pips, 0.0)
    stressed = _alpha_block(stress_frames(frames, spread_mult), spec, expected, pips,
                            stress_slippage_pips)
    pairs = sorted(frames)
    trades_per_pair = {p: len(base["strat"][p]) for p in pairs}
    participation = {p: (len(base["strat"][p]) / len(base["eligible"][p])
                         if base["eligible"][p] else 0.0) for p in pairs}
    active = {}
    for p in pairs:
        elig_m = {d[:7] for d in base["eligible"][p]}
        trade_m = {t["trading_day"][:7] for t in base["strat"][p]}
        active[p] = len(trade_m & elig_m) / len(elig_m) if elig_m else 0.0
    pp = base["per_pair_alpha"]
    return {
        "name": spec.name, "alpha": base["alpha"], "k": base["k"],
        "benchmark_status": base["benchmark_status"],
        "stressed_alpha": stressed["alpha"],
        "stress_benchmark_status": stressed["benchmark_status"],
        "per_pair_alpha": pp,
        "positive_pairs": sum(1 for v in pp.values() if v > 0),
        "worst_pair_alpha": min(pp.values()) if pp else 0.0,
        "participation": participation, "trades_per_pair": trades_per_pair,
        "active_month_ratio": active,
        "n_trades": sum(trades_per_pair.values()),
        "null_percentile": null_percentile if null_percentile is not None else -1.0,
    }


def evaluate_candidate(result: Dict[str, Any]) -> Dict[str, Any]:
    """Every activity and performance gate, AND-ed. One failure blocks the candidate."""
    failed: List[str] = []
    if result.get("benchmark_status") != "OK":
        failed.append("benchmark_undefined")
    if not result["alpha"] > 0:
        failed.append("alpha_not_positive")
    if not result["null_percentile"] >= GATES["min_null_percentile"]:
        failed.append("null_percentile")
    if not result["stressed_alpha"] > 0:
        failed.append("stressed_alpha_not_positive")
    if not result["positive_pairs"] >= GATES["min_positive_pairs"]:
        failed.append("positive_pairs")
    if not result["worst_pair_alpha"] >= GATES["worst_pair_floor"]:
        failed.append("worst_pair_floor")
    for pair, v in result["participation"].items():
        if not v >= GATES["min_participation"]:
            failed.append(f"participation:{pair}")
    for pair, v in result["trades_per_pair"].items():
        if not v >= GATES["min_trades_per_pair"]:
            failed.append(f"trades_per_pair:{pair}")
    for pair, v in result["active_month_ratio"].items():
        if not v >= GATES["min_active_month_ratio"]:
            failed.append(f"active_months:{pair}")
    return {**result, "eligible": not failed, "failed": sorted(failed)}


def select_candidate(results: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Deterministic: highest alpha, then fewer trades, then the locked candidate order."""
    order = list(SPECS)
    graded = [evaluate_candidate(r) for r in results]
    eligible = [r for r in graded if r["eligible"]]
    if not eligible:
        return {"selected": None, "verdict": "FAMILY_KILLED", "frozen": [],
                "candidates": graded}
    best = sorted(eligible, key=lambda r: (-r["alpha"], r["n_trades"],
                                           order.index(r["name"])))[0]
    return {"selected": best["name"], "verdict": "PROCEED", "frozen": [best["name"]],
            "candidates": graded}


def open_confirmation(selection: Optional[Dict[str, Any]]) -> str:
    """The ONLY door to the confirmation segment. Exactly one frozen candidate, or refuse."""
    if not selection or selection.get("verdict") != "PROCEED":
        raise ConfirmationLocked("confirmation stays shut: no candidate passed validation")
    frozen = selection.get("frozen") or []
    if len(frozen) != 1 or selection.get("selected") != frozen[0]:
        raise ConfirmationLocked(
            f"confirmation stays shut: exactly one frozen candidate required, got {frozen}")
    # Re-derive eligibility from the stored measurements. A hand-assembled dict claiming
    # PROCEED must not be able to open the segment on its own say-so.
    record = next((c for c in selection.get("candidates") or []
                   if c.get("name") == frozen[0]), None)
    if record is None:
        raise ConfirmationLocked(
            f"confirmation stays shut: no measurement record for {frozen[0]!r}")
    if not evaluate_candidate(record)["eligible"]:
        raise ConfirmationLocked(
            f"confirmation stays shut: {frozen[0]!r} does not pass validation on recheck")
    return frozen[0]
