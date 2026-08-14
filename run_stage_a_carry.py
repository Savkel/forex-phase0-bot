"""Stage-A entrypoint. Default and currently permitted mode is metadata-only preflight."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from bot.forex.stage_a_preflight import project_preflight


def main(argv=None) -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("mode",nargs="?",choices=("preflight","execute"),default="preflight")
    args=parser.parse_args(argv)
    if args.mode=="execute":
        raise PermissionError("Stage-A performance execution is not authorized; complete the separate final pre-run audit/freeze gate")
    report=project_preflight(Path(__file__).resolve().parent)
    print(json.dumps(report,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
