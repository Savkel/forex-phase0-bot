import numpy as np
import pandas as pd
import pytest
from bot.forex.indicators import add_mid
from bot.forex.meanrev_signals import candidate_decisions, CANDIDATES, _run_state_machine

def _bars(closes):
    n = len(closes)
    return add_mid(pd.DataFrame({
        "open_time": np.arange(n) * 14400000, "time": [f"t{i}" for i in range(n)],
        "bid_o": closes, "bid_h": closes, "bid_l": closes, "bid_c": closes,
        "ask_o": closes, "ask_h": closes, "ask_l": closes, "ask_c": closes,
        "volume": [1]*n, "complete": [True]*n}))

def _max_run_nonzero(d):
    best = cur = 0
    for v in d:
        cur = cur + 1 if v != 0 else 0
        best = max(best, cur)
    return best

# ---- locked names / params ----
def test_candidates_constant_is_correct():
    assert CANDIDATES == ["zscore_20_2.0", "rsi_14_30_70", "boll_20_2.0"]

def test_unknown_candidate_name_raises():
    with pytest.raises(ValueError, match="unknown candidate"):
        candidate_decisions(_bars([1.0]*30), "mom_20")

# ---- z-score entries/exits ----
def test_zscore_warmup_is_flat():
    d = candidate_decisions(_bars([1.0]*25 + [1.5] + [1.0]*10), "zscore_20_2.0")
    assert d[:20].tolist() == [0]*20                 # warm-up / flat pre-spike -> no position

def test_zscore_short_entry_then_exit():
    d = candidate_decisions(_bars([1.0]*25 + [1.5] + [1.0]*10), "zscore_20_2.0")
    assert d[25] == -1                               # z >> +2 -> short (fade)
    assert d[26] == 0                                # z back <= 0 -> exit to flat

def test_zscore_long_entry_then_exit():
    d = candidate_decisions(_bars([1.0]*25 + [0.5] + [1.0]*10), "zscore_20_2.0")
    assert d[25] == 1                                # z << -2 -> long (fade)
    assert d[26] == 0                                # revert -> exit to flat

# ---- RSI entries/exits ----
def test_rsi_long_entry_then_exit():
    closes = list(np.linspace(30.0, 6.0, 16)) + [100.0]*10   # 14 losses -> RSI[14]=0 -> long; huge gain -> exit
    d = candidate_decisions(_bars(closes), "rsi_14_30_70").tolist()
    assert d[14] == 1                                # oversold -> long
    exit_bar = next(i for i in range(15, len(d)) if d[i] == 0)
    assert exit_bar < 14 + 12                        # neutral-cross exit BEFORE the max-hold cap
    assert all(v == 1 for v in d[14:exit_bar])       # held long throughout, no flip

def test_rsi_short_entry_then_exit():
    closes = list(np.linspace(6.0, 30.0, 16)) + [1.0]*10     # 14 gains -> RSI[14]=100 -> short; huge loss -> exit
    d = candidate_decisions(_bars(closes), "rsi_14_30_70").tolist()
    assert d[14] == -1                               # overbought -> short
    exit_bar = next(i for i in range(15, len(d)) if d[i] == 0)
    assert exit_bar < 14 + 12
    assert all(v == -1 for v in d[14:exit_bar])

# ---- Bollinger entries/exits ----
def test_bollinger_short_entry_then_exit():
    d = candidate_decisions(_bars([1.0]*25 + [1.4] + [1.0]*12), "boll_20_2.0")
    assert d[25] == -1                               # above upper band -> short
    assert d[26] == 0                                # price back <= mid -> exit to flat

def test_bollinger_long_entry_then_exit():
    d = candidate_decisions(_bars([1.0]*25 + [0.6] + [1.0]*12), "boll_20_2.0")
    assert d[25] == 1                                # below lower band -> long
    assert d[26] == 0                                # price back >= mid -> exit to flat

# ---- cross-cutting candidate invariants ----
def test_max_holding_bars_caps_a_trade_at_12():
    closes = [1.0]*25 + list(np.linspace(1.5, 3.0, 40))      # persistent deviation, never reverts
    d = candidate_decisions(_bars(closes), "zscore_20_2.0")
    assert _max_run_nonzero(d) <= 12

def test_no_direct_flips_for_all_candidates():
    closes = [1.0]*25 + [1.6, 1.0, 0.4, 1.0, 1.6, 0.4]*4
    for name in CANDIDATES:
        d = candidate_decisions(_bars(closes), name)
        for a, b in zip(d[:-1], d[1:]):
            assert not (a == 1 and b == -1), name    # never +1 -> -1 on adjacent bars
            assert not (a == -1 and b == 1), name    # never -1 -> +1 on adjacent bars

def test_flat_series_never_enters_any_candidate():
    for name in CANDIDATES:                          # flat -> all indicators NaN -> no entry
        d = candidate_decisions(_bars([1.0]*40), name)
        assert d.tolist() == [0]*40, name

# ---- exact state-machine semantics (indicator-independent) ----
def test_state_machine_max_hold_offbyone_and_nan_exit_still_caps():
    # exit ALWAYS False (models an indicator that never reverts / is NaN): only max_hold ends it.
    entry = lambda i: 1 if i == 0 else 0
    never_exit = lambda i, side: False
    out = _run_state_machine(8, entry, never_exit, max_hold=3)
    assert out.tolist() == [1, 1, 1, 0, 0, 0, 0, 0]  # held EXACTLY 3 bars (0,1,2), flat at bar 3

def test_state_machine_hold_counter_resets_after_exit():
    entry = lambda i: 1 if i in (0, 4) else 0
    never_exit = lambda i, side: False
    out = _run_state_machine(12, entry, never_exit, max_hold=3)
    assert out.tolist() == [1, 1, 1, 0, 1, 1, 1, 0, 0, 0, 0, 0]  # 2nd trade also lasts exactly 3

def test_state_machine_exit_bar_goes_flat_not_flipped():
    entry = lambda i: 1 if i == 0 else (-1 if i == 2 else 0)  # short condition present at exit bar
    exit_at_2 = lambda i, side: i == 2                        # long exit fires at bar 2
    out = _run_state_machine(5, entry, exit_at_2, max_hold=99)
    assert out.tolist() == [1, 1, 0, 0, 0]           # bar 2 goes FLAT, does not open short

def test_state_machine_flip_requires_a_flat_bar_first():
    entry = lambda i: 1 if i == 0 else (-1 if i >= 2 else 0)  # short wanted from bar 2 on
    exit_once = lambda i, side: i == 2                        # long exits at bar 2 only
    out = _run_state_machine(6, entry, exit_once, max_hold=99)
    assert out.tolist() == [1, 1, 0, -1, -1, -1]     # short opens at bar 3 (one flat bar after exit)

# ---- causality / look-ahead (folded in here per Task-5 scope) ----
def test_decisions_invariant_to_future_bar_mutation():
    closes = list(np.linspace(1.0, 1.2, 60)) + [1.0]*20
    for name in ("zscore_20_2.0", "rsi_14_30_70", "boll_20_2.0"):
        d_full = candidate_decisions(_bars(closes), name).copy()
        closes2 = closes[:50] + [9.9]*(len(closes)-50)       # mutate bars after idx 49
        d_mut = candidate_decisions(_bars(closes2), name)
        assert np.array_equal(d_full[:50], d_mut[:50]), name # earlier decisions unchanged

# ---- scope guard ----
def test_module_imports_no_engine_cost_or_data_layers():
    import inspect
    import bot.forex.meanrev_signals as ms
    src = inspect.getsource(ms)
    for forbidden in ("backtest", "cost_model", "oanda_data", "portfolio", "multipair_data", "simulate"):
        assert forbidden not in src, forbidden      # signals only: no fill/PnL/cost/engine/data code
