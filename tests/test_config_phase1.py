import pytest
from bot.forex.config_schema_phase1 import (
    validate_phase1_config, ConfigError, UNIVERSE, VALID_CANDIDATES)

def _base():
    return {
        "universe": list(UNIVERSE),
        "split": {"holdout_frac": 0.35},
        "candidates": ["zscore_20_2.0", "rsi_14_30_70", "boll_20_2.0"],
        "acceptance": {"null_percentile": 90, "min_positive_pairs": 5, "per_pair_floor": -0.10},
    }

def test_valid_config_passes_and_fills_defaults():
    cfg = validate_phase1_config(_base())
    assert cfg["starting_equity"] == 10000.0          # default injected
    assert cfg["max_holding_bars"] == 12
    assert cfg["costs"]["pip_overrides"]["USD_JPY"] == 0.01

def test_universe_locked_to_known_majors():
    assert UNIVERSE == ["EUR_USD", "GBP_USD", "USD_JPY", "USD_CHF",
                        "AUD_USD", "USD_CAD", "NZD_USD"]
    assert VALID_CANDIDATES == {"zscore_20_2.0", "rsi_14_30_70", "boll_20_2.0"}

def test_unknown_top_level_key_raises():
    bad = _base(); bad["leverage"] = 10
    with pytest.raises(ConfigError, match="unknown.*leverage"):
        validate_phase1_config(bad)

def test_unknown_nested_key_raises():
    bad = _base(); bad["acceptance"]["fudge"] = 1
    with pytest.raises(ConfigError, match="acceptance.*fudge"):
        validate_phase1_config(bad)

def test_foreign_pair_rejected():
    bad = _base(); bad["universe"] = ["EUR_USD", "BTC_USD"]
    with pytest.raises(ConfigError, match="BTC_USD"):
        validate_phase1_config(bad)

def test_duplicate_pair_rejected():
    bad = _base(); bad["universe"] = ["EUR_USD", "EUR_USD"]
    with pytest.raises(ConfigError, match="duplicate"):
        validate_phase1_config(bad)

def test_bad_candidate_name_rejected():
    bad = _base(); bad["candidates"] = ["zscore_20_2.0", "mom_20"]
    with pytest.raises(ConfigError, match="mom_20"):
        validate_phase1_config(bad)

def test_holdout_frac_bounds():
    bad = _base(); bad["split"]["holdout_frac"] = 1.5
    with pytest.raises(ConfigError, match="holdout_frac"):
        validate_phase1_config(bad)

def test_per_pair_floor_must_be_nonpositive():
    bad = _base(); bad["acceptance"]["per_pair_floor"] = 0.05
    with pytest.raises(ConfigError, match="per_pair_floor"):
        validate_phase1_config(bad)

def test_min_positive_pairs_within_universe():
    bad = _base(); bad["acceptance"]["min_positive_pairs"] = 9
    with pytest.raises(ConfigError, match="min_positive_pairs"):
        validate_phase1_config(bad)

def test_runs_ge_min_runs():
    bad = _base(); bad["null_bench"] = {"runs": 100, "min_runs": 500}
    with pytest.raises(ConfigError, match="runs"):
        validate_phase1_config(bad)

from pathlib import Path
from bot.forex.config_loader_phase1 import load_phase1_config

def test_committed_yaml_is_locked_pre_registration():
    cfg = load_phase1_config(Path("config/forex_phase1.yaml"))
    assert cfg["universe"] == UNIVERSE                       # all 7 majors, in order
    assert cfg["candidates"] == ["zscore_20_2.0", "rsi_14_30_70", "boll_20_2.0"]
    assert cfg["max_holding_bars"] == 12
    assert cfg["split"]["holdout_frac"] == 0.35
    assert cfg["acceptance"]["min_positive_pairs"] == 5
    assert cfg["acceptance"]["per_pair_floor"] == -0.10
    assert cfg["cost_stress"] == {"spread_mult": 1.5, "swap_mult": 2.0}
