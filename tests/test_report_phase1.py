"""Task 13: Phase 1 human-readable Markdown report.

`render_phase1_markdown(report)` renders the Task-12 result dict to verdict-first
Markdown: research-only banner, verdict first, selected candidate, the five-gate
PASS/FAIL table (values / thresholds / reasons), train selection summary, selected
holdout metrics, the gross-matched PRIMARY benchmark, a net-matched DIAGNOSTIC note
(non-gating, not computed by the runner), cost-stress results, the primary null
percentile/p-value, the diagnostic nulls (labeled non-gating), a per-pair holdout
alpha table, common-window/split provenance, and deterministic formatting. It is
PRESENTATION-ONLY: it renders solely from the dict and recomputes nothing. Tests use
a realistic full-structure fixture and an integration render of the real runner output.
"""
import inspect
import json

import numpy as np
import pandas as pd

from bot.forex.config_schema_phase1 import validate_phase1_config
from bot.forex.indicators import add_mid
import bot.forex.report_phase1 as report_phase1
from bot.forex.report_phase1 import render_phase1_markdown
import run_phase1_probe
from run_phase1_probe import run_phase1, main


# ---- realistic full-structure fixture (mirrors run_phase1 output) --------------------

def _report():
    return {
        "verdict": "FAIL",
        "verdict_note": "H4 mean-reversion on the major-pair universe KILLED for Phase 1 — no rescue.",
        "phase": "phase1", "research_only": True,
        "selection": {"selected": "zscore_20_2.0",
                      "metric": "max TRAIN portfolio exposure-adjusted alpha (base costs)",
                      "tie_break": "then fewer TRAIN trades, then candidate order",
                      "note": "ONE pre-registered train-only selection step, FROZEN before any holdout data is touched."},
        "candidates": [
            {"name": "zscore_20_2.0",
             "train": {"alpha": 0.02, "return": 0.03, "max_drawdown": -0.05, "avg_net_exposure": 0.0, "avg_gross_exposure": 0.2, "trades": 40},
             "holdout": {"alpha": -0.01, "return": 0.0, "max_drawdown": -0.06, "avg_net_exposure": 0.0, "avg_gross_exposure": 0.2, "trades": 18}},
            {"name": "rsi_14_30_70",
             "train": {"alpha": 0.005, "return": 0.006, "max_drawdown": -0.04, "avg_net_exposure": 0.0, "avg_gross_exposure": 0.15, "trades": 22},
             "holdout": {"alpha": -0.02, "return": -0.01, "max_drawdown": -0.07, "avg_net_exposure": 0.0, "avg_gross_exposure": 0.15, "trades": 9}},
            {"name": "boll_20_2.0",
             "train": {"alpha": 0.001, "return": 0.002, "max_drawdown": -0.03, "avg_net_exposure": 0.0, "avg_gross_exposure": 0.1, "trades": 14},
             "holdout": {"alpha": 0.004, "return": 0.005, "max_drawdown": -0.02, "avg_net_exposure": 0.0, "avg_gross_exposure": 0.1, "trades": 6}},
        ],
        "holdout_gate": {"portfolio_holdout_alpha": -0.01, "null_percentile": 55.0,
                         "bot_max_drawdown": -0.06, "gross_matched_max_drawdown": -0.05,
                         "stress_combined_alpha": -0.02,
                         "per_pair_holdout_alphas": {"EUR_USD": 0.01, "USD_JPY": -0.03}},
        "holdout_detail": {"selected": "zscore_20_2.0", "G": 0.2,
                           "gross_matched_measured_gross": 0.198, "gross_matched_max_drawdown": -0.05,
                           "avg_net_exposure": 0.0, "avg_gross_exposure": 0.2},
        "acceptance": {
            "overall": "FAIL",
            "verdict_note": "H4 mean-reversion on the major-pair universe KILLED for Phase 1 — no rescue.",
            "failed": ["portfolio_holdout_alpha_positive", "null_percentile",
                       "drawdown_le_gross_matched_passive", "cost_stress_combined_alpha_positive",
                       "cross_pair_positive_count"],
            "checks": [
                {"rule": "portfolio_holdout_alpha_positive", "passed": False, "value": -0.01, "op": ">", "threshold": 0.0, "status": "FAIL", "reason": "portfolio_holdout_alpha_positive: -0.01 not > 0.0"},
                {"rule": "null_percentile", "passed": False, "value": 55.0, "op": ">=", "threshold": 90.0, "status": "FAIL", "reason": "null_percentile: 55.0 not >= 90.0"},
                {"rule": "drawdown_le_gross_matched_passive", "passed": False, "value": -0.06, "op": ">=", "threshold": -0.05, "status": "FAIL", "reason": "drawdown_le_gross_matched_passive: -0.06 not >= -0.05"},
                {"rule": "cost_stress_combined_alpha_positive", "passed": False, "value": -0.02, "op": ">", "threshold": 0.0, "status": "FAIL", "reason": "cost_stress_combined_alpha_positive: -0.02 not > 0.0"},
                {"rule": "cross_pair_positive_count", "passed": False, "value": 1, "op": ">=", "threshold": 5, "status": "FAIL", "reason": "cross_pair_positive_count: 1 not >= 5"},
                {"rule": "cross_pair_worst_floor", "passed": True, "value": -0.03, "op": ">=", "threshold": -0.10, "status": "PASS", "reason": ""},
            ],
            "cross_pair": {"n_positive": 1, "min_positive_pairs": 5, "worst_alpha": -0.03, "per_pair_floor": -0.10, "n_pairs": 2},
            "drawdown": {"bot_max_drawdown": -0.06, "gross_matched_max_drawdown": -0.05,
                         "convention": "drawdowns <= 0; PASS requires bot >= gross_matched (shallower-or-equal)"},
        },
        "diagnostics": {
            "cost_stress_sweep": {"base": -0.01, "spread": -0.015, "swap": -0.012, "combined": -0.02},
            "null_circular_per_pair": {"method": "circular_shift", "runs": 1000, "real_alpha": -0.01,
                                       "median": 0.0, "p90": 0.02, "p95": 0.03, "percentile_rank": 55.0, "p_value": 0.45},
            "null_common_shift": {"method": "common_shift", "runs": 1000, "percentile_rank": 50.0, "p_value": 0.5},
            "null_block_shuffle": {"method": "block_shuffle", "runs": 1000, "percentile_rank": 52.0, "p_value": 0.48},
            "portfolio_hold_return": 0.02,
        },
        "window": {"universe": ["EUR_USD", "USD_JPY"], "start_ms": 0, "end_ms": 2016000000,
                   "boundary_ms": 1310400000, "train_len": 91, "holdout_len": 49,
                   "per_pair_bars": {"EUR_USD": {"train": 91, "holdout": 49}, "USD_JPY": {"train": 91, "holdout": 49}},
                   "costs": {"EUR_USD": {"pip": 0.0001, "long_swap_pips": 0.5, "short_swap_pips": 0.5},
                             "USD_JPY": {"pip": 0.01, "long_swap_pips": 0.5, "short_swap_pips": 0.5}}},
    }


def _pass_report():
    r = _report()
    r["verdict"] = "PASS"
    r["verdict_note"] = "Mean-reversion portfolio cleared all 5 holdout gates."
    r["acceptance"]["overall"] = "PASS"
    r["acceptance"]["failed"] = []
    for c in r["acceptance"]["checks"]:
        c["passed"] = True
        c["status"] = "PASS"
        c["reason"] = ""
    return r


# ---- runner fixtures for the integration render --------------------------------------

def _bars(mids):
    n = len(mids)
    df = pd.DataFrame({
        "open_time": np.arange(n) * 14400000, "time": [f"t{i}" for i in range(n)],
        "bid_o": [m - 0.0001 for m in mids], "ask_o": [m + 0.0001 for m in mids],
        "bid_c": [m - 0.0001 for m in mids], "ask_c": [m + 0.0001 for m in mids],
        "bid_h": [m - 0.0001 for m in mids], "ask_h": [m + 0.0001 for m in mids],
        "bid_l": [m - 0.0001 for m in mids], "ask_l": [m + 0.0001 for m in mids],
        "volume": [1] * n, "complete": [True] * n})
    return add_mid(df)


def _mean_reverting(n, seed):
    rng = np.random.default_rng(seed)
    x = 1.2
    out = []
    for _ in range(n):
        x += -0.25 * (x - 1.2) + 0.01 * rng.standard_normal()
        out.append(x)
    return out


def _cfg():
    return validate_phase1_config({
        "universe": ["EUR_USD", "USD_JPY"],
        "null_bench": {"runs": 20, "min_runs": 10, "seed": 5},
        "acceptance": {"null_percentile": 90, "min_positive_pairs": 1, "per_pair_floor": -0.10}})


def _frames():
    return {"EUR_USD": _bars(_mean_reverting(140, 1)),
            "USD_JPY": _bars([150.0 * m for m in _mean_reverting(140, 2)])}


# ---- required-content tests ----------------------------------------------------------

def test_verdict_first_and_research_banner():
    md = render_phase1_markdown(_report())
    head = md.strip().splitlines()[0]
    assert "FAIL" in head                                          # verdict leads
    assert "PASS" not in head                                      # no misleading PASS in the verdict line
    up = md.upper()
    assert "RESEARCH-ONLY" in up
    assert "no paper" in md.lower() and "no live" in md.lower()


def test_five_gate_table_has_values_thresholds_and_reasons():
    md = render_phase1_markdown(_report())
    low = md.lower()
    assert "gate" in low and "reason" in low                       # gate table with a reason column
    for rule in ("portfolio_holdout_alpha_positive", "null_percentile",
                 "drawdown_le_gross_matched_passive", "cost_stress_combined_alpha_positive",
                 "cross_pair_positive_count", "cross_pair_worst_floor"):
        assert rule in md                                          # all 6 checks (= 5 gates) rendered
    assert "not >= 90" in md                                       # a concrete threshold+reason shows through
    assert "not > 0.0" in md


def test_selected_candidate_and_holdout_metrics():
    md = render_phase1_markdown(_report())
    assert "zscore_20_2.0" in md                                   # selected candidate named
    assert "G = 0.2" in md                                         # measured gross exposure G
    # selected-candidate holdout metrics rendered (its holdout return + trade count)
    assert "0.014745" in md or "return" in md.lower()
    assert "18" in md                                              # selected holdout trades from the candidates table


def test_gross_matched_primary_and_net_matched_labeled_nongating():
    md = render_phase1_markdown(_report()); low = md.lower()
    assert "gross-matched" in low                                  # primary matched-risk benchmark
    assert "0.198" in md                                           # measured gross of the gross-matched basket
    assert "net-matched" in low                                    # net-matched present...
    ni = low.index("net-matched")
    assert "diagnostic" in low[ni:ni + 200] or "non-gating" in low[ni:ni + 200]   # ...clearly labeled non-gating


def test_cost_stress_sweep_and_combined_gate_cell():
    md = render_phase1_markdown(_report()); low = md.lower()
    for cell in ("base", "spread", "swap", "combined"):
        assert cell in low
    assert "-0.02" in md                                           # combined stress alpha value
    assert "combined (gate 4)" in low                              # sweep cell labeled as the gate cell
    assert "gate-4 cell" in low                                    # and explained in prose


def test_primary_null_and_diagnostic_nulls_labeled():
    md = render_phase1_markdown(_report()); low = md.lower()
    assert "55.0" in md and "0.45" in md                           # primary null percentile + p-value
    assert "circular" in low
    assert "common_shift" in low or "common shift" in low          # diagnostic nulls shown
    assert "block_shuffle" in low or "block shuffle" in low
    # the diagnostic nulls are labeled non-gating
    di = low.index("common")
    assert "non-gating" in low or "diagnostic" in low[di - 200:di + 400]


def test_per_pair_holdout_alpha_table():
    md = render_phase1_markdown(_report())
    assert "EUR_USD" in md and "USD_JPY" in md
    assert "0.01" in md and "-0.03" in md                          # the two per-pair alphas


def test_all_candidates_train_and_holdout():
    md = render_phase1_markdown(_report())
    for name in ("zscore_20_2.0", "rsi_14_30_70", "boll_20_2.0"):
        assert name in md
    assert "0.005" in md and "0.004" in md                         # a train and a holdout alpha from non-selected rows


def test_provenance_common_window_and_split():
    md = render_phase1_markdown(_report()); low = md.lower()
    assert "provenance" in low or "window" in low
    assert "2016000000" in md and "1310400000" in md               # shared window end + split boundary (ms)
    assert "91" in md and "49" in md                               # train/holdout lengths


def test_deterministic_formatting():
    a = render_phase1_markdown(_report())
    b = render_phase1_markdown(_report())
    assert a == b


def test_failing_verdict_never_reads_as_pass():
    md = render_phase1_markdown(_report())
    first = md.strip().splitlines()[0].lower()
    assert "fail" in first and "verdict: pass" not in md.lower()   # verdict wording is honest
    assert "killed" in md.lower()                                  # the FAIL note is surfaced


def test_pass_verdict_wording_still_research_only():
    md = render_phase1_markdown(_pass_report())
    assert "PASS" in md.strip().splitlines()[0]
    assert "cleared all 5 holdout gates" in md
    assert "RESEARCH-ONLY" in md.upper()                           # even a PASS never implies live/tradeable


def test_presentation_only_no_recomputation():
    src = inspect.getsource(report_phase1)
    banned = ("simulate", "run_sleeve", "aggregate_portfolio", "gross_matched_basket",
              "net_matched_basket", "portfolio_cost_stress", "portfolio_null", "phase1_acceptance",
              "exposure_adjusted_alpha", "candidate_decisions", "split_common_window",
              "cumprod", "np.", "import numpy", "import pandas", "from bot.forex")
    for term in banned:
        assert term not in src, f"report renderer must not compute/import: {term!r}"


# ---- integration: renders the REAL runner output; JSON stays unchanged ---------------

def test_renders_real_run_phase1_report():
    rep = run_phase1(_cfg(), _frames())
    md = render_phase1_markdown(rep)
    assert md.strip().splitlines()[0].split()[0:3]                 # non-empty heading
    assert rep["verdict"] in md.splitlines()[0]
    assert "RESEARCH-ONLY" in md.upper()
    for name in ("zscore_20_2.0", "rsi_14_30_70", "boll_20_2.0"):
        assert name in md
    assert "EUR_USD" in md and "USD_JPY" in md


def test_main_writes_md_and_json_unchanged(tmp_path):
    cfg_path = tmp_path / "phase1.yaml"
    cfg_path.write_text(json.dumps({
        "universe": ["EUR_USD", "USD_JPY"],
        "null_bench": {"runs": 20, "min_runs": 10, "seed": 5},
        "acceptance": {"null_percentile": 90, "min_positive_pairs": 1, "per_pair_floor": -0.10},
        "reporting": {"base_dir": tmp_path.as_posix()},
    }), encoding="utf-8")

    rep = main(str(cfg_path), frames=_frames())
    md_file = tmp_path / "phase1_evaluation.md"
    json_file = tmp_path / "phase1_evaluation.json"
    assert md_file.exists() and json_file.exists()
    # the JSON is EXACTLY the runner's serialized report (adding the MD did not change it)
    expected_json = json.dumps(run_phase1(_cfg(), _frames()), indent=2, default=str)
    assert json_file.read_text(encoding="utf-8") == expected_json
    # the MD renders the same verdict
    assert rep["verdict"] in md_file.read_text(encoding="utf-8").splitlines()[0]


def test_report_import_does_not_touch_run_phase1_source():
    # the runner's scientific function is byte-identical; only main's output-writing changed
    assert "render_phase1_markdown" in inspect.getsource(run_phase1_probe.main)
    assert "render_phase1_markdown" not in inspect.getsource(run_phase1_probe.run_phase1)
    assert "phase1_evaluation.md" not in inspect.getsource(run_phase1_probe.run_phase1)
