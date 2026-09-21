# Family-5 portfolio-breadth final results

## External adjudication

Family 5 is CLOSED by explicit external adjudication on 2026-09-21. Retain `K4_CONTROL`
(`k=4`) for historical DEVELOPMENT. K3 and K5 remain valid, immutable DEVELOPMENT results
but are not selected. No automatic winner/rejection rule made this decision.

The retained DEVELOPMENT configuration remains **U14 + H2 (h=2) + EQ + M1 weekly cadence + k=4**,
with long sleeve +1, short sleeve -1, currency gross 2, and active magnitude 1/4.
All original Stage-A evidence is immutable; the original Stage-A U14/k4/H0 strategy remains
the sole frozen strategy for isolated prospective Stage B. This closure is historical DEVELOPMENT
evidence, not prospective OOS or trading permission.

Raw result/candidate dispositions remain `PENDING_EXTERNAL_ADJUDICATION` and the completion
remains `ECONOMICS_COMPLETED_PENDING_EXTERNAL_ADJUDICATION`. They are intentionally preserved
unchanged; this document records the subsequent external decision.

## Execution and operational recovery provenance

- Frozen prereg commit: `f41f8524c30cd45ae48000127d2452baca1795af`.
- Approved implementation checkpoint: `2c64264ea9d7618c258bc81c69b5fbe3c63e0e5b`.
- Original economics authorization commit: `69e78605dddf45a1bf23a514393d71fb6c825c12`.
- Separate ENOSPC recovery authorization commit: `7f07e54ad21aed9aadcdbd9b47e8f7bbfdbfdbe4`.
- Both operational attempts used the identical manually launched command:
  `python -B run_family5_breadth.py execute-candidates`.

The first attempt ended incomplete solely because of `OSError [Errno 28] No space left on device`
(ENOSPC). It produced no valid result/completion artifact. K3 had finished all 15 cases in the
process; K5 had finished FULL and AUD-LOCO and persisted CAD-LOCO through zero-based benchmark
index 686, including spread_x3/D365. This partial computation did not constitute a completed
scientific result. The damaged candidate archive held 105,460 complete records and an unfinished
gzip tail, occupied 8,471,757,436 bytes, and had SHA-256
`1e6f938b8f198dcc892cefd77cbe4fdddc420f54c81ae8307e06f4fdaba1c10f`.
Its last write was 2026-09-21 12:20:06 UTC.

Under separate explicit external operational-recovery adjudication, that archive was hash-verified
and deleted as unnecessary incomplete operational output. A concise audit and retry authorization
were committed; the original marker was preserved byte-for-byte as
`prereg/2026-09-20-tms-carry-unlevered-family-5-portfolio-breadth-execution-attempt-1-enospc.json`.
Only the failed marker was relocated to clear the existing execution guard. Frozen code, prereg,
original authorization, inputs, seeds/books, readiness, parity and successful K4 evidence were
unchanged. Free space exceeded the authorized 20,000,000,000-byte minimum before the retry.

The separately authorized clean retry recomputed K3 then K5 with identical scientific semantics
and reused the successful hash-bound K4 control. It completed successfully on
2026-09-21 at 19:02:52 UTC. There were two operational attempts and one successful scientific
completion: this was neither tuning nor a second scientific result. No partial-result reuse,
parameter adjustment, data fetch, or outcome-dependent code change occurred.

The successful marker and completion record `consumption_count=1`. The old and new execution
markers have identical contents and SHA-256 because the frozen CLI has no attempt identifier.
Attempt lineage is established by the committed recovery sidecar, its preserved prior-marker
contents, and the artifact chronology; the marker hash alone does not distinguish attempts.
The completed result/completion/archive and all negative evidence must remain immutable.
No further execution is authorized.

## Verification and completeness

Post-execution verification matched the frozen source/input/readiness bindings (35 source files
and 13 price caches), authorization, parity, exact K4 payload reuse, and completion/result/marker
hashes. The frozen offline code and result/completion flags record no Stage-B or network access.
Closure preparation rechecked all 13 Family-5 evidence hashes and all 35 source hashes.

K3 and K5 each completed FULL plus all 14 fixed-k LOCO cases, with 1,000 matched static books
per case, base/adverse/spread_x3 scenarios, both D360/D365, and all B1/B2/B3 blocks.
The successful candidate archive contains 178,660 records: K3 has 90 strategy paths, 89,196
unique-book scenario/denominator paths and 134 duplicate-book references; K5 has 90, 88,980
and 170 respectively. Duplicate multiplicity/order are preserved. The archive occupies
15,789,358,836 bytes (60,058,542,474 bytes uncompressed). The prior read-only verification
checked every ordered record identity/duplicate reference, compressed and uncompressed hashes,
gzip CRC/end-of-stream, and all 1,260 thousand-element report distributions across K3/K4/K5.
The unchanged reusable K4 archive contains 89,455 records.

The approved implementation checkpoint records 75 focused and 697 full-suite passing tests.
These historical checks were verified from its commit message; tests were not rerun for closure.
K4 parity evidence records 1,349,231,725 numeric and 540,074,611 discrete comparisons, zero
numeric/discrete/shape mismatches, and maximum absolute delta 1.4210854715202004e-14 against
tolerance 1e-12. Neither parity nor economics was rerun during verification or closure.

## Decision-relevant results

Pairs are D360 / D365; unpaired values are denominator-invariant. Attribution is percent of
initial equity; spread cost is positive and subtracted. Signed MaxDD is negative. Positive
matched MDD difference (percentage points) means shallower drawdown than the matched median.
RAP/Calmar are ratios. Turnover values are cumulative over the frozen sample.

| Metric | K3 (valid, not selected) | K4_CONTROL (retained) | K5 (valid, not selected) |
|---|---:|---:|---:|
| CAGR % | 2.5897 / 2.5625 | 3.1238 / 3.0971 | 2.4030 / 2.3822 |
| Total return % | 8.9000 / 8.8038 | 10.8020 / 10.7063 | 8.2406 / 8.1673 |
| RAP | 0.0641 / 0.0635 | 0.0950 / 0.0942 | 0.0863 / 0.0856 |
| Calmar | 0.2694 / 0.2653 | 0.5118 / 0.5059 | 0.4674 / 0.4601 |
| MaxDD % | -9.6130 / -9.6598 | -6.1033 / -6.1218 | -5.1414 / -5.1776 |
| Matched benchmark RAP excess | 0.1237 / 0.1228 | 0.1586 / 0.1570 | 0.1632 / 0.1615 |
| Matched benchmark MDD difference, pp | 1.1422 / 1.0824 | 3.7306 / 3.7106 | 4.2491 / 4.1669 |
| Adverse return % | 1.8821 / 1.8469 | 5.7483 / 5.6924 | 3.9264 / 3.8857 |
| Spread x3 return % | 3.1072 / 3.0161 | 5.9853 / 5.8937 | 4.0383 / 3.9678 |
| B1 return % | 2.8176 / 2.7711 | 3.4245 / 3.3833 | 2.1012 / 2.0656 |
| B2 return % | -3.7259 / -3.7489 | -1.4919 / -1.5157 | -0.0600 / -0.0773 |
| B3 return % | 10.0147 / 9.9935 | 8.7557 / 8.7313 | 6.0767 / 6.0601 |
| Financing % | 6.5581 / 6.4654 | 6.4947 / 6.4030 | 5.0620 / 4.9910 |
| Spot P&L % | 5.1017 / 5.0970 | 6.5802 / 6.5754 | 5.1895 / 5.1865 |
| Spread cost % | 2.7599 / 2.7587 | 2.2729 / 2.2721 | 2.0109 / 2.0102 |
| Currency turnover | 47.3333 / 47.3333 | 46.5000 / 46.5000 | 46.4000 / 46.4000 |
| Routed turnover | 60.7021 / 60.6740 | 47.9579 / 47.9382 | 45.7607 / 45.7444 |
| Mean routed gross | 2.3963 / 2.3950 | 1.8299 / 1.8290 | 1.7699 / 1.7692 |
| Maximum routed gross | 2.9457 / 2.9432 | 2.2366 / 2.2347 | 2.2714 / 2.2703 |
| Trades/fills | 1159 | 1284 | 1510 |
| Gross-normalized HHI | 0.1667 | 0.1250 | 0.1000 |
| Currencies selected at all 157 evaluable decisions | 4 | 5 | 6 |

Ordinary long/short replacements are 4/1, 4/1 and 4/2 for K3/K4/K5; within-k suppressed
replacements are 53, 92 and 108. These persistence diagnostics do not imply continuous holdings
across gaps; frozen gap exit/reset/re-entry and terminal-flat semantics remain operative.

## LOCO tails and retained negative evidence

Every configuration has positive baseline total return and positive benchmark RAP excess in
14/14 omissions under both denominators. Stress tails can nevertheless be negative. Each cell
below identifies the omission producing that metric minimum; minima need not share an omission.

| Candidate / denominator | Minimum CAGR % | Minimum total return % | Deepest MaxDD % | Minimum RAP excess | Minimum MDD difference, pp | Minimum adverse return % | Minimum spread x3 return % |
|---|---|---|---|---|---|---|---|
| K3 / D360 | 0.3064 (JPY) | 1.0255 (JPY) | -11.0391 (JPY) | 0.0756 (JPY) | -0.3498 (JPY) | -4.0508 (JPY) | -4.2301 (JPY) |
| K3 / D365 | 0.2833 (JPY) | 0.9477 (JPY) | -11.0766 (JPY) | 0.0745 (JPY) | -0.4554 (JPY) | -4.0921 (JPY) | -4.3039 (JPY) |
| K4_CONTROL / D360 | 1.2104 (PLN) | 4.0938 (PLN) | -9.7245 (PLN) | 0.1066 (PLN) | 0.1715 (PLN) | -0.1469 (PLN) | 0.0092 (PLN) |
| K4_CONTROL / D365 | 1.1837 (PLN) | 4.0020 (PLN) | -9.7693 (PLN) | 0.1052 (PLN) | 0.1035 (PLN) | -0.2055 (PLN) | -0.0790 (PLN) |
| K5 / D360 | 0.8143 (JPY) | 2.7414 (JPY) | -6.4650 (NOK) | 0.1150 (JPY) | 2.9359 (NOK) | -1.1159 (JPY) | -1.5536 (JPY) |
| K5 / D365 | 0.8008 (JPY) | 2.6954 (JPY) | -6.4998 (NOK) | 0.1140 (JPY) | 2.8442 (NOK) | -1.1373 (JPY) | -1.5977 (JPY) |

K3 has deeper drawdowns, higher routed turnover/costs, weaker B2 and worse stress tails than K4.
K5 lowers drawdown, concentration, spread cost and B2 losses and has higher matched RAP excess,
but lower raw RAP, CAGR, financing, spot contribution and full-sample stress returns than K4.
Candidate-matched benchmarks differ with k; higher RAP excess is not the same claim as higher
raw RAP. B2 remains negative for all three candidates. Under D365 even K4 has negative adverse
and spread-x3 tails when PLN is omitted. All negative evidence and valid unselected results
are preserved; the recorded external preference for K4 does not invalidate K3 or K5.

## Immutable evidence ledger

Paths and SHA-256 below identify local artifact bytes, which remain unchanged. Report/archive
files are local and gitignored; execution markers remain local/untracked. This closure commits
only the final-results document and handoff, not those generated files.

| Artifact path | SHA-256 |
|---|---|
| `prereg/2026-09-20-tms-carry-unlevered-family-5-portfolio-breadth-prereg.md` | `af832109ca374fde71ab70a4f984e9fee0f996c09a6ecb0e64ddcab6fe947eb7` |
| `prereg/2026-09-20-tms-carry-unlevered-family-5-portfolio-breadth-execution-authorization.json` | `7155e6c7d7c47b57b60483dad3e9b25a9a684f11b6d26573fd2c7d134569acd4` |
| `prereg/2026-09-20-tms-carry-unlevered-family-5-portfolio-breadth-readiness.json` | `b24d796cb889d771d2be4540e55d68cbadfafaa62e6a792d39b20900f0da61e0` |
| `prereg/2026-09-20-tms-carry-unlevered-family-5-portfolio-breadth-k4-parity-start.json` | `ee29c32c2c9930059dc8c94cbb71b1bb6878b20e89e41bf515c736e1580a81c4` |
| `prereg/2026-09-20-tms-carry-unlevered-family-5-portfolio-breadth-k4-parity.json` | `eafe337788f6f67ed08a77abd95e335c57243fbb2ee98ab8ebb49c9b504e7a9b` |
| `prereg/2026-09-20-tms-carry-unlevered-family-5-portfolio-breadth-operational-recovery-authorization.json` | `91f9c5d73065e63eebc3e9fdbeccc0b4fcc77b55383f564b2da926efd7290fee` |
| `prereg/2026-09-20-tms-carry-unlevered-family-5-portfolio-breadth-execution-attempt-1-enospc.json` | `eb7cdf5c484e6b235d3e88c688d6efb40d3245c73357a345fe0f5c4f56708600` |
| `prereg/2026-09-20-tms-carry-unlevered-family-5-portfolio-breadth-execution.json` | `eb7cdf5c484e6b235d3e88c688d6efb40d3245c73357a345fe0f5c4f56708600` |
| `reports/forex/family5/family5-k4-control.json` | `e1518d90d3e78d52c53ee125181aa25ffa779637c3605b75b6030bd64a768137` |
| `reports/forex/family5/family5-k4-paths.jsonl.gz` | `92a3178b9a2196539edbecd3916c4e02dd976a73a4c1b060dd44d557fd4fa430` |
| `reports/forex/family5/family5-portfolio-breadth-result.json` | `5b7105375bc539b22a29e4278927e7515d9808a804173f2e17b9b1deeed6c883` |
| `reports/forex/family5/family5-portfolio-breadth-completion.json` | `4019102689c553768813c6e5bb410dcfca1643452669f27be839c3c082fc954d` |
| `reports/forex/family5/family5-candidate-paths.jsonl.gz` | `a50bad8d0d8c76918003170886e38442b931a778b271dc66717d9f8cef9aa165` |

Candidate archive uncompressed stream SHA-256:
`39ca1a32c80494456c90ff3cb6201ae998a73bbae48a2513695c3b5e4b489f6e`.
K4 archive uncompressed stream SHA-256:
`de19ba9f485444269ccfb890732e4c6d2c0d42a9c892fc9180278c68f19e5b90`.

The recovery authorization Git blob normalizes line endings and has SHA-256
`e1c23e49937db52ede5f7b871a3b54df91e97667187f46b2e8789695be404b7b`;
its local-byte hash above is different only for line endings. JSON contents were verified equal.

## Subsequent work

No subsequent research gate is defined by the current authoritative state. Do not infer a
Family-6 hypothesis or begin a design. Any further research requires separate external direction.
Family 5 is closed; no rerun, tuning, Stage-B substitution or trading authorization follows.
