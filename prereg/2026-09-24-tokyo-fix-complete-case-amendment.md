# Pre-economics complete-case evaluability amendment

## Authority and preserved history

On 2026-09-24 the user explicitly authorized gate
`TOKYO_FIX_COMPLETE_CASE_REPAIR_AND_READINESS`, after freezing the full OANDA
availability map and before any Tokyo economics. The approval states:

> Use a GENERAL pre-economics complete-case rule:
> - calendar rules determine economic eligibility;
> - data completeness determines evaluability only;
> - an eligible date is evaluable iff ALL frozen required observations for primary, both timing controls and passive benchmark exist and validate;
> - if any required observation is absent, exclude that entire date from ALL matched legs;
> - never interpolate, synthesize, delay execution or selectively drop individual legs;
> - freeze the exact excluded-date set before economics;
> - report exclusion count/rate and preserve the full gap map.

This general rule applies to matched research legs, not to a particular signal,
instrument, clock window, return direction or result. It is an externally authorized
change to **evaluability**, not merely a restatement of the old missingness policy.
The original preregistration remains unchanged at freeze commit
`36e786b36e0c6ea038f4548c95cd92c2691b0816`, SHA-256
`38fe09cde8f98f0b8dab159f4d9acb9c3bb0a493b2951b04510f1eafb3328f4b`.
Its no-complete-case and all-2,445-date invalidation language in Sections 4, 5,
6 and 9 is superseded only as necessary to apply this approved common-date mask.
The original failed readiness and every acquisition/diagnostic artifact are retained.
`CLAUDE.md` and the general intraday passive benchmark amendment are unchanged.

## Frozen observations and sample

Required observations include every primary/control/passive entry, intermediate,
exit and preceding decision bar already specified. Quote validity includes complete
bars, finite positive ordered bid/ask OHLC, valid volume, consistent UTC timestamps,
and executable base/stress opens. Identity, schema, duplicate/order or seal failures
remain global integrity blockers; they are not opportunities to select dates.
The independently verified permitted cache has no invalid candles. All 983 missing
required timestamps are absent from the queried OANDA practice M15 BA endpoint;
there are zero recoverable or unresolved classifications. This is not a claim
about every possible OANDA archive.

The exact ordered included/excluded-date manifest, including missing timestamps
and fixed reasons, is [complete-case-dates.json](2026-09-24-tokyo-fix-complete-case-dates.json),
SHA-256 `a72c47b72465a215cc310e1241e1fdf180adeec71018238112bdad54f793f0ca`.
The original isolated cache remains byte-for-byte unchanged; no derived price cache
or synthetic bar is needed. Calendar eligibility remains 2,446 dates. The original
2014-01-06 envelope exclusion remains separate, leaving 2,445 boundary-evaluable
dates. The frozen common data exclusion removes 44 dates (44/2,445 = 1.79959100204499%),
leaving 2,401 evaluable dates. Including the original boundary exclusion, 45/2,446
calendar-eligible dates are not evaluable. No further exclusions may be discovered
silently during economics: disagreement with this mask blocks execution.

Preserve and bind the full map:

- `data/forex_ohlcv/tokyo_fix_gap_repair/classification_20260924T135846_438176Z/classification_manifest.json`:
  `1828b2a89b81be880e1b4d72211c01d08028f45a9c948b0351d24f23434e9b64`.
- Its `gap_classification.json`:
  `5d3a7fe9d91a78d9d0feb48d8e5443c6492f209a58df49707f4e7f894b655e6c`.
- The manifest binds all 41 new raw responses and two reused, hash-verified
  diagnostic absences; readiness revalidates that evidence and original inputs.

## Application without other scientific changes

Apply the same frozen date mask to the primary, both controls, unit passive and
matched passive. Excluded dates produce no observations in any paired comparison.
All books remain cash between retained holding windows and compound without equity
resets. Retain the full original permitted M15 grid, including cash intervals, as
the common exposure denominator; recompute the same schedule-defined N, G, q and
f=G/q on the masked schedules. Never cap f, modify the strategy or fit drawdown.

The paired-date bootstrap operates on the chronologically ordered **2,401 evaluable
paired dates**. Twenty consecutive indices now refer to this frozen common sample;
excluded dates do not become zero returns or replacement observations. Preserve
20-date circular blocks, 10,000 replicates, PCG64 seed 20260923, one-time centering,
row-major starts, wrap/truncation, fsum, ties and exact plus-one p-value arithmetic.
Any missing/nonfinite D among these retained dates still invalidates the test;
no additional complete-case selection is allowed. Base/stress share one start matrix.
There is no new significance threshold or automatic chronological-block gate.

Signal, primary/control/passive timings, direction, sizes, calendar, research
envelope, exact cash/units ledger, incremental spread costs, stress and zero financing
under the explicit DAILY venue assumption remain unchanged. Existing alpha and
drawdown kill tests remain mandatory. Report exclusions and coverage overall and
within the original chronological blocks; retain all negative evidence.

The estimand is conditional on the frozen historical complete-case sample. Missingness
may be nonrandom. A future-dependent availability mask is not a live signal or a
claim that missing bars were predictable before entry. Results cannot establish
performance on excluded dates or feasibility on an actual account. Execution intent
and sizing on retained dates remain causal. No economics has been inspected to choose
the mask; after economics starts neither mask nor methodology may change.

## Readiness and authorization boundary

Bind this amendment, date manifest, unchanged original authorities, all implementation
and test sources, runtime versions and completed synthetic/structural checks before
the one-shot command can execute. The current gate authorizes implementation and
readiness only. It does not authorize running economics, fetching data, accessing
sealed Phase-2A prices or Stage B, committing, pushing, or updating memory.
