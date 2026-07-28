"""Task 12: Phase 1 deliver loop (`run_phase1_probe`).

Orchestration ONLY — wires already-tested components: config -> 7-pair load ->
common-calendar split -> 3 candidate decisions -> TRAIN-only selection (locked
ranking/tie-break) -> holdout-only 5-gate verdict for the SELECTED candidate ->
deterministic verdict-first JSON. Tests prove: exact orchestration order;
train-only + deterministic tie-breaks; holdout never influences selection; the
selected candidate flows through every holdout component; all five gate inputs are
wired; the PRIMARY null (only) feeds Gate 2 and diagnostics cannot move the
verdict; deterministic JSON schema; a failing verdict never emits a misleading
PASS; and no scientific primitive is re-implemented in the runner. All offline
(frames injected; no network, no orders).
"""
import json
import inspect

import numpy as np
import pandas as pd
import pytest

from bot.forex.config_schema_phase1 import validate_phase1_config
from bot.forex.multipair_data import split_common_window
from bot.forex.meanrev_signals import candidate_decisions
from bot.forex.indicators import add_mid
import run_phase1_probe
from run_phase1_probe import run_phase1, main, _select, _cost_by_pair, _per_pair_holdout_alphas


# ---- fixtures ------------------------------------------------------------------------

def _bars(mids):
    # mid columns are added exactly as the data layer (parse_candles -> add_mid) does, so
    # the frame matches what a parsed OANDA frame looks like when it reaches run_phase1.
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
        x += -0.25 * (x - 1.2) + 0.01 * rng.standard_normal()   # AR(1) toward 1.2
        out.append(x)
    return out


def _cfg():
    return validate_phase1_config({
        "universe": ["EUR_USD", "USD_JPY"],
        "null_bench": {"runs": 30, "min_runs": 10, "seed": 5},
        "acceptance": {"null_percentile": 90, "min_positive_pairs": 1, "per_pair_floor": -0.10},
    })


def _frames():
    return {"EUR_USD": _bars(_mean_reverting(140, 1)),
            "USD_JPY": _bars([150.0 * m for m in _mean_reverting(140, 2)])}


_ALL_CANDIDATES = {"zscore_20_2.0", "rsi_14_30_70", "boll_20_2.0"}


def _fake_acceptance(overall="FAIL"):
    def _f(m, **kw):
        return {"overall": overall, "verdict_note": f"stub {overall}", "failed": [] if overall == "PASS" else ["x"],
                "checks": [], "cross_pair": {}, "drawdown": {}}
    return _f


# ---- plan-verbatim shape / verdict / selection ---------------------------------------

def test_run_phase1_report_shape_and_verdict():
    rep = run_phase1(_cfg(), _frames())
    assert rep["verdict"] in ("PASS", "FAIL")
    assert rep["phase"] == "phase1" and rep["research_only"] is True
    names = {c["name"] for c in rep["candidates"]}
    assert names == _ALL_CANDIDATES                                  # all three reported (train AND holdout)
    for c in rep["candidates"]:
        assert set(c) >= {"name", "train", "holdout"}
    assert rep["selection"]["selected"] in names
    assert "G" in rep["holdout_detail"]
    assert set(rep["holdout_gate"]["per_pair_holdout_alphas"]) == {"EUR_USD", "USD_JPY"}


def test_selected_candidate_drives_the_gate():
    rep = run_phase1(_cfg(), _frames())
    assert rep["acceptance"]["overall"] == rep["verdict"]            # verdict mirrors the single acceptance call


# ---- 1) exact orchestration order ----------------------------------------------------

def test_orchestration_order(monkeypatch):
    events = []

    def rec(label, fn):
        def w(*a, **k):
            events.append(label)
            return fn(*a, **k)
        return w

    monkeypatch.setattr(run_phase1_probe, "split_common_window", rec("split", run_phase1_probe.split_common_window))
    monkeypatch.setattr(run_phase1_probe, "_select", rec("select", run_phase1_probe._select))
    monkeypatch.setattr(run_phase1_probe, "gross_matched_basket", rec("gross_matched", run_phase1_probe.gross_matched_basket))
    monkeypatch.setattr(run_phase1_probe, "portfolio_cost_stress", rec("cost_stress", run_phase1_probe.portfolio_cost_stress))
    monkeypatch.setattr(run_phase1_probe, "portfolio_null", rec("null", run_phase1_probe.portfolio_null))
    monkeypatch.setattr(run_phase1_probe, "phase1_acceptance", rec("accept", run_phase1_probe.phase1_acceptance))

    run_phase1(_cfg(), _frames())

    assert events[0] == "split"                                     # load/split precedes everything
    assert events.count("select") == 1                             # exactly ONE selection step
    assert events.count("accept") == 1                             # exactly ONE verdict
    assert events.count("gross_matched") == 1                      # exactly ONE gross-matched (selected only)
    assert events.count("cost_stress") == 1                        # exactly ONE stress sweep (selected only)
    i_sel, i_acc = events.index("select"), events.index("accept")
    assert events.index("split") < i_sel < i_acc
    # holdout-verdict components run AFTER selection is frozen and BEFORE the gate
    assert i_sel < events.index("gross_matched") < i_acc
    assert i_sel < events.index("cost_stress") < i_acc
    null_idx = [i for i, e in enumerate(events) if e == "null"]
    assert len(null_idx) == 3                                       # primary + 2 diagnostics
    assert sum(1 for i in null_idx if i < i_acc) == 1              # ONLY the primary null precedes the verdict
    assert sum(1 for i in null_idx if i > i_acc) == 2              # both diagnostics are computed AFTER the verdict


# ---- 2) train-only selection + deterministic tie-breaks ------------------------------

def test_selection_is_train_only_and_deterministic():
    a = run_phase1(_cfg(), _frames())
    b = run_phase1(_cfg(), _frames())
    assert a["selection"]["selected"] == b["selection"]["selected"]
    assert a["verdict"] == b["verdict"]
    assert "TRAIN" in a["selection"]["metric"].upper()


def _row(name, tr_alpha, tr_trades, ho_alpha=0.0):
    keys = ("return", "max_drawdown", "avg_net_exposure", "avg_gross_exposure")
    return {"name": name,
            "train": dict({"alpha": tr_alpha, "trades": tr_trades}, **{k: 0.0 for k in keys}),
            "holdout": dict({"alpha": ho_alpha, "trades": 0}, **{k: 0.0 for k in keys})}


def test_select_ranking_and_tie_breaks():
    order = ["zscore_20_2.0", "rsi_14_30_70", "boll_20_2.0"]
    # (a) highest TRAIN alpha wins, regardless of a much larger HOLDOUT alpha on a loser
    rows = [_row("zscore_20_2.0", 0.01, 5, ho_alpha=9.9),
            _row("rsi_14_30_70", 0.05, 5, ho_alpha=-9.9),
            _row("boll_20_2.0", 0.02, 5, ho_alpha=9.9)]
    assert _select(rows, order) == "rsi_14_30_70"
    # (b) tie on TRAIN alpha -> fewer TRAIN trades wins
    rows = [_row("zscore_20_2.0", 0.05, 9), _row("rsi_14_30_70", 0.05, 3), _row("boll_20_2.0", 0.05, 7)]
    assert _select(rows, order) == "rsi_14_30_70"
    # (c) tie on alpha AND trades -> earliest candidate order wins
    rows = [_row("boll_20_2.0", 0.05, 4), _row("rsi_14_30_70", 0.05, 4), _row("zscore_20_2.0", 0.05, 4)]
    assert _select(rows, order) == "zscore_20_2.0"


def test_select_ignores_holdout_block():
    # _select must SUBSCRIPT only the `train` block; a `["holdout"]` read would be a leak
    # (docstring prose may still mention holdout — the guard checks executable references)
    src = inspect.getsource(_select)
    assert '["train"]' in src and '["holdout"]' not in src


# ---- 3) holdout is untouched until selection is frozen -------------------------------

def test_select_receives_train_only_records(monkeypatch):
    captured = {}
    real = run_phase1_probe._select

    def spy(rows, order):
        captured["rows"] = [dict(r) for r in rows]
        return real(rows, order)

    monkeypatch.setattr(run_phase1_probe, "_select", spy)
    rep = run_phase1(_cfg(), _frames())
    # every selection record is TRAIN-ONLY: a `train` block and NO holdout field at all
    for r in captured["rows"]:
        assert set(r.keys()) == {"name", "train"}
        assert "holdout" not in r
    # and the frozen pick is reproducible from the train blocks alone
    order = list(_cfg()["candidates"])
    train_pick = sorted(captured["rows"],
                        key=lambda r: (-r["train"]["alpha"], r["train"]["trades"], order.index(r["name"])))[0]["name"]
    assert rep["selection"]["selected"] == train_pick


def test_no_holdout_access_before_selection(monkeypatch):
    # no holdout frame/decision/metric may be TOUCHED before `_select` completes
    events = []
    holder = {}
    real_split = run_phase1_probe.split_common_window

    def spy_split(frames, frac):
        out = real_split(frames, frac)
        holder["train"], holder["holdout"] = out["train"], out["holdout"]
        return out

    def _tag(frames):
        if frames is holder.get("holdout"):
            return "holdout"
        if frames is holder.get("train"):
            return "train"
        return "other"

    real_pm = run_phase1_probe._portfolio_metrics
    real_dec = run_phase1_probe._decisions
    real_sel = run_phase1_probe._select

    def spy_pm(frames, dec, cbp, eq):
        events.append(("pm", _tag(frames)))
        return real_pm(frames, dec, cbp, eq)

    def spy_dec(frames, name, max_hold):
        events.append(("dec", _tag(frames)))
        return real_dec(frames, name, max_hold)

    def spy_sel(rows, order):
        events.append(("select", None))
        return real_sel(rows, order)

    monkeypatch.setattr(run_phase1_probe, "split_common_window", spy_split)
    monkeypatch.setattr(run_phase1_probe, "_portfolio_metrics", spy_pm)
    monkeypatch.setattr(run_phase1_probe, "_decisions", spy_dec)
    monkeypatch.setattr(run_phase1_probe, "_select", spy_sel)
    run_phase1(_cfg(), _frames())

    sel_i = next(i for i, e in enumerate(events) if e[0] == "select")
    assert all(tag != "holdout" for _, tag in events[:sel_i])                 # nothing holdout before the freeze
    assert all(tag == "train" for kind, tag in events[:sel_i] if kind in ("pm", "dec"))
    assert any(e == ("pm", "holdout") for e in events[sel_i + 1:])            # selected holdout evaluated AFTER


def test_nonselected_holdout_cannot_alter_selection_or_verdict(monkeypatch):
    base = run_phase1(_cfg(), _frames())
    selected0, verdict0 = base["selection"]["selected"], base["verdict"]
    base_rows = {c["name"]: c["holdout"] for c in base["candidates"]}

    holder = {}
    fired = {"n": 0}
    real_split = run_phase1_probe.split_common_window
    real_dec = run_phase1_probe._decisions

    def spy_split(frames, frac):
        out = real_split(frames, frac)
        holder["holdout"] = out["holdout"]
        return out

    def corrupt_nonselected(frames, name, max_hold):
        d = real_dec(frames, name, max_hold)
        if frames is holder.get("holdout") and name != selected0:
            fired["n"] += 1
            return {p: np.zeros_like(v) for p, v in d.items()}               # flatten non-selected holdout decisions
        return d

    monkeypatch.setattr(run_phase1_probe, "split_common_window", spy_split)
    monkeypatch.setattr(run_phase1_probe, "_decisions", corrupt_nonselected)
    rep = run_phase1(_cfg(), _frames())
    new_rows = {c["name"]: c["holdout"] for c in rep["candidates"]}

    nonsel = [name for name in base_rows if name != selected0]
    assert fired["n"] >= 1                                                    # the corruption path really ran
    assert rep["selection"]["selected"] == selected0                         # selection unchanged
    assert rep["verdict"] == verdict0                                        # verdict unchanged
    for n in nonsel:
        assert new_rows[n]["trades"] == 0                                    # flattened decisions reached each report row
    assert any(new_rows[n] != base_rows[n] for n in nonsel)                  # >=1 non-selected report row genuinely changed
    assert new_rows[selected0] == base_rows[selected0]                       # ...but the SELECTED row is untouched


# ---- 4) selected candidate flows through all holdout components -----------------------

def test_selected_candidate_flows_through_holdout_components(monkeypatch):
    captured = {}
    real_cs = run_phase1_probe.portfolio_cost_stress

    def spy_cs(frames, dec, cbp, sm, wm, weights=None, eq=10000.0):
        captured["cost_stress"] = {p: np.asarray(dec[p]).copy() for p in dec}
        return real_cs(frames, dec, cbp, sm, wm, weights, eq)

    real_gm = run_phase1_probe.gross_matched_basket

    def spy_gm(frames, cbp, G, weights=None, eq=10000.0):
        captured["gm_frames"] = list(frames.keys())
        return real_gm(frames, cbp, G, weights, eq)

    real_null = run_phase1_probe.portfolio_null

    def spy_null(frames, dec, cbp, weights=None, *, method="circular_shift", **kw):
        if method == "circular_shift":
            captured["primary_null"] = {p: np.asarray(dec[p]).copy() for p in dec}
        return real_null(frames, dec, cbp, weights, method=method, **kw)

    monkeypatch.setattr(run_phase1_probe, "portfolio_cost_stress", spy_cs)
    monkeypatch.setattr(run_phase1_probe, "gross_matched_basket", spy_gm)
    monkeypatch.setattr(run_phase1_probe, "portfolio_null", spy_null)

    cfg, frames = _cfg(), _frames()
    rep = run_phase1(cfg, frames)
    selected = rep["selection"]["selected"]
    holdout = split_common_window(frames, cfg["split"]["holdout_frac"])["holdout"]
    max_hold = int(cfg["max_holding_bars"])
    sel_dec = {p: candidate_decisions(holdout[p], selected, max_hold) for p in holdout}
    for p in holdout:
        assert np.array_equal(captured["cost_stress"][p], sel_dec[p])   # stress runs the SELECTED holdout decisions
        assert np.array_equal(captured["primary_null"][p], sel_dec[p])  # primary null runs the SELECTED holdout decisions
    assert captured["gm_frames"] == list(holdout.keys())               # gross-matched runs the SAME holdout universe
    # Gate 5's per-pair table is exactly the SELECTED candidate's holdout alphas (no other candidate leaks in)
    cbp = _cost_by_pair(cfg["costs"], list(holdout.keys()))
    exp_pp = _per_pair_holdout_alphas(holdout, sel_dec, cbp, float(cfg["starting_equity"]))
    assert rep["holdout_gate"]["per_pair_holdout_alphas"] == exp_pp


# ---- 5) all five gate inputs are wired correctly -------------------------------------

def test_gate_inputs_are_wired(monkeypatch):
    captured = {}
    real = run_phase1_probe.phase1_acceptance

    def spy(m, **kw):
        captured["m"] = dict(m)
        captured["kw"] = dict(kw)
        return real(m, **kw)

    monkeypatch.setattr(run_phase1_probe, "phase1_acceptance", spy)
    cfg = _cfg()
    rep = run_phase1(cfg, _frames())
    m = captured["m"]
    assert set(m) == {"portfolio_holdout_alpha", "null_percentile", "bot_max_drawdown",
                      "gross_matched_max_drawdown", "stress_combined_alpha", "per_pair_holdout_alphas"}
    # each gate input traces to the reported holdout numbers of the SELECTED candidate
    assert m["portfolio_holdout_alpha"] == rep["holdout_gate"]["portfolio_holdout_alpha"]
    assert m["null_percentile"] == rep["diagnostics"]["null_circular_per_pair"]["percentile_rank"]   # PRIMARY null
    assert m["gross_matched_max_drawdown"] == rep["holdout_detail"]["gross_matched_max_drawdown"]     # gross-matched (Gate 3)
    assert m["stress_combined_alpha"] == rep["diagnostics"]["cost_stress_sweep"]["combined"]
    assert set(m["per_pair_holdout_alphas"]) == set(rep["window"]["universe"])
    # gate thresholds come from the locked acceptance config, not hardcoded
    assert captured["kw"]["null_percentile_gate"] == float(cfg["acceptance"]["null_percentile"])
    assert captured["kw"]["min_positive_pairs"] == int(cfg["acceptance"]["min_positive_pairs"])
    assert captured["kw"]["per_pair_floor"] == float(cfg["acceptance"]["per_pair_floor"])


def test_gross_matched_is_gate3_net_matched_absent():
    # gross-matched drives Gate 3; net-matched is never computed by the runner
    rep = run_phase1(_cfg(), _frames())
    assert "gross_matched_max_drawdown" in rep["holdout_gate"]
    assert "net_matched" not in json.dumps(rep["holdout_gate"])
    assert "net_matched" not in inspect.getsource(run_phase1_probe)


# ---- 6) the PRIMARY null (only) feeds Gate 2; diagnostics cannot alter the verdict ----

def test_primary_null_only_feeds_gate2(monkeypatch):
    captured = {}
    real_acc = run_phase1_probe.phase1_acceptance

    def spy_acc(m, **kw):
        captured["m"] = dict(m)
        return real_acc(m, **kw)

    def fake_null(frames, dec, cbp, weights=None, *, method="circular_shift", **kw):
        pct = {"circular_shift": 95.0, "common_shift": 3.0, "block_shuffle": 4.0}[method]
        return {"method": method, "runs": int(kw.get("runs", 0)), "real_alpha": 0.0,
                "median": 0.0, "p90": 0.0, "p95": 0.0, "percentile_rank": pct, "p_value": 1.0}

    monkeypatch.setattr(run_phase1_probe, "phase1_acceptance", spy_acc)
    monkeypatch.setattr(run_phase1_probe, "portfolio_null", fake_null)
    rep = run_phase1(_cfg(), _frames())
    assert captured["m"]["null_percentile"] == 95.0                          # gate 2 reads the PRIMARY sentinel
    assert rep["diagnostics"]["null_common_shift"]["percentile_rank"] == 3.0  # diagnostics computed...
    assert rep["diagnostics"]["null_block_shuffle"]["percentile_rank"] == 4.0 # ...but never fed to the gate


def test_diagnostics_cannot_alter_verdict(monkeypatch):
    baseline = run_phase1(_cfg(), _frames())["verdict"]
    real_null = run_phase1_probe.portfolio_null

    def corrupt_diagnostics(frames, dec, cbp, weights=None, *, method="circular_shift", **kw):
        if method == "circular_shift":
            return real_null(frames, dec, cbp, weights, method=method, **kw)     # primary untouched
        return {"method": method, "runs": 0, "real_alpha": 0.0, "median": 0.0, "p90": 0.0,
                "p95": 0.0, "percentile_rank": 999.0, "p_value": 0.0}             # absurd diagnostics

    monkeypatch.setattr(run_phase1_probe, "portfolio_null", corrupt_diagnostics)
    assert run_phase1(_cfg(), _frames())["verdict"] == baseline


# ---- 7) deterministic JSON schema / output -------------------------------------------

def test_report_is_verdict_first_and_json_roundtrips():
    rep = run_phase1(_cfg(), _frames())
    assert next(iter(rep)) == "verdict"                             # verdict-first
    assert set(rep) >= {"verdict", "verdict_note", "phase", "research_only", "selection",
                        "candidates", "holdout_gate", "holdout_detail", "acceptance",
                        "diagnostics", "window"}
    loaded = json.loads(json.dumps(rep, default=str))              # fully serializable
    assert loaded["verdict"] == rep["verdict"]


def test_full_report_is_deterministic():
    a = run_phase1(_cfg(), _frames())
    b = run_phase1(_cfg(), _frames())
    assert json.dumps(a, default=str, sort_keys=True) == json.dumps(b, default=str, sort_keys=True)


# ---- 8) failures do not emit a misleading PASS report --------------------------------

def test_failing_gate_reports_fail_not_pass(monkeypatch):
    monkeypatch.setattr(run_phase1_probe, "phase1_acceptance", _fake_acceptance("FAIL"))
    rep = run_phase1(_cfg(), _frames())
    assert rep["verdict"] == "FAIL"
    assert rep["acceptance"]["overall"] == "FAIL"
    assert rep["verdict"] == rep["acceptance"]["overall"]          # verdict can never diverge upward to PASS
    # full provenance is still present on a failing verdict (no blanked report)
    assert len(rep["candidates"]) == 3 and rep["holdout_gate"]["per_pair_holdout_alphas"]


def test_acceptance_error_propagates_no_pass_report(monkeypatch):
    def boom(m, **kw):
        raise ValueError("malformed gate metric")
    monkeypatch.setattr(run_phase1_probe, "phase1_acceptance", boom)
    with pytest.raises(ValueError, match="malformed"):
        run_phase1(_cfg(), _frames())                              # must raise, never fabricate a PASS


# ---- 9) no duplicated scientific logic; no orders; injected data ---------------------

def test_no_duplicated_scientific_logic_in_runner():
    src = inspect.getsource(run_phase1_probe)
    banned = ("cumprod", "ask_o", "bid_o", "mid_o", "spread_frac", "swap_frac", "np.roll",
              ".rolling(", "def simulate", "def exposure_adjusted_alpha", "def max_drawdown",
              "def zscore", "def wilder_rsi", "def bollinger", "Trade(",
              "place_order", "market_order", "create_order")
    for term in banned:
        assert term not in src, f"runner must not re-implement/duplicate: {term!r}"
    # it must WIRE the tested modules, not reinvent them
    for imp in ("from bot.forex.portfolio import", "from bot.forex.acceptance_phase1 import phase1_acceptance",
                "from bot.forex.backtest import simulate", "from bot.forex.multipair_data import split_common_window"):
        assert imp in src


def test_main_writes_report_offline(tmp_path):
    cfg_path = tmp_path / "phase1.yaml"
    cfg_path.write_text(json.dumps({                               # JSON is valid YAML; safe_load parses it
        "universe": ["EUR_USD", "USD_JPY"],
        "null_bench": {"runs": 20, "min_runs": 10, "seed": 5},
        "acceptance": {"null_percentile": 90, "min_positive_pairs": 1, "per_pair_floor": -0.10},
        "reporting": {"base_dir": tmp_path.as_posix()},
    }), encoding="utf-8")
    rep = main(str(cfg_path), frames=_frames())                   # frames injected -> no network, no fetch import
    out = tmp_path / "phase1_evaluation.json"
    assert out.exists()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["verdict"] == rep["verdict"] and loaded["phase"] == "phase1"
