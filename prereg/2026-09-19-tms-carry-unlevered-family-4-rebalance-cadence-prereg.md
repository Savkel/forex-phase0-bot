# Unlevered Carry Development Family 4 — Rebalance-Cadence Preregistration

- **Status:** PREREGISTERED FAMILY-4 DESIGN; LOCKED ON COMMIT; NOT EXECUTION-AUTHORIZED.
- **Selected DEVELOPMENT base:** U14 + Family-2 H2 (`h=2`) + equal weighting, `k=4`.
- **Scope:** historical DEVELOPMENT research only; no network access, trading, deployment, or Stage-B change.

## 1. Isolated hypothesis

Test only rebalance cadence. `M2/M4` jointly change trade frequency and the timing at which H2
membership/state is refreshed. The hypothesis is that a slower cadence may improve net return/risk
efficiency by changing this complete rebalance process while preserving the causal U14/H2 carry
opportunity. Any observed improvement must be attributed to the combined cadence effect, not solely
to lower turnover or spread cost.

This is distinct from Family 2, which changed membership persistence while retaining every weekly
target reset, and Family 3, which changed within-sleeve weights. Universe, H2 and equal weights do
not vary here.

`NO AUTOMATIC CANDIDATE REJECTION OR WINNER SELECTION; FINAL ADJUDICATION IS EXTERNAL.`

## 2. Candidate family

Let `m` be the deterministic ordinal interval between rebalance opportunities on the frozen
eligible weekly decision sequence within a contiguous evaluable segment:

| ID | m | Semantics |
|---|---:|---|
| `M1_CONTROL` | 1 | Execute at every eligible weekly decision; exact selected EQ_H2 control. |
| `M2` | 2 | Execute at every second eligible weekly decision: segment indices `0,2,4,...`. |
| `M4` | 4 | Execute at every fourth eligible weekly decision: segment indices `0,4,8,...`. |

For every candidate, the cadence anchor is explicitly the first evaluable decision after strategy
initialization or gap re-entry; that decision is local index `0` and always executes. Subsequent
eligible decisions increment the local ordinal by one. Cadence never uses weekdays, elapsed days,
ISO weeks or a rolling calendar, so holiday-length intervals create no ambiguity. No other cadence
may be added after results.

## 3. Exact state and accounting semantics

Each contiguous evaluable segment starts at local index `0`. Its first decision always executes,
uses the current causal signal, resets H2 state to current top/bottom four, and targets equal
`+0.25/-0.25` weights. A gap destroys both incumbent state and the cadence counter.

At a later decision whose local index is divisible by `m`, apply the frozen H2 state machine once
using the current causal ranks and memberships actually held since the preceding execution. Reset
the resulting four-long/four-short book to equal `+0.25/-0.25` targets and execute at the frozen
common H1 bid/ask OPEN.

At every intervening decision:

- continue the frozen weekly mark-to-market, return-period boundary and financing accounting at
  the same frozen common H1 OPEN;
- do not solve new target units, trade, resize, or update H2 incumbent state;
- hold the existing routed units exactly unchanged;
- ignore the current signal for portfolio decisions, while retaining it for invariant IC evidence;
- continue frozen financing and spot accounting on those held units.

Weekly accounting returns and the frozen 52/52/53 blocks remain defined at all 157 evaluable
boundaries. A hold-mark closes the prior weekly return period and opens the next without a trade.
The existing execution contract overrides the ordinary cadence wherever required: an immediate
gap exit liquidates the book, gap re-entry immediately establishes the current reset book and
restarts local index `0`, and terminal liquidation immediately leaves the strategy flat. None may
be delayed or skipped by M2/M4. Their costs remain attributed under the frozen rules.

Target gross at every strategy-controlled execution is exactly `2`, with sleeves `+1/-1` and net
currency weight `0`. No target, volatility scaling, risk targeting or leverage multiplier may
exceed this frozen scale. Passive exposure drift while exact units are held is not active leverage;
realized currency/routed gross drift must be reported explicitly.

## 4. Frozen interactions and invariants

Frozen throughout: U14; `k=4`; H2 `h=2`; equal weighting; latent carry solve; rank/tie rule;
causal lag; availability mask; all 157 weekly valuation boundaries; routes including direct GBP;
OANDA H1 bid/ask OPEN evidence; financing-event identity and schedule selection; spot/financing
accounting; D360/D365 independence; historical window; adverse financing and spread-x3 rules;
LOCO definitions; chronological blocks; data/artifact hashes; and Stage-B isolation.

Forbidden interactions include changing H2, `k`, weights, universe, signal, gap policy, execution
time, costs, carry threshold, hysteresis threshold, concentration cap, or gross scale. No
cost-aware override may force or suppress an otherwise scheduled execution.

For LOCO, retain frozen N13/`k=4` H2 mechanics. The cadence counter follows the same segment-local
rule and does not depend on the omitted currency.

## 5. Benchmark and invariant evidence

Reuse the identical frozen static-book memberships and seeds. For each `m`, book memberships stay
static, H2 is never applied, and the corresponding static benchmark uses exactly the candidate's
rebalance cadence and the same gap/terminal overrides: equal weights reset only at its execution
opportunities and exact routed units remain unchanged at skipped decisions. Thus every
candidate-versus-benchmark comparison uses matched cadence. All benchmark turnover, spreads,
financing, spot P&L, gross drift, risks, stresses and blocks must be recomputed.

The latent signal and forward-return methodology are unchanged, so signal IC alone remains
invariant and may be hash-reused. No realized strategy or benchmark economics may be reused across
cadences.

## 6. Required evidence and diagnostics

For every candidate and both D360/D365, recompute total return, CAGR, RAP, positive-return Calmar,
signed MaxDD, benchmark-relative RAP/MDD, base/adverse/spread-x3 paths, all LOCO cases, and frozen
52/52/53 blocks. Report spot/financing attribution, spread cost, currency/routed turnover, trade
and fill counts, mean/max routed gross, concentration and membership persistence.

Cadence-specific diagnostics must include segment action schedules and hashes; executed,
hold-mark, forced-exit and re-entry counts; elapsed days between executions; H2 retained/exited/
entered memberships only at execution opportunities; skipped target resets; and turnover/cost
differences versus `M1_CONTROL`. Every result remains visible; all comparisons are diagnostic.

## 7. Control parity and readiness

Before any `M2/M4` economics, `M1_CONTROL` must reproduce immutable Family-3 `EQ_H2`:

- exact timestamps, action types, memberships, routes, financing-event identities/counts and all
  other discrete paths;
- elementwise floating equality within absolute `1e-12` for strategy, benchmark, stress, LOCO,
  block, attribution, turnover, concentration and risk arrays/scalars;
- exact IC evidence hash reuse.

Readiness must be network-free and hash-bound, prove all three deterministic action schedules,
gross/weight/gap invariants and static-book semantics, and report no candidate economics. Synthetic
tests must prove that a hold-mark creates no fill/cost or target-unit solve, preserves exact units,
still closes a weekly return period, and applies financing to those held units.

## 8. Artifacts and one-shot policy

A future approved implementation gate must create separate readiness and M1 parity artifacts.
A later separately authorized economic gate must write an immutable execution marker before any
`M2/M4` economics, set `consumption_count=1`, execute both candidates exactly once, then write
result and completion artifacts preserving every output with
`PENDING_EXTERNAL_ADJUDICATION`. Any existing execution/result/completion artifact blocks rerun.

No tuning, rescue execution, new cadence, automatic rejection, or automatic winner selection is
permitted. Prospective Stage B for the original Stage-A/H0 strategy remains untouched.
