# Unlevered Carry Development Family 3 — Carry-Strength Weighting Preregistration

- **Status:** PREREGISTERED FAMILY-3 DESIGN; LOCKED ON COMMIT; NOT EXECUTION-AUTHORIZED.
- **Programme:** historical DEVELOPMENT optimization, separate from closed Stage A and Families 1–2.
- **Selected DEVELOPMENT base:** U14 with Family-2 `H2` (`h=2`), `k=4`.
- **Scope:** research only; no network access, trading, deployment, or Stage-B change.

## 1. Governance and research question

Stage A and closed Families 1–2 remain immutable. This family asks whether causal
carry-strength-aware weighting improves net return/risk efficiency versus equal `±0.25`
weights while preserving total gross `2` and adding no leverage.

All configurations and results remain visible. Diagnostic comparisons cannot reject, select,
rank, or declare a winner.

`NO AUTOMATIC CANDIDATE REJECTION OR WINNER SELECTION; FINAL ADJUDICATION IS EXTERNAL.`

## 2. Frozen base and candidates

The eligible universe is frozen U14:

`AUD CAD CHF CZK EUR GBP HUF JPY NOK NZD PLN SEK USD ZAR`

Family-2 `H2` membership selection, retention, deterministic rank/tie ordering, vacancy fill,
gap reset, gap exit, and terminal-flat rules remain unchanged. Every active path has four long
and four short currencies.

| ID | tau | Implied absolute-weight range |
|---|---:|---:|
| `EQ_H2` | `0` | `[0.25, 0.25]` |
| `CS_MILD` | `0.10` | `[0.20, 0.30]` |
| `CS_STRONG` | `0.20` | `[0.15, 0.35]` |

No other intensity, cap, floor, mapping, or result-informed variant may be added.

## 3. Frozen causal weighting rule

At each evaluable decision, first determine final memberships through the frozen H2 state
machine. For each sleeve independently, orient the current causal latent carry score `s_i` as
`x_i=s_i` for a long and `x_i=-s_i` for a short. Define:

```text
d_i = x_i - mean(x)
D   = sum_i abs(d_i)
R   = max(active-universe s) - min(active-universe s)
z_i = d_i / max(D, 1e-12 * R)
|w_i| = 0.25 + tau * z_i
```

If `D=0` or `R=0`, all four sleeve magnitudes are `0.25`. Equal oriented scores receive equal
weights. The full U14 score range supplies `R` for full/static-book paths; a LOCO path uses its
active N13 score range.

Apply positive signs to longs and negative signs to shorts. Each long sleeve sums exactly `+1`,
each short sleeve exactly `-1`, net currency weight is `0`, and currency gross is `2`. The
formula itself implies the frozen ranges above. Clipping, discretionary residual adjustment,
volatility scaling, risk targeting, rescaling, and additional leverage are forbidden.

Weights are recomputed causally at every evaluable decision after membership selection. Gap
re-entry first resets membership through the frozen H2 rule and then applies this formula.
Gap exits and terminal liquidation remain flat.

## 4. Frozen invariants

Only weights within selected sleeves change. U14, `k=4`, H2 membership mechanics, signal and
latent solve, causal timing, availability mask, rebalance schedule, transaction timestamps,
routes, OANDA H1 bid/ask OPEN execution, financing and spot accounting, D360/D365 independence,
historical window, adverse corner, and spread-x3 sensitivity remain unchanged.

All realized weight changes enter routed turnover, trades, spreads, financing exposure, and
accounting. Weight-only turnover must be reported separately from membership-change turnover,
alongside total currency/routed turnover and realized costs.

## 5. Benchmark and reused evidence

Reuse the identical frozen Family-2 static-book memberships and deterministic seeds. Each book's
long and short memberships remain static. At every evaluable decision, apply the candidate's
current `tau` causally within each fixed sleeve using Section 3. Do not apply H2 membership,
retention, vacancy-fill, or gap-reset selection logic inside static books. Include every resulting
weight-only trade, routed turnover, spread cost, financing exposure, and accounting effect.

Only the unchanged latent-signal IC and its bootstrap evidence are invariant and reusable. Reuse
must be hash-bound. No candidate realized-path or benchmark economic evidence may be reused.

## 6. Recomputed evidence

For `EQ_H2`, `CS_MILD`, and `CS_STRONG`, separately recompute D360 and D365 realized economics;
candidate-weighted static benchmarks; base, adverse and spread-x3 scenarios; LOCO; frozen
52/52/53 chronological blocks; CAGR, total return, RAP, positive-return Calmar and signed MaxDD;
benchmark-relative RAP/MDD; spot and financing attribution; turnover, trades and spread costs;
and membership/weight concentration diagnostics.

Before any nonzero-`tau` economic calculation, `EQ_H2` must reproduce the immutable Family-2 H2
control: exact discrete/categorical paths and elementwise absolute numeric difference `<=1e-12`
for floating arrays/scalars. Shapes, mismatch counts, and maximum differences must be recorded.
A parity mismatch blocks execution but is not a candidate verdict.

## 7. Artifacts and adjudication

Future readiness, parity, execution, result, and completion artifacts must be network-free,
hash-bound to this preregistration and frozen sources, preserve every configuration and result,
and use `PENDING_EXTERNAL_ADJUDICATION` as the sole scientific decision state. No rescue tuning,
post-result rule invention, automatic rejection, or winner selection is permitted.
