# Unlevered Carry Development Family 5 - Portfolio-Breadth Preregistration

- Status: PREREGISTERED FAMILY-5 DESIGN; LOCKED ON COMMIT; NOT IMPLEMENTATION- OR EXECUTION-AUTHORIZED.
- Gate: FAMILY5_PORTFOLIO_BREADTH_DESIGN.
- Selected DEVELOPMENT base: U14 + H2 (h=2) + EQ + M1 weekly cadence.
- Only experimental parameter: currencies per sleeve, k.
- Scope: historical DEVELOPMENT only. No Stage-B access, network/data fetch, trading, or deployment.

## 1. Authority and recovered state

Authority: CLAUDE.md; the closed Stage-A specification; Family-2 and Family-4 committed
preregistrations; FAMILY4_REBALANCE_CADENCE_FINAL_RESULTS.md and its immutable evidence.
Family 4 is CLOSED; external adjudication retained M1_CONTROL. Families 1-4 and original
Stage A remain immutable. Family 1 changed universe and k jointly; it did not isolate breadth.

On 2026-09-20, live local Git verified main == origin/main ==
1ea00d2ad566c9e0a3de934b7b32fe719462f97e, ahead/behind 0/0, tracked tree/index clean,
with only CODEX_HANDOFF.md and review.txt untracked before this draft. This describes the
local remote-tracking ref; no remote query was needed. The handoff's historical hashes are
audit context, not contradictions. RESEARCH_HANDOFF.md names this design gate; it references
no separate current optimization roadmap. No tracked roadmap/optimization-named document
was found, so no historical roadmap was substituted.

Verified SHA-256 anchors:

| Family-4 artifact | SHA-256 |
|---|---|
| Execution | eb2b97d96924e694e868bf087506070a5953860c1766bc2880f179366300927e |
| Result | b92f6d12d7cd7274bf3e60dca44fc402bd7bfe6d9fa6ee8fcc78f1cb31bdb6a8 |
| Completion | 85469fed3c81b74c6783da40302e2548ff53f7c66794baae345ace68eaaa9547 |
| Readiness | d292d6355ad27b23b515b72d8704b03b337582b5b2adf8a40b66e6bca5700e25 |
| M1 parity | a7528e78462dd48ea3f6124c161d5882c521b501e6a7d3a43628f22963c5ebfa |

Paths are those recorded in RESEARCH_HANDOFF.md: prereg/2026-09-19-tms-carry-unlevered-family-4-rebalance-cadence-*
and reports/forex/family4/family4-rebalance-cadence-*. The exact control authority is the
Family-4 M1_CONTROL evidence, including its recorded control payload, not a recreated selection.

## 2. Hypothesis and complete candidate set

At unchanged sleeve scale, narrowing k may strengthen exposure to carry extremes but increase
concentration and rotation sensitivity; broadening k may diversify currency-specific spot risk
but dilute carry separation. Test whether either produces better net benchmark-relative
return/risk evidence across stresses, chronological blocks, and LOCO than retained k=4.
Breadth mechanically changes equal position size and the H2 boundaries; these are consequences
of k, not independently tuned parameters. No improvement is presumed.

| ID | k | Active currencies | Each active magnitude | Structural rationale |
|---|---:|---:|---:|---|
| K3 | 3 | 6 | 1/3 | One fewer currency per sleeve; tests stronger extremes with still three contributors per side. |
| K4_CONTROL | 4 | 8 | 1/4 | Exact retained Family-4 M1_CONTROL. |
| K5 | 5 | 10 | 1/5 | One more per sleeve; tests diversification/dilution at the maximum disjoint full-U14 H2 breadth. |

This is the complete frozen set: k in {3,4,5}, with k=4 evaluated first at the future parity
gate. k=1/2 are omitted on structural concentration grounds (100%/50% per sleeve constituent),
not performance. k>=6 is excluded because full-U14 symmetric H2 retention bands overlap.
Values were chosen without computing or inspecting Family-5 economics; there is no grid,
adaptive search, candidate expansion, or result-dependent change.

## 3. Generalized H2 semantics and separation

Universe, in ISO order, remains exactly:
AUD CAD CHF CZK EUR GBP HUF JPY NOK NZD PLN SEK USD ZAR.

For active rankable universe A of size N, use the frozen causal full-grid latent scores.
Rank by score descending, then ISO code ascending, using exact values with no rounding or
near-tie tolerance. Rank 1 has the highest carry score. Hysteresis h is always 2.

For disjoint prior memberships Lprev and Sprev, first form both retained sets:

- RL = {c in Lprev : rank(c) <= k+h}.
- RS = {c in Sprev : rank(c) >= N-k+1-h}.

Assign both retained sets before any entrants. Fill long vacancies in ascending rank order
(best first), excluding every currency already in either sleeve. Then fill short vacancies
in descending rank order (worst first), again excluding both assigned sleeves. Stop at exactly
k members on each side. An exited incumbent may immediately enter the opposite sleeve through
this fill rule. Never truncate incumbents, introduce a tie override, or refresh state with
future scores. Record the completed book as the next prior state.

These formulas and ordering match hysteresis_accounting_steps in bot/forex/family2_hysteresis.py
and cadence_accounting_steps in bot/forex/family4_cadence.py. Both existing functions currently
derive k=floor(N/3), require k=4, and assign +/-0.25. The mathematics is already generalized;
their interfaces and weights are not. A later Family-5 implementation must explicitly parameterize
k without altering frozen historical entry points or silently passing through the floor rule.

For the full study, disjoint rank bands require
k+h < N-k+1-h, equivalently 2(k+h) <= N for integer ranks.

| k | N=14 long retention | N=14 short retention | Neutral ranks between bands |
|---:|---|---|---|
| 3 | 1-5 | 10-14 | 6-9 |
| 4 | 1-6 | 9-14 | 7-8 |
| 5 | 1-7 | 8-14 | none |

All candidates also satisfy 2k <= N. Both retained sets are subsets of disjoint previous
sleeves; the exclusion rule preserves disjointness as vacancies are filled. There are at least
2k available currencies, so both sleeves can be completed. No currency can be long and short
simultaneously. Full-U14 k=5 has adjacent, unambiguous bands; it does not select all currencies.

Fill-order independence proof: after both retained sets are assigned, let rL=|RL|,
rS=|RS| and F be the common free ranking, of size N-rL-rS. Longs require a=k-rL
entrants and shorts require b=k-rS. Since N>=2k,
|F|=N-rL-rS >= (k-rL)+(k-rS)=a+b. The first a and last b elements of F are therefore
disjoint. Whichever sleeve fills first cannot remove any element the other would select.
The final sets are RL union the first a elements and RS union the last b elements;
they are disjoint and have exactly k members each, including zero-vacancy cases.
This proves membership independence for all frozen full/LOCO cases, including K5/N13.
Preserve inherited long-first execution and record ordering; the proof does not authorize
changing either. Both retained sets must always be assigned before any fill.

## 4. Scale, timing, and forced transitions

Every active target has w(c)=+1/k for c in L, -1/k for c in S, and zero otherwise:
|L|=|S|=k; sum(long weights)=+1; sum(short weights)=-1;
sum(weights)=0; sum(abs(weights))=2. These are mathematical target invariants.
Floating checks use absolute tolerance 1e-12 (not bit equality for sums involving 1/3);
membership counts, signs, and sets are exact. Each selected value uses the same 1/k expression;
do not adjust a residual constituent to force a floating sum.

Preserve M1: every eligible weekly decision applies H2 once and resets equal targets, even if
membership is unchanged. Use the existing causal signal lag and exact common synchronous
H1 bid/ask OPEN mapping. Preserve the 167 defined/157 evaluable periods and 168 signal/action
steps from frozen artifacts. Weekly valuation and financing continue under the frozen rules;
there are no cadence skips or added timing/cost overrides.

Initialization selects current top k and bottom k without incumbent retention. An immediate
gap exit liquidates and clears both sleeves/state. Re-entry uses only the current causal
top/bottom k and restarts the local cadence ordinal at zero. Terminal liquidation immediately
leaves zero weights and zero routed positions. Forced costs remain in accounting; forced events
and fresh initialization remain excluded from ordinary avoided-replacement counts.

No added leverage, volatility targeting, risk scaling, exposure multiplier, or concentration cap.
Currency gross 2 is a target at active rebalances, not a promise that marked exposures cannot
drift between executions. Report routed/netted gross and passive drift using frozen definitions.

## 5. LOCO: explicit breadth treatment and the K5 boundary

Run all 14 omissions for every k, excluding only that currency from rankable/weightable
membership. Preserve it in the full 35-pair latent solve and as a possible routing intermediary.
Keep candidate k unchanged in LOCO, with N=13, h=2, EQ, M1, and gross 2.

This explicitly parameterizes the old floor((N-1)/3) convention for the new isolated breadth
experiment. Automatically resetting every LOCO case to k=4 would cease to test K3/K5.
K4_CONTROL still uses exactly the frozen N13/k4 rule. This externally approved Family-5
generalization is frozen with this design; it does not revise any earlier family.

| k | N=13 long retention | N=13 short retention | Boundary treatment |
|---:|---|---|---|
| 3 | 1-5 | 9-13 | Disjoint bands. |
| 4 | 1-6 | 8-13 | Disjoint bands; exact control. |
| 5 | 1-7 | 7-13 | Rank 7 is eligible for retention only on its own prior side. |

K5 LOCO has one shared eligibility rank, not overlapping membership or an ambiguous decision:
if rank 7 was a prior long, only RL can retain it; if a prior short, only RS can retain it;
if previously unheld, neither retains it and it remains unselected after vacancy filling.
The incumbent sets are disjoint, so these cases are mutually exclusive. At initialization/
re-entry, rank 7 is unselected (top/bottom five use ranks 1-5 and 9-13).

Unheld-rank-7 proof: when rank 7 belongs to neither prior sleeve, RL is contained in
ranks 1-6 and RS in ranks 8-13. After assigning both retained sets, the upper six ranks
provide 6-rL free currencies for only 5-rL long vacancies, and the lower six provide
6-rS free currencies for only 5-rS short vacancies. Each side has one surplus extreme
entrant, so neither fill reaches rank 7 or consumes the other side's extreme entrants.
Thus rank 7 remains unselected in either fill order. If it was an incumbent long or short,
its inclusive cutoff retains it on that side before fills and excludes it from the other.

No arbitration rule, h reduction, k reduction, or new rank tie rule is introduced.
This is the same incumbent-conditioned resolution explicitly frozen for Family-2 N13/k4/H3,
which also has thresholds <=7 and >=7. Validate all three prior-side cases at future implementation
readiness. Record rank-7 side/retention counts to expose this boundary effect.

Strictly nonintersecting eligibility bands for N13 would instead require k<=4 at h=2.
This specification distinguishes rank eligibility from actual sleeve membership explicitly;
it does not claim K5 LOCO has disjoint bands. External review accepted this documented,
deterministic inherited behavior and fixed-k LOCO before freeze. Never silently substitute
a smaller LOCO k, omit K5 LOCO, or invent a different H2 boundary.

## 6. Candidate-matched static benchmarks

For each full or LOCO active set and k, use the frozen E-static generation method:
M(N,k)=C(N,k)*C(N-k,k), with long/short roles distinct.

| k | M(14,k) | M(13,k) | Ensemble size per full/omission case |
|---:|---:|---:|---:|
| 3 | 60,060 | 34,320 | 1,000 |
| 4 | 210,210 | 90,090 | 1,000 |
| 5 | 252,252 | 72,072 | 1,000 |

Preserve family1_benchmark_books / frozen Stage-A generator exactly: ISO-sorted input;
fresh dedicated numpy Generator(PCG64(20260809)) for each (active set,k) ensemble;
path-major draws of 2k distinct currencies within a book, first k long and remaining k short,
with frozen output ordering. Independent books may duplicate; do not deduplicate or change
RNG consumption. Preserve equal probability and numpy.median aggregation. Existing exhaustive
enumeration for spaces <=1000 stays part of the methodology, but none of these cases uses it.

K4 full and all omission book identities must reproduce the Family-4 books exactly.
K3/K5 require newly generated breadth-matched books; neither rescale nor truncate a K4 book.
Same seed does not imply the same constituent memberships or paired sample identities across k.

Each static book holds fixed membership throughout, with no signal selection or H2. Reset
+/-1/k at every M1 eligible execution, using identical routes, quotes, costs, financing,
valuation, gap exits/re-entry, terminal liquidation, and D360/D365 accounting. Re-entry restores
that fixed static book. Use the same books for base/adverse/spread-x3 and all chronological blocks.
No benchmark redraw by scenario, denominator, or block. Match LOCO benchmarks to N13 and that
candidate's k. Preserve frozen benchmark-relative RAP and signed-MDD definitions; neither add
risk scaling nor substitute a raw-return comparison as the headline.

## 7. Reuse versus recomputation

| Quantity | Required treatment |
|---|---|
| Historical data, availability mask, causal full-grid scores, routes, quotes, timestamps, financing schedules/event input grid, block boundaries | Hash-reuse unchanged inputs; verify every required route/input remains covered. No new data or time-boundary relaxation. |
| Full-U14 spot-only Spearman IC series, mean, bootstrap block selection, replicate evidence and lower bound | Hash-reuse unchanged Family-4 IC evidence, including seed 20260808 and original 10,000-replicate method. IC uses all U14 scores and forward spot returns, not selected k memberships or financing. No new IC hypothesis/test. |
| Selected-sleeve carry separation, rank persistence, concentration, turnover, any membership/weight-conditioned statistic | Recompute for each k and each omission; these are not invariant IC. Do not label subset/portfolio IC as the reused full-U14 IC. No new LOCO-IC hypothesis is introduced. |
| Membership/state paths and +/-1/k targets | Regenerate for every k/full/LOCO case; audit k=4 against the control. |
| Static memberships | K4 hash-verify exact frozen books; regenerate K3/K5 for each active set with frozen RNG method. |
| Strategy and benchmark routed units, fills, turnover/costs, held-leg financing, spot P&L, equity, returns, risk and attribution | Recompute for every changed k, both denominators and all scenarios/omissions. Shared financing-event inputs do not imply shared accrual amounts or held-leg contributions. |
| Stress evidence | Re-run frozen adverse financing and spread-x3 accounting for strategies and matched static books. Re-solving target units/equity is required; never scale the base output arithmetically. |
| Chronological evidence | Recompute frozen B1/B2/B3 (52/52/53) slices and matched-book summaries from each complete path, including LOCO; preserve full-path state across block boundaries. No block restart/reselection or book redraw. |
| K4 economics | Recompute once at the future control parity gate, compare to immutable M1, then hash-reuse the successful Family-5 control result in the one-shot report. Do not rerun it with non-controls. |

Cache only exactly identical accounting problems with all determining input hashes, active set,
k/weights, book, m=1, execution/financing rules and scenarios represented in the key or isolated
cache namespace. No cross-k economics reuse. Repeated identical static books may share computation
only if multiplicity/order and every output are preserved. Runtime saving is not evidence of
invariance. Financing and routed-leg usage can change when k changes even with identical sources.

For every candidate report total return, CAGR, RAP, positive-return Calmar, signed MaxDD,
matched benchmark RAP excess and MDD difference, D365-minus-D360, stresses, all blocks and omissions;
spot/financing/spread attribution; trade/fill counts; currency and routed turnover; mean/max
routed gross; concentration and membership persistence. Preserve distributions and worst cases,
including negative blocks/results. Rotation records retain prior/retained/exited/entered/final
sets, exact ranks, actual replacements and reconciled suppressed counts. Within-k suppressed
replacement comparisons use that k's current top/bottom book; comparisons against K4 are
separately labelled.

## 8. Required implementation tests and fail-closed control gate

Future tests must cover:

1. Strict config validation: only frozen IDs/k, exact U14, h=2, EQ, m=1, sleeves +/-1.
   Reject unknown keys, booleans/fractional k, unsupported k, overlap/duplicate memberships,
   missing/nonfinite scores and invalid omissions. Never fall back to floor(N/3).
2. Boundary fixtures for both sides at retention cutoffs and one rank beyond, each k and N;
   ties, immediate opposite-side eligibility, both retained sets assigned before long-first
   vacancy filling, and stable complete state records.
3. Disjoint k/k membership, equal targets, gross/net/sleeve invariants across transitions;
   deterministic multi-step fixtures and property checks over valid states, including K5
   LOCO rank 7 previously long, short, or unheld. All 14 omissions keep candidate k.
   Explicitly assert rank 7 stays long, stays short, or remains unselected respectively;
   in the unheld case check 6-rL >= 5-rL and 6-rS >= 5-rS free extreme capacity.
   Compare long-first and short-first fills after assigning identical retained sets for
   every frozen (N,k), including zero vacancies and K5/N13 collision cases. Require exact
   final membership equality, k/k cardinality and disjointness. Independently check the
   first-a/last-b free-ranking characterization. Preserve and test the inherited long-first
   production execution and record ordering; a reversed-order test oracle changes neither.
4. Causality/prefix invariance: changing later scores/quotes cannot change earlier decisions
   or fills. Gap liquidation/reset/re-entry, repeated gaps and immediate terminal flat;
   M1 action schedules and weekly target resets unchanged.
5. Deterministic 1,000-book ensembles with exact K4 full/LOCO identities; candidate sizes,
   weights, exclusion of omitted names, duplicate multiplicity, seed/draw order, constant
   membership and matched M1/gap/terminal execution.
6. Synthetic accounting coverage for 1/3 and 1/5 weights, equity-aware routed-unit solving,
   netting/direct GBP routing, both financing denominators, held-leg accrual, costs/stress,
   and block attribution. Test input/hash/cache isolation and immutable-source guards.
7. Readiness and CLI/import boundaries: no economics during preflight/readiness; no network,
   Stage-B reads or trading; reject stale/missing parity or source hashes; atomically prevent
   concurrent execution and reruns without overwriting evidence.

Before ANY K3/K5 historical economics, K4_CONTROL must reproduce Family-4 M1_CONTROL:

- Zero timestamp, rank/membership/state/action, route, event-identity/count, book-identity,
  scenario, block, omission, schema-shape, or other discrete mismatches.
- Elementwise absolute difference <=1e-12 across every relevant floating array/scalar:
  strategy/static-book accounting paths, units/fills/costs/accruals, equity/returns, attribution,
  turnover/concentration, risk, stresses, blocks and LOCO, not just headline metrics.
- Exact inherited IC evidence hash; exact full/LOCO static membership hashes.
- Emit compared shapes/counts, zero mismatch counts, max differences and input/source hashes.
  Compare the implemented control to an independent frozen reference; never copy the reference
  into the implementation output and declare parity. If full paths are absent from stored
  summaries, reconstruct only K4 with hash-verified frozen code at this authorized later gate.

Different Family-5 ID/provenance wrapper fields may be explicitly mapped for comparison;
mapping must not drop economic/state evidence. Any failure blocks all non-control economics.
An infrastructure failure is not an economic candidate rejection. Historical Family-4 parity
does not certify this future Family-5 implementation.

## 9. Artifacts, checkpoints, and one-shot execution

External design review approved k={3,4,5}, fixed-k LOCO and incumbent-side K5/N13 overlap,
subject to the two proofs and future test requirements now included. This preregistration
freezes on its authorized commit. Subsequent gates, in order: separately authorized
implementation and tests; K4 parity; infrastructure checkpoint; separately authorized economics.
The design/freeze authorization does not authorize those later actions.

Future Family-5 artifacts must be separate and hash-bound: frozen candidate/LOCO/benchmark
definitions; non-economic readiness with membership/state/action/book hashes and source/data
manifest; K4 parity and reusable control evidence; infrastructure checkpoint with code/prereg
hashes and exact reviewed PowerShell command; exclusive execution marker; complete result and
completion artifacts. Regenerate every candidate-dependent path/diagnostic identified above.
Preserve prior-family files and link their hashes. This design/freeze gate changes only this preregistration.

Prefer manual execution: after the checkpoint, the user launches the approved command once in
PowerShell. Codex must not run the same economics concurrently. Write an exclusive immutable
execution marker before K3 or K5 economics, consumption_count=1; execute both once in fixed order
K3 then K5, and attach the verified K4 result. Existing execution/result/completion artifacts
block rerun. A partial/error run remains preserved and requires separate adjudication; no
automatic restart or deletion. Never rerun a successful one-shot result.

Every candidate/result carries PENDING_EXTERNAL_ADJUDICATION. Preserve all negative evidence.
No automatic winner, rejection, score, ranking, rescue, parameter change or Stage-B substitution.

## 10. Isolation and external adjudication

No Stage-B data, prospective outcomes, or data discovery outside frozen DEVELOPMENT inputs.
The original Stage-A U14/k4/H0 strategy remains unchanged for prospective Stage B; a DEVELOPMENT
selection cannot replace it. Do not alter CLOSED_FAIL experiments or immutable Stage-A evidence.

The user and ChatGPT adjudicate externally. Approximately <=25% drawdown preferred,
25-30% acceptable only with unusually strong robust alpha, and >30% generally unattractive are
diagnostic preferences, not automatic gates. A 4-6% CAGR is a goal, not a pass/fail threshold.
Report benchmark-relative economics, stresses, chronological weaknesses and LOCO tails without
encoding scientific dispositions. No trading authorization follows.

## 11. Design-stage verification and remaining work

Read frozen Family-2/4 specifications, relevant membership/benchmark/accounting code and
Family-4 closure/readiness/completion/parity evidence. All five Family-4 artifact hashes above
matched their authoritative records. Independently calculated the six static-book space sizes.

Executed existing synthetic tests only:
python -B -m pytest tests/test_family2_hysteresis.py tests/test_family4_cadence.py -q -p no:cacheprovider -k "not readiness"
Result: 15 passed. These validate existing frozen mechanics, including incumbent-conditioned
shared-rank handling; they do not establish unimplemented K3/K5 behavior or Family-5 parity.

The approval-with-corrections gate verified both proofs against the specified retained-set and
vacancy rules and added the corresponding future tests. No Family-5 implementation, readiness
emission, historical economics or memory update is authorized by this freeze.

Next gate: FAMILY5_PORTFOLIO_BREADTH_IMPLEMENTATION (separate authorization required), including
the specified implementation tests before the later K4 parity and infrastructure checkpoints.
