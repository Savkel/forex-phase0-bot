"""Bounded, credential-free official CFTC acquisition; never acquires FX prices."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'reports/forex/cftc_positioning/inputs'
FIELDS = ('report_date_as_yyyy_mm_dd', 'cftc_contract_market_code',
          'market_and_exchange_names', 'open_interest_all',
          'lev_money_positions_long', 'lev_money_positions_short')
QUERY = {'$select': ','.join(FIELDS),
         '$where': "cftc_contract_market_code='097741' AND report_date_as_yyyy_mm_dd between '2014-01-07T00:00:00' and '2023-12-19T23:59:59'",
         '$order': 'report_date_as_yyyy_mm_dd', '$limit': '600'}
URL = 'https://publicreporting.cftc.gov/resource/gpe5-46if.json?' + urlencode(QUERY)


def main():
    DEST.mkdir(parents=True, exist_ok=False)
    with urlopen(Request(URL, headers={'User-Agent': 'FX-exploratory-research/1.0'}), timeout=60) as response:
        if urlparse(response.url).hostname != 'publicreporting.cftc.gov':
            raise RuntimeError('Unexpected source redirect')
        raw = response.read(500001)
        meta = {'url': URL, 'final_url': response.url, 'query': QUERY,
                'retrieved_utc': datetime.now(timezone.utc).isoformat(),
                'http_status': response.status, 'headers': dict(response.headers),
                'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
                'dataset': 'CFTC TFF Futures Only gpe5-46if',
                'original_vintage_certified': False}
    (DEST / 'tff_jpy_raw.json').write_bytes(raw)
    (DEST / 'acquisition.json').write_text(json.dumps(meta, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    rows = json.loads(raw)
    if len(raw) > 500000 or len(rows) != 520 or any(set(r) != set(FIELDS) for r in rows):
        raise RuntimeError('Unexpected bounded response; retained for audit, not accepted')
    print(json.dumps({'rows': len(rows), 'sha256': meta['sha256'], 'path': str(DEST)}))


if __name__ == '__main__':
    main()
