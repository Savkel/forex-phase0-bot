"""Phase 1 deliver loop: load/fetch the 7-pair H4 universe -> common-calendar
split -> STRICTLY STAGED train-only selection then holdout-only verdict -> write a
deterministic verdict-first JSON report.

The staging enforces OOS hygiene (no holdout leak into selection):
  Stage 1  screen ALL candidates on TRAIN only (portfolio exposure-adjusted alpha);
           no holdout frame/decision/metric is accessed.
  Stage 2  FREEZE the selection on max TRAIN alpha (tie-break: fewer train trades,
           then candidate order); the selection records carry no holdout field.
  Stage 3  ONLY AFTER the freeze, evaluate HOLDOUT for the SELECTED candidate ONLY --
           the sole holdout book that feeds benchmarks, stress, the primary null,
           per-pair robustness, the five gates, and the verdict.
  Stage 4  AFTER the verdict, compute report-only holdout numbers for the other two
           candidates and the null diagnostics; these are strictly non-gating and
           cannot influence selection or verdict.

Selection is TRAIN-only; the verdict is HOLDOUT-only; a failing holdout is never
rescued. This module is ORCHESTRATION ONLY — every numeric primitive (fills, spread,
swap, drawdown, exposure-adjusted alpha, matched-risk benchmarks, the timing null,
and the 5-gate acceptance) lives in an already-tested `bot/forex/*` module. Nothing
here re-implements strategy, cost, execution, benchmark, null, or gate logic; it
wires the tested functions and serializes the report. No paper/live orders; the real
OANDA pull is reached only when `main` is called without injected `frames` (env
token via `fetch_candles`), and is separately gated by explicit human sign-off."""
from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd

from bot.forex.config_loader_phase1 import load_phase1_config
from bot.forex.cost_model import CostModel
from bot.forex.multipair_data import split_common_window
from bot.forex.meanrev_signals import candidate_decisions
from bot.forex.backtest import simulate
from bot.forex.evaluate import exposure_adjusted_alpha, hold_long
from bot.forex.portfolio import (run_sleeve, aggregate_portfolio, portfolio_hold_basket,
                                 gross_matched_basket, portfolio_cost_stress, portfolio_null)
from bot.forex.acceptance_phase1 import phase1_acceptance

# The primary/gating null is ALWAYS the per-pair independent circular shift (the locked
# pre-registered Gate-2 distribution). It is hardcoded here so a `null_bench.method`
# value can never demote the gating null to a diagnostic. `common_shift`/`block_shuffle`
# are computed only as non-gating diagnostics.
_PRIMARY_NULL_METHOD = "circular_shift"


def _cost_by_pair(costs_cfg: Dict[str, Any], universe) -> Dict[str, CostModel]:
    """Per-pair CostModel from the locked config (JPY pip override honored; all other
    cost fields shared). No cost math here — the tested engine consumes these models."""
    ov = costs_cfg.get("pip_overrides", {})
    return {p: CostModel(pip=float(ov.get(p, costs_cfg["pip"])),
                         long_swap_pips=costs_cfg["long_swap_pips"],
                         short_swap_pips=costs_cfg["short_swap_pips"],
                         rollover_hour_utc=costs_cfg["rollover_hour_utc"],
                         spread_mult=costs_cfg["spread_mult"],
                         swap_mult=costs_cfg["swap_mult"]) for p in universe}


def _decisions(frames, name, max_hold):
    """Per-pair decision arrays for ONE candidate (reused `meanrev_signals`)."""
    return {p: candidate_decisions(frames[p], name, max_hold) for p in frames}


def _portfolio_metrics(frames, dec, cbp, eq):
    """One window's portfolio metrics for a decision book: per-pair sleeves through the
    tested engine (`run_sleeve`), 1/N combined (`aggregate_portfolio`), exposure-adjusted
    alpha vs the costed hold basket (reused `exposure_adjusted_alpha`). Every fill/cost/PnL
    is delegated to the tested primitives; the runner re-derives nothing."""
    sleeves = [run_sleeve(frames[p], dec[p], cbp[p], 1.0, eq) for p in frames]
    agg = aggregate_portfolio(sleeves, None, eq)
    hold = portfolio_hold_basket(frames, cbp, None, 1.0, eq)
    alpha = exposure_adjusted_alpha(agg["portfolio_return"], agg["avg_net_exposure"],
                                    hold["portfolio_return"])
    trades = sum(int(s["summary"]["trade_count"]) for s in sleeves)
    return {"alpha": round(float(alpha), 6), "return": round(agg["portfolio_return"], 6),
            "max_drawdown": agg["max_drawdown"], "avg_net_exposure": agg["avg_net_exposure"],
            "avg_gross_exposure": agg["avg_gross_exposure"], "trades": trades,
            "agg": agg, "hold": hold}


def _per_pair_holdout_alphas(frames, dec, cbp, eq):
    """Per-pair holdout exposure-adjusted alpha (Gate-5 evidence): each pair scored
    independently through the tested engine + reused alpha helper."""
    out = {}
    for p in frames:
        s = simulate(frames[p], dec[p], cbp[p], 1.0, eq)["summary"]
        hr = hold_long(frames[p], cbp[p], eq)["total_return"]
        out[p] = round(exposure_adjusted_alpha(s["total_return"], s["avg_net_exposure"], hr), 6)
    return out


def _select(cand_rows: List[Dict[str, Any]], order: List[str]) -> str:
    """The ONE pre-registered, TRAIN-ONLY selection: highest train exposure-adjusted
    alpha, tie-break fewer train trades, then candidate order. Reads ONLY each row's
    `train` block — the untouched-holdout numbers never influence the choice."""
    return sorted(cand_rows, key=lambda r: (-r["train"]["alpha"], r["train"]["trades"],
                                            order.index(r["name"])))[0]["name"]


def run_phase1(cfg: Dict[str, Any], frames: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
    eq = float(cfg["starting_equity"])
    universe = list(frames.keys())
    max_hold = int(cfg["max_holding_bars"])
    cbp = _cost_by_pair(cfg["costs"], universe)

    split = split_common_window(frames, cfg["split"]["holdout_frac"])
    train, holdout, meta = split["train"], split["holdout"], split["meta"]

    order = list(cfg["candidates"])
    keys = ("alpha", "return", "max_drawdown", "avg_net_exposure", "avg_gross_exposure", "trades")

    # === Stage 1: TRAIN-ONLY screening. No holdout frame, decision, metric, or result is
    #     accessed here; the selection records carry a `train` block and NO holdout field. ===
    train_by_name: Dict[str, Any] = {}
    train_rows: List[Dict[str, Any]] = []
    for name in order:
        tr = _portfolio_metrics(train, _decisions(train, name, max_hold), cbp, eq)
        train_by_name[name] = {k: tr[k] for k in keys}
        train_rows.append({"name": name, "train": train_by_name[name]})

    # === Stage 2: freeze the ONE pre-registered selection on TRAIN alpha only ===
    selected = _select(train_rows, order)
    selection = {"selected": selected,
                 "metric": "max TRAIN portfolio exposure-adjusted alpha (base costs)",
                 "tie_break": "then fewer TRAIN trades, then candidate order",
                 "note": "ONE pre-registered train-only selection step, FROZEN before any holdout "
                         "data is touched; all 3 candidates are reported. Holdout never selects; "
                         "the other two candidates' holdout numbers are non-gating diagnostics."}

    # === Stage 3: HOLDOUT is evaluated only AFTER the freeze, for the SELECTED candidate ONLY.
    #     This is the sole holdout book that feeds benchmarks, stress, null, per-pair
    #     robustness, the five gates, and the verdict. ===
    dh = _decisions(holdout, selected, max_hold)
    sel = _portfolio_metrics(holdout, dh, cbp, eq)
    G = sel["avg_gross_exposure"]
    gm = gross_matched_basket(holdout, cbp, G, None, eq)                    # Gate-3 drawdown reference
    sweep = portfolio_cost_stress(holdout, dh, cbp, cfg["cost_stress"]["spread_mult"],
                                  cfg["cost_stress"]["swap_mult"], None, eq)
    nb = cfg["null_bench"]
    null_primary = portfolio_null(holdout, dh, cbp, None, runs=int(nb["runs"]),
                                  method=_PRIMARY_NULL_METHOD, seed=int(nb["seed"]),
                                  guard_frac=float(nb["guard_frac"]), block_len=nb["block_len"], eq=eq)
    per_pair = _per_pair_holdout_alphas(holdout, dh, cbp, eq)

    gate_metrics = {
        "portfolio_holdout_alpha": sel["alpha"],
        "null_percentile": null_primary["percentile_rank"],               # PRIMARY (circular-shift) null only
        "bot_max_drawdown": sel["max_drawdown"],
        "gross_matched_max_drawdown": gm["max_drawdown"],                  # gross-matched, NOT net-matched
        "stress_combined_alpha": sweep["combined"],
        "per_pair_holdout_alphas": per_pair,
    }
    acc = phase1_acceptance(gate_metrics,
                            null_percentile_gate=float(cfg["acceptance"]["null_percentile"]),
                            min_positive_pairs=int(cfg["acceptance"]["min_positive_pairs"]),
                            per_pair_floor=float(cfg["acceptance"]["per_pair_floor"]))

    # === Stage 4: report-only diagnostics, computed AFTER selection AND the verdict are
    #     frozen, so they can never influence either. Non-selected candidates' holdout
    #     numbers are produced here purely for the report (spec: all 3 reported); the
    #     selected candidate reuses its already-computed Stage-3 holdout metrics (so its
    #     holdout is evaluated exactly once). ===
    holdout_by_name: Dict[str, Any] = {}
    for name in order:
        ho = sel if name == selected else _portfolio_metrics(holdout, _decisions(holdout, name, max_hold), cbp, eq)
        holdout_by_name[name] = {k: ho[k] for k in keys}
    candidates = [{"name": name, "train": train_by_name[name], "holdout": holdout_by_name[name]}
                  for name in order]

    diagnostics = {
        "cost_stress_sweep": sweep,
        "null_circular_per_pair": null_primary,
        "null_common_shift": portfolio_null(holdout, dh, cbp, None, runs=int(nb["runs"]),
                                            method="common_shift", seed=int(nb["seed"]),
                                            guard_frac=float(nb["guard_frac"]), eq=eq),
        "null_block_shuffle": portfolio_null(holdout, dh, cbp, None, runs=int(nb["runs"]),
                                             method="block_shuffle", seed=int(nb["seed"]),
                                             block_len=nb["block_len"], eq=eq),
        "portfolio_hold_return": round(sel["hold"]["portfolio_return"], 6),
    }

    return {
        "verdict": acc["overall"], "verdict_note": acc["verdict_note"],   # verdict-first
        "phase": "phase1", "research_only": True,
        "selection": selection, "candidates": candidates,
        "holdout_gate": gate_metrics,
        "holdout_detail": {"selected": selected, "G": round(float(G), 6),
                           "gross_matched_measured_gross": round(gm["avg_gross_exposure"], 6),
                           "gross_matched_max_drawdown": gm["max_drawdown"],
                           "avg_net_exposure": sel["avg_net_exposure"],
                           "avg_gross_exposure": sel["avg_gross_exposure"]},
        "acceptance": acc, "diagnostics": diagnostics,
        "window": {"universe": universe, "start_ms": meta["start_ms"], "end_ms": meta["end_ms"],
                   "boundary_ms": meta["boundary_ms"], "train_len": meta["train_len"],
                   "holdout_len": meta["holdout_len"],
                   "per_pair_bars": {p: {"train": int(len(train[p])), "holdout": int(len(holdout[p]))}
                                     for p in universe},
                   "costs": {p: {"pip": cbp[p].pip, "long_swap_pips": cbp[p].long_swap_pips,
                                 "short_swap_pips": cbp[p].short_swap_pips} for p in universe}},
    }


def main(config_path: str, *, frames: Optional[Dict[str, pd.DataFrame]] = None) -> Dict[str, Any]:
    """Load the locked config, run the deliver loop, write the JSON report, print the
    verdict. Fetches the real OANDA data ONLY when `frames is None` (tests inject
    `frames`, so no network is touched). The real pull needs OANDA_API_TOKEN (env, via
    `fetch_candles`) and is separately gated by explicit human sign-off — it produces no
    verdict until run. No paper/live orders are ever placed."""
    cfg = load_phase1_config(config_path)
    if frames is None:
        from bot.forex.multipair_data import load_universe
        from bot.forex.oanda_data import fetch_candles
        frames = load_universe(cfg["data"], cfg["universe"],
                               fetch_fn_factory=lambda pair, c: fetch_candles(c))
    report = run_phase1(cfg, frames)
    out_dir = Path(cfg["reporting"]["base_dir"]); out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "phase1_evaluation.json").write_text(json.dumps(report, indent=2, default=str),
                                                    encoding="utf-8")
    print(f"VERDICT: {report['verdict']} — {report['verdict_note']}")
    print(f"selected={report['selection']['selected']} G={report['holdout_detail']['G']} "
          f"gate={json.dumps({k: v for k, v in report['holdout_gate'].items() if k != 'per_pair_holdout_alphas'})}")
    return report


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "config/forex_phase1.yaml")
