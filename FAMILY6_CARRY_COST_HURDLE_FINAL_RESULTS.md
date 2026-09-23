# Family-6 carry-cost-hurdle final results

## External adjudication

Family 6 is CLOSED by explicit external adjudication on 2026-09-23. Retain
`HURDLE_OFF_CONTROL`, which is the unchanged Family-5 `K4_CONTROL`, for historical
DEVELOPMENT. `HURDLE_1X` and `HURDLE_2X` remain valid, immutable DEVELOPMENT results but
are not selected. No automatic winner or rejection rule made this decision.

The retained DEVELOPMENT configuration remains **U14 + H2 (`h=2`) + EQ + M1 weekly cadence
+ `k=4`**, with long sleeve +1, short sleeve -1, currency gross 2 and no extra leverage or
risk scaling. The original Stage-A U14/k4/H0 strategy remains isolated and unchanged for any
separately authorized prospective Stage B. This closure is neither prospective OOS evidence nor
trading permission.

Raw candidate dispositions remain `PENDING_EXTERNAL_ADJUDICATION`; completion remains
`ECONOMICS_COMPLETED_PENDING_EXTERNAL_ADJUDICATION`. Emitted evidence is preserved unchanged.
This document records the subsequent external decision.

## Execution and verification provenance

- Frozen preregistration commit: `a34c0fec0ceaafd4f7fc05e9ae32fce544a8fb5d`.
- Approved hurdle implementation checkpoint: `e79facfb3a6ca3ac208382cfd5752935a7eaee66`.
- Economics execution layer: `6b8823ab18521a1cecef7606f33837867bedb25d`.
- Authorization-guard fix: `f27ec7fb9a47487a1b4e62fe1ef20245cb53b6b2`.
- One-shot execution authorization: `80d72b748ed52f8ec6836de8a955082dfe6e9f63`.
- Manually launched command: `python -B run_family6_economics.py execute-candidates`.
- Fixed order: `HURDLE_1X` then `HURDLE_2X`.

There was one operational attempt and one completed scientific execution. Execution and
completion record scientific consumption count 1; no recovery authorization or retry exists.
The candidate archive contains exactly 180 unique ordered cells: two candidates, FULL plus all
14 LOCO omissions, three scenarios and D360/D365. Its compressed and uncompressed hashes, gzip
stream, record identities and first/last order were verified. The 180 paths had identical target
weight schedules across stress and denominator cells. Maximum stored accounting-identity residual
was `1.0047518372857667e-14`; hurdle decisions had zero threshold violations and no non-finite
values.

Frozen preregistration, readiness, source, price-cache, signal, route, financing-event and causal
schedule bindings revalidated. Family-6 CONTROL parity has zero mismatches and maximum difference
0.0 at tolerance `1e-12`. The exact immutable Family-5 K4 benchmark and IC evidence were hash-
reused for all 15 cases. Execution, result and completion record no network or Stage-B access.
No tests, parity or economics were rerun for closure.

## Decision-relevant results

Pairs are D360 / D365. Percentages are of initial equity except RAP, Calmar and turnover. Spread
cost is positive and subtracted. Signed MaxDD is negative; positive matched MDD difference means a
shallower drawdown than the fixed K4 benchmark median.

| Metric | HURDLE_OFF_CONTROL retained | HURDLE_1X valid, unselected | HURDLE_2X valid, unselected |
|---|---:|---:|---:|
| CAGR % | 3.1238 / 3.0971 | 2.7699 / 2.7432 | 3.0348 / 3.0081 |
| Total return % | 10.8020 / 10.7063 | 9.5391 / 9.4444 | 10.4837 / 10.3881 |
| RAP | 0.0950 / 0.0942 | 0.0846 / 0.0838 | 0.0927 / 0.0919 |
| Calmar | 0.5118 / 0.5059 | 0.4371 / 0.4315 | 0.5288 / 0.5223 |
| MaxDD % | -6.1033 / -6.1218 | -6.3375 / -6.3570 | -5.7395 / -5.7591 |
| Matched benchmark RAP excess | 0.1586 / 0.1570 | 0.1482 / 0.1466 | 0.1563 / 0.1547 |
| Matched benchmark MDD difference, pp | 3.7306 / 3.7106 | 3.4963 / 3.4754 | 4.0943 / 4.0734 |
| Adverse return % | 5.7483 / 5.6924 | 4.6457 / 4.5899 | 5.5478 / 5.4915 |
| Spread x3 return % | 5.9853 / 5.8937 | 4.9308 / 4.8400 | 5.8349 / 5.7433 |
| B1 return % | 3.4245 / 3.3833 | 2.5899 / 2.5496 | 2.8180 / 2.7777 |
| B2 return % | -1.4919 / -1.5157 | -1.7377 / -1.7623 | -1.1103 / -1.1351 |
| B3 return % | 8.7557 / 8.7313 | 8.6620 / 8.6379 | 8.6620 / 8.6379 |
| Financing % | 6.4947 / 6.4030 | 6.4572 / 6.3660 | 6.4856 / 6.3939 |
| Spot P&L % | 6.5802 / 6.5754 | 5.2637 / 5.2594 | 6.1869 / 6.1821 |
| Spread cost % | 2.2729 / 2.2721 | 2.1818 / 2.1810 | 2.1888 / 2.1879 |
| Currency turnover | 46.5000 | 45.0000 | 44.5000 |
| Routed turnover | 47.9579 / 47.9382 | 45.0299 / 45.0116 | 45.2005 / 45.1821 |
| Trades/fills | 1284 | 1268 | 1277 |
| Gross-normalized HHI | 0.1250 | 0.1250 | 0.1250 |
| Hurdle accepts / vetoes | bypass | 2 / 11 | 1 / 20 |

## Practical mechanism interpretation

Both hurdles reduced currency/routed turnover, fill count and spread cost. Those savings were too
small to offset weaker realized holdings. Relative to CONTROL under D360, 1X saved 0.0911
percentage points of spread cost but lost 1.3165 points of spot P&L and 0.0375 points of financing;
2X saved 0.0841 points of spread cost but lost 0.3933 points of spot P&L and 0.0091 points of
financing. Thus avoided rotations lost more spot value than the costs they saved, and neither
hurdle improved net CAGR or RAP.

2X nevertheless produced genuine secondary improvements: shallower MaxDD, higher Calmar and a
less-negative B2 under both denominators. These did not compensate for lower full-sample CAGR,
total return, RAP, stresses and spot contribution. 1X also worsened drawdown and B2.

The effects came from few persistent episodes rather than broad diversification. 1X's 11 vetoes
formed four episodes and its accepted membership differed from CONTROL at 18/157 evaluable
decisions. 2X's 20 vetoes formed five episodes and differed at 20/157. Veto involvement centered
on PLN, NZD and CZK. All variants retained HHI 0.125 and five always-selected currencies; largest
selection-frequency changes were +5.1 percentage points for USD under 1X and +5.7 for CZK under
2X. No causal or accounting anomaly explains the result.

## LOCO tails and negative evidence

Each cell gives the minimum across 14 omissions; minima need not share an omission.

| Candidate / denominator | Minimum total return % | Deepest MaxDD % | Minimum RAP excess | Minimum MDD difference, pp | Minimum adverse % | Minimum spread x3 % |
|---|---:|---:|---:|---:|---:|---:|
| CONTROL / D360 | 4.0938 (PLN) | -9.7245 (PLN) | 0.1066 (PLN) | 0.1715 (PLN) | -0.1469 (PLN) | 0.0092 (PLN) |
| CONTROL / D365 | 4.0020 (PLN) | -9.7693 (PLN) | 0.1052 (PLN) | 0.1035 (PLN) | -0.2055 (PLN) | -0.0790 (PLN) |
| 1X / D360 | 3.8904 (PLN) | -9.9009 (PLN) | 0.1049 (PLN) | -0.0049 (PLN) | -0.3275 (PLN) | -0.1636 (PLN) |
| 1X / D365 | 3.7986 (PLN) | -9.9458 (PLN) | 0.1035 (PLN) | -0.0730 (PLN) | -0.3861 (PLN) | -0.2518 (PLN) |
| 2X / D360 | 4.4513 (PLN) | -9.4144 (PLN) | 0.1097 (PLN) | 0.4816 (PLN) | 0.2124 (PLN) | 0.3570 (JPY) |
| 2X / D365 | 4.3590 (PLN) | -9.4596 (PLN) | 0.1083 (PLN) | 0.4133 (PLN) | 0.1534 (PLN) | 0.2901 (PLN) |

All three configurations retain positive baseline return and benchmark RAP excess in every LOCO
case. Negative CONTROL/1X LOCO stress tails and all other negative evidence remain preserved.

## Immutable evidence ledger

| Artifact path | SHA-256 |
|---|---|
| `prereg/2026-09-22-tms-carry-unlevered-family-6-carry-cost-hurdle-prereg.md` | `38a75c3f821843e740401cc7255f83d621c8030ff013ba3170341ea534af6d1d` |
| `prereg/2026-09-22-tms-carry-unlevered-family-6-carry-cost-hurdle-readiness.json` | `2494984371ff670cb91da8104b84d2675a8145dea3247b6188673fd23822a3cf` |
| `prereg/2026-09-22-tms-carry-unlevered-family-6-carry-cost-hurdle-control-parity.json` | `49e25dab4d3ae254da75f8755271baa58190c5c46fcf2a02f18d27de3fb65d38` |
| `prereg/2026-09-22-tms-carry-unlevered-family-6-carry-cost-hurdle-execution-authorization.json` | `ada3b7b09645ff24217c50e5cf88a72795d113f02e693b4e893609e15c949c77` |
| `prereg/2026-09-22-tms-carry-unlevered-family-6-carry-cost-hurdle-execution.json` | `fa45e80edcf3e768bd850b1dbe895d85305ee4d94eca78c631935d974ac2463e` |
| `reports/forex/family6/family6-carry-cost-hurdle-result.json` | `53f4eb679fc2063231499dcf11793b8a7edb7677b6a0d6132132cc0e44a6ae6e` |
| `reports/forex/family6/family6-carry-cost-hurdle-completion.json` | `5114f2fae7cf7f9a3f532dbda5576a39d76e61fece855185587a1cdf535c64da` |
| `reports/forex/family6/family6-candidate-paths-attempt-1.jsonl.gz` | `db6ae7dc773495114aa82caf64ed0ee05f53e803b0291813ae1e1e64c5029199` |
| `reports/forex/family5/family5-k4-control.json` | `e1518d90d3e78d52c53ee125181aa25ffa779637c3605b75b6030bd64a768137` |

Candidate archive uncompressed-stream SHA-256:
`59e7e4d093bd1a4dda78fbb5938389dc4022081e5dc730381a4360eb8291174a`.

The execution-source hashes are `04abfea1...d361d37a` (guard/study),
`627967e3...497ffe29b` (CLI) and `49947c72...fb5caa50` (focused tests), exactly matching
authorization, marker, result and completion. Generated result/completion/archive files are local
and gitignored; the execution marker is local/untracked. This closure commits neither generated
evidence nor any prior-family artifact.

## Subsequent work

Further sequential unlevered optimization is **STOPPED**. Family 6 is the final closed family in
this sequence; do not infer or open Family 7. No new research stage is currently defined. Any
future work requires separate external authorization and its own governance/preregistration.
Prospective Stage B for the original frozen Stage-A strategy remains isolated and untouched; it is
not automatically opened by this closure.
