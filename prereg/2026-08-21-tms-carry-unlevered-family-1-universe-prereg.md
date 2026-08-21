# Unlevered Carry Development Family 1 — Universe Preregistration

- **Status:** PREREGISTERED FAMILY-1 DESIGN; LOCKED ON COMMIT; NOT EXECUTION-AUTHORIZED.
- **Pre-execution parity correction (2026-08-21):** after frozen prereg commit
  `51e769e090a5365fdad7e1aef7dcc891bf35ac58`, the annualization denominator was found to
  conflict with the authoritative Stage-A U14 post-hoc accounting. Before any G10/U8 economic
  output, it is corrected from `365.2425` to `365.25` days per year so U14 accounting and CAGR
  remain exactly comparable to the authoritative Stage-A descriptions.
- **Correction scope:** no other scientific rule, candidate, threshold, metric, diagnostic,
  benchmark, robustness rule, or execution/accounting mechanic is changed.
- **Programme:** separate historical DEVELOPMENT optimization; not a reopening of Stage A.
- **Control:** immutable closed Stage-A U14 result, disposition
  `STAGE_A_SURVIVES_KILL_TEST`.
- **Control specification:**
  `prereg/2026-08-14-tms-carry-no-try-direct-gbp-kill-test-prereg.md`.
- **Control result:** `STAGE_A_CARRY_FINAL_RESULTS.md`; valid Attempt-3 result SHA-256
  `39838d559e36645c7910b65f5190d7b292540ed780ebe1ce3a697b8dbec9e6b8`.
- **Scope:** research-only. No paper/live trading, deployment, Stage-B change, network fetch,
  or execution permission follows.

## 1. Governance and adjudication

`CLAUDE.md` and `AGENTS.md` govern. The frozen Stage-A specification and artifacts remain
immutable. This Family-1 study changes only the eligible rankable/weightable currency universe
and the mechanically implied `k`. It does not retune or reinterpret Stage A, and every result is
exposed DEVELOPMENT evidence rather than prospective OOS evidence.

All configurations and results must remain visible, including weak, adverse, statistically
uncertain, or infrastructure-blocked outcomes. Diagnostic thresholds create labels only. They
cannot eliminate a candidate, issue a scientific verdict, or choose a configuration.

`NO AUTOMATIC CANDIDATE REJECTION OR WINNER SELECTION; FINAL ADJUDICATION IS EXTERNAL.`

Final scientific/business adjudication belongs to human + ChatGPT review after complete,
disaggregated reporting. Result artifacts must use `PENDING_EXTERNAL_ADJUDICATION`; no runner may
emit `PASS`, `FAIL`, `WINNER`, `SELECTED`, `REJECTED`, or an equivalent candidate disposition.

## 2. Research question

Does restricting the frozen long/short carry strategy to ex-ante larger/more-liquid currency
sets materially improve net economic performance and capital efficiency through lower execution
friction or cleaner portfolio behaviour, despite potentially losing raw carry opportunities?

No universe is presumed superior. No arbitrary subset search is permitted.

## 3. Frozen candidates

| ID | Exact eligible currencies | N | k |
|---|---|---:|---:|
| `U14_CONTROL` | AUD CAD CHF CZK EUR GBP HUF JPY NOK NZD PLN SEK USD ZAR | 14 | 4 |
| `G10` | AUD CAD CHF EUR GBP JPY NOK NZD SEK USD | 10 | 3 |
| `U8_LIQUID_MAJORS` | AUD CAD CHF EUR GBP JPY NZD USD | 8 | 2 |

G10 is the conventional G10 currency classification. U8 is a frozen project-defined nested
liquid-major core obtained by removing NOK and SEK from G10. These classifications and exact
memberships are ex ante; no currency may be added or removed after economic output.

For every candidate:

> `k = floor(N / 3)`

Long the top `k`; short the bottom `k`; each selected currency receives `+1/k` or `-1/k`.
Thus each sleeve has gross 1, `sum(w)=0`, and currency `sum(abs(w))=2`. This is the frozen
baseline gross construction, with no additional leverage, volatility scaling, or risk targeting.

## 4. Stage-A invariants

Except for eligible universe and mechanical `k`, the following remain identical:

1. The certified TMS `.pro` corpus, 35-pair no-TRY financing grid, provenance, and complete-grid
   latent carry solve under `mean(r)=0`. G10/U8 scores are subsets of the same U14 full-grid
   latent solution; the latent model is never refit to a reduced universe.
2. The lagged signal schedule, causal timing, exogenous financing-publication decision clock,
   frozen financing-availability mask, 167 defined/157 evaluable periods, ten flat gaps, and no
   stale forward-fill or imputation.
3. One total ordering by `(latent carry descending, ISO currency code ascending)`, without
   rounding or near-tie tolerance. Predictive Spearman IC continues to use average tie ranks.
4. The exact 168 frozen U14 common transaction timestamps, including gap exits and terminal
   liquidation. Subsets do not obtain earlier fills from needing fewer legs.
5. OANDA v20 practice H1 bid/ask candle OPEN execution; buys at ask, sells at bid; actual routed
   turnover and spread costs; USD accounting numeraire; direct/exclusive `GBP_USD` routing.
6. Currency-target-to-routed-unit sizing, currency gross 2, independent equity evolution, spot
   P&L, and venue-evidenced held-leg financing mechanics.
7. Independent, co-equal D360 and D365 accounting paths. Neither is primary; metrics are never
   averaged across denominators.
8. Frozen historical period from the first evaluable decision on 2023-04-03 through terminal
   liquidation on 2026-08-03.
9. Frozen adverse corner: spread x2, debit rate x1.25, debit charged-days x1.10, credit x0.80.
   Spread x3 remains a separately reported non-gating sensitivity.

Candidate routes are the deterministic frozen U14 routes for their non-zero currency targets.
Unused routes carry no position or cost. Financing events are recomputed mechanically from each
candidate's causal held routes while retaining the frozen venue-evidence rule and source corpus.

## 5. Data and readiness

G10 and U8 use only routes contained in the certified 13-leg U14 cache set. No new price or
financing source appears necessary, and network access is prohibited by this preregistration.

Before any economics, a later authorized readiness gate must emit hash-bound candidate artifacts
that verify:

- exact candidate memberships, `N`, `k`, weights, routes, and full-grid signal lineage;
- all 168 frozen U14 transaction timestamps against existing cache identities;
- every candidate-specific venue-evidenced held-leg OPEN and required conversion OPEN;
- no missing required input, substituted route, asynchronous fill, or raw-data mutation.

Readiness failure is an infrastructure status and must be reported. It is not candidate rejection.
Any genuinely required network fetch needs separate explicit human approval and a new gate.

## 6. Candidate-matched E-static benchmarks

For candidate `(N,k)`, the ordered long/short static-book space has size

> `M(N,k) = C(N,k) * C(N-k,k)`.

Long and short sleeves are ordered roles; swapping them defines a different book. Membership is
fixed for the entire study. Every book resets equal `+1/k` and `-1/k` targets at every evaluable
rebalance and uses the candidate's routes, frozen timestamps, actual turnover, costs, financing,
stress, and independent D360/D365 accounting.

The benchmark-generation rule is frozen before economics:

- If `M(N,k) <= 1000`, enumerate every unique ordered long/short book exactly once with equal
  weight. Deterministic order is ISO-sorted lexicographic long combinations, then ISO-sorted
  lexicographic short combinations from the remaining currencies. No RNG is used.
- If `M(N,k) > 1000`, generate 1,000 books using the frozen Stage-A procedure: a dedicated
  `numpy.random.Generator(PCG64(20260809))`, path-major draw order, and a uniform draw without
  replacement of `2k` currencies within each book. Separate books are independent draws and may
  duplicate. All 1,000 paths have equal weight. Construct a fresh dedicated generator with the
  same seed for each full-candidate or LOCO ensemble, matching Stage-A LOCO convention.

Therefore:

| Candidate | M | Benchmark rule |
|---|---:|---|
| U14 | 210,210 | deterministic seeded sample of 1,000 |
| G10 | 4,200 | deterministic seeded sample of 1,000 |
| U8 | 420 | exact enumeration of all 420 once |

Benchmark medians use `numpy.median`; for an even path count this is the arithmetic mean of the
two central sorted values. The same full-study static memberships are reused for chronological-
block diagnostics; books are never redrawn by block.

## 7. Predictive IC diagnostic

For each evaluable period, compute Spearman IC between the candidate-eligible subset of the
full-grid lagged latent carry scores and subsequent common-numeraire spot-only returns over the
same frozen execution-to-execution interval. Financing never enters IC. IC magnitudes across
different `N` are reported but are not treated as directly comparable effect sizes.

U14's immutable historical 95% IC result remains control context and is not a new hypothesis.
Only G10 and U8 constitute the two new IC hypotheses. For each, reuse the Stage-A corrected
Patton-Politis-White block selector, half-up integer block length, stationary bootstrap, 10,000
replicates, and dedicated `PCG64(20260808)` stream. Bonferroni familywise 95% control uses a
one-sided 97.5% lower bound for each new candidate: the 2.5th percentile of its bootstrap mean-IC
replicates. Report mean IC, bound, block length, replicate count, seed, and any degeneracy.

The bound's sign is diagnostic only. It cannot reject, accept, or select a candidate.

## 8. Chronological robustness blocks

Sort the frozen 157 evaluable mask rows chronologically and partition by row index without
splitting a holding period:

| Block | Evaluable rows | Count | Nominal half-open span |
|---|---:|---:|---|
| `B1` | 1-52 | 52 | `[2023-04-03T00:00:00Z, 2024-06-03T00:00:00Z)` |
| `B2` | 53-104 | 52 | `[2024-06-03T00:00:00Z, 2025-06-23T00:00:00Z)` |
| `B3` | 105-157 | 53 | `[2025-06-23T00:00:00Z, 2026-08-03T00:00:00Z)` |

The spans label nominal mask periods; all calculations use the already frozen actual common
execution timestamps. Block RAP and turnover use the corresponding period-return/trade slices.
Block equity is rebased to 1 only for block total-return, CAGR, and MDD reporting. Benchmark
statistics use the unchanged full-study memberships. Report every block under D360 and D365.
No block threshold creates a disposition.

## 9. Minimum economic diagnostics

For U14, G10, and U8, and separately for D360/D365, report at minimum:

- final equity, net total return, elapsed years, and net CAGR;
- per-rebalance net RAP and candidate-matched E-static median RAP/excess;
- signed MaxDD, candidate-matched benchmark median signed MaxDD, and difference;
- Calmar `CAGR / abs(MaxDD)` only when CAGR is positive and MaxDD is finite and non-zero;
  otherwise report `NOT_INTERPRETABLE`;
- total and annualized currency turnover, routed USD-equivalent turnover/gross, trade count,
  total spread cost, total financing, and spot-P&L attribution;
- adverse-corner and spread-x3 total returns;
- instantaneous absolute-weight HHI `sum((abs(w_i)/2)^2)`, per-currency selection frequency,
  mean absolute weight, and longest consecutive selected run;
- every metric available by chronological block, plus full-period D360/D365 differences.

Elapsed years equal actual first-to-last execution seconds divided by
`365.25 * 24 * 60 * 60`. CAGR is `(final_equity / initial_equity) ** (1/years) - 1`.
Currency turnover is `sum_t sum_i abs(w[i,t] - w[i,t-1])`, including gap exits/re-entries and
terminal liquidation; routed turnover uses absolute changes in execution-time USD-equivalent
edge notionals. Annualized turnover is full-period turnover divided by elapsed years.

Accounting attribution must not imply that `financing - spread cost = total return`; spot P&L,
path dependence, sizing, and equity dynamics remain explicit.

## 10. Frozen reference flags — diagnostic only

U14 reference CAGRs are the committed post-hoc descriptions: D360 `2.339411%`; D365
`2.313762%`. For each candidate and denominator, report CAGR difference in percentage points.

- `DELTA_CAGR_GE_1PP_REFERENCE`: candidate CAGR is at least 1.0 percentage point above the
  matching U14 denominator. Also report a joint-both-denominators version.
- `CAGR_GE_4PCT_TARGET` and `CAGR_GE_5PCT_TARGET`: research-target labels only.
- `MAXDD_PREFERRED`: `abs(MaxDD) <= 25%`.
- `MAXDD_ELEVATED_RISK`: `25% < abs(MaxDD) <= 30%`.
- `MAXDD_SEVERE_RISK`: `abs(MaxDD) > 30%`.
- Directional comparison labels for RAP versus U14, Calmar versus U14, benchmark-relative RAP,
  benchmark-relative signed MDD, adverse and x3 stress return signs, turnover, costs, financing,
  routed gross, and concentration.
- `DENOMINATOR_DIRECTIONAL_DISAGREEMENT` whenever a sign, target/reference label, risk region, or
  comparative direction differs between D360 and D365. Always report raw differences.

These flags do not form an AND/OR gate, score, ranking, Pareto selector, tie-breaker, automatic
kill, or automatic survivor rule. Approximately 4% and 5% CAGR are targets, not requirements.

## 11. Leave-one-currency-out diagnostic

For each candidate, omit every eligible currency once from the rankable/weightable set only.
Retain the omitted currency in the full 35-pair latent design and as a possible routing instrument.
Set `k_loco = floor((N-1)/3)`, restore equal sleeves and currency gross 2, and run the identical
dual-accounting, cost, stress, and candidate-matched benchmark diagnostics.

Apply Section 6's benchmark-space rule to each LOCO case. In particular, G10 LOCO has
`M(9,3)=1,680` and uses the seeded 1,000-book sample; U8 LOCO has `M(7,2)=210` and enumerates all
210 books exactly once. Every omission and result is retained. LOCO creates no rejection or
selection rule.

## 12. Mandatory U14 runner parity before new-candidate economics

A future parameterized Family-1 runner may not compute any G10 or U8 economic quantity until a
separately authorized U14 control-parity run completes against the frozen Stage-A accounting.
This is infrastructure validation, not a new Stage-A result or reinterpretation.

Parity requires exact equality for every deterministic discrete/categorical object, including:

- evaluable/excluded periods, actual transaction timestamps, step kinds, signal memberships,
  target signs, routes, benchmark memberships, LOCO definitions, and stress-cell identities;
- financing-event identity, held-leg identity, required conversion identity, event counts,
  closed-market non-events, day multipliers, and denominator labels;
- all other deterministic discrete paths and artifact identities declared by the parity schema.

For floating arrays and scalars generated side-by-side by the legacy and parameterized runners,
require elementwise finite values and absolute difference `<= 1e-12`; no relative-only tolerance,
rounding rescue, reordered comparison, or post-output tolerance change is permitted. The parity
schema must require and compare full equity, period-return, unit/position, trade, spread,
financing, spot-P&L, benchmark, stress, IC, and LOCO arrays/scalars. It must record shapes,
mismatch counts, maximum absolute differences, and canonical deterministic identities.

Every full-precision scalar stored in the immutable Attempt-3 result must also match within
`1e-12`. The committed post-hoc U14 descriptions are rounded display values; the side-by-side
underlying outputs remain subject to `1e-12`, while displayed values must reproduce exactly when
rounded to their published precision. This display check cannot replace underlying parity.

Any mismatch is preserved and reported as `U14_RUNNER_PARITY_BLOCKED`; G10/U8 economics remain
unexecuted. It does not reject any candidate. The parity run itself requires separate explicit
authorization and must not occur during preregistration or implementation review.

## 13. Output preservation and external review

The future result artifact must be immutable, hash-linked to its preregistration, code, source,
readiness, and execution identities, and must contain:

- U14 parity evidence;
- complete U14, G10, and U8 full-period and block diagnostics;
- both accounting denominators without averaging;
- both new-candidate IC outputs and Bonferroni bounds;
- all benchmark books or their exact deterministic membership identities;
- every LOCO case;
- every reference/risk/consistency flag;
- `PENDING_EXTERNAL_ADJUDICATION` as the sole study decision state.

No candidate or failed diagnostic may be hidden, overwritten, pruned, rescued, or followed by
result-informed universe or `k` invention. Later families—hysteresis, weighting, rebalance, or
other parameter research—remain out of scope.
