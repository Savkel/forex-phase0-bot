"""Family-5 study, complete K4 parity, and separately gated one-shot economics."""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import numpy as np

from bot.forex import family4_cadence as reference
from bot.forex.family1_study import ADJUDICATION_POLICY, _scenario_paths, path_diagnostics
from bot.forex.family1_universe import (
    U14, BLOCKS, NUMERIC_TOLERANCE, ParityAccumulator, _canonical_bytes, _canonical_sha,
    _comparison_stats, _json, _path_component_payload, _sha256, event_identity,
    load_frozen_context, path_block_diagnostics, prepare_candidate,
)
from bot.forex.family2_hysteresis import _concentration, _difference, _rotation_diagnostics
from bot.forex.family3_weighting import weight_turnover_diagnostics
from bot.forex.family4_cadence import _accounting_view, _rotation_records, cadence_diagnostics
from bot.forex.stage_a_carry import (
    currency_usd_values, max_drawdown_from_returns, rap, position_financing_cashflow_usd,
    rollover_multiplier, apply_financing_stress,
)
from bot.forex.stage_a_orchestration import IntegrityError
from bot.forex.family5_breadth import (
    CANDIDATES, U14, PREREG_SHA256, FREEZE_COMMIT, READINESS_REL, PARITY_REL,
    PARITY_START_REL, CONTROL_REL, CONTROL_PATHS_REL, CHECKPOINT_REL, EXECUTION_REL,
    RESULT_REL, COMPLETION_REL, REPORT_DIR, BreadthConfig, active_currencies,
    benchmark_books, breadth_accounting_steps, static_breadth_steps, rank7_diagnostics,
    immutable_sources, load_control, offline, exclusive_json, validate_readiness,
)

SCENARIOS = ("base", "adverse", "spread_x3")


def _assert_equal(expected, actual, accumulator, label, *, discrete=False):
    if discrete and _canonical_bytes(expected) != _canonical_bytes(actual):
        raise IntegrityError("exact discrete parity failed: " + label)
    accumulator.add(label, expected, actual)
    cell = accumulator.report()["cells"][label]
    if cell["mismatch_count"]:
        raise IntegrityError("numeric/shape parity failed: " + label)


def _references(steps, inputs):
    # Independent frozen Family-4 accounting reconstruction, never the Family-5 output.
    return reference._scenarios(steps, inputs)


class PathArchive:
    """Exclusive gzip JSONL: complete paths persisted, duplicate book references explicit."""
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.raw = self.path.open("xb")
        self.handle = gzip.GzipFile(filename="", fileobj=self.raw, mode="wb", mtime=0, compresslevel=1)
        self.count = 0
        self.digest = hashlib.sha256()

    def append(self, identity, payload):
        line = _canonical_bytes({"identity": identity, "evidence": payload})
        self.handle.write(line)
        self.digest.update(line)
        self.count += 1

    def close(self):
        self.handle.close()
        self.raw.close()
        return {"path": str(self.path), "sha256": _sha256(self.path),
                "uncompressed_sha256": self.digest.hexdigest(), "records": self.count}


def _payload(path, inputs, scenario, signal_values, event_values):
    adverse = scenario == "adverse"
    result = _path_component_payload(
        path, inputs.signal_steps, inputs.financing_events, inputs.routes,
        adverse_financing=adverse, signal_currency_values=signal_values, event_currency_values=event_values,
    )
    financing_legs = []
    for event, values in zip(inputs.financing_events, event_values):
        cell = {}
        for pair, units in path.trades[event.after_step].target_units.items():
            if units == 0 or pair not in event.opens:
                continue
            code = pair.split(".")[0].replace("_", "")
            cash = position_financing_cashflow_usd(
                event.schedule, pair, units, event.opens[pair].mid, path.denominator,
                rollover_multiplier(event.day, pair) if event.days_charged is None else event.days_charged,
                values[code[3:]],
            )
            cell[pair] = apply_financing_stress(cash) if adverse else cash
        financing_legs.append(cell)
    result["financing_cashflows_by_event_leg"] = financing_legs
    result["blocks"] = list(path_block_diagnostics(path, inputs.signal_steps))
    result["rap"] = rap(path.period_returns)
    result["max_drawdown"] = max_drawdown_from_returns(path.period_returns)
    # All scenario attribution uses actual stressed cashflows, never base-path amounts.
    if abs(sum(result["financing_cashflows_by_event"])-path.total_financing) > NUMERIC_TOLERANCE:
        raise IntegrityError("financing attribution mismatch")
    if abs(sum(result["spot_cashflows_by_step"])+path.total_financing-path.total_spread_cost
           -(path.equities[-1]-1)) > NUMERIC_TOLERANCE:
        raise IntegrityError("scenario equity attribution mismatch")
    result["total_return"] = path.equities[-1]-1
    result["cagr"] = path.equities[-1] ** (1 / ((inputs.signal_steps[-1].timestamp-
        inputs.signal_steps[0].timestamp)/1000/(365.25*86400))) - 1
    result["calmar"] = (result["cagr"]/abs(result["max_drawdown"])
        if result["cagr"] > 0 and result["max_drawdown"] else "NOT_INTERPRETABLE")
    # Frozen routed gross/turnover plus passive pre-rebalance gross at current marks.
    prior_units, prior_weights = {}, {}
    trades = []
    for i, (trade, values) in enumerate(zip(path.trades, signal_values)):
        def gross(units):
            return sum(abs(q)*values[p.split(".")[0].replace("_", "")[:3]] for p, q in units.items())
        keys = set(prior_units) | set(trade.target_units)
        delta = {p: trade.target_units.get(p, 0)-prior_units.get(p, 0) for p in keys}
        currencies = set(prior_weights) | set(trade.target_weights)
        before_equity = (path.equities[i-1] if i else 1.0) + result["spot_cashflows_by_step"][i]
        def currency_gross(units):
            exposure = {c: 0.0 for c in U14.currencies}
            for pair, q in units.items():
                code = pair.split(".")[0].replace("_", "")
                exposure[code[:3]] += q*values[code[:3]]
                exposure[code[3:]] -= q*inputs.signal_steps[i].opens[pair].mid*values[code[3:]]
            return sum(abs(value) for value in exposure.values())
        trades.append({
            "timestamp": trade.timestamp,
            "pre_rebalance_currency_gross": currency_gross(prior_units)/before_equity,
            "pre_rebalance_routed_gross": gross(prior_units)/before_equity,
            "target_currency_gross": currency_gross(trade.target_units)/before_equity,
            "currency_turnover": sum(abs(trade.target_weights.get(c, 0)-prior_weights.get(c, 0))
                                     for c in currencies),
            "routed_usd_turnover": gross(delta),
            "routed_usd_gross": gross(trade.target_units),
            "pre_rebalance_routed_usd_gross": gross(prior_units),
            "fill_count": len(trade.fills),
        })
        prior_units, prior_weights = trade.target_units, trade.target_weights
    result["trade_diagnostics"] = trades
    starts, ends, period = {}, {}, 0
    for i, signal in enumerate(inputs.signal_steps[:-1]):
        if signal.scores is not None:
            starts[i], ends[i+1] = period, period
            period += 1
    components = {key: [0.0]*157 for key in
                  ("spot_pnl", "financing", "spread_cost", "currency_turnover", "routed_usd_turnover", "fill_count")}
    for i, cash in enumerate(result["spot_cashflows_by_step"]):
        if i in ends:
            components["spot_pnl"][ends[i]] += cash
    for event, cash in zip(inputs.financing_events, result["financing_cashflows_by_event"]):
        components["financing"][starts[event.after_step]] += cash
    for i, trade in enumerate(path.trades):
        index = ends.get(i) if trade.kind in ("gap_exit", "terminal") else starts.get(i)
        if index is not None:
            components["spread_cost"][index] += trade.spread_cost
            for key in ("currency_turnover", "routed_usd_turnover", "fill_count"):
                components[key][index] += trades[i][key]
    result["period_components"] = components
    result["block_components"] = {block["block_id"]: {
        key: sum(values[block["start"]:block["stop"]]) for key, values in components.items()}
        for block in BLOCKS}
    return result


def _discrete_path(payload):
    path = payload["path"]
    return {
        "denominator": path["denominator"],
        "trades": [{"timestamp": t["timestamp"], "kind": t["kind"],
                    "weight_signs": {c: int(np.sign(w)) for c, w in t["target_weights"].items()},
                    "unit_legs": sorted(t["target_units"]), "fill_legs": sorted(t["fills"])}
                   for t in path["trades"]],
        "financing_event_legs": [sorted(x) for x in payload["financing_cashflows_by_event_leg"]],
    }


def _capture(paths, inputs, identity, sink, accumulator, expected, values):
    summaries = {}
    for scenario in SCENARIOS:
        summaries[scenario] = {}
        for d in (360, 365):
            payload = _payload(paths[scenario][d], inputs, scenario, *values)
            if accumulator is not None:
                frozen = _payload(expected[scenario][d], inputs, scenario, *values)
                _assert_equal(_discrete_path(frozen), _discrete_path(payload), accumulator,
                              identity["role"]+"_discrete_paths", discrete=True)
                _assert_equal(frozen, payload, accumulator, identity["role"]+"_full_paths_and_components")
            sink.append({**identity, "scenario": scenario, "denominator": d}, payload)
            summaries[scenario][str(d)] = {key: payload[key] for key in
                ("total_return", "cagr", "calmar", "rap", "max_drawdown", "blocks")}
    return summaries


def _empty_ensemble():
    return {str(d): {"rap": [], "max_drawdown": [], "total_return": [],
        "adverse_total_return": [], "spread_x3_total_return": [],
        "blocks": {b["block_id"]: {"rap": [], "max_drawdown": [], "total_return": []} for b in BLOCKS}}
        for d in (360, 365)}


def _book_summary(paths, inputs):
    return {str(d): {
        "rap": rap(paths["base"][d].period_returns),
        "max_drawdown": max_drawdown_from_returns(paths["base"][d].period_returns),
        "total_return": paths["base"][d].equities[-1]-1,
        "adverse_total_return": paths["adverse"][d].equities[-1]-1,
        "spread_x3_total_return": paths["spread_x3"][d].equities[-1]-1,
        "blocks": {b["block_id"]: {key: b[key] for key in ("rap", "max_drawdown", "total_return")}
                   for b in path_block_diagnostics(paths["base"][d], inputs.signal_steps)},
    } for d in (360, 365)}


def _benchmark(inputs, k, omitted, sink, accumulator, values):
    books = benchmark_books(k, omitted)
    distributions = _empty_ensemble()
    # Scope is one input context, active set, k and all fixed scenarios. Only duplicate books reuse.
    cache = {}
    for index, book in enumerate(books):
        key = (tuple(book["longs"]), tuple(book["shorts"]))
        if key not in cache:
            steps = static_breadth_steps(inputs.signal_steps, book, k, omitted=omitted)
            expected = None
            if accumulator is not None:
                refsteps = reference.static_cadence_steps(inputs.signal_steps, book, 1)
                _assert_equal([s.__dict__ | {"opens": None} for s in refsteps],
                              [s.__dict__ | {"opens": None} for s in steps], accumulator,
                              "benchmark_targets_actions", discrete=True)
                expected = _references(refsteps, inputs)
            paths = _scenario_paths(_accounting_view(steps), inputs.financing_events, inputs.routes)
            _capture(paths, inputs, {"role": "benchmark", "k": k, "omitted": omitted,
                     "book_index": index, "book": book}, sink, accumulator, expected, values)
            cache[key] = (_book_summary(paths, inputs), index)
        else:
            sink.append({"role": "benchmark_duplicate", "k": k, "omitted": omitted, "book_index": index},
                        {"same_as_book_index": cache[key][1], "book": book})
        item = cache[key][0]
        for d, target in distributions.items():
            for metric in target:
                if metric == "blocks":
                    for bid, cell in target[metric].items():
                        for name in cell:
                            cell[name].append(item[d]["blocks"][bid][name])
                else:
                    target[metric].append(item[d][metric])
    medians = {}
    for d, target in distributions.items():
        medians[d] = {key: float(np.median(value)) for key, value in target.items() if key != "blocks"}
        medians[d]["blocks"] = {bid: {key: float(np.median(v)) for key, v in cell.items()}
                                 for bid, cell in target["blocks"].items()}
    return books, {"path_count": len(books), "distributions": distributions, "medians": medians}


def _project(expected, actual):
    """Compare every stored field; only map explicitly identified provenance labels."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or set(expected)-set(actual):
            raise IntegrityError("stored control field missing")
        return {key: _project(value, actual[key]) for key, value in expected.items()}
    return actual


def breadth_study(inputs, config, reused_ic, sink, *, parity=None, stored_control=None):
    """Caller supplies frozen historical inputs only after the K4/execution gate."""
    k = config.k
    if parity is not None and k != 4:
        raise PermissionError("parity may compute K4 only")
    values = ([currency_usd_values(s.opens) for s in inputs.signal_steps],
              [currency_usd_values(e.opens) for e in inputs.financing_events])
    cases, extra = {}, {}
    for omitted in (None, *U14.currencies):
        steps, records = breadth_accounting_steps(inputs.signal_steps, k, omitted=omitted)
        expected_paths = None
        if parity is not None:
            refsteps, refrecords = reference.cadence_accounting_steps(inputs.signal_steps, 1, omitted=omitted)
            _assert_equal(refrecords, records, parity, "membership_state_records", discrete=True)
            _assert_equal([s.__dict__ | {"opens": None} for s in refsteps],
                          [s.__dict__ | {"opens": None} for s in steps], parity, "strategy_targets_actions", discrete=True)
            expected_paths = _references(refsteps, inputs)
        paths = _scenario_paths(_accounting_view(steps), inputs.financing_events, inputs.routes)
        scenario_summaries = _capture(paths, inputs, {"role": "strategy", "k": k, "omitted": omitted},
                                       sink, parity, expected_paths, values)
        books, benchmark = _benchmark(inputs, k, omitted, sink, parity, values)
        view = _accounting_view(steps)
        cells = {}
        for d in (360, 365):
            matched = benchmark["medians"][str(d)]
            base = path_diagnostics(paths["base"][d], inputs.signal_steps, inputs.financing_events, inputs.routes)
            cell = {
                "base": base, "adverse_total_return": paths["adverse"][d].equities[-1]-1,
                "spread_x3_total_return": paths["spread_x3"][d].equities[-1]-1,
                "benchmark_rap_excess": base["rap"]-matched["rap"],
            }
            if omitted is None:
                cell.update(benchmark=matched, benchmark_mdd_difference=base["max_drawdown"]-matched["max_drawdown"])
            else:
                cell.update(benchmark_rap=matched["rap"], benchmark_max_drawdown=matched["max_drawdown"],
                    benchmark_adverse_total_return=matched["adverse_total_return"],
                    benchmark_spread_x3_total_return=matched["spread_x3_total_return"], benchmark_blocks=matched["blocks"])
            cells[str(d)] = cell
        case = {"N": len(active_currencies(omitted)), "k": k, "benchmark_books_sha256": _canonical_sha(books),
            "benchmark_economics_reused": False, "benchmark": benchmark, "concentration": _concentration(view),
            "rotation": _rotation_diagnostics(_rotation_records(records)),
            "weight_turnover": weight_turnover_diagnostics(view, inputs.signal_steps),
            "cadence": cadence_diagnostics(steps, records), "denominators": cells}
        cases[omitted or "FULL"] = case
        extra[omitted or "FULL"] = {"scenarios": scenario_summaries, "rank7": rank7_diagnostics(records, k, omitted),
            "benchmark_books": books,
            "benchmark_mdd_difference": {d: cell["base"]["max_drawdown"]-benchmark["medians"][d]["max_drawdown"]
                                          for d, cell in cells.items()},
            "carry_separation": [{"timestamp": s.timestamp,
                "long_mean": sum(s.scores[c] for c in r["final_longs"])/k,
                "short_mean": sum(s.scores[c] for c in r["final_shorts"])/k}
                for s, r in zip(inputs.signal_steps, records) if s.scores is not None]}
        if parity is not None and omitted is not None:
            frozen = stored_control["loco"][omitted]
            _assert_equal(frozen, _project(frozen, case), parity, "stored_loco_all_fields")
    full = cases.pop("FULL")
    result = {**full, "configuration_id": next(cid for cid, value in CANDIDATES.items() if value == k),
        "m": 1, "base_configuration": "EQ_H2", "h": 2, "currencies": list(U14.currencies),
        "currency_gross": 2, "benchmark_book_count": 1000, "ic": dict(reused_ic), "ic_reused": True,
        "D365_MINUS_D360": _difference(full["denominators"]), "loco": cases,
        "candidate_disposition": "PENDING_EXTERNAL_ADJUDICATION", "breadth_diagnostics": extra}
    if parity is not None:
        mapped = {**result, "configuration_id": "M1_CONTROL"}
        _assert_equal(stored_control, _project(stored_control, mapped), parity, "stored_control_all_fields")
    return result


def run_k4_parity(root):
    root = Path(root)
    with offline():
        readiness = validate_readiness(root)
        for rel in (PARITY_START_REL, PARITY_REL, CONTROL_REL, CONTROL_PATHS_REL):
            if (root/rel).exists():
                raise PermissionError("K4 parity already started/completed; preserve evidence for review")
        exclusive_json(root/PARITY_START_REL, {"status": "K4_PARITY_STARTED", "consumption_count": 1,
            "preregistration_sha256": PREREG_SHA256, "readiness_sha256": _sha256(root/READINESS_REL),
            "noncontrol_economics_computed": False})
        inputs = prepare_candidate(load_frozen_context(root), U14)
        stored = load_control(root)
        accumulator = ParityAccumulator()
        sink = PathArchive(root/CONTROL_PATHS_REL)
        try:
            study = breadth_study(inputs, BreadthConfig(4), stored["ic"], sink,
                                  parity=accumulator, stored_control=stored)
        finally:
            archive = sink.close()
        if immutable_sources(root) != readiness["source_sha256"]:
            raise IntegrityError("source changed during K4 parity")
        if _canonical_sha(study["ic"]) != readiness["ic_sha256"]:
            raise IntegrityError("IC hash reuse failed")
        archive["path"] = str(CONTROL_PATHS_REL).replace(chr(92), "/")
        evidence = {"schema_version": 1, "status": "K4_CONTROL_EVIDENCE_COMPLETE",
            "preregistration_sha256": PREREG_SHA256, "readiness_sha256": _sha256(root/READINESS_REL),
            "source_sha256": readiness["source_sha256"], "archive": archive, "control_study": study,
            "noncontrol_economics_computed": False, "network_accessed": False, "stage_b_accessed": False}
        exclusive_json(root/CONTROL_REL, evidence)
        report = accumulator.report()
        counts = {key: sum(cell[key] for cell in report["cells"].values()) for key in
                  ("numeric_values_compared", "discrete_values_compared", "numeric_mismatch_count",
                   "discrete_mismatch_count", "shape_mismatch_count")}
        artifact = {"schema_version": 1, "status": "K4_CONTROL_PARITY_PASSED", "freeze_commit": FREEZE_COMMIT,
            "preregistration_sha256": PREREG_SHA256, "readiness_sha256": _sha256(root/READINESS_REL),
            "source_sha256": readiness["source_sha256"], "control_sha256": _sha256(root/CONTROL_REL),
            "archive": archive, "scope": {"k": 4, "full_cases": 1, "loco_cases": 14,
                "books_per_case": 1000, "scenarios": list(SCENARIOS), "denominators": [360, 365],
                "independent_reference": "hash-verified frozen Family-4 steps/accounting; missing full paths only",
                "stored_reference": str(reference.RESULT_REL).replace(chr(92), "/")},
            "parity": {**report, **counts}, "ic_sha256": readiness["ic_sha256"],
            "network_accessed": False, "noncontrol_economics_computed": False, "stage_b_accessed": False}
        exclusive_json(root/PARITY_REL, artifact)
        return root/PARITY_REL


def validate_control(root, readiness):
    root = Path(root)
    if not (root/PARITY_REL).is_file() or not (root/CONTROL_REL).is_file():
        raise IntegrityError("successful K4 parity/control evidence required")
    parity, control = _json(root/PARITY_REL), _json(root/CONTROL_REL)
    if parity.get("status") != "K4_CONTROL_PARITY_PASSED" or parity.get("parity", {}).get("mismatch_count") != 0:
        raise IntegrityError("K4 parity failed")
    if parity.get("preregistration_sha256") != PREREG_SHA256 or parity.get("source_sha256") != readiness["source_sha256"]:
        raise IntegrityError("stale K4 source/preregistration hashes")
    if parity.get("readiness_sha256") != _sha256(root/READINESS_REL):
        raise IntegrityError("stale K4 readiness hash")
    if parity.get("control_sha256") != _sha256(root/CONTROL_REL):
        raise IntegrityError("K4 control hash mismatch")
    if parity["archive"]["sha256"] != _sha256(root/CONTROL_PATHS_REL):
        raise IntegrityError("K4 path archive hash mismatch")
    if _canonical_sha(control["control_study"]["ic"]) != readiness["ic_sha256"]:
        raise IntegrityError("K4 IC hash mismatch")
    return control


def _validate_execution_authorization(root):
    path = Path(root)/CHECKPOINT_REL
    if not path.is_file():
        raise PermissionError("external infrastructure checkpoint and economics authorization required")
    value = _json(path)
    required = {"schema_version", "external_economics_authorized", "preregistration_sha256",
                "readiness_sha256", "parity_sha256", "source_sha256", "candidate_ids", "command"}
    if set(value) != required or value["schema_version"] != 1 or value["external_economics_authorized"] is not True:
        raise PermissionError("invalid explicit execution authorization")
    if value["preregistration_sha256"] != PREREG_SHA256 or value["candidate_ids"] != ["K3", "K5"]:
        raise IntegrityError("execution configuration differs")
    if value["command"] != "python -B run_family5_breadth.py execute-candidates":
        raise IntegrityError("unreviewed execution command")
    return value


def execute_candidates(root):
    root = Path(root)
    with offline():
        authorization = _validate_execution_authorization(root)
        readiness = validate_readiness(root)
        control = validate_control(root, readiness)
        if (authorization["readiness_sha256"] != _sha256(root/READINESS_REL) or
            authorization["parity_sha256"] != _sha256(root/PARITY_REL) or
            authorization["source_sha256"] != readiness["source_sha256"]):
            raise IntegrityError("stale execution authorization")
        paths_rel = REPORT_DIR/"family5-candidate-paths.jsonl.gz"
        for rel in (EXECUTION_REL, RESULT_REL, COMPLETION_REL, paths_rel):
            if (root/rel).exists():
                raise PermissionError("Family-5 economics already started/completed")
        exclusive_json(root/EXECUTION_REL, {"status": "ECONOMICS_STARTED", "consumption_count": 1,
            "candidate_ids": ["K3", "K5"], "authorization_sha256": _sha256(root/CHECKPOINT_REL),
            "readiness_sha256": _sha256(root/READINESS_REL), "parity_sha256": _sha256(root/PARITY_REL),
            "control_sha256": _sha256(root/CONTROL_REL), "preregistration_sha256": PREREG_SHA256})
        inputs = prepare_candidate(load_frozen_context(root), U14)
        sink = PathArchive(root/paths_rel)
        try:
            candidates = {cid: breadth_study(inputs, BreadthConfig(k), control["control_study"]["ic"], sink)
                          for cid, k in (("K3", 3), ("K5", 5))}
        finally:
            archive = sink.close()
        if immutable_sources(root) != readiness["source_sha256"]:
            raise IntegrityError("source changed during economics")
        archive["path"] = str(paths_rel).replace(chr(92), "/")
        result = {"status": "PENDING_EXTERNAL_ADJUDICATION", "adjudication_policy": ADJUDICATION_POLICY,
            "automatic_candidate_rejection_or_winner_selection": False,
            "preregistration_sha256": PREREG_SHA256, "execution_sha256": _sha256(root/EXECUTION_REL),
            "control_sha256": _sha256(root/CONTROL_REL), "control": control["control_study"],
            "candidates": candidates, "archive": archive, "network_accessed": False, "stage_b_accessed": False}
        exclusive_json(root/RESULT_REL, result)
        exclusive_json(root/COMPLETION_REL, {"status": "ECONOMICS_COMPLETED_PENDING_EXTERNAL_ADJUDICATION",
            "result_sha256": _sha256(root/RESULT_REL), "execution_sha256": _sha256(root/EXECUTION_REL),
            "consumption_count": 1, "network_accessed": False, "stage_b_accessed": False})
        return root/RESULT_REL
