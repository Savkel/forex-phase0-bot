"""Task 2a: direct tests for load_config() over a real temporary YAML file.

Exercises the YAML parse path end-to-end: parsing, defaults layering, the
reject-unknown-keys guard, and the `null_bench` section naming (and why a bare
`null:` key — a YAML reserved word — must be rejected)."""
import pytest

from bot.forex.config_loader import load_config
from bot.forex.config_schema import ConfigError


def _write(tmp_path, text):
    p = tmp_path / "cfg.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_load_config_parses_yaml_and_layers_defaults(tmp_path):
    p = _write(tmp_path, """
data:
  instrument: EUR_USD
  granularity: H4
split:
  holdout_frac: 0.30
null_bench:
  runs: 800
  min_runs: 400
""")
    cfg = load_config(p)
    # 1. YAML parsed correctly (values from the file)
    assert cfg["data"]["instrument"] == "EUR_USD"
    assert cfg["split"]["holdout_frac"] == 0.30
    assert cfg["null_bench"]["runs"] == 800
    # 2. defaults layering still works (keys absent from the YAML come from DEFAULTS)
    assert cfg["starting_equity"] == 10000.0
    assert cfg["data"]["price"] == "BA"
    assert cfg["null_bench"]["method"] == "circular_shift"
    # 4. null_bench is the section key, and there is no None/`null` key
    assert "null_bench" in cfg
    assert None not in cfg


def test_load_config_rejects_unknown_key_through_yaml(tmp_path):
    # 3. reject-unknown-keys is enforced through the YAML path, not bypassed by it
    p = _write(tmp_path, """
data:
  instrument: EUR_USD
leverage: 50
""")
    with pytest.raises(ConfigError, match="leverage"):
        load_config(p)


def test_load_config_bare_null_key_is_rejected(tmp_path):
    # `null:` is a YAML reserved word -> parses to a Python None key -> must be
    # rejected by reject-unknown. This is exactly why the section is `null_bench`.
    p = _write(tmp_path, """
null:
  runs: 100
""")
    with pytest.raises(ConfigError):
        load_config(p)
