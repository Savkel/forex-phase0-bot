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

## 10. Acceptance and dispositions

The five gates and thresholds are inherited unchanged in meaning: benchmark-relative RAP,
spot-only predictive evidence, drawdown versus ensemble median, adverse-stress positive total
return, and all-case LOCO robustness. All PASS yields `SURVIVES_KILL_TEST` only; any valid FAIL
yields permanent `CLOSED_FAIL`; readiness/integrity triggers remain fail-closed. Stage A has not
executed. No result or permission follows from this revision.
