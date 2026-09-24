# Tokyo pre-fixing USD-demand anticipation - FROZEN preregistration

- Gate: `TOKYO_FIX_FREEZE_AND_READINESS`.
- Status: externally approved specification, frozen by the local commit containing this update before implementation/economics; NOT ECONOMICS-READY until all required readiness checks pass. Historical filename retained for stable references.
- Scope: one externally selected historical DEVELOPMENT baseline. No implementation, economics, data fetch, trading, commit or push is authorized by this document.
- Authority: `CLAUDE.md`, including its approved **Intraday passive benchmark rule**, `AGENTS.md`, and the user's Tokyo baseline design, blocker-resolution, calendar-acquisition, exact-common-ledger and general intraday-governance decisions in this conversation. Chronological blocks remain evidence for external adjudication, not automatic gates. Exact common accounting supersedes conflicting Phase-1 legacy accounting; the approved intraday rule supersedes this draft's continuously held passive schedule and resulting historical-financing requirement.
- Repository HEAD observed when drafting: `ad5fd8146265661a6ba502ac8fa2571690c2c2a2`. This records context, not a scientific freeze or a substitute for live Git verification.
- Governance persistence: [General intraday passive benchmark amendment](../governance/2026-09-24-intraday-passive-benchmark-amendment.md) preserves the verbatim user-approved rule, pre-economics approval provenance and exact local `CLAUDE.md` SHA-256. The authorized local freeze commit binds this specification and governance before implementation.

## Freeze-time venue scope clarification (2026-09-24)

Under the user's latest explicit research-venue-assumption instruction, this historical DEVELOPMENT model binds the official **OANDA v20 DAILY convention: 17:00 America/New_York, with historical DST**, rather than asserting the unused practice account's financing mode. [Bound provenance and scientific assessment](../provenance/tokyo_v20_daily_research_venue.md) records the official sources and approval scope. Actual account mode remains UNKNOWN; empty transaction history is not evidence. This clarification supersedes actual venue/account-mode certification language in Sections 5, 9 and 11 for this research run only. The general rule's venue convention is confirmed by official documentation; it is not an account-specific certification. Any eventual result must disclose this assumption and cannot establish account-specific execution feasibility. Flatness implies zero financing only under the declared DAILY model, not under every possible account mode. All frozen trade, calendar, timing, costs, benchmark, null, robustness, seal and readiness semantics remain unchanged. The current user authorizes one local freeze commit followed by implementation and readiness checks, but no economics, orders, push or memory update. Historical statements below about future authorization describe the drafting stage and do not override that current authorization.

This document transcribes the agreed semantics and the approved general intraday benchmark rule. The frozen Tokyo trade ledger, primary/control timing, calendar, costs, research envelope, timing null and robustness design are unchanged. The passive now follows the strategy-independent full financing-day schedule in Section 5, with no rollover exposure; no historical financing rates or substitute financing are required for that schedule. Future readiness checks remain mandatory.

## 1. Hypothesis and separation from closed research

Structural customer demand for USD ahead of the Tokyo 09:55 fixing can produce pre-fixing USD appreciation against JPY. The sole strategy is a predetermined long USD/JPY position during 09:00-09:45 JST on each calendar-eligible date, subject only to the frozen execution-integrity rules.

The signal is the approved calendar and clock. It is not a function of FX returns, price levels, ranges, direction, volatility, news or financing ranks. There are no Gotobi, additional day-of-week, news, volatility, trend, momentum, breakout or reversion filters; no stops, alternative windows, short-direction candidate, position-sizing alternatives, parameter search or optimization. The calendar's Monday-Friday rule is not an invitation to select particular weekdays.

Phase 0, Phase 1 and Phase 2A remain `CLOSED_FAIL`. Only execution/validation methodology may be reused. In particular, no Phase-2A range, breakout trigger, stop, selected session, outcome or failed-null threshold is inherited. The controls in Section 6 are mandatory diagnostic comparisons, never alternative strategy candidates. Carry and Families 1-6 remain unchanged; this experiment is not Family 7 or a carry overlay.

## 2. Research window, calendar and seals

Retain the previously stated UTC research interval exactly:

`[2014-01-06T00:00:00Z, 2024-01-06T00:00:00Z)`.

Retain JST calendar dates `2014-01-06` through `2024-01-05`, inclusive. Use `Asia/Tokyo`, UTC+09:00 without daylight-saving adjustments. Eligibility is exactly:

`Monday-Friday AND not listed in the official Cabinet Office holiday CSV AND not December 31-January 3`.

The bound derived calendar contains 3,652 dates: 2,446 eligible and 1,206 excluded. These are calendar counts, not verified executable-trade counts. Preserve all recorded exclusion reasons, including overlapping reasons. The official CSV includes national, substitute and special holidays; do not recreate them using weekday heuristics, FX quotes or a different holiday library.

The calendar was acquired in 2026 and describes historical legal holidays. It is not a historical publication-time archive or evidence that a bank actually published a fixing on every eligible date. Its verified business-day rule is the approved eligibility rule.

All information used for this historical test is DEVELOPMENT. Neither prior data exposure nor this preregistration creates an untouched historical OOS claim.

Phase-2A confirmation `[2024-01-06T00:00:00Z, 2026-06-27T00:00:00Z)` stays sealed. Carry Stage B stays isolated. The existing full M15 cache contains sealed rows: its path is provenance, not authorization to load the entire file, hash its entire contents, or inspect those rows. A later authorized readiness process must establish a permitted-window input binding without accessing sealed price fields. No sealed outcomes may inform eligibility, controls, costs or design.

Apply the explicitly authorized boundary rule before considering any prices: a JST date is evaluable only if it is calendar-eligible AND the primary and BOTH control windows lie fully inside the frozen UTC envelope. Every entry, intervening M15 boundary and executable exit must satisfy `L <= timestamp < U`, where `L` and `U` are the bounds above. Equality at `U` is outside. Do not clip a window, move a boundary or widen the envelope.

The calendar artifact remains unchanged. Its eligible `2014-01-06` date is excluded from ALL THREE windows with reason `BOUNDARY_OUTSIDE_ENVELOPE`, because its early control lies on UTC `2014-01-05`. Calendar-only timestamp enumeration gives 2,445 boundary-evaluable JST dates, `2014-01-07` through `2024-01-05`; these are not verified trade counts. Preserve the boundary exclusion separately from holiday and quote-missingness reasons. Preceding decision-bar timestamps must also be within the envelope; no pre-window warmup or price access is authorized.

## 3. Scheduled decisions and execution boundaries

For boundary-evaluable JST date `d`, all boundaries below are exact M15 candle OPEN boundaries:

| Role | JST entry | JST exit | UTC entry | UTC exit |
|---|---|---|---|---|
| Sole strategy | d 09:00 | d 09:45 | d 00:00 | d 00:45 |
| Mandatory early control | d 07:30 | d 08:15 | d-1 22:30 | d-1 23:15 |
| Mandatory late control | d 10:30 | d 11:15 | d 01:30 | d 02:15 |

The strategy is long USD/JPY only, enters once and exits once. Intent is scheduled before execution from the known calendar and clock, following the constitution's bar-t-close / bar-(t+1)-open convention. Carry pending intent forward; never recompute it using the fill bar or later observations. The boundary quote supplies the executable price and sizing only. No same-bar high, low, close or eventual candle completeness may supply a signal, improve a fill or suppress an otherwise scheduled trade.

## 4. Accounting, missingness and costs

Use JPY as numeraire. For the strategy, let `E_d` be pre-entry JPY equity, `A_e` the entry ASK OPEN and `B_x` the exit BID OPEN. Invest the starting daily equity once:

`Q_USD = E_d / A_e`, `E_after = Q_USD * B_x`, `r_d = B_x / A_e - 1`.

Compound the daily returns. Remain in cash outside the holding interval. No added leverage, volatility scaling or intratrade resizing is introduced. The position is closed intraday; no overnight financing is charged to the strategy or the two intraday controls. The passive benchmark follows the separately approved rollover-flat schedule in Section 5.

The base case uses observed bid/ask opens. Do not charge that spread a second time. The already specified stress doubles each observed half-spread around its contemporaneous midpoint: with `m=(ASK+BID)/2` and `h=(ASK-BID)/2`, use `ASK_stress=m+2h` and `BID_stress=m-2h`. Apply the same accounting conventions to both controls and identically applicable costs to the passive comparison. Do not substitute mid-price execution.

No empirical additional-slippage calibration exists locally. No additional slippage value, sweep or acceptance threshold is approved here. Hypothetical slippage must not be represented as established executable cost or silently added to the frozen test. Candle opens remain historical execution proxies, not guaranteed fills at an official fixing.

Missingness is fail-closed and must never use future availability to improve the strategy:

- An unavailable entry skips that entry; no delayed replacement entry is allowed. The strategy remains cash for a skipped entry. Report it without changing calendar eligibility.
- A missing intermediate or exit observation after entry invalidates evaluation; do not delete that trade or date, fill forward, interpolate, synthesize prices, substitute a nearby bar or extend the holding interval.
- The timing comparison requires the strategy and both controls on the same approved dates. Missing required observations invalidate the comparison; do not create a post-hoc complete-case subset or replace a control. A permitted strategy-entry skip does not certify an otherwise incomplete timing comparison.
- Non-finite/nonpositive or crossed required quotes, ambiguous/duplicate timestamps, or inconsistent data identity are readiness/integrity failures, not evidence that the strategy passed or failed economically. Do not infer holidays from these failures.

## 5. Constitutional passive benchmark and predefined economic requirements

Apply `CLAUDE.md`'s **Intraday passive benchmark rule**, approved before economics. It preserves a costed constant-fraction passive reference, exposure-adjusted alpha and the no-deeper-drawdown gate, while requiring a strategy-independent full financing-day window and prohibiting benchmark leverage. Retain the exact common cash/units ledger already approved here. Neither the Phase-1 multiplicative mid/half-spread ledger nor its fixed swap proxy is used. Prior closed research is unchanged; this amendment is not a retrospective reinterpretation of its results.

**Fixed passive schedule.** Use USD/JPY and exactly the 2,445 boundary-evaluable JST date labels from Section 2. For each Gregorian date label `d`, the benchmark's closing rollover is `d 17:00 America/New_York`; its preceding DAILY rollover is `(d-1) 17:00 America/New_York`, not the previous eligible date or previous charged business day. Convert each local timestamp separately using the historical IANA timezone rules: 17:00 is 22:00 UTC during EST and 21:00 UTC during EDT. Never subtract a fixed 24 hours from a UTC rollover across a DST transition.

Entry is the first SCHEDULED UTC M15 candle OPEN strictly after the preceding rollover; exit is the last scheduled M15 OPEN strictly before the closing rollover. Thus entry is rollover plus 15 minutes and exit is rollover minus 15 minutes, expressed in UTC after the timezone conversion. During ordinary EST days this is `(d-1) 22:15Z` to `d 21:45Z`; during ordinary EDT days it is `(d-1) 21:15Z` to `d 20:45Z`. Remain in cash outside that interval, including across every rollover. Rebalance only inside it and liquidate at its exit. A missing scheduled quote is not permission to use the first/last available quote instead. This is a full financing-day passive, not a copy of any Tokyo/control window; it can cross calendar midnight while staying flat at financing rollover.

Use the same frozen research envelope and date labels without adding or dropping Tokyo dates. Every passive entry, exit and intervening required open must lie within that envelope; failure blocks benchmark readiness, never widens the seal or clips a window. The first retained date `2014-01-07` has passive entry `2014-01-06T22:15:00Z`, already inside the envelope; the last date `2024-01-05` exits `2024-01-05T21:45:00Z`, also inside. Assign passive daily evidence to its `d` label for the existing chronological blocks. Calendar eligibility is not inferred from passive quote availability. Missing required passive prices invalidate benchmark readiness without changing strategy/control dates or missingness rules.

**Matching and alpha.** Use the same full permitted M15 observation grid over the frozen UTC envelope for strategy and benchmark, including every cash interval, not only the benchmark or Tokyo holding windows. On its `n-1` observed open-to-open intervals, retain the unweighted mean-exposure convention: `N=mean(p_strategy,j*f_strategy)` and `G=mean(abs(p_strategy,j)*f_strategy)`, with Tokyo's unchanged `f_strategy=1`. For the unit-fraction scheduled passive define `q=mean(abs(p_unit,j))`. All three means use the identical denominator and interval set. Weekend/gapped intervals remain single observed intervals, not synthetic candles or wall-clock weights; a gap through a required passive holding interval fails readiness. Let `R_1` be the exact costed compounded total return of the full-day passive with fraction 1. Its gross-matched counterpart uses the single constant fraction `f=G/q` while scheduled to hold and zero otherwise, so its full-grid mean gross exposure is `f*q=G`.

Nonfinite inputs, `q<=0`, invalid negative `G`, or `f>1` make the benchmark UNEVALUABLE and block readiness; do not cap `f`, add leverage, rescale the strategy, change dates/windows, or select another benchmark. If `G=0` and `q>0`, the matched passive is cash at `f=0`, with no fallback to 1. Report `N`, `G`, `q`, `f` and the benchmark's measured mean gross exposure. These are mechanical exposure measurements, not parameters chosen to improve outcomes.

The approved intraday alpha comparison is `alpha = R_strategy - (N/q) * R_1`, not `R_strategy - R_gross_matched`. Dividing by `q` accounts for the unit passive being cash outside its fixed full-day windows; it does not rescale the strategy or replace the costed reference. The gross-matched curve supplies the drawdown reference. Drawdown is `min_t(E_t / max_{s<=t}(E_s) - 1)`, signed nonpositive. Retain `MDD_strategy >= MDD_gross_matched`; do not solve for equal realized drawdowns, fit volatility, or choose a fraction from returns. Cash, controls, raw return and uncosted hold cannot substitute for these references. Timing-specific alpha is tested separately by the unchanged Section 6 null.

**Exact common ledger and valuation.** Keep JPY cash `C` and USD units `Q`; executable liquidation equity at each permitted M15 open is `E=C+Q*B` for the long-only books, where `B` is that cell's executable bid. Buying `delta>0` units changes cash by `-delta*A`; selling `delta<0` changes cash by `-delta*B`, with `Q'=Q+delta`. Thus actual spread is paid on every incremental purchase/rebalance and every sale uses bid; do not add another half-spread debit. Apply the same valuation to Tokyo, controls and passive curves, recording pre/post-transaction liquidation equity and financing cash movements consistently for drawdown. Liquidation marking is valuation, not a synthetic daily close/reopen. Section 4's Tokyo units stay fixed between its scheduled entry and exit; mark-to-liquidation does not resize them or change `B_x/A_e-1`.

**Exact constant-fraction passive.** Retain starting-equity normalization 10,000. Enter and exit only at the fixed daily passive boundaries above; the superseded second-open entry/final-window continuous-hold schedule does not apply. At entry and each subsequent M15 open strictly before that day's exit, target `Q'*B=f*E'`, where `E'=C'+Q'*B` is POST-transaction executable liquidation equity; `f=1` for the unit reference and `f=G/q` for the gross-matched passive. This states constant mix on the approved liquidation-value basis after paying its actual transaction cost. Let `E=C+Q*B` before the transaction. The self-financing solution is `delta=(f*E-Q*B)/(B+f*(A-B))` for a purchase and `delta=(f*E-Q*B)/B` for a sale, chosen by the sign of `f*E-Q*B`; zero means no transaction. Update cash and units as above. No free mid-price reset, gross round-trip rebalance, extra spread debit or independently chosen size is allowed. With cash only and `f=1`, this gives `Q'=C/A`, exactly the frozen Tokyo entry rule. `f=0` remains cash. Each daily exit sells all units at bid instead of rebalancing. Compound across dates without resetting equity. Invalid/nonpositive equity or invalid quotes fail closed; no leverage or repair convention is introduced.

**Rollover exclusion, not a zero-rate assumption.** Under the approved rule both passive references are flat at every daily 17:00 America/New_York rollover, including dates with multi-day financing. Therefore no overnight financing charge or credit is incurred, and historical 2014-2024 financing rates are not required. This follows from the holding schedule, not from imputing a missing financing rate as zero. Venue/account applicability of that daily rollover clock must be evidenced in readiness; the official OANDA financing documentation already reviewed in the preceding availability gates states 17:00 ET (for example `https://www.oanda.com/uk-en/trading/financing-costs/`). A clock mismatch, financing applicable inside the holding interval, or any exposure crossing rollover invalidates this benchmark's readiness; do not shift its boundaries, ignore an incurred charge, or silently fall back to a continuously held benchmark. No source is fetched or new venue evidence certified by this document edit.

Base costs remain observed ask/bid. The existing stress doubles half-spreads exactly as Section 4 specifies for all purchases, sales, liquidation marks and incremental rebalances. Both cells use the identical fixed daily benchmark schedule and zero rollover exposure. No new cost, financing stress, parameter alternative or overnight strategy holding is introduced; the legacy financing proxy and TMS hybrid are not used.

Preserve the minimal previously specified economic requirements:

1. Full-window exposure-adjusted alpha, as defined above, must be strictly positive under base costs.
2. The same alpha must remain strictly positive under the doubled-half-spread stress.

Retain the constitutional no-deeper-drawdown check against the gross-matched passive in the base comparison, as operationalized by the prior framework. Do not reinterpret it as an exact drawdown-equality calibration or add stress/block drawdown gates.

An evaluable nonpositive result in either required cell kills the baseline without rescue. Undefined benchmark/accounting quantities or failed integrity do not manufacture an economic verdict. Survival would be historical DEVELOPMENT evidence only, with no trading or prospective-OOS claim.

**External governance resolution.** Exact common cash/units accounting remains in force. The approved constitutional intraday amendment supplies the passive schedule, `q` normalization and no-leverage readiness rule; it removes the historical-financing blocker without changing Tokyo's frozen trades or its separate timing null. The benchmark schedule is fixed independently of strategy timing and economics. No window, fraction cap, reference family or cost treatment may be searched or selected after results. No parity with the incompatible legacy equity calculation is claimed.

## 6. Fixed timing-specificity comparison

Always retain both control windows from Section 3, with predetermined long USD/JPY direction, the same boundary-evaluable JST dates, equal 45-minute holding duration, identical notional conventions and executable bid/ask costing. Never choose the better control or search additional clock windows.

For each complete same-day observation define the agreed contrast:

`D_d = net_return_d(09:00-09:45) - [net_return_d(07:30-08:15) + net_return_d(10:30-11:15)] / 2`.

The estimand is `E[D]`. Test the one-sided null `E[D] <= 0` using the agreed **centered circular 20-eligible-day block bootstrap**, **10,000 replicates**, **PCG64 seed 20260923**. Freeze the complete calculation as follows:

1. The resampling unit is the whole paired JST date, retaining its primary, early and late returns together. Order the 2,445 boundary-evaluable dates chronologically; weekends, holidays and the predetermined boundary exclusion are not observations. Blocks contain 20 consecutive eligible-date indices, not 20 calendar days or individual M15 bars.
2. Every scheduled date must supply finite, valid returns for all three windows. Any missing/invalid `D`, including one caused by a skipped entry, invalidates the full timing test. Do not remove dates, compress around missing observations, impute zero, or draw replacements. A genuine finite zero contrast remains an observation. No p-value is produced for invalid or empty input.
3. For a complete vector of length `n`, compute `T_observed = fsum(D)/n` and `Y_i=D_i-T_observed` in binary64, where `fsum` denotes Python's accurately summed finite sequence. Center once at the boundary null of zero; do not center each resampled statistic separately, studentize or alter weights.
4. Set `k=ceil(n/20)`. Initialize NumPy `Generator(PCG64(20260923))` once. Generate uniform independent integer starts in `[0,n)` with replacement using `integers(0,n,size=(10000,k),dtype=int64,endpoint=False)`. Consume this matrix in row-major order: replicate first, then block. A block starting at `s` has indices `(s+j) mod n`, `j=0,...,19`. Concatenate its `k` blocks in order and retain exactly the first `n` indices; truncate only the final block. Wrapping from the last eligible date to the first is the specified circular construction.
5. For replicate `b`, compute `T_b=fsum(Y[index_b])/n`. The exact reported upper-tail Monte Carlo p-value is `(1 + count_b[T_b >= T_observed]) / 10001`. Include ties, apply the plus-one numerator/denominator correction, and compare unrounded values without jitter or tolerance. Do not redraw constant samples or special-case their p-values.
6. The base-cost calculation is the primary timing test. Report the already required stress timing evidence using the same index matrix, separately centered stress contrasts and the identical formula; it introduces no additional gate. Chronological-block summaries remain descriptive evidence, with no new block-specific bootstrap test. Record package versions and the start-index matrix hash in later reproducibility artifacts; no seed search or version-dependent silent substitution is allowed.

Report the observed mean contrast and one-sided p-value. The resolved design prescribed reporting, not a numerical significance cutoff: no automatic null-percentile or p-value gate is introduced or inherited. Do not substitute day-shuffling identical clock-driven decisions, which is degenerate.

The symmetric controls address common USD/JPY drift and linear clock-time drift across the surrounding windows. Remaining nonlinear intraday seasonality, opening effects, cost differences and unobserved customer flows limit causal attribution to the fixing itself. The bootstrap is a sampling approximation, not a randomized causal experiment. Timing evidence does not replace the constitutional economic benchmark.

## 7. Chronological robustness: evidence, not automatic gates

Retain the fixed blocks exactly:

- 2014-2016;
- 2017-2020;
- 2021 through the research-window end.

Assign observations by the strategy's eligible JST date. Report disaggregated base/stress economic and timing evidence, observation/missingness counts, adverse blocks and relevant uncertainty for external adjudication. Do not require every block to be positive, apply a block-level significance threshold, or let one negative block automatically veto the experiment. The user's later governance correction supersedes the earlier draft's automatic per-block positivity condition.

Preserve negative evidence and emphasize the weakest blocks rather than using a favorable full-sample average to hide them. Blocks, controls and calendar dates are not selection opportunities.

## 8. Artifact bindings verified for this draft

These SHA-256 values bind the current local bytes, not hypothetical future Git-normalized versions. The source and calendar artifacts are existing local/uncommitted acquisition evidence. This draft neither commits them nor rewrites them.

| Artifact | SHA-256 |
|---|---|
| `provenance/tokyo_v20_daily_research_venue.md` | `b61fa1cb4ae6abac0669e228a88a77746254ff0a1580883035200d9b748e9b0a` |
| `provenance/tokyo_calendar_source.json` | `25fc3fc0a72dce724eef1383fda216df6a2a4e3fa8b29d747fc541fd9cbaa8c6` |
| `data/japan_calendar/raw/syukujitsu.csv` | `cec37a743c96995cdb9cb52b685c9003634682a9b0e1a640a6b9b96881fe964a` |
| `data/japan_calendar/raw/cao_gaiyou.html` | `565ed19991424566812ce202196adc2a5f7932d9e607940ce28df76456413e43` |
| `data/japan_calendar/tokyo_eligible_days_20140106_20240105.csv` | `f1b75436e6002c4e0d7e30455a0ec633d105ca43f77361bc6c6b653a458cc84e` |
| `data/japan_calendar/verification.json` | `05472241ae109f52e4c7e4a9c8dd7235c932a99f9fab548f9e68d3b6771803b3` |
| `scripts/build_tokyo_calendar.py` | `ef06099cbc11d850adbfc58f07731b08cab1758fa7e4f523818655bff0e54f7c` |
| `scripts/acquire_tokyo_calendar.py` | `fa1a94738d80f754db9866d3c16da8f3dc38be41680aa2d0e451137ad3246c00` |
| `tests/test_tokyo_calendar.py` | `76207ec3b4976b72a21c404cda290b538917c9b1475a8c1dcb755b85186e8e0b` |
| `reports/forex/phase2_m15_provenance.json` (existing metadata only) | `a89fa03133729ac30a25c263fae7deb0bf44f569bc99e45361e542f8bbfc9fe0` |

Official source identity: Cabinet Office, Government of Japan. Preserved page:
`https://www8.cao.go.jp/chosei/shukujitsu/gaiyou.html`; linked CSV:
`https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv`.
CSV retrieval: `2026-09-23T16:18:13.274429+00:00`; 21,538 bytes;
official advertised coverage 1955-2027. The prior acquisition verified exceptional holidays,
passed 42 focused checks and reproduced identical calendar bytes offline. Those tests were not
rerun in this document-only drafting gate.

Existing price-source locator, not permission to read its sealed suffix:
`data/forex_ohlcv/phase2_m15/USD_JPY__M15__BA__a0__w1388959200000-1782506700000.csv`.
Source: existing OANDA v20 practice USD/JPY M15 bid/ask candles. The existing provenance report
does not replace a strategy-specific, permitted-window price binding. No such binding, strategy
readiness result, executable implementation, performance artifact or strategy-test pass is claimed.

### 8.1 Frozen protocol for later seal-safe price binding

This is a design requirement for a separately authorized readiness gate, not authorization to read prices or produce an artifact now. The permitted input is an isolated USD/JPY M15 bid/ask subset containing only rows whose candle-open timestamps are in `[L,U)` from Section 2. Preserve the source header and permitted row bytes unchanged; do not resample, repair or normalize prices. The full-cache path is only a locator: never compute a whole-cache hash, load-then-filter it, or inspect a sealed row to establish this binding.

The later extractor must use an unbuffered, timestamp-first binary read. Verify the header identifies `open_time` as the first field and includes the required UTC time, bid/ask OHLC and completeness fields; otherwise stop. Read only the first field through its delimiter before deciding whether a row is permitted. For `open_time < L`, discard the remainder without interpreting price fields or including it in any output/hash. For `L <= open_time < U`, copy that row's original bytes to the isolated subset. At the first timestamp `>= U`, stop immediately after the timestamp field, BEFORE reading any remaining field of that row or any later row. Do not use whole-line reads, chunked dataframes, memory mapping or reader prefetch across this stopping boundary. Only that first excluded timestamp may be recorded as boundary metadata, never its price fields. Check strictly increasing timestamps in the scanned prefix and fail closed on malformed timestamps or an unexpected schema; rely on existing provenance for source ordering beyond the stop, without claiming that the sealed suffix was revalidated.

Hash only the isolated header-plus-permitted-rows bytes. Bind a manifest containing: source locator; existing provenance-report SHA-256; pair/timeframe/bid-ask identity and actual header; exact UTC envelope and timestamp units; subset relative path, SHA-256, byte count, row count and first/last included timestamps; extractor version/commit and runtime versions; final approved preregistration hash; calendar and calendar-verification hashes; and the separate ordered boundary-evaluable-date manifest/hash with its fixed exclusion reason. No sealed-source content hash is required or authorized. Record the stopping timestamp or EOF condition and any integrity failure without outputting excluded price content. Freeze these input identities before economics; an absent or inconsistent binding blocks readiness, not the scientific hypothesis.

The permitted subset covers the full research envelope for the passive comparison, including non-Tokyo intervals. It must not be reduced to the three intraday windows. Reading already permitted rows for later structural validation does not authorize return construction or benchmark execution. Calendar eligibility remains independent of quote availability.

## 9. Required future readiness and integrity evidence

Before any separately authorized economics, establish and preserve:

- The externally reviewed final specification and unchanged source/calendar hashes; exact JST eligibility and UTC mapping; reproduce the calendar-only count of 2,445 boundary-evaluable dates and the `2014-01-06` boundary exclusion without changing the 2,446 calendar-eligible count. No use of quote availability to redefine either set.
- Independently test the Section 8.1 stopping guard on a synthetic stream with an instrumented forbidden suffix: the reader must not request price bytes at or after the sealed boundary. Verify that an isolated subset contains no excluded timestamp and reproduces the same bytes/hash offline. Neither the test nor the check may open actual sealed price fields.
- A completed Section 8.1 manifest and structural validation of the isolated subset only: timestamp identity/order/uniqueness, UTC/M15 alignment, required columns, valid bid/ask relationships, and presence of the exact entry/intermediate/exit opens at 15-minute spacing in all three windows for every boundary-evaluable date. Verify preceding decision-bar availability separately; bar completeness is an integrity check, never a retrospective trade filter. Record every missingness outcome. No complete-case selection, synthetic gap fill or terminal use of the first sealed open.
- Causality checks: pending scheduled intent survives unchanged; later price/quote mutations cannot change past intent, eligibility or sizing; execution consumes only the correct boundary information.
- Hand-ledger/independent accounting parity for long ask-entry/bid-exit, full daily JPY-equity sizing, compounding, cash intervals and half-spread stress, including control symmetry and no double-charged spread.
- Exact equal-duration/timezone control mapping and independent synthetic checks of Section 6: paired-date resampling, centering, wraparound, final-block truncation, RNG consumption, ties/plus-one p-value arithmetic and fail-closed missing-D handling. Base/stress use the same start-index matrix. No real strategy returns may be constructed during these readiness checks.
- Fail-closed tests for hashes, keys, duplicates, malformed quotes, unavailable entries, missing post-entry bars and attempted seal violations. No silent repair or permissive fallback.
- Bind the approved `CLAUDE.md` intraday rule and evidence that the applicable venue/account uses daily 17:00 America/New_York rollover without financing applicable inside the approved holding interval. Record the IANA timezone database version. Verify DST-aware preceding/current rollovers, strict first-after/last-before scheduled M15 opens, identical eligible date labels, complete passive-window price support, and that every passive boundary is inside the unchanged research envelope. Never replace scheduled boundaries with available quotes. No historical financing-rate series is required.
- Independently check that strategy, controls and both passive references are flat at every rollover, with no carried position or cash reset between scheduled dates. A rollover exposure, venue-rule mismatch or missing required passive quote fails readiness; no delayed fill, window change, financing imputation or continuous-hold fallback is allowed.
- Hand-ledger/independent synthetic checks of the common cash/units ledger, liquidation equity, incremental ask/bid rebalances, post-cost constant-fraction identity, daily entry/exit and compounding, and `G=0`. Verify full-grid exposure means `N,G,q`, `f=G/q`, gross parity `f*q=G`, normalized alpha `R_strategy-(N/q)*R_1`, and unchanged drawdown comparison. Undefined inputs, `q<=0` or `f>1` block readiness without capping or strategy rescaling. Verify `f=1` cash entry reduces to `Q=C/A` and round-trip wealth to `Q*B`; base/stress spread is paid exactly once and applied consistently to valuation. No parity with the incompatible legacy equity calculation is claimed. Historical calendar tests alone do not certify strategy or benchmark behavior.

This section states checks to be required in a later authorized implementation/readiness gate. It
does not implement or run them and does not add numerical tolerances, performance thresholds or
alternative strategies that have not been approved.

## 10. Freeze and no post-economics changes

All open items must be resolved externally without inspecting outcomes, before final scientific
freeze, implementation authorization and any separately authorized execution. There is exactly
one strategy baseline; controls and chronological blocks cannot become candidate-selection tools.

Once economics begins, no changes to timing, days, holiday treatment, pair, direction, size,
window, controls, costs, benchmark, null, thresholds, seeds, blocks or missingness rules are
permitted. Do not add filters, shorten the sample, remove losing dates, optimize parameters,
relabel outcomes or rerun adjusted variants to rescue failure. Preserve all unfavorable and
invalid evidence. An infrastructure failure is not scientific survival and does not itself
authorize repair execution or a repeat run.

No historical survival grants access to either sealed research path or permission to trade.

## 11. Final-review and future-readiness status

**The historical-financing blocker is removed by the approved general intraday governance rule.** Section 5's full financing-day passive is flat across every venue rollover; it does not require a deep-history financing-rate archive. The exact common ledger, no-leverage exposure match, normalized alpha and no-deeper-drawdown comparison remain mandatory. This is an approved pre-economics governance change, not a zero-financing proxy or a waiver of the passive comparison.

No unresolved benchmark design choice remains for final external review. Execution readiness is not asserted: the separately authorized Section 9 checks must still establish venue/account rollover applicability, timestamp/quote support, zero rollover exposure, `q>0`, `0<=f<=1`, and independent accounting parity. Failure of a future check blocks readiness rather than authorizing a redesign, altered date sample or skipped charge. No price support, exposure statistic, strategy return or economic verdict has been computed for this document patch.

The Tokyo calendar, boundary rule, primary/control windows, cash/units trade ledger, spread stress, bootstrap conventions and chronological robustness remain unchanged. The seal-safe binding protocol and required later checks remain specified in Sections 8.1 and 9, pending separate authorization. No permitted-window price artifact has been created or inspected. This draft is ready for final review only; it authorizes no implementation, economics, confirmation/Stage-B access, commit or push.
