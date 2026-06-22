"""Load + validate a Phase 0 YAML config."""
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict
import yaml
from bot.forex.config_schema import validate_phase0_config

def load_config(path: str | Path) -> Dict[str, Any]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        from bot.forex.config_schema import ConfigError
        raise ConfigError("top-level config must be a mapping")
    return validate_phase0_config(raw)
