import json
from pathlib import Path

import pytest

from bot.forex.stage_a_preflight import PERFORMANCE_KEYS, preflight


def _write(path, obj):
    path.write_text(json.dumps(obj))


def _fixture(tmp_path):
    spec=tmp_path/'active.md'; spec.write_text('locked')
    names=['AUD_USD','EUR_HUF','EUR_NOK','EUR_PLN','EUR_SEK','EUR_USD','EUR_ZAR','GBP_USD','NZD_USD','USD_CAD','USD_CHF','USD_CZK','USD_JPY']
    universe={"preregistration":str(spec),"currencies":["AUD","CAD","CHF","CZK","EUR","GBP","HUF","JPY","NOK","NZD","PLN","SEK","USD","ZAR"],"N":14,"k_per_leg":4,"routes":{"GBP":{"legs":[["GBPUSD.pro",1]]},"USD":{"legs":[]}},"routing_proof":{"pair_order":[x.replace('_','')+'.pro' for x in names],"verified":True},"provenance":{"index_snapshot_sha256":"a"}}
    mask={"preregistration":str(spec),"n_evaluable":157,"evaluable_rebalances":[{"decision_utc":f"d{i}","hold_end_utc":f"h{i}"} for i in range(84)]}
    # 168 deliberately unique synthetic transaction labels
    readiness={"preregistration":str(spec),"n_routed_legs":13,"routed_legs":[],"readiness_summary":{"cache_reused":5,"newly_fetched":8,"transaction_instants_covered":168,"transaction_instants_required":168,"blocked":0},"granularity":"H1","price_component":"BA (bid and ask candles)","price_field":"OPEN","alignment":{"alignmentTimezone":"UTC","dailyAlignment":0},"required_window_utc":["2023-04-03T00:00:00Z","2026-08-05T00:00:00Z"],"validated_range_utc":["2023-04-03T00:00:00Z","2026-08-05T00:00:00Z"],"readiness":"PASS"}
    paths={k:tmp_path/f'{k}.json' for k in ('universe','mask','readiness')}
    for k,v in zip(paths,(universe,mask,readiness)): _write(paths[k],v)
    caches={}
    for name in names:
        cache=tmp_path/f'{name}.csv'; payload=name.encode(); cache.write_bytes(payload); caches[name]=cache
        readiness['routed_legs'].append({'tms_instrument':name.replace('_','')+'.pro','v20_instrument':name,'h1_ba_coverage_verified':True,'sha256':__import__('hashlib').sha256(payload).hexdigest()})
    _write(paths['readiness'],readiness)
    financing=tmp_path/'parsed.json'; financing.write_text('{}')
    output=tmp_path/'outputs'; output.mkdir(exist_ok=True)
    return spec,paths,caches,financing,output


def test_preflight_rejects_missing_leg_hash_and_timestamp(tmp_path):
    spec,paths,caches,financing,output=_fixture(tmp_path)
    for mutation in ('leg','hash','timestamp'):
        d=json.loads(paths['readiness'].read_text())
        if mutation=='leg': d['routed_legs']=[]; d['n_routed_legs']=0
        elif mutation=='hash': d['routed_legs'][0]['sha256']=None
        else: d['readiness_summary']['transaction_instants_covered']=167
        _write(paths['readiness'],d)
        with pytest.raises(ValueError): preflight(spec,paths,caches,financing,output,lambda _:True)
        _fixture(tmp_path)


def test_preflight_is_metadata_only_and_schema_has_no_values(tmp_path):
    spec,paths,caches,financing,output=_fixture(tmp_path)
    report=preflight(spec,paths,caches,financing,output,lambda _:True)
    assert report['mode']=='PREFLIGHT_ONLY' and report['performance_computed'] is False
    assert not PERFORMANCE_KEYS.intersection(report)
    assert report['future_output_schema']['terminal_verdict']['value'] is None


def test_explicit_execute_mode_is_denied_without_future_approval():
    from run_stage_a_carry import main
    with pytest.raises(PermissionError,match='not authorized'):
        main(['execute'])


def test_preflight_rejects_execution_violations(tmp_path):
    spec,paths,caches,financing,output=_fixture(tmp_path)
    d=json.loads(paths['universe'].read_text()); d['currencies'].append('TRY'); _write(paths['universe'],d)
    with pytest.raises(ValueError,match='TRY'): preflight(spec,paths,caches,financing,output,lambda _:True)


@pytest.mark.parametrize("artifact,mutation",[
    ("universe",lambda d:d["routes"].update({"GBP":{"legs":[["EURGBP.pro",-1],["EURUSD.pro",1]]}})),
    ("readiness",lambda d:d.update({"alignment":{"alignmentTimezone":"Europe/London","dailyAlignment":0}})),
    ("readiness",lambda d:d.update({"price_component":"M"})),
    ("readiness",lambda d:d.update({"required_window_utc":["wrong","window"]})),
])
def test_preflight_rejects_frozen_identity_semantic_changes(tmp_path,artifact,mutation):
    spec,paths,caches,financing,output=_fixture(tmp_path)
    d=json.loads(paths[artifact].read_text()); mutation(d); _write(paths[artifact],d)
    with pytest.raises(ValueError): preflight(spec,paths,caches,financing,output,lambda _:True)
