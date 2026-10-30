# CFTC leveraged-fund positioning: frozen exploratory preregistration

Status: **EXPLORATORY_ONLY / FROZEN_PRE_ECONOMICS**.
Gate: `CFTC_POSITIONING_EXPLORATORY_DESIGN`, authorized by the user before economics.
Repository at design: `95a5193af76bbbc4d4b553af56701e3da8d2a084`.
The original design gate authorized no backtest, FX return calculation, validation
result, implementation, commit or push. The subsequent freeze authorization below
supersedes that preparation restriction. This is one baseline, not a parameter menu.

Freeze authorization: the user's `CFTC_POSITIONING_EXPLORATORY_FREEZE_AND_RUNNER`
gate approves finalization, a local freeze, required official data acquisition,
implementation, synthetic tests and readiness, but **not agent execution on research prices**. The filename
retains its draft suffix for continuity; this status and the freeze record govern.
The earlier design-gate descriptions below remain historical audit context.

### Final frozen clarifications (2026-10-30; before economics)

- The sample is 486 supported weekly observations but only 30 contiguous sign-runs
  with exclusions breaking runs. Neither weeks nor runs are statistically independent.
  The 105-week longest run must remain visible in every emitted report.
- For each decision Monday m, compute t=m-13 calendar days: this is the Tuesday of
  the reporting week two weeks before m. Require exactly one official observation
  on t or the preceding Monday. Its actual date is r. Thus m-r is exactly 13 days
  (Tuesday) or 14 days (Monday holiday substitution), never a fitted lag or inferred
  release date. Decision is m 17:00 America/New_York; execution is m 17:15. This
  conservative rule is not a guarantee against undocumented delays or revisions.
- Long yen futures means long JPY/short USD. Fading positive normalized net yen
  positioning therefore means LONG USD_JPY; fading negative positioning means SHORT
  USD_JPY. Zero is cash. This mapping is invariant to prices and results.
- All outputs remain EXPLORATORY_ONLY, with no validation, statistical-significance,
  independent-event or prospective-OOS claim. The circular-rotation rank is descriptive
  even if numerically small. There is no significance threshold or automatic promotion.
- Acquire only the 520 required reporting-week rows, 2014-01-07 through 2023-12-19;
  omit the unused 2023-12-26 row from the prior 521-row feasibility request. The raw
  response hash will consequently differ. The previous raw response was not retained,
  so byte-level parity with that old response is not asserted; reproduce all frozen
  signal, continuity, exclusion and support counts before accepting the new binding.
- Initial JPY capital is 10,000, purely an accounting normalization. Benchmark f=1
  follows the frozen schedule/exposure formula. Chronological block alpha uses that
  block's schedule-derived N/q; it never fits exposure to realized returns. Report
  both base and stress requirements and the descriptive rank without a rescue path.
- A local freeze record will bind this specification, exact raw acquisition and
  provenance, weekly mask, readiness/test evidence, runtime and implementation hashes.
  The user-run command must verify its expected Git freeze commit and these identities
  before atomically claiming a single attempt; failed attempts remain consumed.

## Hypothesis and universe

Leveraged-fund futures positions can create crowded exposures whose liquidation
pressures the currency in the opposite direction. Test a simple net-position fade,
not a claim that every nonzero position is extreme or about to unwind. The input is
reported trader inventory, never FX price momentum/reversion, a breakout, carry,
VIX, a fixing calendar or fiscal conversions. Economic risk may overlap carry
unwinds; this is not proof of diversification from carry.

Use **USD_JPY only**, chosen for its already isolated, verified ten-year M15 bid/ask
input, not performance. Other currencies are not selected or rejected by economics.
CFTC TFF **Futures Only**, market code **097741**, Japanese Yen / Chicago Mercantile
Exchange; do not mix legacy categories, combined futures/options, other exchanges,
micro contracts, or OFR retrospectively consolidated series.

For a report, define `z=(lev_money_positions_long-lev_money_positions_short)/open_interest_all`.
Use the reported outright long/short fields; do not add spreading positions. OI must
be positive and both counts finite nonnegative integers no greater than OI.
CME yen futures quote USD per JPY, whereas spot USD_JPY quotes JPY per USD.
Therefore **z>0 -> long USD_JPY; z<0 -> short USD_JPY; z=0 -> cash**.
This is contrarian to the yen position. Normalize before taking the sign; magnitude
does not size exposure. Zero is the algebraic direction boundary, not an optimized
crowding threshold. No percentiles, lookbacks, changes, price filters or carry inputs.

The CFTC market-level report aggregates contract expiries; no front-month futures
price splice or roll rule is used. In the inspected 2014-2023 extract, all 521 rows
have the same market name/code, one observation per reporting week, 512 seven-day,
four six-day and four eight-day gaps. Five observations are Monday-dated; the rest
are Tuesday-dated. No missing report week or duplicate was found. This verifies
reported-series continuity, not immutable trader classifications or original vintages.
No in-window yen-specific consolidation break was located in the official special
announcements reviewed; this is not a guarantee against undocumented revisions.

## Fixed weekly causality and execution schedule

Research prices remain inside `[2014-01-06T00:00:00Z,2024-01-06T00:00:00Z)`.
Decision Mondays: **2014-01-20 through 2024-01-01**, inclusive (520 opportunities).
At **17:00 America/New_York** on Monday `m`, set nominal report Tuesday `t=m-13 days`.
Require exactly one report dated `t` or `t-1 day` (the documented Monday observation
substitute). Missing/ambiguous weeks block readiness; do not choose a different lag
or silently use an older/newer report. This gives a fixed 13-day nominal lag and
14 days for Monday observations, comfortably beyond the ordinary Friday 15:30 ET
publication and one/two-business-day holiday delays. It does **not** manufacture
actual historical release timestamps, which CFTC does not comprehensively archive.

Enter once at Monday **17:15 New York**, the first M15 grid open strictly after
rollover. Exit Tuesday **16:45 New York**, the last M15 grid open before its next
rollover. Remain cash for the rest of the week; no additional daily signal decisions
or trades. Convert local boundaries separately with `America/New_York` DST rules.
The single financing-day holding window follows the general benchmark convention;
it is fixed here before economics, not selected using intraday returns. Signal intent
is fixed at 17:00 and cannot use the entry candle. No decision-bar FX price is needed.

Exclude entire matched observations if their report observation date, decision date
or exit date intersects either inclusive availability blackout:

- **2018-12-22 through 2019-03-31**: shutdown and catch-up, conservatively buffered
  through March month-end beyond the January 29 official twice-weekly catch-up plan.
- **2023-01-31 through 2023-03-31**: ION reporting disruption and catch-up. Official
  notices still document delayed publication on March 21; March 10 was not recovery.

The month-end buffers are explicit conservative exploratory choices, not claims of
exact outage-end dates. Exclude source weeks too, so delayed backlog reports cannot
re-enter via the fixed lag. No interpolation of missing release dates or backlog
trading. These historical exclusion masks are not claimed to have been predictable
live. An additional official disruption affecting the proposed cohort requires
review before execution, never a silent change during or after economics.

Current CFTC historical data may contain corrections/reclassifications made after
the nominal decision. The fixed lag addresses ordinary publication latency, not all
vintage risk. This residual limitation is accepted **only for this exploratory experiment**;
there is no claim of certified PIT replication, validation or untouched OOS.

## Price support and complete cases

Reuse price infrastructure only; no Tokyo signal, calendar, timing controls, exclusion
mask or result. Bind the isolated file:
`reports/forex/tokyo_fix/readiness_20260924/USD_JPY_M15_BA_permitted.csv`,
SHA-256 `bb0dd08f5657a0aa845131cecfd610de2a9cef79eac709c0b8c8fe83e43eca81`,
248,784 rows. Its existing `input_binding.json` documents the seal-safe extraction.
The hash was reverified for this review. Full-cache and sealed-suffix access are forbidden.

Each scheduled observation requires all 95 M15 opens from entry through exit for
strategy and both passive references, even for a zero signal. Apply the general
complete-case principle: absent/invalid required observations remove the whole
matched observation from evaluability, never alter the economic schedule or create
a live missingness filter. No delayed fills, synthetic bars, interpolation or
individual-leg deletion. Global schema/order/identity/seal errors block execution.
Validate executable bid/ask opens, finite positive ordered OHLC and completeness
before economics. Previously certified quote integrity is reusable only with the
unchanged cache hash; later readiness must independently verify it.

Metadata-only review found **520 scheduled weeks, 27 disruption exclusions, seven
additional incomplete price windows, and 486 supported matched observations**.
Freeze these seven decision Mondays as the data-completeness exclusions:
`2016-12-26, 2017-01-02, 2019-11-04, 2019-12-23, 2020-05-04, 2020-08-31, 2020-10-26`.
Their missing-open counts are respectively `3,3,2,1,1,1,1`.
Among the 493 non-blackout opportunities, the incompleteness rate is `7/493`.
These are evaluability exclusions, not inferred holiday classifications.

Supported signals: 376 short USD/JPY, 110 long, zero neutral. There are 30 contiguous
same-direction runs when excluded weeks break runs; longest run is 105 weeks.
Runs are descriptive, not certified independent events. Supported counts by decision
year 2014-2024 are `50,52,51,51,51,36,49,52,52,41,1`.
This is sufficient to describe a single exploratory baseline, but weak for identifying
an independent unwind effect: 486 weekly observations are not 486 independent shocks.
Do not respond by changing thresholds, adding currencies or searching lookbacks.

## Accounting, benchmark and evaluation design

Use one unit of initial gross exposure relative to post-cost executable liquidation
equity per trade. Hold USD units fixed until exit; no stops or interim resizing.
JPY cash `C`, USD units `Q`; buys use ask `A`, sells use bid `B`.
Equity is `C+Q*B` for Q>=0 and `C+Q*A` for Q<0. From cash, long entry units are
`Q=C/A`; short entry units are `Q=-C/(2*A-B)`, so initial gross liquidation notional
equals post-spread equity. Exit fully at the executable opposite side. Compound
without equity resets. Negative/nonfinite equity or invalid quotes invalidate the
run; do not introduce margin liquidation rules after results.

Apply observed bid/ask once per actual transaction; do not add another spread debit.
Stress doubles half-spreads about each observed midpoint for all books, including
liquidation marking and passive incremental rebalances. No fitted slippage; candle
opens are executable proxies, not guaranteed account fills during stressed liquidity.
Both books are flat across every daily rollover under the explicitly declared OANDA
v20 DAILY 17:00 New York research convention. Actual demo-account financing mode is
unknown; no deployment or account-specific execution claim follows. No financing
history is required under this conditional rollover-flat convention.

Retain `CLAUDE.md` and
`governance/2026-09-24-intraday-passive-benchmark-amendment.md` protections:
same instrument/evaluable dates, the fixed full financing-day passive window,
constant-fraction long passive, exact common cash/units ledger and incremental costs.
On the unchanged permitted full-grid denominator, `N` is scheduled mean signed
strategy exposure, `G` its mean gross exposure, and `q` unit-passive mean gross exposure.
Unit passive uses f=1; gross-matched passive uses `f=G/q`. Require q>0 and 0<=f<=1;
never cap, add leverage or fit realized drawdown. Preserve inherited comparison
`alpha=R_strategy-(N/q)*R_unit_passive` and signed drawdown requirement
`MDD_strategy>=MDD_gross_matched`. Here every supported signal is nonzero and strategy
and passive share the full window, implying schedule-based f=1. Readiness must verify
this, not infer it from returns. For bidirectional positions, report the actual
costed short-book performance as well: negative N multiplying a long reference is
the inherited alpha convention, not a claim that reversing a costed long return
reproduces a costed short trade. No silent benchmark replacement is permitted.

Report base and stress net performance, exposure-adjusted alpha, matched drawdowns,
turnover and costs, cash reference, direction counts and sample exclusions.
The constitutional positive-alpha/base drawdown/spread-stress requirements remain
necessary; failing them cannot be called success. Passing would still be exploratory.
Fixed chronological evidence blocks are 2014-2016, 2017-2019 and 2020-2024-01-05;
report every block and its support without using blocks to select settings.

Frozen descriptive signal-specificity diagnostic: rotate the chronological 486-element signed
signal vector through **every** circular shift 0..485 over the fixed supported weekly
windows; keep prices, schedules and costs fixed, and recompute identical books and
alpha for each rotation. Direction counts and cyclic ordering are preserved. One-sided
descriptive rank p is `count(alpha_shift>=alpha_observed)/486`, including identity
and ties. No RNG or shift selection; this is not a calibrated independent-sample test
or a new validation gate, given persistence and nonstationarity. No Tokyo timing null
is reused; this experiment tests weekly inventory alignment, not fixing-clock alpha.

## Evidence and remaining readiness work

Official sources reviewed on 2026-10-30:

- CFTC TFF Futures Only: https://publicreporting.cftc.gov/Commitments-of-Traders/TFF-Futures-Only/gpe5-46if
- Definitions: https://publicreporting.cftc.gov/stories/s/TFF-Futures-Only/98ig-3k9y/
- Schedule: https://www.cftc.gov/MarketReports/CommitmentsofTraders/ReleaseSchedule/index.htm
- Historical notices: https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalSpecialAnnouncements/index.htm
- Shutdown/catch-up plan: https://www.cftc.gov/PressRoom/PressReleases/7864-19
- ION notice: https://www.cftc.gov/PressRoom/SpeechesTestimony/cftcstatement020223
- CME quotation: https://www.cmegroup.com/markets/fx/g10/japanese-yen/specs?videoId=6391867030112

Bounded official API review used `/resource/gpe5-46if.json` with:

```text
$select=report_date_as_yyyy_mm_dd,cftc_contract_market_code,market_and_exchange_names,open_interest_all,lev_money_positions_long,lev_money_positions_short
$where=cftc_contract_market_code='097741' AND report_date_as_yyyy_mm_dd between '2014-01-01T00:00:00' and '2023-12-31T23:59:59'
$order=report_date_as_yyyy_mm_dd
$limit=600
```

Response inspected in memory at `2026-10-30T17:43:44.035317+00:00`:
SHA-256 `1542aadd5f9a596f1e279c2bfd345fb27389b0df3826916c6ba3a805f983fdbe`.
521 rows, 2014-01-07 through 2023-12-26; the last row is unused because its decision
would fall beyond the price envelope. Raw signal bytes were not persisted by this
gate; this hash is a review identity, not a complete acquisition archive.

Before any exploratory backtest: externally review this draft, preserve/hash the
official raw extract and source notices, verify any changed extract against this
identity, materialize the fixed weekly mask, independently reproduce sample counts,
test lag/DST/holiday observation substitutions/disruption exclusions, and verify
signed cash/units accounting, stressed quotes, passive matching, signal rotations
and seal guards using synthetic hand ledgers. No data mismatch may silently produce
a different cohort. No code or synthetic tests were created/run in this design gate;
only source, signal-count and timestamp-support checks were performed.

Local constitution SHA-256:
`e46730ea21f97b896ee646556b15c7ccffd0694a902176ef8f9c4a870459635f`.
Phase-2A confirmation and carry Stage B remain inaccessible. Prior closed research
remains closed. VIX/JPY and Fiscal NOK remain DATA_BLOCKED, not scientifically rejected.
No tuning, timeframe/lag/direction/threshold/window/mask changes or rescue may follow
economics. Any later validation requires separately authorized prospective research;
this retrospective exploratory exercise cannot be relabelled validation.

## Freeze and user-run binding (2026-10-30)

The authorized bounded acquisition retained 520 required CFTC rows unchanged at
`reports/forex/cftc_positioning/inputs/tff_jpy_raw.json`, SHA-256
`93034406b3db52bc37c943f63fecd50574ea3858fd692027b760dd77c0a87ced`, retrieved
`2026-10-30T18:08:57.092977+00:00`. Adjacent `acquisition.json` preserves the exact
official query, URL, HTTP headers, retrieval time, size and digest. This is a current
historical extract, not original-release vintages. The 520 rows retain five Monday
observations and four six-day/four eight-day/511 seven-day gaps; dropping the unused
last row accounts for the difference from the earlier 521-row continuity summary.

`official_notices_web_snapshot.json` preserves the official schedule, historical
disruption notices and 2019 catch-up announcement as a labeled web-tool extraction,
not original HTML or historical-vintage evidence. The already stated exploratory
causality limitation is unchanged.

The tracked `prereg/2026-10-30-cftc-positioning-exploratory-freeze.json` binds exact
source/specification bytes, input artifacts, the local constitution, runtime versions,
weekly mask and focused synthetic-test evidence. Raw inputs and generated readiness
remain local/gitignored; their hashes are tracked. The 520-row matched mask is at
`reports/forex/cftc_positioning/readiness_20261030/weekly_mask.json`; readiness and test
evidence are in that same directory. This is price-infrastructure reuse only.

The sole economic entrypoint is `python -m scripts.run_cftc_positioning
--execute-one-shot-exploratory --expected-freeze <full-local-freeze-commit>`.
It verifies exact HEAD, committed frozen sources, all byte bindings and runtime,
then atomically claims `reports/forex/cftc_positioning/economics_once_20261030`.
There is no alternate output path, signal/time parameter, automatic acquisition or
retry. A failed claimed attempt remains consumed. It rechecks structural support
before economics and emits bound result/completion, both cost scenarios, trade
ledgers and equity paths, all rotations, fixed blocks and necessary-requirement flags.
The terminal emitted status is `EXPLORATORY_COMPLETED_PENDING_EXTERNAL_REVIEW`, never
validation or significance. No economics is authorized for the preparing agent;
only the human may choose to execute this one-shot command.
