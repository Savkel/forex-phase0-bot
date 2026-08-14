"""Metadata-only Stage-A preflight. It never reads candle price columns."""
from __future__ import annotations

import hashlib
import bisect
import json
import subprocess
from pathlib import Path
from typing import Callable, Mapping


PERFORMANCE_KEYS=frozenset({"returns","pnl","rap","sharpe","ic","max_drawdown","stress","loco","verdict"})
BOOTSTRAP_SEED=20260808
BENCHMARK_SEED=20260809
FROZEN_WINDOW=["2023-04-03T00:00:00Z","2026-08-05T00:00:00Z"]
FROZEN_LEGS=("AUD_USD","EUR_HUF","EUR_NOK","EUR_PLN","EUR_SEK","EUR_USD","EUR_ZAR",
             "GBP_USD","NZD_USD","USD_CAD","USD_CHF","USD_CZK","USD_JPY")
FROZEN_SHA256={
    "spec":"8e5cd59ee61335a56d44f508373a8cd6a7970e049e82b5fc91aaf3e2cc5e6c45",
    "universe":"461ac8f864b6e443db6c928ac0554084a2c74f2b685131fca4c7341eb1dbcfd0",
    "mask":"5b1b259d62c6adb7203d0c6dab2439be881e19404fff2a56685b29d6464bb005",
    "readiness":"786aba0dc9db881cfe37d94b9b1f151ac84be9fec9005350917b402f91582dd5",
    "manifest":"163dd0d639bd0b1e33c4717480e5d7ee997b4dcca2c7811b7b9a70e0b64b38e9",
    "financing":"b6cdd250c208b2ec614356d78999e36bd30881a407fed56a1b2a219894569c94",
    "financing_readiness":"978a01f1c2de89754ee8d622177190839b94aa42190152f82b686f2e5425b07b",
}


def _read(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()


def future_output_schema(fingerprints: Mapping[str,str]) -> dict:
    return {"schema_version":1,"mode":"STAGE_A_EXECUTION","fingerprints":dict(fingerprints),
            "bootstrap_seed":BOOTSTRAP_SEED,"benchmark_seed":BENCHMARK_SEED,
            "accounting_scenarios":{"required":["D360","D365"],"independent_paths":True,
                                    "preferred":None,"values":None},
            "transaction_timestamps":{"type":"ordered UTC timestamp array","value":None},
            "gate_definitions":{
                "G1":"PASS independently under D360 and D365",
                "G2":"one-sided 95% stationary-bootstrap lower bound on mean Spearman IC > 0",
                "G3":"signed MDD comparison PASS under D360 and D365",
                "G4":"adverse-corner stressed net total return > 0 under D360 and D365",
                "G5":"all 14 LOCO Gate-1 excesses > 0 under D360 and D365",
            },"gate_results":None,
            "non_gating_sensitivities":{"spread_x3_total_return":{"D360":None,"D365":None}},
            "terminal_verdict":{"allowed":["SURVIVES_KILL_TEST","CLOSED_FAIL","UNDETERMINED"],"value":None}}


def preflight(spec_path: Path, artifacts: Mapping[str,Path], caches: Mapping[str,Path],
              financing_path: Path, output_dir: Path,
              is_ignored: Callable[[Path],bool]) -> dict:
    spec_path=Path(spec_path); u=_read(artifacts["universe"]); m=_read(artifacts["mask"]); r=_read(artifacts["readiness"])
    if not spec_path.is_file() or any(Path(x.get("preregistration", "")) != spec_path for x in (u,m,r)):
        raise ValueError("active preregistration/artifact identity mismatch")
    if u.get("N")!=14 or u.get("k_per_leg")!=4 or "TRY" in u.get("currencies",[]):
        raise ValueError("active universe must be N=14/k=4 with TRY absent")
    legs=r.get("routed_legs",[]); names=[x.get("v20_instrument") for x in legs]
    if r.get("n_routed_legs")!=13 or len(legs)!=13:
        raise ValueError("active readiness must contain 13 legs")
    if tuple(names)!=FROZEN_LEGS:
        raise ValueError("active readiness ordered leg identity mismatch")
    if any(x in names for x in ("EUR_TRY","EUR_GBP")) or (len(legs)>1 and "GBP_USD" not in names):
        raise ValueError("active execution routing mismatch")
    pair_order=u.get("routing_proof",{}).get("pair_order",[])
    if len(legs)>1 and (not u.get("routing_proof",{}).get("verified") or
                        pair_order != [x.get("tms_instrument") for x in legs] or
                        u.get("routes",{}).get("GBP",{}).get("legs") != [["GBPUSD.pro",1]] or
                        "EURGBP.pro" in pair_order):
        raise ValueError("active routing identity/proof mismatch")
    summary=r.get("readiness_summary",{})
    if summary.get("transaction_instants_covered")!=168 or summary.get("transaction_instants_required")!=168 or summary.get("blocked")!=0:
        raise ValueError("168/168 transaction instants are required")
    if (not str(r.get("readiness","")).startswith("PASS") or r.get("granularity")!="H1" or
            r.get("price_field")!="OPEN" or r.get("price_component")!="BA (bid and ask candles)" or
            r.get("alignment")!={"alignmentTimezone":"UTC","dailyAlignment":0} or
            r.get("required_window_utc")!=FROZEN_WINDOW or r.get("validated_range_utc")!=FROZEN_WINDOW):
        raise ValueError("price readiness contract mismatch")
    if summary.get("cache_reused")!=5 or summary.get("newly_fetched")!=8:
        raise ValueError("price readiness provenance-count mismatch")
    for leg in legs:
        name=leg.get("v20_instrument"); expected=leg.get("sha256"); path=Path(caches.get(name,""))
        if not leg.get("h1_ba_coverage_verified") or not expected or not path.is_file() or _sha(path)!=expected:
            raise ValueError(f"missing or invalid readiness hash for {name}")
    if not Path(financing_path).is_file(): raise ValueError("certified financing artifact unavailable")
    if not is_ignored(Path(output_dir) / "future-run.json"):
        raise ValueError("future output location must exist and be gitignored")
    fps={"spec":_sha(spec_path),"universe":_sha(artifacts["universe"]),"mask":_sha(artifacts["mask"]),
         "readiness":_sha(artifacts["readiness"]),"financing":_sha(financing_path)}
    return {"mode":"PREFLIGHT_ONLY","performance_computed":False,"active":True,
            "routed_legs":len(legs),"transaction_instants":"168/168",
            "bootstrap_seed":BOOTSTRAP_SEED,"benchmark_seed":BENCHMARK_SEED,
            "fingerprints":fps,"future_output_schema":future_output_schema(fps)}


def project_preflight(root: Path) -> dict:
    """Validate real frozen metadata, hashes and timestamp availability only."""
    import pandas as pd
    root=Path(root)
    spec=Path("prereg/2026-08-14-tms-carry-no-try-direct-gbp-kill-test-prereg.md")
    artifacts={
        "universe":Path("prereg/2026-08-14-tms-carry-no-try-direct-gbp-universe.json"),
        "mask":Path("prereg/2026-08-14-tms-carry-no-try-direct-gbp-mask.json"),
        "readiness":Path("prereg/2026-08-14-tms-carry-no-try-direct-gbp-price-readiness.json"),
    }
    readiness=_read(root/artifacts["readiness"]); mask=_read(root/artifacts["mask"])
    protected={"spec":root/spec,**{k:root/v for k,v in artifacts.items()},
               "manifest":root/"provenance/tms_swap_manifest.json",
               "financing":root/"data/tms_swap_archive/derived/parsed_all.json",
               "financing_readiness":root/"prereg/2026-08-14-tms-carry-financing-readiness.json"}
    for name,path in protected.items():
        if not path.is_file() or _sha(path)!=FROZEN_SHA256[name]:
            raise ValueError(f"frozen {name} identity mismatch")
    start=pd.Timestamp(readiness["required_window_utc"][0]).value//10**6
    end=pd.Timestamp(readiness["required_window_utc"][1]).value//10**6
    caches={}; timestamp_sets=[]
    for leg in readiness["routed_legs"]:
        name=leg["v20_instrument"]
        path=Path("data/forex_ohlcv")/f"{name}__H1__BA__a0__w{start}-{end}.csv"
        absolute=root/path; header=list(pd.read_csv(absolute,nrows=0).columns)
        if not {"open_time","complete","bid_o","ask_o"}.issubset(header):
            raise ValueError(f"{name}: H1 bid/ask OPEN schema missing")
        meta=pd.read_csv(absolute,usecols=["open_time","complete"])
        complete=meta["complete"].astype(str).str.lower().eq("true")
        timestamp_sets.append(set(meta.loc[complete,"open_time"].astype("int64")))
        caches[name]=absolute
    targets=sorted({pd.Timestamp(x[k]).value//10**6 for x in mask["evaluable_rebalances"]
                    for k in ("decision_utc","hold_end_utc")})
    common=sorted(set.intersection(*timestamp_sets)); delays=[]
    for target in targets:
        i=bisect.bisect_left(common,target)
        if i==len(common) or common[i]-target>48*3_600_000:
            raise ValueError("missing first eligible common transaction timestamp")
        delays.append((common[i]-target)//3_600_000)
    def ignored(path: Path) -> bool:
        proc=subprocess.run(["git","check-ignore","-q",str(path)],cwd=root,check=False)
        return proc.returncode==0
    report=preflight(spec,{k:root/v for k,v in artifacts.items()},caches,
                     root/"data/tms_swap_archive/derived/parsed_all.json",
                     root/"reports/forex/stage_a",ignored)
    if len(targets)!=168:
        raise ValueError(f"frozen mask produced {len(targets)} rather than 168 transaction instants")
    if mask.get("n_evaluable")!=157:
        raise ValueError("frozen mask must contain 157 evaluable rebalances")
    manifest=root/"provenance/tms_swap_manifest.json"
    provenance=_read(manifest); universe=_read(root/artifacts["universe"])
    if provenance.get("index_snapshot_sha256") != universe.get("provenance",{}).get("index_snapshot_sha256"):
        raise ValueError("financing provenance identity mismatch")
    code_paths=[root/"bot/forex/stage_a_carry.py",root/"bot/forex/stage_a_preflight.py",root/"run_stage_a_carry.py"]
    report["fingerprints"]["manifest"]=_sha(manifest)
    report["fingerprints"]["code"] = hashlib.sha256("".join(_sha(p) for p in code_paths).encode()).hexdigest()
    report["future_output_schema"]=future_output_schema(report["fingerprints"])
    report["transaction_instants"]="168/168 first eligible common H1 OPEN metadata"
    report["maximum_delay_hours"]=int(max(delays))
    financing_readiness=_read(protected["financing_readiness"])
    records=financing_readiness.get("records",[])
    record_bytes=(json.dumps(records,sort_keys=True,separators=(",",":"),ensure_ascii=True)+"\n").encode("ascii")
    summary={"potential_calendar_candidates":len(records),
             "potential_held_route_records":sum(int(x[1]).bit_count() for x in records),
             "actual_venue_evidenced_held_pair_events":sum(int(x[2]).bit_count() for x in records),
             "closed_market_no_event_records":sum((int(x[1]) & ~int(x[2])).bit_count() for x in records),
             "events_with_all_required_inputs":sum(int(x[3]).bit_count() for x in records),
             "genuinely_required_missing_input_events":sum((int(x[2]) & ~int(x[3])).bit_count() for x in records)}
    source_paths={"prereg/2026-08-14-tms-carry-no-try-direct-gbp-universe.json":artifacts["universe"],
                  "prereg/2026-08-14-tms-carry-no-try-direct-gbp-mask.json":artifacts["mask"],
                  "prereg/2026-08-14-tms-carry-no-try-direct-gbp-price-readiness.json":artifacts["readiness"],
                  "data/tms_swap_archive/derived/parsed_all.json":Path("data/tms_swap_archive/derived/parsed_all.json")}
    if (hashlib.sha256(record_bytes).hexdigest()!=financing_readiness.get("records_sha256") or
            financing_readiness.get("records_sha256")!="7e93e702816833ba5ed2de7432c1476af576186fb52da462de2e4c48a3f26dbf" or
            summary!=financing_readiness.get("summary") or
            any(financing_readiness.get("source_sha256",{}).get(k)!=_sha(root/v)
                for k,v in source_paths.items()) or summary["genuinely_required_missing_input_events"]!=0):
        raise ValueError("venue-evidenced financing-readiness identity mismatch")
    report["financing_readiness"]={**summary,"records_sha256":financing_readiness["records_sha256"]}
    report["execution_eligible"]=False
    return report
