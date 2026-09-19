"""Fail-closed Family-4 readiness, M1 parity, and one-shot execution entry point."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from bot.forex.family4_cadence import build_readiness, emit_m1_parity, emit_readiness, execute_family4


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("preflight", "emit-readiness", "m1-parity", "execute-candidates"),
                        nargs="?", default="preflight")
    args = parser.parse_args(argv); root = Path(__file__).resolve().parent
    if args.mode == "emit-readiness":
        path = emit_readiness(root); status = "READINESS_EMITTED"
    elif args.mode == "m1-parity":
        path = emit_m1_parity(root); status = "M1_PARITY_COMPLETE"
    elif args.mode == "execute-candidates":
        path = execute_family4(root); status = "FAMILY4_ECONOMICS_COMPLETE"
    else:
        print(json.dumps({"mode": "PREFLIGHT_ONLY", "readiness": build_readiness(root)}, sort_keys=True)); return 0
    print(json.dumps({"mode": status, "path": str(path.relative_to(root))}, sort_keys=True)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
