# Tokyo-fix frozen baseline: CLOSED_FAIL

External closure authorized on 2026-09-24 in `TOKYO_FIX_CLOSE_PUSH_SAVE` after
read-only verification of the completed one-shot. **The frozen USD/JPY long
09:00-09:45 JST baseline is CLOSED_FAIL: zero of three frozen economic
requirements passed.** This closes the tested baseline, not all possible
Tokyo-fixing mechanisms.

## Frozen authority and sample

- Original preregistration/governance/DAILY-venue assumption freeze: `36e786b36e0c6ea038f4548c95cd92c2691b0816`.
- Complete-case amendment, exact mask, implementation and readiness freeze: `0a0872c79cd754601ee4f1fe16f21d16f454f428`.
- [Preregistration](prereg/2026-09-23-tokyo-fix-baseline-prereg-draft.md), [complete-case amendment](prereg/2026-09-24-tokyo-fix-complete-case-amendment.md), [frozen dates](prereg/2026-09-24-tokyo-fix-complete-case-dates.json), [freeze bindings](provenance/tokyo_pre_economics_freeze.json).
- Historical DEVELOPMENT envelope: `[2014-01-06T00:00Z, 2024-01-06T00:00Z)`.
- 2,446 calendar-eligible dates; one original envelope exclusion; 44 common data exclusions out of 2,445 (1.799591%); 2,401 paired evaluable dates. All 983 required absent timestamps and the full availability map remain preserved. No repaired/interpolated price series was created.

## Emitted economics (cumulative, not annualized)

| Cost case / leg | Net return | MaxDD |
|---|---:|---:|
| base / primary | -18.014368339491% | -18.969730258441% |
| base / unit_passive | -19.488618376940% | -36.976731154961% |
| base / matched_passive | -0.596119776193% | -1.408586734471% |
| stress / primary | -40.783151582552% | -41.333209434335% |
| stress / unit_passive | -59.260905195376% | -63.114548963459% |
| stress / matched_passive | -2.753066327195% | -3.070908781879% |

The passive constant fraction is the frozen `f=G/q=0.031914893617021274`;
alpha uses `R_primary-(N/q)*R_unit_passive`, not raw buy-and-hold comparison.

| Frozen requirement | Emitted evidence | Outcome |
|---|---|---|
| Base normalized alpha > 0 | -0.17392391157247847 | FAIL |
| Doubled-half-spread normalized alpha > 0 | -0.3889184609759322 | FAIL |
| Base primary MaxDD >= matched-passive MaxDD (signed) | -0.18969730258440576 < -0.014085867344707959 | FAIL |

Timing contrast remains positive: base mean `0.00012255136631729967`
(1.225513663173 bp/date), stress mean `0.00014838683104991757`
(1.483868310499 bp/date). Both have zero exceedances and exact one-sided
bootstrap p-value `1/10001 = 0.00009999000099990002` under the frozen centered
circular 20-date / 10,000-replicate / PCG64-20260923 test. The common start-matrix
SHA-256 is `226d44e0ea274190f56abf203f2749a3d24c7d207b18ec3e104415bdf57224f9`.
This is **relative timing evidence only**, not profitability or proof of a
fixing-specific causal mechanism. The controls lose more. There was no
preregistered numerical timing significance gate; the favorable timing evidence
does not override any failed economic requirement.

| Fixed chronological block | Paired dates / excluded | Base primary net / alpha | Stress primary net / alpha |
|---|---:|---:|---:|
| 2014_2016 | 720 / 12 | -9.188359% / -8.829895% | -18.251550% / -17.450072% |
| 2017_2020 | 952 / 24 | -5.996007% / -5.328670% | -17.043459% / -15.783831% |
| 2021_end | 729 / 8 | -3.960493% / -4.428923% | -12.679718% / -12.356471% |

Every fixed block has negative primary returns and negative normalized alpha in
both cost cases. Blocks are descriptive evidence for external adjudication,
not additional automatic gates. Complete-case missingness may be nonrandom;
results do not cover excluded dates, untouched OOS, guaranteed candle-open
fills or account-specific execution feasibility. Actual account financing mode
remains UNKNOWN; zero financing is conditional on the frozen DAILY research venue.

## Immutable evidence and consumed one-shot

Evidence directory: `reports/forex/tokyo_fix/economics_once_complete_case_20260924/`.

| Artifact | SHA-256 |
|---|---|
| `execution.json` | `4a6a21d60594db120e8491d99c7c7ff193605c7d372ce2266366eb31476ba2bd` |
| `results.json` | `e76505e55be0b746ab48284ab9999cc005d76aa1fc198fa7d0e8d0951df32c7b` |
| `daily_ledgers.json` | `d67993c979a1e888fcdf6bdd69e48f3ff90ab3923d57b67460281a2972de4c1d` |
| `curves_bootstrap.npz` | `1e1311a6da36d4d43eb90202d1b53a826c9eb3634725c3907da1fb47074b346f` |
| `completion.json` | `c63d40e07b211f1cdc8cd22977d27714de830e544c7deaac9d57f830288207c3` |

One retained scientific attempt started `2026-09-24T17:50:53.644313+00:00` and completed
`2026-09-24T17:51:02.723024+00:00`. The exclusive attempt directory, `STARTED_NO_RETRY`
marker and valid completion are present; no failure artifact exists. One-shot
permission is consumed. Do not rerun the command or remove/rename its guard.

The immutable result disposition remains `CLOSED_FAIL`; completion remains
`ECONOMICS_COMPLETED_PENDING_EXTERNAL_ADJUDICATION`. This document records the
subsequent user-authorized final closure without editing emitted artifacts.
Closure reverified result/archive/ledger/marker hashes, committed source/specification
bindings, preserved readiness and test evidence. The 125 passing focused tests
are pre-economics evidence; no tests, strategy calculations, bootstrap or economics
were rerun for closure. No sealed Phase-2A or carry Stage-B data was accessed.

## No rescue and next gate

No post-hoc tuning, altered timings/days/filters/costs/thresholds/mask, parameter
search, relabeling or rerun may rescue this baseline. Preserve positive timing
and all negative economic evidence together. Broader Tokyo-fixing mechanisms
remain eligible only as **separately authorized, independently preregistered new
research**, never a renamed or adjusted replay of this closed baseline.
No next experiment is selected or authorized by closure. Await a separate external
research decision. Carry remains closed to sequential optimization; retained
DEVELOPMENT is `U14 + H2 + EQ + M1 + k=4 + HURDLE_OFF_CONTROL`; no Family 7.
Phase-2A confirmation and carry Stage B remain sealed. No trading permission follows.
