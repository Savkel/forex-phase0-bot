"""Render the Phase 1 result dict (from run_phase1, Task 12) to verdict-first
Markdown. PRESENTATION ONLY: this module contains no strategy/metric/benchmark/
null/gate/selection logic and imports nothing from the bot -- it formats numbers
that are already computed and stored in the report dict, and recomputes nothing.
The verdict wording is honest: a FAIL is reported as FAIL (never dressed as a
near-pass); even a PASS carries the research-only / no-trading banner and never
implies a live or tradeable result. Deterministic given the same dict."""
from __future__ import annotations
from typing import Any, Dict, List

_MISSING = "—"


def _num(x: Any) -> str:
    """Deterministic scalar formatting: floats to <=6 decimals with trailing zeros
    stripped (0 rendered as '0', never '-0'); ints/strings/other as-is."""
    if isinstance(x, bool):
        return str(x)
    if isinstance(x, float):
        if x == 0:
            return "0"
        return f"{x:.6f}".rstrip("0").rstrip(".")
    return str(x)


def _row(cells: List[Any]) -> str:
    return "| " + " | ".join(_num(c) for c in cells) + " |"


def _sep(n: int) -> str:
    return "| " + " | ".join(["---"] * n) + " |"


def render_phase1_markdown(report: Dict[str, Any]) -> str:
    r = report
    sel_name = r["selection"]["selected"]
    hd = r.get("holdout_detail", {})
    hg = r.get("holdout_gate", {})
    acc = r.get("acceptance", {})
    diag = r.get("diagnostics", {})
    w = r.get("window", {})
    out: List[str] = []

    # --- verdict first ---
    out.append(f"# Phase 1 verdict: {r['verdict']} — {r.get('verdict_note', '')}")
    out.append("")
    out.append("> **RESEARCH-ONLY.** No paper trading, no live trading, no broker order "
               "execution, no real money. This is a pre-registered kill-test verdict on frozen "
               "holdout data only; a live edge verdict requires the gated OANDA run.")
    out.append("")
    out.append(f"Selected candidate: **{sel_name}** — {r['selection'].get('metric', '')}; "
               f"tie-break {r['selection'].get('tie_break', '')}. Selection is TRAIN-ONLY and was "
               f"frozen before any holdout data was evaluated.")
    out.append("")

    # --- five-gate acceptance table (values / thresholds / reasons) ---
    out.append("## Holdout 5-gate acceptance (holdout-only; PASS requires ALL five)")
    out.append(_row(["gate", "value", "op", "threshold", "status", "reason"]))
    out.append(_sep(6))
    for c in acc.get("checks", []):
        out.append(_row([c.get("rule", ""), c.get("value", _MISSING), c.get("op", ""),
                         c.get("threshold", _MISSING), c.get("status", ""),
                         c.get("reason") or _MISSING]))
    out.append("")
    out.append("_Gate 5 (cross-pair robustness) is the two `cross_pair_*` rows: a positive-pair "
               "count and a worst-pair floor._")
    cp = acc.get("cross_pair", {})
    if cp:
        out.append("")
        out.append(f"Cross-pair robustness: **{_num(cp.get('n_positive'))}/{_num(cp.get('n_pairs'))}** "
                   f"pairs with positive holdout alpha (need >= {_num(cp.get('min_positive_pairs'))}); "
                   f"worst per-pair alpha {_num(cp.get('worst_alpha'))} (floor {_num(cp.get('per_pair_floor'))}).")
    out.append("")

    # --- selected-candidate holdout metrics ---
    sel_ho = next((c["holdout"] for c in r.get("candidates", []) if c["name"] == sel_name), {})
    out.append(f"## Selected-candidate holdout metrics — {sel_name}")
    out.append(_row(["metric", "value"]))
    out.append(_sep(2))
    out.append(_row(["portfolio holdout alpha (Gate 1)", hg.get("portfolio_holdout_alpha", sel_ho.get("alpha", _MISSING))]))
    out.append(_row(["portfolio holdout return", sel_ho.get("return", _MISSING)]))
    out.append(_row(["max drawdown (Gate 3)", hg.get("bot_max_drawdown", sel_ho.get("max_drawdown", _MISSING))]))
    out.append(_row(["avg net exposure", hd.get("avg_net_exposure", sel_ho.get("avg_net_exposure", _MISSING))]))
    out.append(_row(["avg gross exposure (G)", hd.get("G", sel_ho.get("avg_gross_exposure", _MISSING))]))
    out.append(_row(["trades", sel_ho.get("trades", _MISSING)]))
    out.append("")

    # --- matched-risk benchmarks: gross-matched PRIMARY, net-matched DIAGNOSTIC ---
    out.append("## Matched-risk benchmarks")
    out.append(f"**Gross-matched basket — PRIMARY (Gate-3 drawdown reference).** Always-long at the "
               f"bot's measured gross exposure **G = {_num(hd.get('G'))}**; the basket's own measured "
               f"gross is {_num(hd.get('gross_matched_measured_gross'))}. Gross-matched max drawdown "
               f"{_num(hd.get('gross_matched_max_drawdown'))} vs bot max drawdown "
               f"{_num(hg.get('bot_max_drawdown'))} — PASS needs the bot shallower-or-equal "
               f"(drawdowns <= 0, so bot >= gross-matched).")
    out.append("")
    out.append("**Net-matched basket — DIAGNOSTIC ONLY (non-gating).** Not part of the Phase 1 "
               "verdict path and not computed by this run; the gross-matched basket above is the sole "
               "matched-risk benchmark feeding the drawdown gate.")
    out.append("")

    # --- cost-stress sweep ---
    sweep = diag.get("cost_stress_sweep", {})
    out.append("## Cost-stress sweep (portfolio exposure-adjusted alpha)")
    out.append(_row(["base", "spread", "swap", "combined (Gate 4)"]))
    out.append(_sep(4))
    out.append(_row([sweep.get("base", _MISSING), sweep.get("spread", _MISSING),
                     sweep.get("swap", _MISSING), sweep.get("combined", _MISSING)]))
    out.append("")
    out.append("_`combined` (spread + swap stressed together) is the Gate-4 cell._")
    out.append("")

    # --- timing null: primary GATING + diagnostics ---
    pn = diag.get("null_circular_per_pair", {})
    out.append("## Timing null benchmark")
    out.append(f"**Primary — per-pair-independent circular shift — GATING (Gate 2).** Percentile rank "
               f"**{_num(pn.get('percentile_rank'))}**, p-value {_num(pn.get('p_value'))}, real alpha "
               f"{_num(pn.get('real_alpha'))} (median {_num(pn.get('median'))}, p90 {_num(pn.get('p90'))}, "
               f"p95 {_num(pn.get('p95'))}).")
    out.append("")
    out.append("**Diagnostic nulls — NON-GATING** (shown for context; they never feed the gate):")
    out.append(_row(["method", "percentile rank", "p-value"]))
    out.append(_sep(3))
    for key, label in (("null_common_shift", "common_shift (diagnostic)"),
                       ("null_block_shuffle", "block_shuffle (diagnostic)")):
        d = diag.get(key, {})
        out.append(_row([label, d.get("percentile_rank", _MISSING), d.get("p_value", _MISSING)]))
    out.append("")

    # --- per-pair holdout alpha table (Gate-5 evidence) ---
    out.append("## Per-pair holdout exposure-adjusted alpha (selected candidate — Gate-5 evidence)")
    out.append(_row(["pair", "holdout alpha"]))
    out.append(_sep(2))
    for pair, a in hg.get("per_pair_holdout_alphas", {}).items():
        out.append(_row([pair, a]))
    out.append("")

    # --- all candidates: train selection summary + holdout diagnostics ---
    out.append("## All candidates — train (selection) and holdout (diagnostic)")
    out.append(_row(["candidate", "train alpha", "train trades", "holdout alpha", "holdout trades"]))
    out.append(_sep(5))
    for c in r.get("candidates", []):
        tr, ho = c.get("train", {}), c.get("holdout", {})
        mark = " (selected)" if c["name"] == sel_name else ""
        out.append(_row([c["name"] + mark, tr.get("alpha", _MISSING), tr.get("trades", _MISSING),
                         ho.get("alpha", _MISSING), ho.get("trades", _MISSING)]))
    out.append("")
    out.append("_Selection used the TRAIN column only; the holdout columns for the non-selected "
               "candidates are post-verdict diagnostics and never influence the verdict._")
    out.append("")

    # --- provenance: common window + split ---
    out.append("## Provenance — common window & split")
    out.append(f"Universe: {', '.join(w.get('universe', []))}. Shared window "
               f"[{_num(w.get('start_ms'))}, {_num(w.get('end_ms'))}] ms; split boundary "
               f"{_num(w.get('boundary_ms'))} ms; shared-timeline train/holdout "
               f"{_num(w.get('train_len'))}/{_num(w.get('holdout_len'))}.")
    out.append("")
    out.append(_row(["pair", "train bars", "holdout bars", "pip"]))
    out.append(_sep(4))
    bars = w.get("per_pair_bars", {})
    costs = w.get("costs", {})
    for pair in w.get("universe", []):
        b = bars.get(pair, {})
        out.append(_row([pair, b.get("train", _MISSING), b.get("holdout", _MISSING),
                         costs.get(pair, {}).get("pip", _MISSING)]))
    out.append("")
    return "\n".join(out) + "\n"
