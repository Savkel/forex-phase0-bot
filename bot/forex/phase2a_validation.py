"""Phase 2A validation runner — ONE segment, ONE pass, and a door that stays shut.

Three guarantees, all mechanical rather than procedural:

1. SEGMENT ISOLATION. `assert_validation_only` refuses frames carrying a single bar from
   development or confirmation. It runs before any measurement, so an out-of-segment frame
   cannot even be measured, let alone reported.
2. FROZEN INPUTS. The bars, window, candidate list and gate thresholds are fingerprinted.
   A caller may pass the fingerprint it expects; a mismatch refuses to run rather than
   quietly evaluating something else.
3. CONFIRMATION STAYS SHUT. Whatever the verdict, this module never loads confirmation
   bars. It records what a later, separate step WOULD be permitted to open, and nothing
   more.

No tuning, no reruns, no threshold edits, no pair removal. If no candidate clears every
gate the family is closed as `CLOSED_FAIL`.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from bot.forex.phase2a import SPECS
from bot.forex.phase2a_eval import (
    GATES,
    NULL_RUNS,
    NULL_SEED,
    ConfirmationLocked,
    evaluate_candidate,
    measure_candidate,
    open_confirmation,
    run_null,
    select_candidate,
)


def _ms(s: str) -> int:
    return int(pd.Timestamp(s, tz="UTC").value // 10 ** 6)


# The locked half-open segments. Boundaries sit in the weekend gap, so no bar can be
# shared between two of them.
DEVELOPMENT = (_ms("2014-01-04T00:00:00"), _ms("2021-07-03T00:00:00"))
VALIDATION = (_ms("2021-07-03T00:00:00"), _ms("2024-01-06T00:00:00"))
CONFIRMATION = (_ms("2024-01-06T00:00:00"), _ms("2026-06-27T00:00:00"))

PIPS = {"USD_JPY": 0.01}
UNIVERSE = ("AUD_USD", "EUR_USD", "GBP_USD", "USD_JPY")


def _opt(v: Any) -> Optional[float]:
    """Keep None as None: an all-undefined null has no distribution to report."""
    return None if v is None else float(v)


def assert_validation_only(frames: Dict[str, pd.DataFrame]) -> None:
    """Refuse a single bar from any other segment. Runs BEFORE any measurement."""
    for pair, df in sorted(frames.items()):
        t = df["open_time"].to_numpy("int64")
        if len(t) == 0:
            raise ValueError(f"{pair}: no bars supplied for the validation segment")
        if (t >= CONFIRMATION[0]).any():
            n = int((t >= CONFIRMATION[0]).sum())
            raise ValueError(f"{pair}: {n} bar(s) fall in the confirmation segment; "
                             f"confirmation stays sealed during validation")
        if (t < VALIDATION[0]).any() or (t >= VALIDATION[1]).any():
            n = int(((t < VALIDATION[0]) | (t >= VALIDATION[1])).sum())
            raise ValueError(f"{pair}: {n} bar(s) outside the validation segment "
                             f"[{VALIDATION[0]}, {VALIDATION[1]})")


def fingerprint(frames: Dict[str, pd.DataFrame],
                expected: Optional[np.ndarray] = None) -> str:
    """SHA-256 over every frozen input: bars, window, expected grid, the full candidate
    SPECIFICATIONS (not just their names), gate thresholds, costs and null settings.

    Naming the candidates is not enough — retuning a session window would otherwise leave
    the fingerprint unchanged and the run would look like the same experiment.
    """
    h = hashlib.sha256()
    h.update(json.dumps({"window": list(VALIDATION), "universe": list(UNIVERSE),
                         "candidates": {n: repr(s) for n, s in SPECS.items()},
                         "gates": GATES, "pips": PIPS,
                         "null": {"runs": NULL_RUNS, "seed": NULL_SEED}},
                        sort_keys=True).encode())
    if expected is not None:
        h.update(np.ascontiguousarray(np.asarray(expected, dtype="int64")).tobytes())
    for pair in sorted(frames):
        df = frames[pair]
        h.update(pair.encode())
        h.update(df["open_time"].to_numpy("int64").tobytes())
        for col in sorted(c for c in df.columns if c.startswith(("bid_", "ask_"))):
            h.update(np.ascontiguousarray(df[col].to_numpy(float)).tobytes())
    return h.hexdigest()


def run_validation(frames: Dict[str, pd.DataFrame], *, expected: np.ndarray,
                   expected_fingerprint: Optional[str] = None,
                   supersedes: Optional[Dict[str, str]] = None,
                   measure_fn: Callable[..., Dict[str, Any]] = None,
                   null_fn: Callable[..., Dict[str, Any]] = None) -> Dict[str, Any]:
    """The single validation pass. Verdict-first result; confirmation never opened.

    The null's run count and seed are NOT parameters: they are the locked constants, so a
    run cannot be quietly cheapened. `measure_fn`/`null_fn` are a test seam only, and a
    result produced through them says so in its `engine` field.
    """
    assert_validation_only(frames)
    if sorted(frames) != sorted(UNIVERSE):
        raise ValueError(f"universe mismatch: expected {sorted(UNIVERSE)}, "
                         f"got {sorted(frames)}; no pair may be added or removed")
    fp = fingerprint(frames, expected)
    if expected_fingerprint is not None and fp != expected_fingerprint:
        raise ValueError(f"input fingerprint mismatch: expected {expected_fingerprint}, "
                         f"got {fp}; refusing to evaluate different inputs")

    injected = measure_fn is not None or null_fn is not None
    measure_fn = measure_fn or measure_candidate
    null_fn = null_fn or run_null

    measured: List[Dict[str, Any]] = []
    for name, spec in SPECS.items():
        null = null_fn(frames, spec=spec, expected=expected, runs=NULL_RUNS,
                       seed=NULL_SEED, pips=PIPS)
        m = measure_fn(frames, spec, expected=expected, pips=PIPS,
                       null_percentile=null["percentile_rank"])
        # An activity gate that never sees a pair is not a gate. Every per-pair map must
        # cover the whole universe or the AND-ing is vacuous for the missing ones.
        for field in ("participation", "trades_per_pair", "active_month_ratio"):
            if sorted(m[field]) != sorted(UNIVERSE):
                raise ValueError(f"{name}: {field} covers {sorted(m[field])}, not the "
                                 f"locked universe {sorted(UNIVERSE)}")
        m["null"] = {
            "statistic": null.get("statistic", "volatility_matched_alpha"),
            "real": float(null["real"]),
            "min": _opt(null.get("min")),
            "median": _opt(null.get("median")),
            "max": _opt(null.get("max")),
            "percentile_rank": float(null["percentile_rank"]),
            "runs": int(null["runs"]), "seed": int(null["seed"]),
            "status": null.get("status", "OK"),
            "undefined_replicates": int(null.get("undefined_replicates", 0)),
            "diagnostic_raw": null.get("diagnostic_raw"),
        }
        # The gating statistic is now the SAME volatility-matched alpha as the alpha gate,
        # and an undefined replicate fails closed rather than scoring an empty zero.
        m["null_status"] = m["null"]["status"]
        measured.append(m)

    selection = select_candidate(measured)
    graded = selection["candidates"]

    opened = False
    unlocks: Optional[str] = None
    seal_reason = ""
    try:
        unlocks = open_confirmation(selection)      # asks only WHETHER it would open
        seal_reason = "one candidate cleared every gate; confirmation may be opened by a "\
                      "separate, later step"
    except ConfirmationLocked as e:
        seal_reason = str(e)

    verdict = "PROCEED" if selection["verdict"] == "PROCEED" else "CLOSED_FAIL"
    return {
        "verdict": verdict,
        "verdict_note": ("Session/liquidity breakout family CLOSED as FAILED on the frozen "
                         "validation segment — no rescue, no retune, no rerun."
                         if verdict == "CLOSED_FAIL" else
                         "One candidate is frozen for confirmation. Nothing else proceeds."),
        "phase": "phase2a", "segment": "validation", "research_only": True,
        "selected": selection["selected"], "frozen": selection["frozen"],
        "window": {"start_ms": VALIDATION[0], "end_ms": VALIDATION[1],
                   "start": str(pd.Timestamp(VALIDATION[0], unit="ms", tz="UTC")),
                   "end": str(pd.Timestamp(VALIDATION[1], unit="ms", tz="UTC"))},
        "universe": sorted(frames),
        "fingerprint": fp,
        "engine": "injected" if injected else "production",
        "gating_statistic": "volatility_matched_alpha",
        "supersedes": supersedes,
        "null_settings": {"runs": int(NULL_RUNS), "seed": int(NULL_SEED),
                          "method": "session-preserving day-object permutation",
                          "statistic": "volatility_matched_alpha",
                          "k_per_replicate": True},
        "gates": dict(GATES),
        "candidates": graded,
        "confirmation": {"opened": opened, "unlocks": unlocks, "reason": seal_reason},
    }


def render_markdown(result: Dict[str, Any]) -> str:
    """Verdict-first Markdown. Renders the result; recomputes nothing."""
    L: List[str] = []
    L.append(f"# Phase 2A validation — {result['verdict']}")
    L.append("")
    L.append(f"**{result['verdict_note']}**")
    L.append("")
    L.append(f"Research only. Segment: validation `{result['window']['start']}` → "
             f"`{result['window']['end']}`. Universe: {', '.join(result['universe'])}.")
    if result.get("supersedes"):
        L.append("")
        L.append(f"> Supersedes report `{result['supersedes'].get('sha256', '')[:16]}…` — "
                 f"{result['supersedes'].get('reason', '')}")
        L.append("")
    L.append(f"Input fingerprint `{result['fingerprint'][:16]}…`. Null: "
             f"{result['null_settings']['runs']} runs, seed "
             f"{result['null_settings']['seed']}, "
             f"{result['null_settings']['method']}.")
    L.append("")
    L.append(f"Selected: **{result['selected'] or 'none — family killed'}**")
    L.append("")
    L.append("## Candidates")
    for c in result["candidates"]:
        L.append("")
        L.append(f"### {c['name']} — {'ELIGIBLE' if c['eligible'] else 'REJECTED'}")
        L.append(f"- vol-matched alpha: `{c['alpha']:.6f}` (k = `{c['k']:.4f}`, "
                 f"benchmark {c['benchmark_status']})")
        L.append(f"- stressed alpha: `{c['stressed_alpha']:.6f}`")
        def _f(v):        # an all-undefined null has no distribution to print
            return "n/a" if v is None else f"{v:.6f}"
        L.append(f"- null ({c['null']['statistic']}, {c['null']['runs']} runs, seed "
                 f"{c['null']['seed']}): real `{c['null']['real']:.6f}` vs replicates "
                 f"min `{_f(c['null']['min'])}` / median `{_f(c['null']['median'])}` / "
                 f"max `{_f(c['null']['max'])}`")
        L.append(f"- null percentile: `{c['null']['percentile_rank']:.1f}` "
                 f"(threshold {GATES['min_null_percentile']}, status "
                 f"{c['null']['status']})")
        L.append(f"- positive pairs: `{c['positive_pairs']}`; worst pair alpha: "
                 f"`{c['worst_pair_alpha']:.6f}`")
        L.append(f"- trades: `{c['n_trades']}`; per pair: `{c['trades_per_pair']}`")
        L.append(f"- participation: `{ {k: round(v, 4) for k, v in c['participation'].items()} }`")
        L.append(f"- failed gates: `{c['failed'] or 'none'}`")
    L.append("")
    L.append("## Confirmation")
    L.append(f"- opened: `{result['confirmation']['opened']}`")
    L.append(f"- {result['confirmation']['reason']}")
    L.append("")
    L.append("No tuning, no threshold change, no pair removal, no rerun follows from this "
             "result.")
    return "\n".join(L) + "\n"
