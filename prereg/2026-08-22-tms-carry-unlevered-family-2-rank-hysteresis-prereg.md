# Unlevered Carry Development Family 2 — Rank-Hysteresis Preregistration

- **Status:** PREREGISTERED FAMILY-2 DESIGN; LOCKED ON COMMIT; NOT EXECUTION-AUTHORIZED.
- **Programme:** historical DEVELOPMENT optimization, separate from closed Stage A and Family 1.
- **Control:** immutable U14 carry strategy retained after Family 1.
- **Scope:** research only; no network access, trading, deployment, or Stage-B change.

## 1. Governance and research question

`CLAUDE.md`, the closed Stage-A specification, and committed Family-1 evidence govern. Stage A
and Family 1 remain immutable. This family asks whether stateful rank hysteresis can preserve the
U14 carry opportunity set while reducing unnecessary rotations and spread drag, thereby improving
net CAGR without added leverage.

All configurations and results remain visible. Diagnostic comparisons cannot reject, select, rank,
or declare a winner.

`NO AUTOMATIC CANDIDATE REJECTION OR WINNER SELECTION; FINAL ADJUDICATION IS EXTERNAL.`

## 2. Frozen candidates and portfolio scale

The eligible universe is frozen U14:

`AUD CAD CHF CZK EUR GBP HUF JPY NOK NZD PLN SEK USD ZAR`

For every configuration, `N=14`, `k=4`, each long has weight `+0.25`, each short has weight
`-0.25`, each sleeve gross is 1, currency gross is 2, and net currency weight is 0. There is no
volatility scaling, risk targeting, or additional leverage.

The complete candidate family is the rank exit-buffer set:

| ID | h | Meaning |
|---|---:|---|
| `H0_CONTROL` | 0 | Current U14 top-4/bottom-4 behaviour |
| `H1` | 1 | One-rank exit buffer |
| `H2` | 2 | Two-rank exit buffer |
| `H3` | 3 | Three-rank, maximum symmetric U14 buffer |

No other buffer, threshold, combined mechanism, or result-informed variant may be added.

## 3. Causal state machine

At each evaluable decision, rank all U14 currencies by the frozen total order: latent carry
descending, then ISO currency code ascending. No rounding or near-tie tolerance is allowed.

At an ordinary rebalance for buffer `h`:

1. Retain a prior long incumbent while its current rank is `<= 4+h`.
2. Retain a prior short incumbent while its current rank is `>= 11-h`.
3. Fill long vacancies from rank 1 upward and short vacancies from rank 14 downward, excluding
   currencies already assigned to either sleeve. Retained incumbents are assigned before entrants;
   long vacancies are filled before short vacancies. The resulting sleeves must be disjoint and
   contain exactly four currencies each.
4. Reset every selected currency to equal `+0.25` or `-0.25`; partial weights are forbidden.

`h=0` must reproduce the frozen control exactly. A currency that fails its incumbent condition is
eligible immediately for the opposite sleeve if its current rank reaches that sleeve's fill order.

Gap exits and terminal liquidation remain flat. A gap destroys incumbent state: gap re-entry uses
the current top four and bottom four without hysteresis. Gap/terminal events are excluded from
avoided-replacement counts but remain included in turnover, trades, costs, and accounting.

## 4. Frozen invariants

Only portfolio-membership persistence changes. Signal construction and full-grid latent solve,
causal lag, frozen availability mask, 167 evaluable periods, exact transaction timestamps,
rebalance schedule, routes including direct GBP routing, OANDA H1 bid/ask OPEN execution, equal
weights, gross scale, financing-event model, spot accounting, D360/D365 independence, historical
window, adverse corner, and spread-x3 sensitivity remain identical to frozen Stage A/U14.

Direct carry-advantage-versus-transaction-cost thresholding is out of scope. It requires separate
preregistration of forecast horizon, routed/netted replacement cost, financing conversion, and
decision rule. It must not be combined with rank hysteresis in this family.

## 5. Reused and recomputed evidence

The latent signal is unchanged, so full-U14 predictive IC and its bootstrap evidence are invariant
and reused without a new hypothesis test. Static benchmark memberships and paths are also
invariant because universe, `k`, gross, timestamps, costs, and financing rules are unchanged; the
same U14 E-static distribution is reused for all `h` values. For LOCO, the frozen benchmark for a
given omission is reused across `h` values. Reuse must be hash-bound and reported, never silently
recomputed with different books or seeds.

Each `h` separately recomputes its realized strategy path under D360 and D365, including base,
adverse and spread-x3 scenarios; full-period and frozen 52/52/53 chronological blocks; LOCO;
turnover, routed turnover/gross, spread costs, financing, spot P&L and trade counts; concentration,
selection persistence, CAGR, total return, RAP, positive-return Calmar, signed MaxDD, and
benchmark-relative RAP/MDD diagnostics.

Family-2 LOCO omits each currency from the rankable/weightable set while retaining frozen latent
lineage and routing rules. It keeps `k=floor(13/3)=4`. For an omission, the same state machine uses
active-universe ranks: long retention `rank<=4+h`, short retention `rank>=10-h`; retained sets are
formed first, then vacancies are filled from active extreme ranks using the same exclusion/order
rule. This deterministically handles the single rank-band overlap possible at `h=3` without dual
assignment.

## 6. Rotation diagnostics

For every ordinary rebalance and sleeve, preserve and report:

- prior, retained, exited, entered, and final memberships with current ranks;
- incumbents retained outside the control top/bottom four;
- control entrants displaced by those retained incumbents;
- actual replacement count `4 - |prior sleeve ∩ final sleeve|`;
- suppressed replacement count, equal to the one-for-one retained-outside-control/displaced pairs;
- corresponding full-period and block totals, plus differences versus `H0_CONTROL`;
- currency and routed turnover and realized spread-cost differences versus control.

Sets and counts must reconcile mechanically; no inferred avoided-cost estimate may replace realized
accounting.

## 7. Control parity, artifacts, and adjudication

Before any `H1/H2/H3` economic calculation, `H0_CONTROL` must pass parity against authoritative
U14 accounting: exact discrete/categorical paths and artifact identities, and elementwise absolute
numeric difference `<=1e-12` for floating arrays/scalars. Shapes, mismatch counts, and maximum
absolute differences must be recorded. A parity mismatch blocks candidate execution but is not a
candidate verdict.

Future readiness/execution/result artifacts must be network-free, hash-bound to this frozen
preregistration and source artifacts, preserve every configuration and diagnostic, and use
`PENDING_EXTERNAL_ADJUDICATION` as the sole scientific decision state. No rescue tuning,
post-result threshold invention, automatic rejection, or winner selection is permitted.
