"""Family-1 infrastructure entry point; no candidate-economic mode exists."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from bot.forex.family1_universe import (
    READINESS_ARTIFACT_REL,
    UNIVERSE_ARTIFACT_REL,
    build_readiness_artifact,
    build_universe_artifact,
    emit_readiness_artifacts,
    emit_u14_parity_artifact,
    load_frozen_context,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("preflight", "emit-readiness", "u14-parity"), nargs="?", default="preflight")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parent
    if args.mode == "emit-readiness":
        paths = emit_readiness_artifacts(root)
        print(json.dumps({"mode": "READINESS_EMITTED", "paths": [str(x.relative_to(root)) for x in paths]}, sort_keys=True))
        return 0
    if args.mode == "u14-parity":
        if not (root / UNIVERSE_ARTIFACT_REL).is_file() or not (root / READINESS_ARTIFACT_REL).is_file():
            raise PermissionError("hash-bound Family-1 readiness artifacts are required before U14 parity")
        path = emit_u14_parity_artifact(root)
        print(json.dumps({"mode": "U14_PARITY_COMPLETE", "path": str(path.relative_to(root))}, sort_keys=True))
        return 0
    context = load_frozen_context(root)
    print(json.dumps({
        "mode": "PREFLIGHT_ONLY", "performance_computed": False,
        "universe": build_universe_artifact(root),
        "readiness": build_readiness_artifact(root, context),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
