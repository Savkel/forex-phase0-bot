# Family-2 rank-hysteresis final results

## External adjudication

Family 2 is closed. Select `H2` (`h=2`) as the historical DEVELOPMENT configuration for
subsequent optimization. H0/H1/H2/H3 remain valid and preserved unchanged. H1 and H3 are not
selected. Diagnostic thresholds were not automatic gates; this disposition is external review.

Relative to H0, H2 improved net CAGR, RAP, positive-return Calmar, signed MaxDD, currency/routed
turnover, spread cost, adverse and spread-x3 returns, and worst LOCO stress tails under both D360
and D365. H3 remains credible DEVELOPMENT evidence but was not selected. Every configuration's
B2 return remained negative and must stay visible.

| Configuration | D360 CAGR / RAP / Calmar / MaxDD | D365 CAGR / RAP / Calmar / MaxDD | Currency / routed turnover D360 | Spread cost D360/D365 | Adverse return D360/D365 |
|---|---|---|---:|---:|---:|
| H0 control | 2.3394% / 0.06991 / 0.2813 / -8.3167% | 2.3138% / 0.06919 / 0.2776 / -8.3340% | 62.5 / 63.4107 | 2.6479% / 2.6468% | 2.4824% / 2.4340% |
| H1 | 2.1286% / 0.06583 / 0.2532 / -8.4071% | 2.1023% / 0.06507 / 0.2495 / -8.4256% | 51.0 / 50.9879 | 2.3046% / 2.3037% | 2.2652% / 2.2127% |
| H2 selected | 3.1238% / 0.09498 / 0.5118 / -6.1033% | 3.0971% / 0.09421 / 0.5059 / -6.1218% | 46.5 / 47.9579 | 2.2729% / 2.2721% | 5.7483% / 5.6924% |
| H3 | 3.0077% / 0.09146 / 0.5081 / -5.9198% | 2.9811% / 0.09069 / 0.5020 / -5.9384% | 46.0 / 47.2707 | 2.2629% / 2.2621% | 5.3451% / 5.2899% |

H2's worst adverse LOCO was PLN at `-0.1469%/-0.2055%` D360/D365; worst spread-x3 LOCO was
PLN at `+0.0092%/-0.0790%`. Corresponding benchmark-relative RAP excess remained
`+0.10657/+0.10523`. H2 B2 return was `-1.4919%/-1.5157%`.

This is exposed historical DEVELOPMENT evidence, not prospective OOS or trading permission. H2
does not replace the original frozen Stage-A/H0 strategy on its isolated prospective Stage-B path.

## Immutable evidence

- Execution: `prereg/2026-08-22-tms-carry-unlevered-family-2-rank-hysteresis-execution.json`,
  SHA-256 `705e6ab6b3863a726dad77d2665a10f0c0c6e6e76308feb738f3879426a36f2d`.
- Result: `reports/forex/family2/family2-rank-hysteresis-result.json`, SHA-256
  `04c7d5bf34fef2b8a80dccf9e1cce2543bb1a49f32482e745526311bc754247c`.
- Completion: `reports/forex/family2/family2-rank-hysteresis-completion.json`, SHA-256
  `3f23c7a02bcfb5f003f0882d25fabe739e3c5f5f0b48c1091f530d000154abb0`.
- Frozen preregistration SHA-256:
  `d839767097b8b2d6a5043ae7e8e0c92c2255404f72814daa8a26627404b934e1`.
- Readiness SHA-256: `68c45ee6f162d84a033ce25aeea2de02a8187f484d4f2faf34a495055427e4a7`.
- H0 parity SHA-256: `0ced81728ed3678877b63cd8008f05a8436802aba072c35f50c0456863669641`.

## Next gate

`FAMILY3_CARRY_STRENGTH_WEIGHTING_DESIGN`
