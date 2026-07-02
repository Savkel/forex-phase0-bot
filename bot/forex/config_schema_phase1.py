"""Phase 1 config validation. Unknown keys hard-fail (CLAUDE.md §5). Separate
from the Phase 0 schema — Phase 0 is untouched."""
from __future__ import annotations
import copy
from typing import Any, Dict

class ConfigError(ValueError):
    pass

UNIVERSE = ["EUR_USD", "GBP_USD", "USD_JPY", "USD_CHF", "AUD_USD", "USD_CAD", "NZD_USD"]
VALID_CANDIDATES = {"zscore_20_2.0", "rsi_14_30_70", "boll_20_2.0"}

DEFAULTS: Dict[str, Any] = {
    "starting_equity": 10000.0,
    "data": {"granularity": "H4", "price": "BA", "alignment_hour_utc": 0,
             "cache_dir": "data/forex_ohlcv/"},
    "universe": list(UNIVERSE),
    "split": {"holdout_frac": 0.35},
    "costs": {"pip": 0.0001, "pip_overrides": {"USD_JPY": 0.01},
              "long_swap_pips": 0.5, "short_swap_pips": 0.5,
              "rollover_hour_utc": 21, "spread_mult": 1.0, "swap_mult": 1.0},
    "cost_stress": {"spread_mult": 1.5, "swap_mult": 2.0},
    "null_bench": {"runs": 1000, "min_runs": 500, "method": "circular_shift",
                   "block_len": None, "seed": 12345, "guard_frac": 0.02},
    "candidates": ["zscore_20_2.0", "rsi_14_30_70", "boll_20_2.0"],
    "max_holding_bars": 12,
    "acceptance": {"null_percentile": 90, "min_positive_pairs": 5, "per_pair_floor": -0.10},
    "reporting": {"base_dir": "reports/forex/"},
}

_ALLOWED = {
    "_top": set(DEFAULTS.keys()),
    "data": set(DEFAULTS["data"].keys()),
    "split": set(DEFAULTS["split"].keys()),
    "costs": set(DEFAULTS["costs"].keys()),
    "cost_stress": set(DEFAULTS["cost_stress"].keys()),
    "null_bench": set(DEFAULTS["null_bench"].keys()),
    "acceptance": set(DEFAULTS["acceptance"].keys()),
    "reporting": set(DEFAULTS["reporting"].keys()),
}

def _reject_unknown(d: Dict[str, Any], allowed: set, ctx: str) -> None:
    if not isinstance(d, dict):
        raise ConfigError(f"{ctx}: expected a mapping, got {type(d).__name__}")
    unknown = sorted(k for k in d if k not in allowed)
    if unknown:
        raise ConfigError(f"{ctx}: unknown key(s) {unknown}; allowed {sorted(allowed)}")

def _deep_merge(base: Dict[str, Any], over: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out

def validate_phase1_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    merged = _deep_merge(DEFAULTS, cfg or {})
    _reject_unknown(merged, _ALLOWED["_top"], "config")
    for section in ("data", "split", "costs", "cost_stress", "null_bench",
                    "acceptance", "reporting"):
        _reject_unknown(merged[section], _ALLOWED[section], section)

    uni = merged["universe"]
    if not isinstance(uni, list) or not uni:
        raise ConfigError("universe: must be a non-empty list")
    if len(uni) != len(set(uni)):
        raise ConfigError("universe: duplicate pair(s) not allowed")
    foreign = [p for p in uni if p not in set(UNIVERSE)]
    if foreign:
        raise ConfigError(f"universe: unknown pair(s) {foreign}; allowed {UNIVERSE}")

    cands = merged["candidates"]
    if not isinstance(cands, list) or not cands:
        raise ConfigError("candidates: must be a non-empty list")
    badc = [c for c in cands if c not in VALID_CANDIDATES]
    if badc:
        raise ConfigError(f"candidates: unknown {badc}; allowed {sorted(VALID_CANDIDATES)}")

    if not isinstance(merged["costs"]["pip_overrides"], dict):
        raise ConfigError("costs.pip_overrides: must be a mapping pair->pip")

    if not 0.0 < float(merged["split"]["holdout_frac"]) < 1.0:
        raise ConfigError("split.holdout_frac must be in (0,1)")
    if int(merged["max_holding_bars"]) < 1:
        raise ConfigError("max_holding_bars must be >= 1")

    acc = merged["acceptance"]
    if not 0.0 <= float(acc["null_percentile"]) <= 100.0:
        raise ConfigError("acceptance.null_percentile must be in [0,100]")
    if not 1 <= int(acc["min_positive_pairs"]) <= len(uni):
        raise ConfigError(f"acceptance.min_positive_pairs must be in [1,{len(uni)}]")
    if float(acc["per_pair_floor"]) > 0.0:
        raise ConfigError("acceptance.per_pair_floor must be <= 0 (a loss floor)")

    if int(merged["null_bench"]["runs"]) < int(merged["null_bench"]["min_runs"]):
        raise ConfigError("null_bench.runs must be >= null_bench.min_runs")
    if merged["null_bench"]["method"] not in ("circular_shift", "common_shift", "block_shuffle"):
        raise ConfigError("null_bench.method must be circular_shift|common_shift|block_shuffle")
    return merged
