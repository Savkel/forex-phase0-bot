"""Frozen Family-5 breadth mechanics and network-free readiness; imports run no economics."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from math import fsum, isfinite
from pathlib import Path
from typing import Mapping, Sequence
import json
import socket

from bot.forex.family1_universe import (
    U14, BLOCKS, NUMERIC_TOLERANCE, _canonical_bytes, _canonical_sha, _json, _sha256,
    accounting_membership_records, event_identity, family1_benchmark_books,
    load_frozen_context, prepare_candidate,
)
from bot.forex.family4_cadence import (
    CadenceStep, _accounting_view, cadence_accounting_steps, cadence_diagnostics,
    static_cadence_steps,
)
from bot.forex.stage_a_orchestration import IntegrityError

STEM = "2026-09-20-tms-carry-unlevered-family-5-portfolio-breadth"
PREREG_REL = Path("prereg") / (STEM + "-prereg.md")
READINESS_REL = Path("prereg") / (STEM + "-readiness.json")
PARITY_REL = Path("prereg") / (STEM + "-k4-parity.json")
PARITY_START_REL = Path("prereg") / (STEM + "-k4-parity-start.json")
CHECKPOINT_REL = Path("prereg") / (STEM + "-execution-authorization.json")
EXECUTION_REL = Path("prereg") / (STEM + "-execution.json")
REPORT_DIR = Path("reports/forex/family5")
CONTROL_REL = REPORT_DIR / "family5-k4-control.json"
CONTROL_PATHS_REL = REPORT_DIR / "family5-k4-paths.jsonl.gz"
RESULT_REL = REPORT_DIR / "family5-portfolio-breadth-result.json"
COMPLETION_REL = REPORT_DIR / "family5-portfolio-breadth-completion.json"
PREREG_SHA256 = "af832109ca374fde71ab70a4f984e9fee0f996c09a6ecb0e64ddcab6fe947eb7"
FREEZE_COMMIT = "f41f8524c30cd45ae48000127d2452baca1795af"
CANDIDATES = {"K3": 3, "K4_CONTROL": 4, "K5": 5}
FAMILY4_READINESS = Path("prereg/2026-09-19-tms-carry-unlevered-family-4-rebalance-cadence-readiness.json")
FAMILY4_RESULT = Path("reports/forex/family4/family4-rebalance-cadence-result.json")
FAMILY4_ANCHORS = {
    str(FAMILY4_READINESS): "d292d6355ad27b23b515b72d8704b03b337582b5b2adf8a40b66e6bca5700e25",
    str(FAMILY4_RESULT): "b92f6d12d7cd7274bf3e60dca44fc402bd7bfe6d9fa6ee8fcc78f1cb31bdb6a8",
    "prereg/2026-09-19-tms-carry-unlevered-family-4-rebalance-cadence-execution.json": "eb2b97d96924e694e868bf087506070a5953860c1766bc2880f179366300927e",
    "prereg/2026-09-19-tms-carry-unlevered-family-4-rebalance-cadence-m1-parity.json": "a7528e78462dd48ea3f6124c161d5882c521b501e6a7d3a43628f22963c5ebfa",
    "reports/forex/family4/family4-rebalance-cadence-completion.json": "85469fed3c81b74c6783da40302e2548ff53f7c66794baae345ace68eaaa9547",
}
SOURCE_PATHS = (
    "bot/forex/family5_breadth.py", "bot/forex/family5_study.py",
    "run_family5_breadth.py", "tests/test_family5_breadth.py",
    "bot/forex/stage_a_preflight.py", "bot/forex/stage_a_orchestration.py",
    "bot/forex/stage_a_lineage.py",
)


def _validate_k(k):
    if type(k) is not int or k not in CANDIDATES.values():
        raise ValueError("k must be a frozen integer 3, 4 or 5")


@dataclass(frozen=True)
class BreadthConfig:
    k: int
    h: int = 2
    m: int = 1
    weighting: str = "EQ"
    currencies: tuple[str, ...] = U14.currencies
    long_target: float = 1.0
    short_target: float = -1.0
    gross: float = 2.0

    def __post_init__(self):
        _validate_k(self.k)
        if type(self.h) is not int or self.h != 2 or type(self.m) is not int or self.m != 1:
            raise ValueError("H2 and M1 are frozen")
        if self.weighting != "EQ" or self.currencies != U14.currencies:
            raise ValueError("EQ and exact U14 are frozen")
        for value, expected in ((self.long_target, 1.0), (self.short_target, -1.0), (self.gross, 2.0)):
            if type(value) not in (int, float) or value != expected:
                raise ValueError("sleeve/gross targets are frozen")

    @classmethod
    def from_mapping(cls, config):
        unknown = set(config) - set(cls.__dataclass_fields__)
        if unknown or "k" not in config:
            raise ValueError("unknown configuration keys or missing k")
        value = dict(config)
        if "currencies" in value:
            value["currencies"] = tuple(value["currencies"])
        return cls(**value)


def active_currencies(omitted=None):
    if omitted is not None and omitted not in U14.currencies:
        raise ValueError("invalid omission")
    return tuple(c for c in U14.currencies if c != omitted)


def _ordered(scores, active):
    if set(scores) != set(U14.currencies) or any(not isfinite(float(v)) for v in scores.values()):
        raise IntegrityError("exact U14 finite score columns required")
    return tuple(sorted(active, key=lambda c: (-float(scores[c]), c)))


def validate_signals(signals):
    if not signals or signals[-1].kind != "terminal":
        raise IntegrityError("terminal signal required")
    held = False
    for i, signal in enumerate(signals):
        if i and signals[i-1].timestamp >= signal.timestamp:
            raise IntegrityError("signals must be strictly ordered")
        if signal.scores is None:
            if signal.kind not in ("gap_exit", "terminal") or not held:
                raise IntegrityError("flat event without holding period")
            if signal.kind == "terminal" and i != len(signals)-1:
                raise IntegrityError("premature terminal")
            held = False
        else:
            _ordered(signal.scores, U14.currencies)
            expected = "rebalance" if held or i == 0 else "gap_reentry"
            if signal.kind != expected:
                raise IntegrityError("invalid causal gap/reentry state")
            held = True


def select_memberships(order, k, prior_longs=(), prior_shorts=(), *, fresh=False):
    """Both retained sets first; inherited long-first fills and total rank order."""
    _validate_k(k)
    order = tuple(order)
    if len(order) not in (13, 14) or len(set(order)) != len(order) or not set(order) <= set(U14.currencies):
        raise IntegrityError("invalid active ranking")
    lp, sp = set(prior_longs), set(prior_shorts)
    if len(lp) != len(prior_longs) or len(sp) != len(prior_shorts) or lp & sp or not lp | sp <= set(order):
        raise IntegrityError("invalid/overlapping incumbent memberships")
    if (lp or sp) and (len(lp) != k or len(sp) != k):
        raise IntegrityError("incumbents must have exactly k members per sleeve")
    if fresh:
        return set(order[:k]), set(order[-k:]), set(), set()
    if not lp or not sp:
        raise IntegrityError("nonfresh transition requires both incumbent sleeves")
    ranks = {c: i+1 for i, c in enumerate(order)}
    rl = {c for c in lp if ranks[c] <= k+2}
    rs = {c for c in sp if ranks[c] >= len(order)-k-1}
    longs, shorts = set(rl), set(rs)
    for c in order:
        if len(longs) == k:
            break
        if c not in longs and c not in shorts:
            longs.add(c)
    for c in reversed(order):
        if len(shorts) == k:
            break
        if c not in longs and c not in shorts:
            shorts.add(c)
    if len(longs) != k or len(shorts) != k or longs & shorts:
        raise IntegrityError("exact-k/disjointness failed")
    return longs, shorts, rl, rs


def equal_targets(longs, shorts, k, *, active):
    _validate_k(k)
    ls, ss = set(longs), set(shorts)
    if len(longs) != k or len(shorts) != k or len(ls) != k or len(ss) != k or ls & ss:
        raise IntegrityError("invalid target membership")
    if not ls | ss <= set(active):
        raise IntegrityError("target contains excluded currency")
    weights = {c: (1/k if c in ls else -1/k if c in ss else 0.0) for c in U14.currencies}
    if (abs(fsum(w for w in weights.values() if w > 0)-1) > NUMERIC_TOLERANCE or
        abs(fsum(w for w in weights.values() if w < 0)+1) > NUMERIC_TOLERANCE or
        abs(fsum(map(abs, weights.values()))-2) > NUMERIC_TOLERANCE):
        raise IntegrityError("target scale failed")
    return weights


def breadth_accounting_steps(signals: Sequence[SignalStep], k: int, *, omitted: str | None = None):
    """Frozen segment-local cadence layered over the H2 state machine."""
    _validate_k(k)
    active = active_currencies(omitted)
    n = len(active)
    validate_signals(signals)
    prior_longs: set[str] = set(); prior_shorts: set[str] = set()
    steps: list[CadenceStep] = []; records: list[dict[str, object]] = []
    evaluable_index = 0; segment_index: int | None = None
    for signal in signals:
        if signal.scores is None:
            steps.append(CadenceStep(signal.timestamp, {c: 0.0 for c in U14.currencies}, signal.opens, signal.kind, True))
            records.append({"timestamp": signal.timestamp, "kind": signal.kind, "evaluable_index": None,
                "segment_index": None, "action": signal.kind, "execute": True, "state_reset": True,
                "counted_rotation": False, "prior_longs": sorted(prior_longs),
                "prior_shorts": sorted(prior_shorts), "final_longs": [], "final_shorts": [],
                "suppressed_replacements": 0})
            prior_longs.clear(); prior_shorts.clear(); segment_index = None
            continue
        segment_index = 0 if segment_index is None else segment_index + 1
        execute = True
        order = _ordered(signal.scores, active); ranks = {c: i + 1 for i, c in enumerate(order)}
        control_longs, control_shorts = set(order[:k]), set(order[-k:])
        rank_list = lambda values: [c for c in order if c in values]
        fresh = segment_index == 0 or signal.kind == "gap_reentry" or not prior_longs or not prior_shorts
        longs, shorts, retained_longs, retained_shorts = select_memberships(
            order, k, prior_longs, prior_shorts, fresh=fresh)
        retained_outside_long = retained_longs - control_longs
        retained_outside_short = retained_shorts - control_shorts
        displaced_long = control_longs - longs; displaced_short = control_shorts - shorts
        if len(retained_outside_long) != len(displaced_long) or len(retained_outside_short) != len(displaced_short):
            raise IntegrityError("Family-5 retained/displaced counts do not reconcile")
        counted = not fresh and signal.kind == "rebalance"
        record = {"timestamp": signal.timestamp, "kind": signal.kind, "evaluable_index": evaluable_index,
            "segment_index": segment_index, "action": "execute", "execute": True,
            "state_reset": fresh, "counted_rotation": counted, "ranks": {c: ranks[c] for c in order},
            "prior_longs": rank_list(prior_longs), "prior_shorts": rank_list(prior_shorts),
            "retained_longs": rank_list(retained_longs), "retained_shorts": rank_list(retained_shorts),
            "exited_longs": rank_list(prior_longs-longs), "exited_shorts": rank_list(prior_shorts-shorts),
            "entered_longs": rank_list(longs-prior_longs), "entered_shorts": rank_list(shorts-prior_shorts),
            "final_longs": rank_list(longs), "final_shorts": rank_list(shorts),
            "retained_outside_control_longs": rank_list(retained_outside_long),
            "retained_outside_control_shorts": rank_list(retained_outside_short),
            "displaced_control_longs": rank_list(displaced_long), "displaced_control_shorts": rank_list(displaced_short),
            "actual_long_replacements": (k-len(prior_longs&longs)) if counted else 0,
            "actual_short_replacements": (k-len(prior_shorts&shorts)) if counted else 0,
            "suppressed_long_replacements": len(retained_outside_long) if counted else 0,
            "suppressed_short_replacements": len(retained_outside_short) if counted else 0,
            "suppressed_replacements": (len(retained_outside_long)+len(retained_outside_short)) if counted else 0,
            "avoided_long_replacements": len(retained_outside_long) if counted else 0,
            "avoided_short_replacements": len(retained_outside_short) if counted else 0,
            "avoided_replacements": (len(retained_outside_long)+len(retained_outside_short)) if counted else 0}
        weights = equal_targets(longs, shorts, k, active=active)
        steps.append(CadenceStep(signal.timestamp, weights, signal.opens, signal.kind, True)); records.append(record)
        prior_longs, prior_shorts = longs, shorts; evaluable_index += 1
    if evaluable_index != 157:
        raise IntegrityError("Family-5 requires 157 evaluable decisions")
    return tuple(steps), tuple(records)


def static_breadth_steps(signals, book, k, *, omitted=None):
    active = active_currencies(omitted)
    if set(book) != {"longs", "shorts"}:
        raise IntegrityError("unknown static book keys")
    target = equal_targets(book["longs"], book["shorts"], k, active=active)
    return tuple(CadenceStep(s.timestamp,
        {c: 0.0 for c in U14.currencies} if s.scores is None else dict(target),
        s.opens, s.kind, True) for s in signals)


def benchmark_books(k, omitted=None):
    _validate_k(k)
    return family1_benchmark_books(active_currencies(omitted), k)


def rank7_diagnostics(records, k, omitted):
    cases = []
    if k == 5 and omitted is not None:
        for row in records:
            if "ranks" not in row:
                continue
            c = next(c for c, rank in row["ranks"].items() if rank == 7)
            prior = "long" if c in row["prior_longs"] else "short" if c in row["prior_shorts"] else "unheld"
            final = "long" if c in row["final_longs"] else "short" if c in row["final_shorts"] else "unheld"
            if final != ("unheld" if row["state_reset"] else prior):
                raise IntegrityError("K5/N13 rank-7 retention proof violated")
            cases.append({"timestamp": row["timestamp"], "currency": c, "prior": prior,
                          "final": final, "reset": row["state_reset"]})
    return {"cases": cases, "counts": {side: sum(r["final"] == side for r in cases)
                                      for side in ("long", "short", "unheld")}}


@contextmanager
def offline():
    """All entry-point work runs with outbound socket creation blocked."""
    def denied(*args, **kwargs):
        raise PermissionError("Family-5 prohibits network access")
    connect, connect_ex, create, dns = socket.socket.connect, socket.socket.connect_ex, socket.create_connection, socket.getaddrinfo
    socket.socket.connect = socket.socket.connect_ex = socket.create_connection = socket.getaddrinfo = denied
    try:
        yield
    finally:
        socket.socket.connect, socket.socket.connect_ex, socket.create_connection, socket.getaddrinfo = connect, connect_ex, create, dns


def immutable_sources(root):
    root = Path(root)
    expected = {str(PREREG_REL): PREREG_SHA256, **FAMILY4_ANCHORS}
    for rel, digest in list(expected.items()):
        if not (root/rel).is_file() or _sha256(root/rel) != digest:
            raise IntegrityError("frozen evidence changed: " + rel)
    pending = [_json(root/FAMILY4_READINESS)]
    while pending:
        manifest = pending.pop()
        for rel, digest in manifest.get("source_sha256", {}).items():
            if rel in expected:
                if expected[rel] != digest:
                    raise IntegrityError("inconsistent source lineage: " + rel)
                continue
            if not (root/rel).is_file() or _sha256(root/rel) != digest:
                raise IntegrityError("frozen source changed: " + rel)
            expected[rel] = digest
            if rel.endswith(".json") and "readiness" in rel:
                pending.append(_json(root/rel))
    for rel in SOURCE_PATHS:
        expected[rel] = _sha256(root/rel)
    return {str(Path(k)).replace(chr(92), "/"): v for k, v in sorted(expected.items())}


def load_control(root):
    value = _json(Path(root)/FAMILY4_RESULT)
    control = value["control"]
    if control["configuration_id"] != "M1_CONTROL" or control["k"] != 4:
        raise IntegrityError("immutable M1 control absent")
    return control


def _schedule_payload(steps):
    return [{"timestamp": s.timestamp, "kind": s.kind, "execute": s.execute} for s in steps]


def build_readiness(root):
    root = Path(root)
    with offline():
        sources = immutable_sources(root)
        context = load_frozen_context(root)
        inputs = prepare_candidate(context, U14)
        control = load_control(root)
        configs = {}
        for cid, k in CANDIDATES.items():
            cases = {}
            for omitted in (None, *U14.currencies):
                steps, records = breadth_accounting_steps(inputs.signal_steps, k, omitted=omitted)
                books = benchmark_books(k, omitted)
                if k == 4:
                    refsteps, refrecords = cadence_accounting_steps(inputs.signal_steps, 1, omitted=omitted)
                    if steps != refsteps or records != refrecords:
                        raise IntegrityError("non-economic K4 discrete parity failed")
                    frozen = control if omitted is None else control["loco"][omitted]
                    if _canonical_sha(books) != frozen["benchmark_books_sha256"]:
                        raise IntegrityError("K4 benchmark identities differ")
                for book in books:
                    equal_targets(book["longs"], book["shorts"], k, active=active_currencies(omitted))
                static = static_breadth_steps(inputs.signal_steps, books[0], k, omitted=omitted)
                if _schedule_payload(static) != _schedule_payload(steps):
                    raise IntegrityError("unmatched static schedule")
                cases[omitted or "FULL"] = {
                    "N": len(active_currencies(omitted)), "k": k,
                    "memberships_sha256": _canonical_sha(accounting_membership_records(_accounting_view(steps))),
                    "state_sha256": _canonical_sha(records),
                    "action_schedule_sha256": _canonical_sha(_schedule_payload(steps)),
                    "static_schedule_sha256": _canonical_sha(_schedule_payload(static)),
                    "benchmark_books_sha256": _canonical_sha(books),
                    "benchmark_books": books, "benchmark_book_count": len(books),
                    "rank7": rank7_diagnostics(records, k, omitted),
                }
            configs[cid] = {"k": k, "h": 2, "m": 1, "weighting": "EQ", "cases": cases,
                            "economic_outputs_computed": False}
        return {
            "schema_version": 1, "status": "FAMILY5_READINESS_PASSED",
            "freeze_commit": FREEZE_COMMIT, "preregistration_sha256": PREREG_SHA256,
            "source_sha256": sources, "cache_sha256": dict(sorted(context.cache_sha256.items())),
            "transaction_mapping_sha256": _canonical_sha(context.transaction_mapping),
            "signal_count": len(inputs.signal_steps), "evaluable_count": 157,
            "signal_sha256": _canonical_sha([{"timestamp": s.timestamp, "kind": s.kind, "scores": s.scores}
                                            for s in inputs.signal_steps]),
            "routes_sha256": _canonical_sha(inputs.routes),
            "financing_event_count": len(inputs.financing_events),
            "financing_event_sha256": _canonical_sha(event_identity(inputs.financing_events)),
            "ic_sha256": _canonical_sha(control["ic"]), "ic_reuse_only": True,
            "benchmark_seed": 20260809, "bootstrap_seed": 20260808,
            "blocks": list(BLOCKS), "configurations": configs,
            "performance_computed": False, "network_accessed": False,
            "noncontrol_economics_authorized": False, "stage_b_accessed": False,
        }


def exclusive_json(path, value):
    """Atomic exclusive reservation; never overwrite/restart even after partial failure."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, sort_keys=True, indent=2, allow_nan=False)
        handle.write("\n")


def emit_readiness(root):
    root = Path(root)
    readiness = build_readiness(root)
    path = root/READINESS_REL
    if path.exists():
        if _canonical_bytes(_json(path)) != _canonical_bytes(readiness):
            raise IntegrityError("existing readiness differs; preserve it for review")
        return path
    exclusive_json(path, readiness)
    return path


def validate_readiness(root):
    root = Path(root)
    path = root/READINESS_REL
    if not path.is_file():
        raise IntegrityError("Family-5 readiness required")
    actual = _json(path)
    if _canonical_bytes(actual) != _canonical_bytes(build_readiness(root)):
        raise IntegrityError("Family-5 readiness/source/data hashes are stale")
    return actual
