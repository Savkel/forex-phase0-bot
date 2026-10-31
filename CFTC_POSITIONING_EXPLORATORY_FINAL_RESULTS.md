# CFTC positioning exploratory baseline: EXPLORATORY_NOT_SUPPORTED

External closure recorded 2026-10-31 under the user's
`CFTC_POSITIONING_EXPLORATORY_CLOSE_PUSH_SAVE` instruction, following read-only
adjudication of the completed one-shot. **EXPLORATORY_NOT_SUPPORTED** applies to
this frozen leveraged-fund yen-positioning fade. Strict PIT certification and
further optimization are not justified by its evidence. This is not a
validation-level rejection of all positioning mechanisms.

## Frozen authority and limitations

- Freeze: `62dfb7748208beedeadf5e3edae2a0982db7a364`.
- [Specification](prereg/2026-10-30-cftc-positioning-exploratory-prereg-draft.md) and
  [bindings](prereg/2026-10-30-cftc-positioning-exploratory-freeze.json) remain unchanged.
- USD/JPY only; sign of official CFTC TFF Futures Only leveraged-fund yen net/OI,
  faded with the frozen futures/spot mapping and deterministic 13/14-day lag.
  Monday 17:15 to Tuesday 16:45 America/New_York, cash across rollover.
- Pre-seal envelope `[2014-01-06T00:00Z,2024-01-06T00:00Z)`; 520 scheduled weeks,
  27 publication-blackout exclusions, seven further complete-case exclusions,
  486 supported observations (110 long USD/JPY; 376 short).
- Only 30 sign-runs; longest 105 weeks. Weeks and runs are not independent shocks.
  Current historical CFTC records may contain later revisions; the lag and documented
  blackout buffers do not certify original PIT vintages. Exclusions are retrospective
  evaluability controls, not guaranteed live information. Missingness may be nonrandom.
- Candle bid/ask opens are executable proxies, not guaranteed fills. Zero financing
  is conditional on the frozen v20 DAILY research convention; actual account mode
  remains unknown. No OOS, validation, significance or deployment claim follows.

## Verified results

Initial capital: JPY 10,000. Returns are cumulative; MaxDD is signed. Spread costs
are already included in the ledgers, measured against contemporaneous midpoint;
they must not be deducted twice. Financing is zero in both scenarios.

| Scenario / book | Net return | MaxDD | Spread costs, JPY |
|---|---:|---:|---:|
| Base strategy | -26.09649394% | -29.43574208% | 1,136.454693 |
| Base unit/gross-matched passive | +3.92544861% | -10.60084387% | 1,322.341923 |
| Doubled-half-spread strategy | -35.09414126% | -37.05123399% | 2,137.646093 |
| Doubled-half-spread passive | -8.74231327% | -13.19450998% | 2,478.181410 |

Passive fraction f=1; signed exposure normalization N/q=-0.5473251028806584.
Inherited alpha is strategy return minus N/q times unit-passive return; multiplying
a costed long return by a negative coefficient is not an executable short-book return.
Base alpha **-0.2394799737330223** and stress alpha **-0.39879028769545466** both fail
the positive-alpha requirement. Base strategy drawdown is deeper than the matched
passive, failing the third requirement. **Zero of three necessary requirements passed.**

Full-envelope descriptive CAGR, derived at adjudication using elapsed days/365.25:
base -2.97923245%, stress -4.23080874%; these are not added gates.
Long trades contributed -222.807786 JPY and short trades -2,386.841608 JPY to actual
portfolio P&L. Their separately compounded net returns were -2.64036039% and
-24.09225593%, respectively; those compounded percentages are not additive.

| Fixed block | Weeks | Base net / alpha | Stress net / alpha |
|---|---:|---:|---:|
| 2014-2016 | 153 | -6.372690% / -7.094469pp | -9.371886% / -11.390494pp |
| 2017-2019 | 138 | -4.247774% / -2.291554pp | -7.347348% / -7.003942pp |
| 2020-2024-01-05 | 195 | -17.564625% / -16.424371pp | -22.702917% / -26.020466pp |

Every fixed block is negative in both scenarios. Blocks remain adjudication evidence,
not additional automatic gates. Only 12 of 30 frozen sign-runs were positive;
median run return -0.191341%, best +1.525868%, worst -8.942467%. The worst run
(98 weeks, 2021-03-15 through 2023-01-23) contributed 28.6% of net loss; the worst
week contributed 11.1%. Broad losses are not explained by one isolated losing week.
These are descriptive aggregations of emitted ledgers, not reruns or selection.

The complete 486-rotation diagnostic has 382 exceedances including identity/ties:
descriptive rank p=382/486=0.7860082304526749 in both scenarios. This is neither
calibrated significance nor evidence supporting the inventory-alignment hypothesis.

## Immutable evidence and one-shot consumption

Directory: `reports/forex/cftc_positioning/economics_once_20261030/`.

| Artifact | SHA-256 |
|---|---|
| `attempt.json` | `8e162235b5d7a8fb47c083c453783955e664bd0fa232cbfb37480703bf08a1f8` |
| `result.json` | `1cc8291b1bed785210eeb4634b7ca45e2a37ac264259143f9a3c9bf98f406d9b` |
| `completion.json` | `9f28071debaa4fbb4cba4d4157b91d7c83367630a99afd873c946157c31d4a0d` |
| `base_ledger.npz` | `f748bb6dd34224b63b1b9b8b99f09ce0171d13ef1ee82f8e6275621a33fad3dd` |
| `base_strategy_trades.json` | `1ad923913fef418f609f1a48fab5abec31768d3af350a112500477f3ed5b40e8` |
| `base_passive_trades.json` | `e26c2326977dabe291ca07fc7781f4ead803240f12b543255193edd6652f4cee` |
| `spread_stress_ledger.npz` | `9513eebb1a679031883b05ef72ff0ca06ccc5aad1562dce9bf15c499e983fb7d` |
| `spread_stress_strategy_trades.json` | `1febefa217704d5b50e1b71a6425d3aa43d240d4e4387c961978337b247800c2` |
| `spread_stress_passive_trades.json` | `6f8d0f3b73783ffcc7b1d20b26b93993ba843f97891968b70ecb2bf1e9c72c56` |

One retained attempt began `2026-10-30T18:28:25.949723+00:00` and completed
`2026-10-30T18:28:29.162877+00:00`. Both markers record consumption_count=1;
the exclusive directory remains present with no failure artifact. Permission is
consumed: never rerun, delete/rename/reset the guard, or silently issue a new command.
Raw result/completion status remains **EXPLORATORY_COMPLETED_PENDING_EXTERNAL_REVIEW**;
this closure records the subsequent external disposition without rewriting evidence.

Closure reverified committed frozen sources/specification, all input and emitted-file
hashes, matching cohort, one-shot consumption and retained test evidence (80 passing
pre-economics tests, zero failures/errors). No tests, readiness computation, strategy,
rotation null or economics were rerun. No protected data was accessed. Generated
raw inputs, ledgers and reports remain local/gitignored with tracked hash bindings;
the repository alone is not a complete runnable evidence archive.

## Terminal governance

No strict PIT acquisition/certification, further optimization, post-hoc thresholds,
lag/holding-time changes, favorable direction/year/run subset, or renamed replay is
authorized. This closes the tested exploratory baseline, not every positioning
mechanism. Any genuinely distinct successor requires separate human authorization
and an independent preregistration; none is selected. Fiscal NOK and VIX/JPY remain
DATA_BLOCKED, not scientifically rejected. Prior closures and frozen carry remain
unchanged; no Family 7, sealed Phase-2A confirmation or carry Stage-B access follows.
