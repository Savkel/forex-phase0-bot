# Family-3 carry-strength-weighting final results

## Execution provenance

The user manually ran the frozen one-shot command from a separate PowerShell:

`python -B run_family3_weighting.py execute-candidates`

Codex did not run the Family-3 candidate economics. The single manual execution completed as
`FAMILY3_ECONOMICS_COMPLETE`; the execution artifact records `consumption_count=1` and all
execution, result, and completion integrity links match. No network access occurred.

## External adjudication

Family 3 is closed. Retain equal-weight `EQ_H2` (`tau=0`) as the historical DEVELOPMENT
configuration. `CS_MILD` (`tau=0.10`) and `CS_STRONG` (`tau=0.20`) remain valid DEVELOPMENT
results but are not selected. All results remain preserved unchanged.

Increasing carry-strength weighting increased financing contribution, but progressively worsened
net CAGR, RAP, positive-return Calmar, signed MaxDD, adverse/spread-x3 stress performance,
currency/routed turnover, spread cost, and concentration versus `EQ_H2`. Chronological block B2
remained negative and worsened as `tau` increased. No automatic gate selected or rejected any
candidate; this disposition is external adjudication.

| Configuration | D360 CAGR / RAP / Calmar / MaxDD | D365 CAGR / RAP / Calmar / MaxDD | Currency turnover | Spread cost D360/D365 | Financing D360/D365 | Adverse return D360/D365 | B2 return D360/D365 | Mean HHI |
|---|---|---|---:|---:|---:|---:|---:|---:|
| `EQ_H2` retained | 3.1238% / 0.09498 / 0.5118 / -6.1033% | 3.0971% / 0.09421 / 0.5059 / -6.1218% | 46.5000 | 2.2729% / 2.2721% | 6.4947% / 6.4030% | 5.7483% / 5.6924% | -1.4919% / -1.5157% | 0.125000 |
| `CS_MILD` | 3.0904% / 0.08840 / 0.4651 / -6.6449% | 3.0624% / 0.08764 / 0.4596 / -6.6635% | 47.3908 | 2.3651% / 2.3641% | 6.7900% / 6.6939% | 5.1710% / 5.1161% | -1.7716% / -1.7955% | 0.126428 |
| `CS_STRONG` | 3.0505% / 0.08216 / 0.4241 / -7.1925% | 3.0213% / 0.08142 / 0.4190 / -7.2111% | 48.2816 | 2.4697% / 2.4686% | 7.0850% / 6.9846% | 4.5611% / 4.5073% | -2.0616% / -2.0855% | 0.130712 |

This is exposed historical DEVELOPMENT evidence, not prospective OOS or trading permission.
`EQ_H2` does not replace the original frozen Stage-A/H0 strategy on its isolated prospective
Stage-B path.

## Immutable evidence

- Execution: `prereg/2026-08-22-tms-carry-unlevered-family-3-carry-strength-weighting-execution.json`, SHA-256 `3e231b9f94bdf5b8c8328b7d5af0a5115224c24829f5a8c4a95acc1cb72bd490`.
- Result: `reports/forex/family3/family3-carry-strength-weighting-result.json`, SHA-256 `88f00d40db42b568952c9866973d94e44ce7df481ddb0b8bdfe901a5419e86ac`.
- Completion: `reports/forex/family3/family3-carry-strength-weighting-completion.json`, SHA-256 `922eb763a35abfbee2973b253e17cff42433578168ca051871fcca326f45f17a`.
- Readiness: SHA-256 `9afc7f1140e48a3ff2f7ce5f181f56138c4e753f2a396a0d1ddc302c12b88890`.
- EQ_H2 parity: SHA-256 `6060e8aa81c2b17a12536abe46028159076fba959dac069fb636841c131a91e0`.

## Next gate

`FAMILY4_CONTROLLED_PARAMETER_DESIGN`
