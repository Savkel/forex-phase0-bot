"""User-run guarded exploratory one-shot. No network or configurable research knobs."""
import argparse
import json
import traceback
import numpy as np

from bot.forex.cftc_positioning_readiness import ROOT, load_prices, write_json, sha, require, readiness
from bot.forex.cftc_positioning_binding import verify, claim, MASK, now


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-one-shot-exploratory', action='store_true', required=True)
    parser.add_argument('--expected-freeze', required=True)
    args = parser.parse_args()
    freeze = verify(args.expected_freeze)
    target = claim()
    write_json(target/'attempt.json', {'status': 'CLAIMED_CONSUMED', 'utc': now(),
                                     'freeze_commit': args.expected_freeze, 'consumption_count': 1})
    try:
        fresh = readiness()
        frozen_mask = json.loads((ROOT/MASK).read_text(encoding='utf-8'))
        require(fresh['mask'] == frozen_mask and
                json.loads(json.dumps(fresh['summary'])) == freeze['sample'],
                'Structural readiness drift; attempt consumed, no economics')
        prices, invalid = load_prices()
        require(not invalid, 'Unexpected invalid price rows')
        from bot.forex.cftc_positioning import economics
        result, ledgers = economics(prices.open_time.to_numpy(), prices.bid_o.to_numpy(),
                                     prices.ask_o.to_numpy(), frozen_mask)
        result.update(freeze_commit=args.expected_freeze, sample=freeze['sample'],
                      excluded_weeks=[r for r in frozen_mask if r['status'] != 'SUPPORTED'])
        for scenario, archive in ledgers.items():
            arrays = {'stamps': archive['stamps']}
            for leg in ('strategy', 'passive'):
                arrays.update({leg+'_'+k: v for k,v in archive[leg].items()})
                write_json(target/f'{scenario}_{leg}_trades.json', archive[leg+'_trades'])
            np.savez_compressed(target/f'{scenario}_ledger.npz', **arrays)
        write_json(target/'result.json', result)
        files = {p.name: sha(p) for p in sorted(target.iterdir()) if p.is_file()}
        write_json(target/'completion.json', {'status': result['status'], 'utc': now(),
                   'freeze_commit': args.expected_freeze, 'consumption_count': 1,
                   'files': files, 'input_bindings': freeze['bindings'], 'exploratory_only': True})
        print(json.dumps({'status': result['status'], 'output': str(target)}))
    except Exception:
        write_json(target/'failure.json', {'status': 'FAILED_ATTEMPT_CONSUMED', 'utc': now(),
                                           'traceback': traceback.format_exc()})
        raise


if __name__ == '__main__':
    main()
