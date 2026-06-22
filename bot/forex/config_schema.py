"""Phase 0 config validation. Unknown keys hard-fail (CLAUDE.md §5)."""
from __future__ import annotations
import copy
from typing import Any, Dict

class ConfigError(ValueError):
    pass

VALID_CANDIDATES = {"mom_20", "mom_50", "donchian_50"}

DEFAULTS: Dict[str, Any] = {
    "starting_equity": 10000.0,
    "data": {"instrument": "EUR_USD", "granularity": "H4", "price": "BA",
             "alignment_hour_utc": 0, "cache_dir": "data/forex_ohlcv/"},
    "split": {"holdout_frac": 0.35},
    "costs": {"pip": 0.0001, "long_swap_pips": 0.0, "short_swap_pips": 0.0,
              "rollover_hour_utc": 21, "spread_mult": 1.0, "swap_mult": 1.0},
    "cost_stress": {"spread_mult": 1.5, "swap_mult": 2.0},
    "null_bench": {"runs": 1000, "min_runs": 500, "method": "circular_shift",
                   "block_len": None, "seed": 12345, "guard_frac": 0.02},
    "candidates": ["mom_20", "mom_50", "donchian_50"],
    "acceptance": {"null_percentile": 90},
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

def validate_phase0_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    merged = _deep_merge(DEFAULTS, cfg or {})
    _reject_unknown(merged, _ALLOWED["_top"], "config")
    for section in ("data", "split", "costs", "cost_stress", "null_bench", "acceptance", "reporting"):
        _reject_unknown(merged[section], _ALLOWED[section], section)
    cands = merged["candidates"]
    if not isinstance(cands, list) or not cands:
        raise ConfigError("candidates: must be a non-empty list")
    bad = [c for c in cands if c not in VALID_CANDIDATES]
    if bad:
        raise ConfigError(f"candidates: unknown {bad}; allowed {sorted(VALID_CANDIDATES)}")
    if not 0.0 < float(merged["split"]["holdout_frac"]) < 1.0:
        raise ConfigError("split.holdout_frac must be in (0,1)")
    if int(merged["null_bench"]["runs"]) < int(merged["null_bench"]["min_runs"]):
        raise ConfigError("null_bench.runs must be >= null_bench.min_runs")
    return merged
