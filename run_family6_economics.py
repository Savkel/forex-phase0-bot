"""Manual, prereg-bound Family-6 non-control economics entry point."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from bot.forex.family6_execution import execute_candidates


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("execute-candidates",))
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parent
    path = execute_candidates(root)
    print(json.dumps({"mode": args.mode, "path": str(path.relative_to(root)).replace(chr(92), "/")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
