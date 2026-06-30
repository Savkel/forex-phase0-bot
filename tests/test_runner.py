import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from bot.forex.config_schema import validate_phase0_config, ConfigError
from bot.forex.config_loader import load_config
from run_phase0_probe import run_phase0, main, _cost

REPO_ROOT = Path(__file__).resolve().parents[1]


def _frame(mid):
    mid = np.asarray(mid, dtype=float); n = len(mid); half = 0.0001
    return pd.DataFrame({
        # int64 to avoid int32 overflow on Windows (epoch-ms ~1.6e12 exceeds int32)
        "open_time": (np.arange(n, dtype=np.int64) * 14400 + 1_600_000_000) * 1000,
        "time": [f"t{i}" for i in range(n)],
        "bid_o": mid - half, "ask_o": mid + half, "bid_c": mid - half, "ask_c": mid + half,
        "bid_h": mid - half, "ask_h": mid + half, "bid_l": mid - half, "ask_l": mid + half,
        "volume": [1] * n, "complete": [True] * n})


def _bars(n=600, seed=0):
    rng = np.random.default_rng(seed)
    mid = 1.10 + rng.normal(0.0002, 0.004, n).cumsum()       # mild trend + noise
    return _frame(mid)


def _cfg(**over):
    base = {"null_bench": {"runs": 120, "min_runs": 50, "seed": 7}}
    base.update(over)
    return validate_phase0_config(base)


# --- offline full report over all three candidates ---

def test_runner_offline_full_report_all_three_candidates():
    report = run_phase0(_cfg(), _bars())                     # in-memory bars => no data layer / no network
    assert report["verdict"] in ("PASS", "FAIL")
    names = [c["name"] for c in report["candidates"]]
    assert names == ["mom_20", "mom_50", "donchian_50"]      # all three, in pre-registered order
    for c in report["candidates"]:
        assert "train" in c and "holdout" in c
        assert "alpha" in c["train"] and "alpha" in c["holdout"]
    assert report["selection"]["selected"] in names
    assert set(["holdout_alpha", "null_percentile", "bot_max_drawdown",
                "gross_matched_max_drawdown", "stress_combined_alpha"]).issubset(report["holdout_gate"])
    assert report["verdict"] == report["acceptance"]["overall"]


# --- selection is TRAIN-only; holdout never influences it ---

def test_selection_uses_train_alpha_only():
    report = run_phase0(_cfg(), _bars())
    cands = report["candidates"]
    order = [c["name"] for c in cands]
    best = sorted(cands, key=lambda r: (-r["train"]["alpha"], r["train"]["trades"], order.index(r["name"])))[0]["name"]
    assert report["selection"]["selected"] == best          # = argmax TRAIN alpha (tie-break trades, then order)
    assert "train" in report["selection"]["metric"].lower()


def test_holdout_does_not_influence_selection():
    cfg = _cfg()
    bars = _bars(seed=0)
    sel1 = run_phase0(cfg, bars)["selection"]["selected"]
    n = len(bars); cut = int(round(n * (1.0 - cfg["split"]["holdout_frac"])))
    bars2 = bars.copy()
    for col in ("bid_o", "ask_o", "bid_c", "ask_c", "bid_h", "ask_h", "bid_l", "ask_l"):
        bars2.loc[cut:, col] = bars2.loc[cut:, col] * 1.5    # mutate ONLY the holdout region
    sel2 = run_phase0(cfg, bars2)["selection"]["selected"]
    assert sel1 == sel2                                      # train-only selection is unaffected by holdout changes


# --- holdout-only verdict; train cannot rescue a failing holdout ---

def test_holdout_failure_is_not_rescued_by_train():
    n = 600; hf = 0.35; cut = int(round(n * (1.0 - hf)))
    rng = np.random.default_rng(3)
    mid = np.empty(n)
    mid[:cut] = 1.10 + np.linspace(0.0, 0.20, cut) + rng.normal(0, 0.0008, cut)   # real train uptrend
    mid[cut:] = mid[cut - 1]                                                       # FLAT holdout -> cannot clear gates
    report = run_phase0(_cfg(), _frame(mid))
    assert report["verdict"] == "FAIL"
    # the verdict is a pure function of the HOLDOUT gate — recompute it independently
    from bot.forex.acceptance import phase0_acceptance
    independent = phase0_acceptance(report["holdout_gate"], 90.0)
    assert independent["overall"] == report["verdict"] == "FAIL"
    assert report["selection"]["selected"] in [c["name"] for c in report["candidates"]]   # selection still happened


# --- gross-matched drawdown uses the MEASURED avg gross exposure ---

def test_gross_matched_dd_uses_measured_avg_gross_exposure():
    cfg = _cfg()
    report = run_phase0(cfg, _bars())
    hd = report["holdout_detail"]
    assert abs(hd["gross_matched_f"] - (hd["avg_gross_exposure"] or 1.0)) < 1e-12   # measured, not hardcoded
    # recompute matched_gross at that measured exposure and confirm the gate DD matches exactly
    from bot.forex.evaluate import matched_gross
    from bot.forex.indicators import compute_features
    feats = compute_features(_bars(), cfg["candidates"])
    n = len(feats); cut = int(round(n * (1.0 - cfg["split"]["holdout_frac"])))
    holdout = feats.iloc[cut:].reset_index(drop=True)
    g = matched_gross(holdout, _cost(cfg, stress=False), hd["avg_gross_exposure"] or 1.0, float(cfg["starting_equity"]))
    assert abs(report["holdout_gate"]["gross_matched_max_drawdown"] - g["max_drawdown"]) < 1e-12


# --- null benchmark is deterministic under the configured seed ---

def test_null_benchmark_is_deterministic_with_seed():
    cfg = _cfg(); bars = _bars()
    r1 = run_phase0(cfg, bars)
    r2 = run_phase0(cfg, bars)
    assert r1["holdout_gate"] == r2["holdout_gate"]
    assert r1["verdict"] == r2["verdict"]
    assert r1["diagnostics"]["null_circular"] == r2["diagnostics"]["null_circular"]


# --- B3: a configured null_bench.block_len reaches the block-shuffle diagnostic null ---

def test_configured_block_len_reaches_block_shuffle_diagnostic():
    bars = _bars()
    # null_distribution echoes the block length it actually used; a configured value must win
    # over the auto-computed median. Two distinct configured values must produce two distinct
    # reported block lengths — proving the runner forwards the config (not silently ignoring it).
    r_small = run_phase0(_cfg(null_bench={"runs": 120, "min_runs": 50, "seed": 7, "block_len": 3}), bars)
    r_big = run_phase0(_cfg(null_bench={"runs": 120, "min_runs": 50, "seed": 7, "block_len": 9}), bars)
    assert r_small["diagnostics"]["null_block_shuffle"]["block_len"] == 3
    assert r_big["diagnostics"]["null_block_shuffle"]["block_len"] == 9
    # circular-shift GATE ignores block_len (irrelevant there): verdict + gate + circular null unchanged
    assert r_small["holdout_gate"] == r_big["holdout_gate"]
    assert r_small["verdict"] == r_big["verdict"]
    assert r_small["diagnostics"]["null_circular"] == r_big["diagnostics"]["null_circular"]


# --- F2: cost-stress multipliers are RELATIVE to the base cost multipliers ---

def _combined_alpha_at(cfg, bars, spread_mult, swap_mult):
    """Recompute the combined-stress cell EXACTLY as run_phase0 does, but at the given
    absolute multipliers, so a test can pin the effective multipliers the runner used."""
    from dataclasses import replace
    from bot.forex.backtest import simulate
    from bot.forex.evaluate import exposure_adjusted_alpha, hold_long
    from bot.forex.indicators import compute_features
    from bot.forex.signals import candidate_decisions
    feats = compute_features(bars, cfg["candidates"])
    n = len(feats); cut = int(round(n * (1.0 - cfg["split"]["holdout_frac"])))
    holdout = feats.iloc[cut:].reset_index(drop=True)
    selected = run_phase0(cfg, bars)["selection"]["selected"]
    d_hold = candidate_decisions(holdout, selected)
    eq = float(cfg["starting_equity"])
    c = replace(_cost(cfg, stress=False), spread_mult=spread_mult, swap_mult=swap_mult)
    s = simulate(holdout, d_hold, c, 1.0, eq)["summary"]
    hr = hold_long(holdout, c, eq)["total_return"]
    return round(exposure_adjusted_alpha(s["total_return"], s["avg_net_exposure"], hr), 6)


def test_cost_stress_multipliers_are_relative_to_base():
    bars = _bars()
    # non-default base multipliers; swap pips non-zero so the swap channel is actually exercised
    cfg = _cfg(costs={"spread_mult": 2.0, "swap_mult": 2.0, "long_swap_pips": 0.5, "short_swap_pips": 0.5},
               cost_stress={"spread_mult": 1.5, "swap_mult": 1.5})
    combined = run_phase0(cfg, bars)["holdout_gate"]["stress_combined_alpha"]
    # relative scaling => effective multipliers are base(2.0) * stress(1.5) = 3.0, NOT the bare 1.5
    assert combined == _combined_alpha_at(cfg, bars, 3.0, 3.0)
    assert combined != _combined_alpha_at(cfg, bars, 1.5, 1.5)   # the old absolute-override behavior


def test_default_base_multipliers_leave_stress_sweep_unchanged():
    bars = _bars()
    cfg = _cfg()   # default base mult 1.0/1.0; cost_stress 1.5/2.0
    combined = run_phase0(cfg, bars)["holdout_gate"]["stress_combined_alpha"]
    # base 1.0 => relative == absolute; combined still equals the documented default gate cell (1.5, 2.0)
    assert combined == _combined_alpha_at(cfg, bars, 1.5, 2.0)


# --- config goes through the validated loader; unknown keys still fail ---

def test_config_yaml_loads_through_validated_loader():
    cfg = load_config(str(REPO_ROOT / "config" / "forex_phase0.yaml"))
    assert cfg["candidates"] == ["mom_20", "mom_50", "donchian_50"]
    assert cfg["data"]["instrument"] == "EUR_USD" and cfg["data"]["granularity"] == "H4"
    assert cfg["null_bench"]["method"] == "circular_shift"
    assert cfg["starting_equity"] == 10000.0


def test_unknown_config_key_still_fails(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("leverage: 50\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(str(bad))


def test_phase0_yaml_contains_no_secrets():
    text = (REPO_ROOT / "config" / "forex_phase0.yaml").read_text(encoding="utf-8").lower()
    for needle in ("token", "secret", "password", "bearer", "api_key", "account_id"):
        assert needle not in text


# --- main() runs fully offline with injected bars and writes a report ---

def test_main_runs_offline_with_injected_bars(tmp_path, monkeypatch):
    import bot.forex.oanda_data as od
    def _boom(*a, **k):
        raise AssertionError("no network / real OANDA call allowed in tests")
    monkeypatch.setattr(od, "fetch_candles", _boom)         # defensive: prove fetch is never reached
    base = str(tmp_path).replace("\\", "/")
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text(
        "null_bench:\n  runs: 80\n  min_runs: 50\n  seed: 5\n"
        f'reporting:\n  base_dir: "{base}"\n',
        encoding="utf-8")
    report = main(str(cfg_path), bars=_bars())
    assert report["verdict"] in ("PASS", "FAIL")
    assert len(report["candidates"]) == 3
    assert (tmp_path / "phase0_evaluation.json").exists()    # deterministic report written
