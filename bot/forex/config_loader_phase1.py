"""Load + validate a Phase 1 YAML config."""
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict
import yaml
from bot.forex.config_schema_phase1 import validate_phase1_config, ConfigError

def load_phase1_config(path: str | Path) -> Dict[str, Any]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ConfigError("top-level config must be a mapping")
    return validate_phase1_config(raw)
