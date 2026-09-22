"""Family-6 CLI: non-economic readiness and authorized CONTROL-only parity."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from bot.forex.family6_hurdle import build_readiness, emit_readiness, run_control_parity


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("preflight", "emit-readiness", "control-parity"),
                        nargs="?", default="preflight")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parent
    if args.mode == "preflight":
        value = build_readiness(root)
        print(json.dumps({"status": value["status"],
                          "configurations": list(value["configurations"])}, sort_keys=True))
        return
    path = emit_readiness(root) if args.mode == "emit-readiness" else run_control_parity(root)
    print(path)


if __name__ == "__main__":
    main()
