"""OANDA v20 bid/ask candle client + per-variant CSV cache. The cache/drop-
unclosed-candle structure is adapted from the crypto data layer; the FETCH is
rebuilt for OANDA (not Binance). Credentials come ONLY from the environment and
are never hardcoded, printed, or written to config. Mid prices are derived from
bid/ask via the same `add_mid` the engine uses, so the parsed frame is
engine-ready and internally consistent."""
from __future__ import annotations
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional
import pandas as pd
from bot.forex.indicators import add_mid

PRACTICE_HOST = "https://api-fxpractice.oanda.com"

# Parsed-frame column order (mid_* appended by add_mid). Defined so an empty
# payload still yields a stable, engine-shaped (and cache-shaped) frame.
_BID_ASK_COLS = ["open_time", "time", "bid_o", "bid_h", "bid_l", "bid_c",
                 "ask_o", "ask_h", "ask_l", "ask_c", "volume", "complete"]

def _to_ms(time_str: str) -> int:
    """OANDA times are epoch-seconds (UNIX format, possibly with a ns fraction)
    or RFC3339. Handle both; never silently produce a wrong/zero timestamp."""
    try:
        return int(float(time_str) * 1000)
    except (ValueError, TypeError):
        s = str(time_str).replace("Z", "+00:00")
        if "." in s:                                   # trim over-long ns fraction for fromisoformat
            head, rest = s.split(".", 1)
            tz = ""
            for sign in ("+", "-"):
                if sign in rest:
                    rest, tz = rest.split(sign, 1); tz = sign + tz; break
            s = f"{head}.{rest[:6]}{tz}"
        return int(datetime.fromisoformat(s).timestamp() * 1000)

def parse_candles(payload: Dict[str, Any]) -> pd.DataFrame:
    """OANDA `candles` JSON -> bars frame. Drops still-forming candles
    (complete == False) so a half-formed bar is never cached or traded. Builds
    bid/ask OHLC + mid OHLC and returns rows in ascending open_time. Malformed or
    missing fields raise (KeyError/ValueError) — they are never silently coerced."""
    rows = []
    for c in payload.get("candles", []):
        if not c.get("complete", False):
            continue                                   # never cache a still-forming candle
        ms = _to_ms(c["time"])
        bid, ask = c["bid"], c["ask"]
        rows.append({
            "open_time": ms,
            "time": datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat(timespec="seconds"),
            "bid_o": float(bid["o"]), "bid_h": float(bid["h"]), "bid_l": float(bid["l"]), "bid_c": float(bid["c"]),
            "ask_o": float(ask["o"]), "ask_h": float(ask["h"]), "ask_l": float(ask["l"]), "ask_c": float(ask["c"]),
            "volume": int(c.get("volume", 0)), "complete": True,
        })
    df = pd.DataFrame(rows, columns=_BID_ASK_COLS)     # columns kwarg keeps shape even when rows is empty
    df = add_mid(df)                                   # mid_* = (bid+ask)/2, same derivation as the engine
    return df.sort_values("open_time").reset_index(drop=True)

def _safe(s: Any) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "-", str(s))

def cache_path(data_cfg: Dict[str, Any]) -> Path:
    """Per-variant CSV path: instrument / granularity / price, plus an optional
    date-range component (`from`/`to`/`count`) so different windows never share a
    cache file. Filesystem-safe (RFC3339 colons etc. are sanitized)."""
    d = Path(data_cfg.get("cache_dir", "data/forex_ohlcv/"))
    parts = [data_cfg["instrument"], data_cfg["granularity"], data_cfg.get("price", "BA")]
    rng = "_".join(_safe(data_cfg[k]) for k in ("from", "to", "count")
                   if k in data_cfg and data_cfg[k] is not None)
    if rng:
        parts.append(rng)
    return d / (f"{'__'.join(_safe(p) for p in parts)}.csv")

def load_or_fetch(data_cfg: Dict[str, Any], *,
                  fetch_fn: Optional[Callable[[], pd.DataFrame]] = None) -> pd.DataFrame:
    """Return cached candles if the per-variant CSV exists; otherwise call
    `fetch_fn` exactly once (cache miss), write the CSV, and return it. Raises if
    there is neither a cache nor a fetch_fn/live credentials."""
    path = cache_path(data_cfg)
    if path.exists():
        return pd.read_csv(path)
    if fetch_fn is None:
        raise RuntimeError(f"No cache at {path} and no fetch_fn/live credentials provided.")
    df = fetch_fn()
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return df

def fetch_candles(data_cfg: Dict[str, Any], token: Optional[str] = None,
                  *, session: Any = None) -> pd.DataFrame:
    """Live fetch from OANDA practice, paging backward via `to`/`count`. The API
    token comes from the `token` arg or the OANDA_API_TOKEN env var (never
    hardcoded); a missing token fails clearly BEFORE any network call. Pass a
    `session` to run fully offline in tests. The candles endpoint needs only the
    token — no account id."""
    token = token or os.environ.get("OANDA_API_TOKEN")
    if not token:
        raise RuntimeError("OANDA_API_TOKEN not set; provide it via the environment (never hardcode).")
    sess = session
    if sess is None:
        import requests                                # imported only for a real fetch
        sess = requests.Session()
    sess.headers.update({"Authorization": f"Bearer {token}",
                         "Accept-Datetime-Format": "UNIX"})
    inst = data_cfg["instrument"]; gran = data_cfg["granularity"]
    url = f"{PRACTICE_HOST}/v3/instruments/{inst}/candles"
    frames = []
    to_time = None
    for _ in range(2000):                              # hard page cap
        params = {"granularity": gran, "price": data_cfg.get("price", "BA"), "count": 5000}
        if to_time is not None:
            params["to"] = to_time
        resp = sess.get(url, params=params, timeout=30)
        resp.raise_for_status()
        df = parse_candles(resp.json())
        if df.empty:
            break
        frames.append(df)
        earliest = int(df["open_time"].min())
        new_to = datetime.fromtimestamp(earliest / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        if new_to == to_time or len(df) < 4999:
            break
        to_time = new_to
    if not frames:
        return parse_candles({"candles": []})
    return (pd.concat(frames).drop_duplicates("open_time")
            .sort_values("open_time").reset_index(drop=True))
