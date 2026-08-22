"""Fail-closed Family-3 readiness, EQ_H2 parity, and one-shot execution entry point."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from bot.forex.family3_weighting import (
    build_readiness, emit_eq_h2_parity, emit_readiness, execute_family3,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode", choices=("preflight", "emit-readiness", "eq-h2-parity", "execute-candidates"),
        nargs="?", default="preflight",
    )
    args = parser.parse_args(argv); root = Path(__file__).resolve().parent
    if args.mode == "emit-readiness":
        path = emit_readiness(root); status = "READINESS_EMITTED"
    elif args.mode == "eq-h2-parity":
        path = emit_eq_h2_parity(root); status = "EQ_H2_PARITY_COMPLETE"
    elif args.mode == "execute-candidates":
        path = execute_family3(root); status = "FAMILY3_ECONOMICS_COMPLETE"
    else:
        print(json.dumps({"mode": "PREFLIGHT_ONLY", "readiness": build_readiness(root)}, sort_keys=True))
        return 0
    print(json.dumps({"mode": status, "path": str(path.relative_to(root))}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
