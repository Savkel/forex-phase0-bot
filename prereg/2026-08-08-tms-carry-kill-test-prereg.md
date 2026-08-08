# Direct-TMS Cross-Sectional Carry — Stage-A Preregistration (historical kill-test)

- **Status:** PREREGISTERED (2026-08-08). Locked on commit.
- **Repo root:** `E:\Claude\forex_bot`
- **Governing document:** `CLAUDE.md`. Where this document and the constitution conflict, the
  constitution wins and this document must be corrected.
- **Relationship to prior phases:** Phase 0 (trend/momentum/Donchian), Phase 1 (short-term mean
  reversion) and Phase 2A (M15 session breakout) are permanently `CLOSED_FAIL`. This is a new,
  independent experiment and reuses none of their signals. The CBPOL proxy preregistration
  (`000c29c`, `9bbc5ba`, `eec2e27`) is untouched fallback/audit history and is **not active**.
- **Financing data:** the certified OANDA TMS `.pro` archive, ingested only through
  `bot/forex/tms_swap.parse_swap_document` with geometry-corroborated pairing
  (`bot/forex/tms_layout`), provenance in `provenance/tms_swap_manifest.json`.

**Research-only. No deployment, paper-trading or live-trading permission follows from any
outcome, including `SURVIVES_KILL_TEST`.**

---

## 1. Stage-A status

**All historical information is DEVELOPMENT.** This covers the entire 2023-03-27 → 2026-08-02
financing archive *and* the overlapping historical price information already touched by this
project — cached bid/ask panels for seven major pairs, and the spread-by-hour diagnostic measured
during closed phases.

**No historical out-of-sample dimension is claimed. None exists.**

**"Price access" means, throughout this document:** any access to the Stage-A routed-leg H1 panels
of Section 9, or the computation of any return, performance, drawdown or information-coefficient
quantity for this strategy. It does **not** mean that no price data has ever been touched by this
project — Section 1 states plainly that it has.

Stage A is therefore **one precommitted historical falsification test**, not an OOS evaluation.

| | Stage A — historical kill-test | Stage B — prospective confirmation |
|---|---|---|
| Data | development throughout | observations that do not exist at freeze time |
| Runs | one (plus at most one corrected execution, Section 10.2) | one (Section 10.2 applies identically) |
| FAIL | permanent `CLOSED_FAIL` | permanent `CLOSED_FAIL` |
| PASS | **`SURVIVES_KILL_TEST`** — permits Stage B and nothing else | research PASS; still no trading permission |
| Tuning | none | none — spec and code frozen at Stage A |

**A Stage-A PASS can never become research permission or trading permission.**

### 1.1 Why a decisive FAIL is legitimate here

The decisive-FAIL rule is **governance, not a bias argument.** This document makes **no** claim
that historical design exposure produces only one-sided bias — the direction and magnitude of that
exposure are unknown and unknowable from the record.

The rule is adopted because a test with no out-of-sample dimension can still *falsify*: if a
strategy cannot clear precommitted thresholds on data its designer was free to inspect, no
subsequent evidence will rescue it. The project accepts the risk of discarding a real edge in
exchange for a hard, unarguable stop. A PASS carries no symmetric weight, because the same
inspection freedom that makes FAIL decisive makes PASS uninformative.

---

## 2. Hypothesis and candidate

> Does a **lagged** broker-native OANDA TMS `.pro` cross-sectional financing ranking predict
> subsequent relative-value **spot-FX** performance, and does the resulting book survive realistic
> financing and costs?

**Economic mechanism.** Broker financing embeds tom-next interest differentials plus an
instrument-specific markup. The classical claim is that high-funding currencies pay a premium
compensating crash risk. The claim under test is that this is detectable in the broker's own
published schedule as **predictive content about spot prices**, not merely as financing collected.

**One candidate. Carry only.** Momentum is deferred entirely: cross-sectional momentum shares
Phase 0's premium and would risk an accidental rescue. One candidate means **no multiple-testing
correction**; adding any second candidate reopens multiplicity and requires a new preregistration.

**Sign convention.** `long_p` / `short_p` are the published percentage-point-per-annum rates for
holding pair `p` long and short respectively, positive = credit, negative = debit. Ranking uses
the side-neutral midpoint `m_p = (long_p − short_p)/2`, which cancels any markup applied
symmetrically to both sides; asymmetric markup is not separable and is carried into the signal.

---

## 3. Frozen universe, routing and portfolio representation

Everything in this section is **emitted programmatically from the certified financing archive**
into frozen artifacts committed alongside this document, and is never transcribed by hand:

- `prereg/2026-08-08-tms-carry-universe.json` — pairs, currencies, routes, representation-gate
  results, persistence diagnostics;
- `prereg/2026-08-08-tms-carry-mask.json` — the rebalance schedule and availability mask;
- `prereg/2026-08-08-tms-carry-price-readiness.json` — the routed-leg price manifest.

The tables below reproduce those artifacts; on any discrepancy the artifacts are authoritative and
the integrity suite (Section 10.1) fails.

**Archive accounting.** 170 documents parse; two of them are a byte-identical re-upload of the same
schedule (`swap_points_tms_en_2025.06.30.pdf` / `..._0.pdf`, one sha256), leaving **169 distinct
printed intervals**. One further pair of intervals shares an end date (`2024-11-04→2024-11-17` and
`2024-11-11→2024-11-17`); the signal sequence collapses these to the later-starting one, giving
**168 signal intervals**. Coverage for `F(d)` uses all 169.

### 3.1 Continuously-available `.pro` FX universe

The 36 `.pro` FX pairs present in **every** parsed schedule:

```
AUDCAD AUDCHF AUDJPY AUDNZD AUDUSD CADCHF CADJPY CHFJPY CHFPLN EURAUD
EURCAD EURCHF EURCZK EURGBP EURHUF EURJPY EURNOK EURNZD EURPLN EURSEK
EURTRY EURUSD EURZAR GBPAUD GBPCAD GBPCHF GBPJPY GBPNZD GBPPLN GBPUSD
NZDJPY NZDUSD USDCAD USDCHF USDCZK USDJPY
```

Spanning **15 currencies**: `AUD CAD CHF CZK EUR GBP HUF JPY NOK NZD PLN SEK TRY USD ZAR`.
`N = 15`, `k = floor(N/3) = 5` per leg.

### 3.2 Route matrix (frozen, cost-blind)

Accounting numeraire **USD**. A currency routes through its USD pair when one exists in the
continuous set, otherwise through EUR. Sign `+1` = base of the named pair, `−1` = quote.

| Currency | Kind | Legs |
|---|---|---|
| AUD | direct | `AUDUSD.pro` (+1) |
| CAD | direct | `USDCAD.pro` (−1) |
| CHF | direct | `USDCHF.pro` (−1) |
| CZK | direct | `USDCZK.pro` (−1) |
| EUR | direct | `EURUSD.pro` (+1) |
| GBP | direct | `GBPUSD.pro` (+1) |
| JPY | direct | `USDJPY.pro` (−1) |
| NZD | direct | `NZDUSD.pro` (+1) |
| USD | numeraire | — |
| HUF | via EUR | `EURHUF.pro` (−1) + `EURUSD.pro` (+1) |
| NOK | via EUR | `EURNOK.pro` (−1) + `EURUSD.pro` (+1) |
| PLN | via EUR | `EURPLN.pro` (−1) + `EURUSD.pro` (+1) |
| SEK | via EUR | `EURSEK.pro` (−1) + `EURUSD.pro` (+1) |
| TRY | via EUR | `EURTRY.pro` (−1) + `EURUSD.pro` (+1) |
| ZAR | via EUR | `EURZAR.pro` (−1) + `EURUSD.pro` (+1) |

**No currency is structurally unroutable, so none is excluded.** For a two-leg route, one unit of
currency exposure is one unit of the EUR-cross leg plus the offsetting `EURUSD` leg that leaves no
residual EUR exposure; offsetting legs are netted across the book before execution, so `EURUSD` is
traded once at its net size. **14 distinct instruments** are required in total.

**Costs never influence routing.** The matrix is fixed for the whole study from the instrument list
alone and applied identically to the strategy and to every benchmark path. Spreads are applied only
after routes are fixed.

### 3.3 Latent-carry representation gate (executed, PASSED, frozen)

Latent per-currency carry is recovered by least squares from the pair midpoints `m_p`, design
matrix `A` (`+1` base, `−1` quote), under `mean(r) = 0`. Thresholds frozen before observation:
`R² ≥ 0.90` and `max|ε| ≤ 0.25 × SD(m)` on **every** schedule date.

| Grid | Rows | Currencies | min `R²` | max `|ε|/SD(m)` | Verdict |
|---|---|---|---|---|---|
| Full | 36 | 15 | 0.999889 | 0.0422 | PASS |
| **Over-identified subgraph** | **31** | **10** | **0.999816** | **0.0504** | **PASS** |

**Why the subgraph is reported.** `HUF`, `NOK`, `SEK`, `TRY` and `ZAR` each appear in exactly one
pair. A degree-1 currency is *exactly identified* by that single row, so its residual is
identically zero for any input whatsoever — the full-grid gate is **vacuous for precisely the
currencies that dominate both legs of the book**. The subgraph drops those five rows and
currencies, retains the 31 rows carrying over-identifying restrictions, and still passes. Both
grids are gated; a breach of either on an evaluated date is an `UNDETERMINED` trigger
(Section 10.3). Switching to pair-direction ranking after a breach is prohibited.

Worst date 2023-03-27 on both grids. No prices or returns were touched.

### 3.4 Portfolio representation — USD resolved

Exposures are defined **in currency space**:

> `w ∈ R^15`, `Σ_i w_i = 0`, `Σ_i |w_i| = 1`. Long the top `k = 5` by `r̂` at `+0.1` each, short
> the bottom `k = 5` at `−0.1` each. The middle 5 carry zero weight.

**USD is a rankable currency carrying a weight like any other**, which is coherent because:

- the additive constant in `r̂` is unidentified, so the *ranking* is invariant to the numeraire
  regardless of normalisation; `mean(r̂) = 0` merely fixes a representative;
- any zero-sum currency vector lies in the span of the pair-difference basis, so `w` is exactly
  implementable through the frozen routes, the via-EUR legs cancelling the EUR residual and the
  USD leg falling out as `−Σ_{i≠USD} w_i`;
- `Σ|w| = 1` holds in **every** rebalance whether or not USD is selected, so gross normalisation
  is always well-defined.

USD's role as *accounting* numeraire is confined to P&L conversion and affects no exposure, ranking
or statistic. No leverage knob, no volatility targeting, no position limits beyond the above.

### 3.5 Disclosed limitation: the ranking is highly persistent

Measured on financing data alone across the 168 signal intervals, before any price access:

| Diagnostic | Value |
|---|---|
| Mean Kendall τ between consecutive rankings | **0.972** (min 0.829) |
| Mean overlap of the selected 10 currencies | **9.67 / 10** |
| Distinct selected-set states | **22** |
| Always long | HUF, TRY, ZAR |
| Always short | CHF, EUR, JPY, SEK |

**This is reported as a limitation and a diagnostic. It is not used to derive an effective sample
size, and no inference in this document is adjusted by it.** Section 6.4 states precisely what the
persistence does and does not compromise.

---

## 4. Causal rebalance rule

The rebalance clock is **exogenous** — it is the financing source's own publication calendar. No
timestamp, hour or session in this study is selected from spread, return or performance
diagnostics.

### 4.1 Signal schedule `S_j`

> `S_j` = the printed schedule whose **complete printed validity interval `I_j` has ended**.

A schedule is **never** admitted while still in force. Where two intervals share an end date, the
later-starting one is the most recently published and governs.

### 4.2 Decision instant, execution and holding period

- **Decision instant** `T_j` = (end date of `I_j`) **+ 1 day at 00:00:00 UTC**. This is the first
  instant at which `I_j` is complete. It is derived entirely from the printed interval — there is
  no chosen hour.
- **Execution** = **one common book-level timestamp `τ_j` per rebalance**: the first eligible OANDA
  v20 practice H1 timestamp at or after `T_j` at which **every one of the 14 routed legs has
  complete bid and ask data**, with `alignmentTimezone=UTC` and `dailyAlignment=0` (matching
  `bot/forex/range_fetch.py`), within a 48-hour tolerance. **There are no asynchronous fills**: the
  whole book prices off the same bar. The same requirement applies at **every instant at which the
  book transacts** — `τ_j` for each evaluable rebalance, **and `τ_{j+1}` for each of them**, which
  includes the 10 gap-boundary exits and the terminal exit at 2026-08-03. If no such timestamp
  exists at any transacting instant, price readiness FAILS (Section 9) and Stage A does not run —
  this is never resolved by dropping a rebalance after results. The gap-boundary exit at
  2024-03-03T00:00:00Z falls on a Sunday and will roll forward to the week open; it is named here
  because it is the most likely single point of readiness failure in the study. All timestamps are UTC; no local or DST-shifting calendar is used.
- **Price component — the H1 candle OPEN, never the close.** Every fill and every return uses the
  **open** of the bar timestamped `τ_j`: `mid = (bid_open + ask_open)/2`, buys at `ask_open`, sells
  at `bid_open`. Using the close would consume an hour of information after the decision instant
  and violate the constitution's look-ahead rule; the repo's own engine is open-to-open
  (`cost_model.spread_frac(bid_o, ask_o)`) and this document inherits that convention explicitly.
- **Holding period** = `[τ_j, τ_{j+1})`, the **actual common execution-to-execution interval**.
  Both the predictive returns of Section 6 and all P&L use this same interval; the nominal `T_j`
  instants are never used to price anything. Irregular schedule lengths move the next decision
  automatically. Observed evaluable nominal holding lengths: 7 days ×142, 6 ×6, 8 ×4, 14 ×2,
  4 ×1, 9 ×1, 10 ×1.
- **Gaps** use the frozen mask of Section 5. The book is **flat**: positions are closed at the
  preceding execution and re-entered after the gap, and **the exit and re-entry are charged as
  actual turnover**. **Attribution, frozen here:** the exit cost attaches to the net return of the
  *preceding* evaluable rebalance and the re-entry cost to the *following* one. Because Gate 4 is
  an absolute test, these ~10 extra full-book round trips do not cancel against the benchmark and
  are a real charge against the strategy. Nothing is carried forward, forward-filled or imputed.
- **Disclosed conditioning on `τ_j`.** The bar is selected because it *has* complete bid+ask for
  all 14 legs — a property known only once the bar has closed — while the fill uses that bar's
  open. The conditioning is on data availability, not on price level, so the bias risk is slight;
  it is disclosed rather than assumed away. In Stage B the same rule is applied live, where
  availability is observed forward and this conditioning does not arise.
- **Target weights are reset to `±0.1` at every evaluable rebalance**, for the strategy and for
  every benchmark path alike, so gross notional is exactly 1 at each execution and never drifts.

### 4.3 Realized financing `F(d)`

`F(d)` = the printed interval containing calendar day `d`; where intervals overlap, the
later-starting one governs. `F` is **contractual effectiveness** — what was actually charged — and
is used **only** for economic financing accounting. `F` never enters the signal, the ranking, the
predictive statistic, or any inferential quantity.

`S` and `F` are structurally disjoint: `I_j` ended strictly before `T_j`, and every `F(d)` used in
holding period `j` covers a day at or after `T_j`.

---

## 5. Data-availability mask (frozen before any price access)

A **DATA-AVAILABILITY MASK**: research-sample eligibility derived from published financing
coverage. It is **not** a claim that a historical trader could have known a future PDF would be
missing. Frozen from `provenance/tms_swap_manifest.json`, applied **identically** to the strategy
and to every benchmark path.

**Rule.** Rebalance `j` is evaluable iff **every calendar day in `[T_j, T_{j+1})` has an
authoritative `F(d)`**. Otherwise the book is flat: no position, no cashflow, no turnover, and the
rebalance is absent from every return series on both sides of every comparison. Nothing is
forward-filled, imputed or carried. Staleness cannot arise, because the decision clock *is* the
schedule sequence.

**Emitted result:**

| Quantity | Value |
|---|---|
| Rebalances defined | 167 |
| **Evaluable rebalances** | **157** |
| Excluded | 10 |
| First decision / last holding end | 2023-04-03T00:00:00Z / 2026-08-03T00:00:00Z |

All 10 exclusions are genuine financing-coverage gaps. The mask refuses to forward-fill even a
single uncovered Sunday (2024-03-03).

**Disclosed conditioning.** The excluded rebalances cluster on holiday-adjacent weeks, so the
evaluable subsample is mildly conditioned toward normal-liquidity periods. The historical claim is
a statement about this subsample, not about the calendar span.

**Sample sufficiency is a pre-execution readiness fact, not a gate.** 157 evaluable rebalances is
the frozen count recorded here; it appears in none of the five gates of Section 11 and is not
re-decided after results.

---

## 6. Primary predictive test

Global currency-label permutation is **withdrawn**: currencies are not exchangeable — TRY, ZAR, HUF
and CZK differ from the majors by orders of magnitude in carry, volatility, spread and routing, so
relabelling changes risk, routes and costs. The test is **identity-preserving**.

### 6.1 Exact claim

> **Higher lagged carry rank → better subsequent common-numeraire spot-return rank.**

This is a test of the cross-sectional carry **level** effect. It is **not** solely a test of timing
from rank transitions: a ranking that is constant through the sample can still produce a non-zero
information coefficient, and the statistic below will detect it.

**No factor neutralisation is performed, and none is claimed.** An earlier draft subtracted the
cross-sectional mean return and described that as removing the dollar/market factor. That step is
**withdrawn**: it is mathematically inert under a rank statistic (Spearman ranks are invariant to
subtracting a constant from every element), and it would not have neutralised a common factor in
any case, because currencies load on it unequally.

**Stated limitation — heterogeneous betas are not isolated.** A common USD or global-risk cycle
with heterogeneous loadings systematically reorders the cross-section. The selected book is
near-static, permanently long high-beta HUF/TRY/ZAR and short low-beta CHF/JPY (Section 3.5), so
**a single multi-year dollar or risk cycle remains a live alternative explanation of a positive
`ρ̄`, and this statistic does not exclude it.** This is a limitation of the test, disclosed before
the run, not something to be argued away after it.

### 6.2 Statistic

For each evaluable rebalance `j`:

1. `c_{i,j}` = latent carry of currency `i` recovered from `S_j` (Section 3.3), ranked within `j`.
2. `r_{i,j}` = log spot return of currency `i` in the common numeraire USD over the actual
   execution-to-execution interval `[τ_j, τ_{j+1})` (Section 4.2), computed through the frozen
   route matrix from **mid** prices.
3. `ρ_j` = **Spearman rank correlation** between `c_{·,j}` and `r_{·,j}` across all 15 currencies.
   Average ranks on ties.

**Test statistic:** `ρ̄ = (1/T) Σ_j ρ_j`, `T` = number of evaluable rebalances. Each rebalance is
weighted equally regardless of its holding length; the *decision* is the unit of analysis.

**Numeraire-invariance.** Changing the common numeraire adds the same constant to every currency's
log return, so the ranks — and therefore `ρ_j` — are unchanged. Under USD numeraire `r_USD,j ≡ 0`;
this does not privilege USD, because under any other numeraire that currency's return is zero
instead and the ranking is identical.

`ρ̄` is taken over all 15 currencies, including the middle 5 that carry no weight. It therefore
tests the informativeness of the full ranking, which is the claim in 6.1, and is not restricted to
the traded extremes.

**Financing cannot make this gate pass.** `ρ_j` is a function of `c` (from a schedule that ended
before the position existed) and of **spot prices only**. **Financing contributes exactly zero to
`ρ_j`**: no cashflow, credit, debit or accrual enters `r`. Selecting currencies that pay well
cannot, by itself, move this statistic.

### 6.3 Null hypothesis, inference and threshold

**H0:** `ρ̄ = 0`. **H1 (one-sided):** `ρ̄ > 0`.

Inference uses the **stationary bootstrap** (Politis & Romano 1994) on the series `{ρ_j}`, expected
block length from the **corrected Patton–Politis–White (2009)** selector, as
`arch.bootstrap.optimal_block_length` then `arch.bootstrap.StationaryBootstrap`, `arch>=7.2,<8`.
The selected `b` is rounded half-up to an integer.

- Resamples **10 000**; a dedicated `numpy.random.Generator(PCG64(20260808))` instance constructed
  for this procedure alone.
- One-sided **95%** lower bound on `ρ̄` = the **5th percentile of the 10 000 bootstrap replicates**
  of `ρ̄` (equal-tail percentile convention).

**Threshold, frozen before any return is computed: the one-sided 95% lower bound on `ρ̄` must be
strictly greater than 0.**

**Fail-closed degenerate-block rules.** If the selector raises, or `b` is non-finite, or `b < 1`,
or `b > T/2`, the study is `UNDETERMINED` (Section 10.3). These are not resolved post hoc.

`{ρ_j}` is indexed by **evaluable rebalance**, so the 10 excluded rebalances are closed up before
the selector sees the series. This is a declared assumption, not an oversight.

No effect-size floor is imposed on `ρ̄`; economic relevance is tested non-redundantly by Gates 1
and 4.

### 6.4 What persistence does and does not compromise — stated honestly

The bootstrap corrects for **serial dependence in `{ρ_j}`** and nothing else. It does not, and is
not claimed to, correct for the ranking itself being highly persistent (Section 3.5).

Because `c` is near-constant across `j`, the serial dependence of `ρ_j` is inherited largely from
the cross-sectional ordering of spot returns, which is close to serially uncorrelated. **The
selector will therefore likely return a short block length and a correspondingly narrow interval.**
No claim is made here that the procedure is conservative.

The honest statement of scope: rejecting H0 establishes that *this* carry ranking had positive
common-numeraire spot-rank performance over *this* sample, under a ranking that varied little and
without isolating heterogeneous USD/global-risk betas (Section 6.1). It does not establish
robustness across ranking regimes, because the sample contains few, and it does not distinguish
carry from a dollar-cycle exposure.

**Required reported diagnostics** (non-gating, declared now so they cannot be reclassified): the
selected block length `b` and the implied number of bootstrap blocks; the Newey–West HAC
t-statistic on `{ρ_j}` with lag `⌊4(T/100)^{2/9}⌋`; the mean of `ρ_j` within each of the 22
distinct selected-set states, reported as 22 group means with their counts; and a **calendar-year
breakdown of `ρ̄` and of net P&L**. The last exists because the sample spans the August-2024
yen-carry unwind while the book is permanently short JPY, so a single macro episode could dominate
both quantities; it is reported so that concentration is visible, and it is **not** a gate.

---

## 7. Economic benchmark

The benchmark answers "would rank-blind allocation have done as well?" The predictive test
(Section 6) answers "is the ranking informative?" These are different objects and are never
conflated. **The benchmark supplies levels; it is never used for significance, and the predictive
IC inference never uses benchmark paths.**

**There is no volatility scaling anywhere in this study.** The post-hoc scalar and its
`[0.5, 2.0]` clamp are withdrawn entirely: a clamp cannot be conservative in both directions, and a
scaled path is no longer at gross notional 1, which would silently invalidate the
gross-notional-1 basis on which Gate 3 is compared.

### 7.1 Ensemble `E-static`

`B = 1000` paths. Each path draws, **once for the entire study**, a uniform selection without
replacement of 5 long and 5 short currencies from the same 15. **Memberships are fixed** for the
whole study; **equal target weights are reset to `±0.1` at every evaluable rebalance**, exactly as
for the strategy, so every path is at gross notional 1 at each execution and never drifts. Frozen
before any price access: algorithm as stated, `B = 1000`, a dedicated
`numpy.random.Generator(PCG64(20260809))` instance constructed for this procedure alone (a distinct
seed from Section 6.3's `20260808`, so the two procedures cannot share a stream), path-major draw
order.

Held identical to the strategy: universe, `k = 5` per leg, `Σw = 0`, `Σ|w| = 1`, the frozen route
matrix, the frozen mask (including flat gaps with exit and re-entry charged), the common
book-level execution timestamps `τ_j`, financing accounting and spread machinery. **Actual turnover
and costs are recomputed honestly and independently for every path** — nothing is assumed equal.

Every path is a real, non-zero-risk long/short book. **Exposure paths are never averaged** —
averaging would collapse exposures toward zero and produce a risk-free straw man.

`E-static` is the appropriate comparator because the strategy is itself near-static (Section 3.5).
**No claim is made that turnover is equal**: static books generally trade less, which makes them a
**conservative** comparator on the cost dimension — the strategy pays more. Realized turnover is
measured and reported for both.

### 7.2 Comparison statistic

Strategy and **each** benchmark path are scored with the **same predefined risk-adjusted
statistic**, computed identically on the same series:

> `RAP = mean(per-rebalance net total return) / SD(per-rebalance net total return)`

on the gross-notional-1 path, net of all costs and financing. Comparison is *strategy scalar*
versus the **median** of the 1000 path scalars; the excess `RAP_strategy − median(RAP_ensemble)` is
the frozen Gate-1 quantity. Because it is a ratio, no scaling step is required and **no
volatility scaling or clamp is applied anywhere in this study**.

**Fail-closed:** if `SD ≤ 0` or `RAP` is non-finite for the strategy or for any path, the study is
`UNDETERMINED` (Section 10.3). Note the ratio's known sign pathology — for a negative mean, a
larger `SD` yields a larger ratio — cannot produce a false PASS here, because Gate 4 independently
requires stressed net total return `> 0`, which implies a positive base-cell mean.

### 7.3 Declared deviation from the constitution

`CLAUDE.md` specifies the headline as exposure-adjusted alpha versus a **matched-risk** passive
benchmark clearing **at equal drawdown**, and states that Sharpe is never the headline verdict.
This study deviates, and the deviation is named rather than left to inference:

| Constitution | This study | Why |
|---|---|---|
| constant-mix passive benchmark on the same instrument | rank-blind static long/short ensemble | a market-neutral cross-sectional currency book has no single-instrument constant-mix analog |
| matched **risk** | matched universe, construction, gross notional, mask, routing | post-hoc volatility scaling was withdrawn as an inflation channel; the ratio statistic absorbs the risk adjustment instead |
| Sharpe never the headline | `RAP = mean/SD` used **benchmark-relative** against an ensemble median | it is a relative comparison against a matched-construction counterfactual, not a standalone Sharpe verdict |
| clears at **equal** drawdown | drawdown no deeper than the ensemble **median** | "equal" is undefined against a distribution; the median is the distributional analog |

If the project owner judges any row unacceptable, this document must be corrected before execution
— per the header, the constitution wins.

Risk is handled by the ratio statistic (Gate 1) together with the drawdown comparison (Gate 3).
`E-static` is matched on universe, construction, gross notional, mask and routing — **not** on
realized volatility; the phrase "matched-risk" is therefore not used for it. **The inferential
weight of this study sits on Gate 2**; Gate 1 carries the constitution's cost-adjusted,
risk-adjusted, benchmark-relative requirement.

---

## 8. Costs and financing

Realized financing for notional `Q` base-currency units of pair `XXX/YYY` over rollover date `d`:

```
charge = Q × price(XXX/YYY) × (rate_annual / 100 / basis_YYY) × days_charged(d) × fx_to_account(YYY)
```

- `rate_annual` — the `.pro` `longRate` / `shortRate` as printed in `F(d)`, **percentage points**
  per annum, sign convention per Section 2. The `/100` converts percentage points to a fraction.
- `price(XXX/YYY)` — the **mid-open** of the H1 bar timestamped `d` 21:00 UTC.
- `basis_YYY` — the documented day-count for the quote currency (360 or 365).
- `days_charged(d)` — the **version-aware** rollover calendar from the TMS terms in force on `d`:
  FX weekend accrual **Wednesday ×3**; `USDTRY`/`CADTRY` on **Thursday** from the 2024-09-24 terms;
  the excepted set becoming `USDTRY`/`USDCAD` from the 2025-10-02 terms. Rollover instant 21:00
  UTC, business days only.
- `fx_to_account` — same-day conversion to the USD account currency at contemporaneous mid.

**Implementation note (not a rescue lever).** `bot/forex/cost_model.py` charges swap in *pips per
night* and knows only the Wednesday ×3 rule. TMS publishes *percentage points per annum* with a
version-dependent excepted set, so Stage A adds a TMS-native financing accountant; it reuses
`spread_frac` and the rollover-counting convention unchanged.

**Spreads** are charged on turnover at each rebalance from the measured `ask_open − bid_open` at
`τ_j`, after routing, using the convention of `bot/forex/cost_model.spread_frac`: **half the full bid/ask spread
per one-way fill**, so a round trip pays approximately one full spread. Flat-gap exits and
re-entries are charged on the same basis.

### 8.1 Adverse stress (sign-aware)

Credits can never improve; debits can never become cheaper.

| Dimension | Base | Adverse |
|---|---|---|
| Spread | ×1 | ×2 |
| Financing debits | ×1 | ×1.25 |
| Financing credits | ×1 | ×0.80 |
| Debit `days_charged` | ×1 | ×1.10 |

The `days_charged` ×1.10 cell is a preregistered adverse sensitivity covering **undocumented
holiday deviations**: TMS publishes no holiday calendar, so this is explicitly *not* reconstructed
history. The magnitude is a round 10%, chosen before observation, applied once at the end so it
cannot double-count the Wed/Thu rules, and never applied to credits.

Gate 4 must hold at the **adverse corner** (all four cells simultaneously). A spread ×3 cell is
computed and reported as a non-gating sensitivity.

---

## 9. Price-data readiness (pre-execution, blocking)

**Stage A is BLOCKED until the price manifest is complete.** Readiness is established *before* any
performance quantity is computed, and its result is recorded in
`prereg/2026-08-08-tms-carry-price-readiness.json`.

**Hybrid disclosure.** Financing is OANDA TMS Brokers S.A. (EU) `.pro`. Prices and spreads come
from the OANDA v20 **practice** environment — a different division, with different instrument names
and different spreads. `.pro` is a low-spread product and practice-demo quotes are not it.
**Stage A is explicitly a HYBRID approximation and is never a replication of a `.pro` account.**
This is a permanent limitation of the historical test, not a defect to be corrected later.

Required for **every one of the 14 routed legs**, with no exceptions:

| Field | Requirement |
|---|---|
| v20 instrument name | e.g. `EURHUF.pro` → `EUR_HUF` |
| Environment | `api-fxpractice.oanda.com` |
| Cache status | existing-cache or new-fetch, stated per leg |
| Window | covers 2023-04-03T00:00:00Z → **2026-08-05T00:00:00Z** (the terminal exit at 2026-08-03 plus the 48h tolerance band) |
| Granularity | `H1` |
| Price component | `BA` (bid **and** ask); the **open** field of each candle is used for all fills and returns |
| Coverage | a **common** H1 timestamp at which **all 14 legs** have complete bid+ask exists at **every transacting instant** — both entries and exits, gap boundaries and the terminal exit — within the 48h tolerance |
| Hash | sha256 of the stored panel |

**Current status: BLOCKED — 0 of 14 legs have verified H1 bid/ask coverage.** Seven legs
(`AUD_USD`, `EUR_USD`, `GBP_USD`, `NZD_USD`, `USD_CAD`, `USD_CHF`, `USD_JPY`) have H4 or M15 caches
from closed phases, which are **not** usable for H1 execution; seven (`USD_CZK`, `EUR_HUF`,
`EUR_NOK`, `EUR_PLN`, `EUR_SEK`, `EUR_TRY`, `EUR_ZAR`) have no cache at all.

**No routed leg may be dropped, substituted or re-routed after results.** If any leg cannot be
covered, Stage A does not run and the disposition is decided **before** any performance is
computed — never after:

- **transient coverage shortfall** (the instrument exists at the venue but the panel is incomplete)
  → `UNDETERMINED` → `SUSPENDED`, re-executable on the identical frozen spec once complete;
- **structural unavailability** (a routed instrument is not offered in the v20 practice
  environment at all) → **`SUSPENDED_INFRA`**, no verdict. This case is separated because
  `SUSPENDED` permits only re-execution of the identical spec while re-routing is forbidden, which
  would otherwise be a guaranteed loop. Seven routed legs (`USD_CZK`, `EUR_HUF`, `EUR_NOK`,
  `EUR_PLN`, `EUR_SEK`, `EUR_TRY`, `EUR_ZAR`) have never been fetched by this project and their
  availability is unverified; this is the most likely structural blocker.

---

## 10. Defect, VOID and UNDETERMINED policy

### 10.1 Integrity suite runs before the verdict

A preregistered integrity suite executes and its output is written and hashed **before any
performance statistic is computed or displayed**:

1. every PDF sha256 matches `provenance/tms_swap_manifest.json`;
2. `tms_swap` and `tms_layout` parser sha256s match the manifest;
3. text/layout pairing agreement on every schedule used;
4. the mask reproduces `2026-08-08-tms-carry-mask.json` byte-identically;
5. the universe and routes reproduce `2026-08-08-tms-carry-universe.json` byte-identically;
6. every quantity reproduced in the prose of Sections 3 and 5 matches the artifacts, checked
   mechanically against a table of literals extracted from this document;
7. both representation grids hold on every evaluated date;
8. the price manifest is complete, covers every transacting instant, and every panel hash matches;
9. a look-ahead assertion: every fill timestamp is strictly after the `valid_to` of the schedule
   that produced its signal, and every fill uses a bar **open**;
10. bootstrap and ensemble PRNG algorithm, count and seed match this document.

### 10.2 VOID — capped at one corrected execution

**At most ONE corrected Stage-A execution** is permitted, and only when **all four** hold:

1. **Demonstrated independently of performance** — a reproducible failing test or integrity check
   whose statement makes no reference to the run's returns, its verdict, or a desire to re-run;
2. **Reviewer-confirmed** by an independent reviewer shown the defect evidence and not the verdict;
3. **Scientific spec unchanged** — universe, routing, signal rule, statistic, inference, benchmark,
   gates and thresholds all identical;
4. **The invalid run is permanently retained** with its outputs, its verdict and the defect report.

Any post-verdict VOID must additionally carry a written statement of why the Section 10.1 suite
failed to catch the defect.

**A second material defect ends the study as `SUSPENDED_INFRA`. No further Stage-A execution is
permitted, ever.** Otherwise the verdict is final. A defect may never become a route to changing
any preregistered choice.

### 10.3 UNDETERMINED

Triggers, exhaustively: incomplete price readiness including any missing routed leg or any
rebalance lacking a common execution timestamp (Section 9); a representation-gate breach on either
grid at an evaluated date; a degenerate bootstrap block length (Section 6.3); or a non-finite `RAP`
(Section 7.2).

**Timing fence.** Every trigger except the last two must be established **before** any performance
statistic is computed, under the Section 10.1 ordering. The bootstrap-block and `RAP` rules are
deterministic properties of the frozen procedure evaluated within the single run, not post-verdict
discoveries. **An integrity failure discovered after the verdict never yields `UNDETERMINED`:** it
either satisfies all four Section 10.2 conditions, yielding the one permitted corrected execution,
or **the verdict stands**. There is no path by which failing to meet the VOID bar produces a softer
disposition than meeting it.

**Disposition: `SUSPENDED`.** The family is neither killed nor cleared. The only permitted
continuation is re-executing the **identical frozen spec**. No threshold, parameter, universe,
cadence or statistic may change. `UNDETERMINED` is never a tuning route and never a second attempt
at a verdict.

---

## 11. Stage-A acceptance gates

All five are AND-ed, evaluated once. Sample size is **not** among them (Section 5).

**Sign convention, stated once:** maximum drawdown is a **non-positive** number, so a *deeper*
drawdown is a *smaller* number. This is the convention used throughout `CLAUDE.md`.

| # | Gate | Requirement |
|---|---|---|
| 1 | **Benchmark-relative risk-adjusted net performance** | `RAP_strategy` **>** `median(RAP_E-static)`, net of costs and financing, base cost cell, gross notional 1 (Section 7.2) |
| 2 | **Independent spot-only predictive evidence** | One-sided 95% stationary-bootstrap lower bound on `ρ̄` **> 0** (Section 6.3) |
| 3 | **Risk — no deeper than the benchmark median** | `MDD_strategy` **≥** `median(MDD_E-static)`, signed, on the gross-notional-1 net total-return path |
| 4 | **Adverse-stress economics** | Stressed net total return (spot + realized financing − costs) at the adverse corner **> 0** (Section 8.1) |
| 5 | **Leave-one-currency-out robustness** | For **each of the 15 currencies**, remove it for the whole study, recompute `k = floor(14/3) = 4`, re-run the identical pipeline including a 14-currency `E-static` ensemble at the same seed, and require the Gate-1 excess `RAP_strategy − median(RAP_ensemble)` **> 0**. **All 15 cases must pass.** |

**Non-redundancy.** Gate 1 is benchmark-relative risk-adjusted economics; Gate 2 is
benchmark-free, financing-free statistical evidence; Gate 3 is risk; Gate 4 is absolute survival
under adverse costs; Gate 5 is concentration robustness. Each can fail while the others pass.

**Gate 5 is fully mechanical**: 15 predetermined runs, no re-tuning, no discretion about which
currency to drop, and no statistic computed after results to choose one. Currency-neutrality and
`Σ|w| = 1` restore by construction at `k = 4` (4 long and 4 short at `±0.125`).

**What "removed" means, precisely.** A currency is removed from the **rankable and weightable**
set only. It is **retained as a column of the latent-carry design matrix and as a routing
instrument**, so **all 36 rows are kept in every one of the 15 cases** and the representation gate
is unchanged from Section 3.3 throughout. Only the ranking set and the weight vector shrink to 14.

This is not a convenience: removing a currency from the design matrix would make the EUR case
**impossible**. EUR has pair-incidence degree 14, and `HUF`, `NOK`, `SEK`, `TRY` and `ZAR` each have
degree 1 with their single pair being an EUR cross. Dropping EUR's rows would leave those five
currencies with no rows at all and their latent carry wholly unidentified — and they are precisely
the permanently-selected currencies of Section 3.5. Retaining every removed currency as a
regression column and routing instrument makes all 15 cases well-defined and mutually comparable.

### 11.1 Dispositions

| Outcome | Disposition |
|---|---|
| Gates 1–5 all PASS | **`SURVIVES_KILL_TEST`** — permits Stage B only. Not a research PASS. No trading permission. |
| Any gate FAIL | **`CLOSED_FAIL`** — the direct-TMS cross-sectional carry family is permanently killed |
| Any Section 10.3 trigger | **`UNDETERMINED` → `SUSPENDED`** |
| Second material defect | **`SUSPENDED_INFRA`** |

**Required disaggregated reporting.** A Gate 2 FAIL with a Gate 1/4 PASS is a scientifically
distinct outcome — "the carry premium is collected but is not prediction" — and must be reported as
such, not as an undifferentiated kill. It remains a `CLOSED_FAIL`.

**No-rescue disposition.** After a valid `CLOSED_FAIL`: no retune, no change to `k`, cadence,
universe, routing, benchmark, statistic, inference, thresholds or stress grid; no candidate
additions; no re-run. The failure is reported plainly.

---

## 12. Stage B lock

Stage B inherits, verbatim and unmodified: the strategy specification of Sections 3, 4 and 8; the
frozen code at the Stage-A execution commit, identified by sha256; the predictive statistic, null,
inference and seeds of Section 6; the benchmark construction, `B`, seed and comparison statistic of
Section 7; and **the five gates and every threshold of Section 11, unchanged.**

**No threshold may be changed after Stage A, in either direction, for any reason.**

- **Eligibility rule:** the Section 5 rule, evaluated in real time against the then-current
  archive. The *rule* is inherited; only its input is live. Section 4.1's signal definition applies
  directly and causally.
- **Start:** the first decision instant strictly after the Stage-A freeze commit timestamp.
- **Terminal evaluation:** the first decision instant at which **both** ≥ **78 evaluable causal
  rebalances** and ≥ **18 calendar months** have elapsed. Both conditions are deterministic and
  observable without any performance quantity, so the stopping rule is not performance-dependent.
- **No interim performance inspection.** No return, statistic, gate or partial verdict is computed
  before the terminal evaluation.
- **Horizon compatibility.** All five gates are computable at 78 rebalances: Gate 1, 3 and 4 are
  path statistics; Gate 2's bootstrap operates on a 78-point series, well within the selector's
  domain, with the same degenerate-block fail-closed rules; Gate 5 re-runs the same pipeline. No
  gate encodes a sample-size threshold, which is why none of them conflicts with the shorter
  horizon.
- **Dispositions:** identical to Section 11.1, except that all-gates-PASS is a **research PASS**.
  Trading permission still requires separate explicit human sign-off and is not granted by this
  document.

---

## 13. Provenance fingerprint

| Item | Value |
|---|---|
| Financing source | OANDA TMS Brokers S.A. public archive, `https://www.oanda.com/eu-en/documents` |
| Index snapshot sha256 | `a929d3e81bb4c2ac1d251ac9eac34210dedd956b1d49cde6c64a431eb0c2bb2b` |
| Retrieved (UTC) | `2026-08-07T21:15:40+00:00` |
| Documents in index / parsed | 171 / 170 (one excluded: published `#VALUE!` cell) |
| Distinct printed intervals / signal intervals | 169 / 168 |
| `tms_swap` sha256 | `8b5798ba657140ca1d0202bf2b6d58a5f7fb3477821f93ef755010dbda0b6d2a` |
| `tms_layout` sha256 | `077eb0f9b24e8be5bc67a966458ba2f7ce8d7edea0c53eab3171e8abcf04889a` |
| Pairing authority | PDF layout geometry; flattened text must agree on every instrument |
| Interval authority | the PDF's printed `Valid from` interval; the archive index label is audit-only (16 disagreements) |
| Reproducibility | 15 165 instrument-week cells, 0 changed rate mappings |
| Price panels | none yet — see Section 9; hashes recorded there before execution |

Raw PDFs are **not** redistributed; only URL + sha256 provenance is recorded. No automated-access
prohibition was identified in the reviewed public terms; bounded private research retrieval was
performed under that interpretation. This is not a legal claim.

---

## 14. Sufficiency statement

The archive supports a **single-run historical falsification test** on 157 evaluable rebalances —
not an out-of-sample evaluation, and not a three-segment experiment. History is not extended with
CBPOL or any proxy. Stage A can kill the family; only Stage B can confirm it.
