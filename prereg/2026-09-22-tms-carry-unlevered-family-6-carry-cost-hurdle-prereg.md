# Unlevered Carry Development Family 6 - Carry/Cost Hurdle Preregistration

- **Status:** PREREGISTERED FAMILY-6 DESIGN; LOCKED ON COMMIT; NOT IMPLEMENTATION- OR EXECUTION-AUTHORIZED.
- **Gate:** `FAMILY6_CARRY_COST_HURDLE_DESIGN`.
- **Base:** retained DEVELOPMENT configuration U14 + H2 (`h=2`) + EQ + M1 + `k=4`.
- **Scope:** historical DEVELOPMENT only. No Stage-B access, network/data fetch, trading, or deployment.

## 1. Authority, isolation, and hypothesis

`CLAUDE.md`, the closed Stage-A specification, the frozen Family-2 and Family-5
preregistrations, and the Family-5 closure govern. Families 1-5 and Stage A remain immutable.
The original Stage-A U14/k4/H0 strategy remains isolated for prospective Stage B.

Family 2 section 4 deferred a separately preregistered carry-advantage-versus-transaction-cost
rule. This family tests only that pre-existing idea: whether vetoing a complete H2 rotation when
its causally expected financing improvement does not cover its contemporaneously estimable,
routed and netted replacement cost improves robust net evidence. It does not add a signal,
forecast-horizon search, leverage, risk scaling, or a subset optimizer.

`NO AUTOMATIC CANDIDATE REJECTION OR WINNER SELECTION; FINAL ADJUDICATION IS EXTERNAL.`

## 2. Frozen candidate set

| ID | multiplier lambda | Decision |
|---|---:|---|
| `HURDLE_OFF_CONTROL` | 0 / bypass | Accept every complete H2 proposal; exact retained Family-5 K4 behavior. |
| `HURDLE_1X` | 1 | Require one scheduled week's expected financing improvement to cover the contemporaneous replacement cost. |
| `HURDLE_2X` | 2 | Require it to cover the immediate cost plus one equal-cost unwind reserve, both valued at the current snapshot. |

This is the complete set: exactly one control and two nonzero, economically interpreted hurdles.
No other multiplier, adaptive rule, forecast horizon, per-currency threshold, or combined
mechanism may be added. Lambda is the only Family-6 candidate dimension; the fixed dual-ledger
envelope is inherited D360/D365 uncertainty handling, not another candidate or tuning axis.

## 3. Causal proposal and hurdle timestamp

At every ordinary M1 rebalance, first run the frozen K4/H2 state machine from the candidate's
currently accepted incumbent sleeves. Define two same-snapshot counterfactual EQ targets:

- `A`: incumbent membership reset to the normal M1 `+0.25/-0.25` targets;
- `B`: the complete normal H2 proposed membership reset to the same M1 targets.

Signal ranks use the existing causal financing schedule selected at the nominal decision and the
frozen score/ISO tie order. H2 completes `B` before hurdle evaluation. If memberships in `A`
and `B` are identical, execute the ordinary M1 reset `A=B` without applying or counting a
hurdle. The hurdle exists only when membership differs.

The hurdle decision occurs at the already-frozen resolved common H1 execution OPEN `t`. The H2
proposal and its causal schedule already exist; the simultaneous bid/ask OPEN snapshot is then
observable and is the only price/quote snapshot the hurdle may use. No later quote, price,
financing schedule, financing event, or realized outcome is accessible. Acceptance/veto and the
fill use that same snapshot; there is no extra timing choice.

## 4. Exact incremental hurdle calculation

Maintain the candidate's two unstressed base accounting ledgers, D360 and D365, through time
using the same prior hurdle decisions. At `t`, for each `D`, let `E_D>0` and `q_D^-` be
causally accumulated pre-trade equity and routed base units after current mark-to-market. From
the same `E_D`, routes and OPEN midpoint graph, solve `u_D(A)` and `u_D(B)`. Thus A and B
contain identical ordinary M1 resizing mechanics and differ only in membership.

For `W` in `{A,B}`, compute the frozen base-spread counterfactual execution cost

`TC_D(W) = fsum_p(abs(u_D(W)[p]-q_D^-[p]) * abs(fill_p(u_D(W)[p]-q_D^-[p])-mid_p) * quote_to_USD_p)`,

with zero deltas omitted. Pair iteration is lexicographic; route aggregation precedes the cost.
The incremental cost return attributable to choosing B rather than A is
`dc_D=(TC_D(B)-TC_D(A))/E_D`. Define `K=max(0,dc_360,dc_365)`. Therefore if both cost
differences are nonpositive, `K=0`; a cheaper B receives no artificial credit and must still
have nonnegative financing benefit. If either difference is positive, the larger normalized
increment is used. This denominator-robust envelope preserves one membership path and includes
direct GBP, synthetic EUR, all shared-leg netting, resizing interactions and side reversals.

Let `S` be exactly the causal schedule already used to form the current signal. Horizon `H=7`
is the calendar-day difference between this nominal weekly decision and its frozen scheduled hold
end. This is a purely hypothetical projection formed at hurdle decision timestamp `t`: `S` is
held fixed for the full forecast window and D360/D365 use only their frozen deterministic
denominator mechanics. It is not extended to a later evaluable execution or altered for holidays. For `W` in
`{A,B}` define the expected financing return

`f_D(W)=(7/E_D)*fsum_p(abs(u_D(W)[p])*mid_p*(rate_S(p,sign(u_D(W)[p]))/100/D)*quote_to_USD_p)`.

Choose the printed Long/Short rate by routed pair-base sign exactly as in frozen accounting.
Define incremental expected benefit
`G=min(f_360(B)-f_360(A),f_365(B)-f_365(A))`.

Causality is mechanical: `S` must satisfy the existing `valid_to < nominal decision date`
selection rule; `H` comes only from the current frozen decision/hold-end record; `E_D` and
`q_D^-` contain only ledger history through `t`; and every midpoint, bid, ask and conversion
is from the single row at `t`. The forecast neither enumerates nor reads future financing-event
rows, later TMS schedules, later price rows, or later quote rows. Future-prefix mutation must
leave the decision unchanged. Seven-day pro-rating is an expectation proxy, not predicted
venue-evidenced accrual.

When membership differs: the control accepts B unconditionally; `HURDLE_1X` accepts B iff
`G>=K`; `HURDLE_2X` accepts B iff `G>=2K`. Equality accepts. The second threshold reserves
the positive immediate incremental cost once more as a same-snapshot symmetric unwind proxy,
giving the intended round-trip-cost rationale without a future quote. When `K=0`, both nonzero
variants require `G>=0`. Use binary64, `math.fsum`, sorted pairs, no rounding or tolerance.
Record all `TC_D`, `dc_D`, `f_D`, `G`, `K`, threshold, margin, routed deltas and decision.

## 5. Atomic state semantics

Acceptance executes B. Veto executes A, including its ordinary M1 EQ resize; it never passively
holds `q_D^-`. Either outcome pays its realized frozen execution cost. A veto leaves A's
membership as incumbent state for the next H2 proposal.

H2 resolves all retained incumbents, exits, vacancies, entrants, immediate opposite-sleeve moves,
and exact score ties before the hurdle. The hurdle never pairs entrants with exits and never
accepts a subset. All simultaneous changes, same-currency side reversals, shared routed legs and
netting enter one order-independent portfolio delta. Selecting a best subset would be a new
combinatorial portfolio optimization problem and is expressly out of scope.

Initialization and gap re-entry use frozen fresh top/bottom four and are not hurdled because no
incumbent exists. Gap exit and terminal liquidation are forced, immediate and unhurdled; they
clear state and retain all costs. Fresh/forced transitions are excluded from hurdle counts.
Full and all LOCO cases keep frozen K4/H2 rules; an omitted currency retains only its inherited
latent/routing roles.

## 6. Benchmarks, reuse, and accounting

The hurdle is signal-, incumbent- and proposal-dependent. A static E-book has no H2 proposal or
replacement decision, so candidate-matched hurdle semantics are undefined and must not be
invented. Reuse the exact hash-bound Family-5 K4 full/LOCO static memberships and paths for every
candidate. Universe, `k`, weights, gross, M1 timing, routes, quote inputs, costs, financing and
liquidation rules are unchanged. No benchmark redraw or candidate-specific filter is permitted.

Reuse frozen full-U14 IC evidence. Recompute each non-control strategy path and all membership,
rotation and hurdle diagnostics. Preserve independent D360/D365 accounting, base, adverse and
spread-x3 scenarios, 52/52/53 chronological blocks, all 14 LOCO omissions, attribution, turnover,
routed gross, concentration and deterministic benchmarks. Hurdle decisions are fixed from the
unstressed dual-ledger calculation and are not re-decided under stresses or denominators.
Preserve all negative evidence.

## 7. Fail-closed control parity before non-control economics

Before any `HURDLE_1X` or `HURDLE_2X` historical economics, `HURDLE_OFF_CONTROL` must reproduce
the immutable Family-5 K4 control/reference:

- zero timestamp, score-rank, membership/state/rotation/action, gap/terminal, route, event,
  static-book, scenario, block, omission, schema-shape or other discrete mismatches;
- elementwise absolute difference `<=1e-12` for every strategy and static-book unit, fill, cost,
  accrual, equity, return, attribution, turnover, risk, stress, block and LOCO float;
- exact inherited input, IC, full/LOCO book, control-result and control-path hashes;
- recorded shapes/counts, zero mismatch counts, maximum differences and source hashes.

The control must traverse the new proposal interface with a true bypass, not copy expected output.
Any mismatch blocks non-control execution and is an infrastructure failure, not an economic
verdict. Readiness, parity, implementation/tests, and economics require separate authorization.

## 8. Required tests, risks, and execution governance

Future tests must cover strict candidate/config validation; future-prefix invariance; same-snapshot
A/B target construction; unchanged-membership M1 reset without a hurdle; veto execution of A
rather than passive hold; exact routed/netted `TC_D(B)-TC_D(A)`; positive, zero and negative
cost differences; direct GBP and synthetic EUR routes; negative benefit and exact-threshold
acceptance; multi-name and side reversals; veto-state recursion; H2 vacancy/tie boundaries; gaps,
re-entry and terminal flat; denominator- and stress-identical decisions; LOCO; and complete
control parity. Imports/readiness must run no economics or network access.

Main limitations are: `S` can be stale and future rates can change; seven-day pro-rata expected
financing deliberately ignores source-insufficient future holiday/event realization; execution
evidence remains hybrid TMS-rate/OANDA-quote; the same-snapshot unwind reserve is a proxy rather
than a future realized exit cost; and atomic veto may conceal a beneficial subset. These are
disclosed model risks, not permissions for adaptive tuning.

Future economics, if separately approved after freeze and infrastructure review, are one-shot and
manual under an exclusive immutable marker. A partial/error run requires external adjudication;
there is no automatic rerun. Results use only `PENDING_EXTERNAL_ADJUDICATION`; no code selects,
rejects, ranks, rescues, or substitutes a candidate into Stage B.
