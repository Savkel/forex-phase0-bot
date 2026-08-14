"""Stage-A entrypoint. Default and currently permitted mode is metadata-only preflight."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from bot.forex.stage_a_orchestration import (Authorization,build_real_input_plan,
                                              execute_real_authorized)


def main(argv=None) -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("mode",nargs="?",choices=("preflight","correction-preflight","execute"),default="preflight")
    parser.add_argument("--authorization-file",type=Path)
    args=parser.parse_args(argv)
    root=Path(__file__).resolve().parent
    if args.mode=="execute" and args.authorization_file is None:
        raise PermissionError("Stage-A performance execution is not authorized without a separate run-bound human authorization file")
    if args.mode=="correction-preflight":
        from bot.forex.stage_a_preflight import project_preflight
        report=project_preflight(root)
        print(json.dumps(report,sort_keys=True))
        return 0
    plan,report=build_real_input_plan(root)
    if args.mode=="execute":
        raw=json.loads(args.authorization_file.read_text(encoding="utf-8"))
        authorization=Authorization(raw["authorization_id"],raw["run_id"],
                                    raw.get("approved") is True,int(raw.get("attempt",1)),
                                    raw.get("execution_manifest_sha256",""),
                                    raw.get("spec_sha256",""),raw.get("implementation_sha256",""),
                                    raw.get("stage_lineage_id",""),
                                    int(raw.get("pre_statistics_defect_count",-1)),
                                    int(raw.get("post_statistics_material_defect_count",-1)),
                                    raw.get("corrected_economic_execution_used") is True,
                                    raw.get("lineage_registry_sha256",""))
        output=execute_real_authorized(root,plan,report,authorization)
        print(json.dumps({"mode":"EXECUTION_COMPLETE","output":str(output)},sort_keys=True))
        return 0
    report={**report,"mode":"PREFLIGHT_ONLY","run_id":plan.run_id,
            "future_output_template":plan.output_template()}
    print(json.dumps(report,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
