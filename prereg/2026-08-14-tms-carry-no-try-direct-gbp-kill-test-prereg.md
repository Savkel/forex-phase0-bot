# Direct-TMS Cross-Sectional Carry — No-TRY Direct-GBP Stage-A Preregistration

- **Status:** PREREGISTERED ROUTING CORRECTION (2026-08-14). Locked on commit.
- **Prior specifications:** the original `2026-08-08` spec and commit/spec `2c81d140` are retained
  unchanged with disposition **`SUPERSEDED_UNEXECUTED`**.
- **Reason:** explicit human routing simplification before any Stage-A performance computation:
  TRY remains excluded; GBP uses direct `GBP_USD`; `EUR_GBP` remains financing evidence only.
- **Prior readiness outcome:** the prior `EUR_TRY` endpoint shortfall produced no Stage-A result.
  No return, P&L, IC, benchmark, drawdown, or acceptance gate was computed.
- **Scientific status:** this is not performance rescue. All historical information remains
  DEVELOPMENT; Stage A remains a historical kill-test with no historical OOS claim.
- **Pre-execution clarification:** the portfolio exact-tie rule in Section 5 was frozen by human
  decision before implementation or any Stage-A execution. No price or performance information
  informed it; Stage A has never executed and no Stage-A performance result exists.
- **Governance:** `CLAUDE.md` prevails. Research-only; no paper/live/deployment permission.

## 1. Inheritance and artifacts

Except where this document explicitly revises a rule, the prior preregistration is inherited
verbatim: financing source/provenance, lagged signal, exogenous decision clock, mask eligibility,
common execution rule, H1 OPEN semantics, financing/cost accounting, predictive inference,
bootstrap/ensemble seeds, five-gate AND disposition, VOID/UNDETERMINED policy, and Stage-B lock.
There is one candidate: carry only.

Authoritative revised emitted artifacts:

- `prereg/2026-08-14-tms-carry-no-try-direct-gbp-universe.json`
- `prereg/2026-08-14-tms-carry-no-try-direct-gbp-mask.json`
- `prereg/2026-08-14-tms-carry-no-try-direct-gbp-price-readiness.json`

On discrepancy, emitted artifacts prevail and integrity fails closed.

## 2. Certified source and active financing grid

The certified TMS corpus is preserved unchanged. TRY rows remain in the raw/certified archive.
Starting mechanically from the 36 continuously available `.pro` FX pairs, remove every pair
incident to excluded currency TRY. Only `EURTRY.pro` is removed from the active grid, leaving
35 financing pairs and these 14 rankable/weightable currencies:

`AUD CAD CHF CZK EUR GBP HUF JPY NOK NZD PLN SEK USD ZAR`

`N = 14`; unchanged rule `k = floor(N/3)` gives `k = 4`. TRY is not investable and cannot enter
ranking, weights, routing, benchmarks, LOCO, or readiness.

## 3. Financing representation gate

Latent carry is recovered from the 35-pair active grid under `mean(r)=0`, using the unchanged
thresholds on every schedule: `R² >= 0.90`, `max|eps| <= 0.25 * SD(m)`.

| Grid | Rows | Currencies | min R² | max rel eps | Verdict |
|---|---:|---:|---:|---:|---|
| Full active grid | 35 | 14 | 0.999881 | 0.0431 | PASS |
| Over-identified subgraph | 31 | 10 | 0.999816 | 0.0504 | PASS |

The subgraph excludes degree-1 `HUF NOK SEK ZAR`; full and subgraph gates both remain binding.
No price data was accessed to derive or evaluate this representation.

## 4. Frozen routing and proof

Accounting numeraire is USD. Routing is deterministic and price/cost/performance-blind:

| Currency | Execution legs for one unit of currency vs USD |
|---|---|
| AUD | `AUDUSD.pro` +1 |
| CAD | `USDCAD.pro` -1 |
| CHF | `USDCHF.pro` -1 |
| CZK | `USDCZK.pro` -1 |
| EUR | `EURUSD.pro` +1 |
| GBP | `GBPUSD.pro` +1 |
| HUF | `EURHUF.pro` -1, `EURUSD.pro` +1 |
| JPY | `USDJPY.pro` -1 |
| NOK | `EURNOK.pro` -1, `EURUSD.pro` +1 |
| NZD | `NZDUSD.pro` +1 |
| PLN | `EURPLN.pro` -1, `EURUSD.pro` +1 |
| SEK | `EURSEK.pro` -1, `EURUSD.pro` +1 |
| USD | no leg |
| ZAR | `EURZAR.pro` -1, `EURUSD.pro` +1 |

`EURGBP.pro` remains in the 35-pair financing observation grid but is not an execution leg.
GBP exposure uses only direct `GBPUSD.pro`, so GBP exposure is not duplicated.

Each route is the zero-sum basis vector `e_c-e_USD`. For GBP this is supplied directly by
`GBPUSD.pro`. Thus for any `sum(w)=0` target, route quantity
`w_c` for every non-USD currency reconstructs every target exposure exactly; USD is the residual
`-sum(c != USD, w_c)=w_USD`. The universe artifact verifies the complete matrix identity.

## 5. Portfolio rule

Rank all 14 active currencies by lagged latent carry. Long top 4 at `+0.25` each; short bottom 4
at `-0.25` each; middle 6 zero. Therefore `sum(w)=0` and `sum(abs(w))=2`. USD remains rankable.
Targets reset at every evaluable rebalance. No leverage, volatility-target, or routing optimizer.

**Deterministic exact-tie rule.** At every rebalance form one total ordering of all currently
rankable currencies by `(latent carry descending, ISO currency code ascending)`. Longs are the
first `k` members and shorts are the last `k` members of that same ordering; separate long and
short sorts are prohibited. The ISO key applies only when the frozen deterministic latent-score
calculation produces exactly equal values. No rounding, epsilon, or near-tie tolerance is added.
It is solely a reproducibility convention for economically indistinguishable exact-score ties,
not an additional signal or optimization. Active Stage A uses `N=14`, `k=4`; every LOCO case uses
the identical rule with `N=13`, `k=4`; Stage B inherits the rule unchanged. This portfolio rule is
separate from the predictive Spearman-IC rule, which continues to use average ranks on ties.

Financing-only persistence diagnostics are declared non-gating: mean consecutive Kendall tau
0.968 (minimum 0.802), selected-set overlap 7.76/8, 13 distinct selected-set states, always-long
HUF/ZAR, always-short CHF/JPY. Heterogeneous USD/global-risk betas remain an explicit limitation.

## 6. Causal mask and execution

The emitted mask preserves byte-equivalent schedule content: 167 defined rebalances, 157
evaluable, 10 excluded; the financing-calendar decision clock and gap policy are unchanged.
At every entry, gap-boundary exit, and terminal liquidation, the whole book uses the first common
OANDA v20 practice H1 timestamp at/after the target with complete bid+ask for all routed legs,
within 48 hours. Fills and returns use candle OPEN. No asynchronous fills or timing substitution.

The execution approximation remains HYBRID: financing is TMS `.pro`; prices/spreads are OANDA v20
practice. It is never represented as historical `.pro` replication.

## 7. Predictive statistic and benchmark

The primary spot-only statistic is unchanged except its cross-section is the 14 active currencies.
The seeded `E-static` benchmark remains 1,000 static rank-blind books, same algorithm and PCG64
seed 20260809. Each draws 4 long and 4 short members once from the same 14 currencies, assigns
`+0.25/-0.25`, resets targets at each evaluable rebalance, and later recomputes actual routing,
turnover, financing, spreads, and risks. Membership is frozen before revised price access.

## 8. Leave-one-currency-out Gate 5

Run all 14 active-currency omissions. The omitted currency is removed only from the rankable and
weightable set; it remains a latent-design column and routing instrument, and the 35 active
financing rows remain. Each case has `N=13`, mechanical `k=floor(13/3)=4`, four long/four short at
`+0.25/-0.25`, `sum(w)=0`, `sum(abs(w))=2`, and its own unchanged-seed 13-currency static ensemble.
All 14 Gate-1 excesses must be strictly positive. No omission is chosen from results.

## 9. Revised price readiness

The prior readiness artifact belongs to the superseded design. Revised readiness starts BLOCKED
without inspecting or fetching prices during this revision. The emitted 13 required v20 legs are:

`AUD_USD EUR_HUF EUR_NOK EUR_PLN EUR_SEK EUR_USD EUR_ZAR GBP_USD NZD_USD USD_CAD USD_CHF USD_CZK USD_JPY`

Required frozen window: `2023-04-03T00:00:00Z` through `2026-08-05T00:00:00Z`; H1; bid+ask;
UTC alignment 0; OPEN field; common-timestamp coverage at every transaction. Existing caches may
be assessed only in a separately approved readiness gate. No leg may be dropped/substituted.

The Section 5 exact-tie clarification changes no universe, route, transaction instant, price
requirement, or cache identity: TRY remains excluded, GBP routes through `GBP_USD`, and the same
13 legs and 168 transaction instants remain certified by the committed readiness artifact.
`PRICE_READINESS_COMMITTED` therefore remains valid and no readiness rerun or refetch is required.

## 10. Acceptance and dispositions

### 10.1 Currency targets, routed notionals, and executable units

This accounting clarification was frozen by human decision before implementation and before any
Stage-A performance execution. No price or performance information informed it. At rebalance `t`,
let `E_t` be the accounting-scenario-specific USD equity immediately before the rebalance and let
`w` be the frozen currency target. Define `x = E_t * w`. For the frozen 14-currency, 13-edge
routing incidence matrix `R` (base `+1`, quote `-1`), solve `R n = x`. The target is zero-sum and
the routing graph is a spanning tree, so the signed USD-equivalent edge-notional vector `n` must be
unique; otherwise evaluation fails closed.

For routed pair `p`, target signed base units are
`Q_p = n_p / V_base,USD_mid(t)`. Valuation uses the midpoint of the same common H1 OPEN used for
execution: USD base has value 1; an `XXX_USD` base uses that pair's midpoint; an EUR-cross base
uses the simultaneous `EUR_USD` midpoint. Paths are fixed by routing, never selected from costs or
performance. The midpoint sizes the target only. Actual change `delta_Q = Q_target - Q_current`
buys at ASK OPEN when positive and sells at BID OPEN when negative, so actual fills—not target
selection—introduce spread P&L. Strategy, every benchmark book, and every LOCO case use identical
mechanics. Direct-USD, USD-base, and EUR-cross routes must reconstruct `x` exactly.

### 10.2 Gross convention

The binding normalization is currency gross `sum(abs(w)) = 2`: long sleeve gross 1 and short
sleeve gross 1. It is never rescaled to gross 1. Routed edge notionals are not separately
normalized; their gross can exceed 2 because synthetic EUR routes use multiple legs, which is a
routing/cost diagnostic rather than a risk target. This paragraph and Section 5 override every
inherited reference to `gross notional 1`, `sum(abs(w)) = 1`, or equivalent. Gate thresholds are
unchanged. Strategy, benchmark, and LOCO all use currency gross 2.

### 10.3 Client-financing day-count uncertainty

The certified TMS corpus does not uniquely specify the denominator converting a published
annualized client FX Long/Short rate into daily cash accrual. Therefore two complete accounting
scenarios are mandatory: `D360` uses denominator 360 and `D365` uses denominator 365. This is a
human-defined uncertainty envelope, not a claim that either scenario is historically correct,
preferred, primary, or exhaustive of every conceivable contractual convention. Neither scenario
may be selected or discarded after results, and the study is not exact historical TMS cash
replication.

For each scenario independently, start from identical initial USD equity; use only its denominator
in the inherited financing formula; evolve its own equity; and use that equity in every later
`x = E_t * w`, unit target, turnover, transaction cost, financing cashflow, and P&L calculation.
Strategy, all 1,000 benchmark books, every stress cell, and every LOCO case are separate complete
paths under each denominator. A shared trade path with financing substituted afterward is
prohibited. Signals, timestamps, memberships, seeds, routing, and all non-day-count rules remain
identical across scenarios.

All other inherited financing mechanics remain binding: position sign selects printed Long versus
Short rate from contemporaneous `F(d)`; the selected signed percentage rate alone preserves the
debit/credit sign; and the financing notional is the unsigned magnitude
`abs(Q_p) * pair_mid` in quote currency. Thus a short position does not apply its sign a second
time to an already signed Short rate. Apply the charged-day multiplier once, divide by scenario
denominator `D`, and convert the resulting signed quote-currency cash amount contemporaneously to
USD. Adverse stress worsens debits and reduces credits. The holiday-deviation multiplier remains
a distinct stress dimension and is not day-count uncertainty. This replaces the inherited signed
`Q` use and `basis_YYY` term only; all remaining financing mechanics are unchanged.

### 10.4 Dual-scenario gate disposition

The five thresholds remain unchanged, but their required scope is explicit. Gate 2 is spot-only
and denominator-independent, so it is evaluated once. Gates 1 and 3 must each PASS independently
under both `D360` and `D365`. Gate 4's existing adverse spread/financing corner must PASS under
both. Gate 5 requires every one of the 14 active-currency LOCO cases to PASS under both, with each
case retaining mechanical `N=13`, `k=4` and its scenario-specific benchmark paths. Results are
never averaged and no better or primary scenario is selected.

Any required failure in either scenario yields Stage-A `CLOSED_FAIL`. Only Gate 2 PASS together
with Gates 1/3/4/5 PASS under both scenarios yields `SURVIVES_KILL_TEST`. Readiness/integrity
triggers remain fail-closed. Stage B inherits the identical dual-accounting requirement.

This clarification changes no universe, tie rule, route, mask, execution timestamp, price leg, or
cache identity: 14 active no-TRY currencies, `k=4`, direct `GBP_USD`, 13 price legs, and all 168
certified transaction instants remain binding. `PRICE_READINESS_COMMITTED` remains valid; no
refetch or readiness rerun is required. Stage A has not executed and no result or permission
follows from this clarification.

### 10.5 Venue-evidenced financing events (pre-performance clarification)

This rule was frozen by explicit human decision after the first authorized attempt stopped in
pre-statistics integrity and before any economic or performance statistic was computed. Attempt 1
remains `UNDETERMINED_SUSPENDED`: it has no Stage-A verdict and no performance result artifact.
The prior freeze manifest remains immutable historical evidence but is ineligible for execution.
This is neither performance rescue nor VOID. Any future attempt requires this committed
clarification, reviewed implementation, a new immutable freeze, and new explicit authorization.

For each conceptually held routed pair independently, a baseline financing valuation/accrual event
exists only when that held instrument has a venue-evidenced H1 OPEN at the contractual 21:00 UTC
rollover timestamp inside an active/evaluable holding interval. Held membership is derived only
from the causal financing schedule, latent ranking, `k=4`, fixed routing, and holding interval;
equity magnitude, prices and performance never determine membership. A Monday-Friday calendar
label alone does not create an event. If the held instrument has no such OPEN, the disposition is
`NO_STANDALONE_BASELINE_FINANCING_EVENT_AT_THAT_TIMESTAMP`: no price is synthesized, carried,
backfilled, advanced, interpolated or moved to another date. This convention does not assert that
TMS economically charged zero; exact historical holiday cashflow timing is source-insufficient.

An eligible event requires only the inputs used by its non-zero held route. Its own same-time H1
OPEN midpoint is mandatory. Direct `XXX_USD` needs no extra conversion leg; `USD_XXX` uses the
same pair inversely; an EUR-cross also requires same-time `EUR_USD` for USD conversion. Inactive
or unrelated members of the 13-leg execution universe are irrelevant. Once a held-pair event is
venue-evidenced, a missing required conversion input is a fail-closed financing-readiness failure;
the event may not be skipped.

The standard rollover/day-multiplier rules are unchanged. Historical holiday-specific deviations
are not reconstructed, and missing holiday charges are not shifted. `D360` and `D365` use the
same venue-evidenced event set and differ only by denominator. The existing adverse cell remains
the sole uncertainty sensitivity: it worsens observed debits (`x1.25`, with `days_charged x1.10`)
and reduces credits (`x0.80`), so its direction is adverse under either possible debit/credit
holiday uncertainty. It is a sensitivity, not a claim to bound or reconstruct omitted cashflows.

The mechanically emitted pre-performance evidence is
`prereg/2026-08-14-tms-carry-financing-readiness.json`. Transaction execution readiness remains
separate and unchanged: no-TRY `N=14`, `k=4`, direct `GBP_USD`, 13 execution legs, the existing
cache hashes, and all 168 nominal/resolved mappings remain binding and certified.

Scientific disclosure: historical financing is not exact `.pro` client-cash replication. The
source-insufficient denominator is covered by mandatory `D360`/`D365`; holiday multipliers and
closed-market cashflow timing are unavailable; baseline accounting therefore uses only
venue-evidenced events, with the preregistered adverse financing/holiday sensitivity reporting the
remaining uncertainty. Stage B inherits this rule.

### 10.6 Pre-statistics infrastructure-defect governance

This clarification is frozen by explicit human decision while
`REAL_STAGE_A_PERFORMANCE_COMPUTED = NO`. It separates defects adjudicated before any real
economic/statistical calculation from the existing post-statistics material-defect/VOID policy;
it does not change any scientific parameter, universe, route, signal, gate or threshold.

The research begins in `PRE_STATISTICS`. It transitions irreversibly to `ECONOMICS_STARTED`
immediately before the first computation on real Stage-A data capable of producing any economic
or statistical performance quantity, including PnL/returns, financing cashflow contributing to
equity, benchmark performance, IC, MDD, stress, LOCO or a gate statistic. Metadata, hash, schema,
timestamp and preflight operations do not cross this boundary. Once crossed, Stage A can never
return to `PRE_STATISTICS`.

A material implementation, data or integrity defect is a `PRE_STATISTICS_INFRA_DEFECT` only when
it is discovered before `ECONOMICS_STARTED`, independently demonstrated, reviewer-confirmed,
defined outcome-independently, no performance statistic or result has been computed or inspected,
and its correction uses no performance information. It blocks execution/freeze, creates no
Stage-A verdict, and does not consume the one corrected-economic-execution allowance. It must be
retained permanently in lineage and requires correction, review, tests, a completely new immutable
freeze and new explicit human authorization. Authorization consumption and operational attempt
history are never reset; attempt identifiers increase monotonically across run and freeze IDs.

After `ECONOMICS_STARTED`, the pre-statistics correction window is permanently closed. Any later
qualifying material implementation/data defect remains governed by Section 10.2 without
relaxation: the original result/artifact is retained immutably, at most one corrected economic
execution is permitted under the unchanged scientific specification, and a second qualifying
post-statistics material defect yields `SUSPENDED_INFRA` with no further Stage-A execution.

Four separate histories are binding and may not be conflated: operational authorization/execution
attempt lineage; pre-statistics infrastructure-defect history; post-statistics qualifying
material-defect count; and corrected-economic-execution allowance. Multiple pre-statistics defects
create no additional post-statistics allowance. Infrastructure correction cannot change a
scientific choice; any scientific change requires its own explicit human preregistration gate.
No authorization is reusable, no corrected infrastructure state may execute without a fresh
manifest and explicit authorization, and no correction triggers automatic execution.

Current lineage is frozen as follows. Operational Attempt 1 remains retained and its authorization
consumed. Its pre-statistics integrity failure occurred before economics began; no performance
result or Stage-A verdict exists. Root cause `ORCHESTRATOR_INTEGRITY_DEFECT` is classified
`PRE_STATISTICS_INFRA_DEFECT`, with immutable evidence retained and no performance-result VOID.
The independently reviewed cross-freeze lineage defect is also a `PRE_STATISTICS_INFRA_DEFECT`:
it materially affects authorization count, correction eligibility and terminal governance and
must be corrected before a new freeze. Thus the current post-statistics material-defect count is
zero and the single corrected-economic-execution allowance remains unused. A future manifest must
inherit Attempt 1 and both pre-statistics defects across run/freeze IDs; it may not reset the next
operational attempt to 1.

### 10.7 Infrastructure-invalid run policy (human governance amendment)

This amendment supersedes only the Stage-A-closing interpretation of the second-defect rule above.
Stage A closes only on a valid, auditable strategy verdict or when reliable evaluation becomes
technically impossible. An infrastructure defect invalidates and VOIDs only the affected execution,
which remains immutable; outcome-independent infrastructure-only correction may permit another
execution of the exact same scientific experiment. It cannot change the strategy, universe,
parameters, gates, window, benchmark, inference, or thresholds.

Attempt 2 exposed a provisional disposition through a defective, unauditable result artifact. That
disposition is not scientific evidence, and any later historical execution is not independent
confirmation. The next valid auditable execution is the decisive Stage-A evaluation. A valid gate
failure closes the family without tuning or rescue; all-gates survival has only the preregistered
`SURVIVES_KILL_TEST` meaning. Every invalid run and authorization remains retained and consumed;
each later execution requires reviewed infrastructure, a new immutable freeze, and new explicit
human authorization. Reliable evaluation becoming technically impossible closes infrastructure
without manufacturing a strategy verdict.
