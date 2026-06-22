import pytest
from bot.forex.config_schema import validate_phase0_config, ConfigError

def _base():
    return {
        "data": {"instrument": "EUR_USD", "granularity": "H4"},
        "split": {"holdout_frac": 0.35},
        "costs": {"long_swap_pips": 0.5, "short_swap_pips": 0.3, "rollover_hour_utc": 21},
        "cost_stress": {"spread_mult": 1.5, "swap_mult": 2.0},
        "null_bench": {"runs": 1000, "method": "circular_shift"},
        "candidates": ["mom_20", "mom_50", "donchian_50"],
        "acceptance": {"null_percentile": 90},
        "reporting": {"base_dir": "reports/forex/"},
    }

def test_valid_config_passes_and_fills_defaults():
    cfg = validate_phase0_config(_base())
    assert cfg["data"]["instrument"] == "EUR_USD"
    assert cfg["starting_equity"] == 10000.0  # default injected

def test_unknown_top_level_key_raises():
    bad = _base(); bad["leverage"] = 50
    with pytest.raises(ConfigError, match="unknown.*leverage"):
        validate_phase0_config(bad)

def test_unknown_nested_key_raises():
    bad = _base(); bad["null_bench"]["seed_typo"] = 7
    with pytest.raises(ConfigError, match="null_bench.*seed_typo"):
        validate_phase0_config(bad)

def test_bad_candidate_name_raises():
    bad = _base(); bad["candidates"] = ["mom_20", "rsi_14"]
    with pytest.raises(ConfigError, match="rsi_14"):
        validate_phase0_config(bad)
