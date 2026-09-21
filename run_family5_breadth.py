"""Family-5 CLI: non-economic readiness, authorized K4 parity, future gated economics."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from bot.forex.family5_breadth import build_readiness, emit_readiness
from bot.forex.family5_study import run_k4_parity, execute_candidates


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("preflight", "emit-readiness", "k4-parity", "execute-candidates"),
                        nargs="?", default="preflight")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parent
    if args.mode == "preflight":
        value = build_readiness(root)
        print(json.dumps({"status": value["status"], "performance_computed": False,
                          "configurations": list(value["configurations"])}))
        return 0
    action = {"emit-readiness": emit_readiness, "k4-parity": run_k4_parity,
              "execute-candidates": execute_candidates}[args.mode]
    path = action(root)
    print(json.dumps({"mode": args.mode, "path": str(path.relative_to(root))}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
