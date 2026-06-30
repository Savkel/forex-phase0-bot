"""Phase 0 deliver loop: load/fetch -> features -> screen all 3 candidates on
TRAIN -> select by max TRAIN exposure-adjusted alpha -> holdout verdict (alpha,
gross-matched passive DD at MEASURED gross, cost-stress sweep, execution-faithful
null benchmark) -> HOLDOUT-ONLY acceptance. Selection is train-only; the verdict
is holdout-only; a failing holdout is never rescued by train. All three
candidates' train AND holdout results are reported (spec §2.5). No strategy/cost
logic lives here — this only orchestrates the already-tested modules."""
from __future__ import annotations
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, Optional
import pandas as pd

from bot.forex.config_loader import load_config
from bot.forex.cost_model import CostModel
from bot.forex.indicators import compute_features
from bot.forex.signals import candidate_decisions
from bot.forex.backtest import simulate
from bot.forex.evaluate import (exposure_adjusted_alpha, hold_long, matched_gross,
                                passive_benchmarks, segmented_evaluation)
from bot.forex.nullbench import null_distribution
from bot.forex.acceptance import phase0_acceptance

def _cost(cfg: Dict[str, Any], stress: bool = False) -> CostModel:
    c = cfg["costs"]
    sm = cfg["cost_stress"]["spread_mult"] if stress else c["spread_mult"]
    wm = cfg["cost_stress"]["swap_mult"] if stress else c["swap_mult"]
    return CostModel(pip=c["pip"], long_swap_pips=c["long_swap_pips"],
                     short_swap_pips=c["short_swap_pips"], rollover_hour_utc=c["rollover_hour_utc"],
                     spread_mult=sm, swap_mult=wm)

def _eval_window(bars: pd.DataFrame, decisions, cost: CostModel, eq: float) -> Dict[str, Any]:
    """Costed window metrics + exposure-adjusted alpha vs the costed always-long
    benchmark (both through the SAME engine)."""
    s = simulate(bars, decisions, cost, 1.0, eq)["summary"]
    hold = hold_long(bars, cost, eq)["total_return"]
    return {"total_return": s["total_return"], "max_drawdown": s["max_drawdown"],
            "avg_net_exposure": s["avg_net_exposure"], "avg_gross_exposure": s["avg_gross_exposure"],
            "trades": s["trade_count"],
            "alpha": round(exposure_adjusted_alpha(s["total_return"], s["avg_net_exposure"], hold), 6)}

def run_phase0(cfg: Dict[str, Any], bars: pd.DataFrame) -> Dict[str, Any]:
    eq = float(cfg["starting_equity"])
    base = _cost(cfg, stress=False)
    feats = compute_features(bars, cfg["candidates"])
    n = len(feats)
    cut = int(round(n * (1.0 - cfg["split"]["holdout_frac"])))
    train = feats.iloc[:cut].reset_index(drop=True)
    holdout = feats.iloc[cut:].reset_index(drop=True)

    # --- screen ALL candidates on TRAIN and HOLDOUT; report all three ---
    cand_rows = []
    for name in cfg["candidates"]:
        cand_rows.append({
            "name": name,
            "train": _eval_window(train, candidate_decisions(train, name), base, eq),
            "holdout": _eval_window(holdout, candidate_decisions(holdout, name), base, eq),
        })

    # --- selection: highest TRAIN exposure-adjusted alpha ONLY (tie-break: fewer trades, then order) ---
    order = list(cfg["candidates"])
    selected = sorted(cand_rows, key=lambda r: (-r["train"]["alpha"], r["train"]["trades"],
                                                order.index(r["name"])))[0]["name"]
    selection = {"selected": selected, "metric": "max TRAIN exposure-adjusted alpha (base costs)",
                 "note": "ONE pre-registered selection step on TRAIN only; all 3 candidates reported. "
                         "Holdout is never used to select."}

    # --- holdout verdict for the selected candidate (read once) ---
    d_hold = candidate_decisions(holdout, selected)
    sel = simulate(holdout, d_hold, base, 1.0, eq)["summary"]
    hold_ret = hold_long(holdout, base, eq)["total_return"]
    f_gross = sel["avg_gross_exposure"] or 1.0                  # MEASURED avg gross; 1.0 only as fallback
    gross = matched_gross(holdout, base, f_gross, eq)           # gross-matched DD reference
    holdout_alpha = exposure_adjusted_alpha(sel["total_return"], sel["avg_net_exposure"], hold_ret)

    # --- cost-stress sweep (multipliers from config); 'combined' is the gate cell ---
    sm, wm = cfg["cost_stress"]["spread_mult"], cfg["cost_stress"]["swap_mult"]
    sweep = {}
    for label, s_m, w_m in (("base", 1.0, 1.0), ("spread", sm, 1.0), ("swap", 1.0, wm), ("combined", sm, wm)):
        c = replace(base, spread_mult=s_m, swap_mult=w_m)
        ss = simulate(holdout, d_hold, c, 1.0, eq)["summary"]
        hr = hold_long(holdout, c, eq)["total_return"]
        sweep[label] = round(exposure_adjusted_alpha(ss["total_return"], ss["avg_net_exposure"], hr), 6)

    nb = null_distribution(holdout, d_hold, base, 1.0, eq, runs=int(cfg["null_bench"]["runs"]),
                           method=cfg["null_bench"]["method"], seed=int(cfg["null_bench"]["seed"]),
                           guard_frac=float(cfg["null_bench"]["guard_frac"]))

    gate_metrics = {
        "holdout_alpha": round(holdout_alpha, 6),
        "null_percentile": nb["percentile_rank"],
        "bot_max_drawdown": sel["max_drawdown"],
        "gross_matched_max_drawdown": gross["max_drawdown"],
        "stress_combined_alpha": sweep["combined"],
    }
    acc = phase0_acceptance(gate_metrics, float(cfg["acceptance"]["null_percentile"]))

    holdout_detail = {
        "selected": selected, "hold_return": round(hold_ret, 6),
        "avg_net_exposure": sel["avg_net_exposure"], "avg_gross_exposure": sel["avg_gross_exposure"],
        "gross_matched_f": f_gross, "gross_matched_max_drawdown": gross["max_drawdown"],
    }

    diagnostics = {
        "passive_benchmarks": passive_benchmarks(holdout, base, eq),
        "cost_stress_sweep": sweep,
        "null_block_shuffle": null_distribution(holdout, d_hold, base, 1.0, eq,
                                                runs=int(cfg["null_bench"]["runs"]), method="block_shuffle",
                                                seed=int(cfg["null_bench"]["seed"]),
                                                guard_frac=float(cfg["null_bench"]["guard_frac"]),
                                                block_len=cfg["null_bench"]["block_len"]),  # honor config (None=auto)
        "segmented_full_span": segmented_evaluation(feats, candidate_decisions(feats, selected), base, 1.0, eq),
        "null_circular": nb,
    }

    return {
        "verdict": acc["overall"], "verdict_note": acc["verdict_note"],
        "selection": selection, "candidates": cand_rows,
        "holdout_gate": gate_metrics, "holdout_detail": holdout_detail, "acceptance": acc,
        "diagnostics": diagnostics,
        "window": {"train_bars": len(train), "holdout_bars": len(holdout),
                   "holdout_start": str(holdout["time"].iloc[0]), "holdout_end": str(holdout["time"].iloc[-1])},
    }

def main(config_path: str, *, bars: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    cfg = load_config(config_path)
    if bars is None:
        from bot.forex.oanda_data import load_or_fetch, fetch_candles
        bars = load_or_fetch(cfg["data"], fetch_fn=lambda: fetch_candles(cfg["data"]))
    report = run_phase0(cfg, bars)
    out_dir = Path(cfg["reporting"]["base_dir"]); out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "phase0_evaluation.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"VERDICT: {report['verdict']} — {report['verdict_note']}")
    print(f"selected={report['selection']['selected']} gate={json.dumps(report['holdout_gate'])}")
    return report

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "config/forex_phase0.yaml")
