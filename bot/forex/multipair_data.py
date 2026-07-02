"""Multi-pair assembly on top of the existing single-instrument data layer.
Reuses oanda_data.load_or_fetch per pair (cache already isolated per instrument,
CLAUDE.md §6). No network in tests: inject fetch_fn_factory. The common-window
train/holdout split is added in Task 3; this module is raw loading only."""
from __future__ import annotations
from typing import Any, Callable, Dict, List, Optional
import pandas as pd
from bot.forex.oanda_data import load_or_fetch

def _pair_data_cfg(data_cfg: Dict[str, Any], pair: str) -> Dict[str, Any]:
    """A per-pair copy of data_cfg with instrument=pair (the source is NOT mutated),
    so load_or_fetch keys its cache on this pair alone -> per-pair cache isolation."""
    d = dict(data_cfg)
    d["instrument"] = pair
    return d

def load_universe(data_cfg: Dict[str, Any], universe: List[str], *,
                  fetch_fn_factory: Optional[Callable[[str, Dict[str, Any]], pd.DataFrame]] = None
                  ) -> Dict[str, pd.DataFrame]:
    """Load every configured pair into a deterministic {pair -> bars DataFrame}
    mapping (keys in universe order), each via its own isolated cache path.
    Raises RuntimeError if a pair has neither a cache nor a fetch_fn (missing
    data), and ValueError if a pair loads but is empty (0 rows). Preserves the
    columns produced by the existing OANDA parser. fetch_fn_factory(pair, pair_cfg)
    -> DataFrame is injected in tests so no OANDA network call ever occurs; a real
    run wires it to oanda_data.fetch_candles."""
    out: Dict[str, pd.DataFrame] = {}
    for pair in universe:
        pcfg = _pair_data_cfg(data_cfg, pair)
        fetch_fn = None
        if fetch_fn_factory is not None:
            fetch_fn = (lambda p=pair, c=pcfg: fetch_fn_factory(p, c))
        frame = load_or_fetch(pcfg, fetch_fn=fetch_fn)
        if frame is None or len(frame) == 0:
            raise ValueError(f"pair {pair!r}: loaded data is empty (0 rows); refusing to proceed")
        out[pair] = frame
    return out
