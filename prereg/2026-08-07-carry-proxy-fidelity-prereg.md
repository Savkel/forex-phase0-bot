# Carry-Proxy Fidelity — Preregistration (financing-measurement study)

- **Status:** PREREGISTERED (2026-08-07). Locked on commit. Execution is **BLOCKED** until the
  prerequisites in Section 2 are satisfied.
- **Date:** 2026-08-07
- **Repo root:** `E:\Claude\forex_bot`
- **Governing document:** `CLAUDE.md` (project constitution). Where this document and the
  constitution conflict, the constitution wins and this document must be corrected.
- **Relationship to prior phases:** Phase 0 (trend/momentum/Donchian), Phase 1 (short-term
  mean reversion) and Phase 2A (M15 session/liquidity breakout) are **CLOSED_FAIL** and killed.
  This document is **not** a rescue of any of them and reuses none of their signals. It is also
  **not itself a strategy experiment** — see Section 1.
- **File location note:** `docs/` is gitignored in this repository (local governance docs). A
  preregistration derives its scientific value from being immutable and timestamped in version
  control, so this document is placed in the tracked `prereg/` directory instead. Relocation is
  a governance decision for the maintainer; no `.gitignore` rule was modified or overridden.

---

## 1. Purpose and scientific claim

This preregisters a **financing-measurement study**, not an edge study. It asks exactly one
question:

> Do **BIS central-bank policy-rate (CBPOL) differentials** reproduce the **cross-sectional
> ordering** of **OANDA's quoted broker financing** across FX instruments, well enough to serve
> as a deep-history proxy for carry research?

No prices, returns, equity curves, drawdowns or strategy quantities enter this study at any
point.

### 1.1 What PASS licenses

PASS means exactly:

> **CBPOL has adequate global cross-sectional ordering fidelity against OANDA broker financing
> within the calibration regime.**

### 1.2 What PASS does NOT establish

- It does **not** establish that CBPOL equals tradable tom-next carry.
- It does **not** measure or validate the covered-interest-parity basis.
- It does **not** validate any admin-fee or financing-cost estimate (Section 10).
- It does **not** extend beyond the calibration window's rate regime.
- It does **not** validate any tail, top-k or basket construction. Any future top-k rule
  requires its **own separately preregistered fidelity condition** before strategy evaluation.
- It confers **no** deployment, paper-trading or live-trading permission.

### 1.3 Anti-rescue

If global fidelity **FAILS**, the primary proxy **P1 cannot be rescued, re-specified, replaced
by any other proxy, re-thresholded, re-windowed, or re-run**. The failure is reported plainly.

---

## 2. Hard prerequisites (execution blockers)

Calibration execution must not begin until **all** of the following hold. Writing and committing
this document does not require them.

1. **OANDA division evidence.** The applicable `divisionId` / `tradingGroupId` must be evidenced
   from the account's legal entity, using this **precedence order** (first available wins, no
   discretion): (1) the legal entity named on the account statement; (2) the regulator/entity
   line in the trading platform footer; (3) the regional domain used at signup. The US values
   (`divisionId=1`, `tradingGroupId=1`) observed on the public US page are **not** assumed. Both
   remain symbolic in this document.
2. **Explicit maintainer approval for repeated `labs-api.oanda.com` access**, having considered
   the site's terms. The endpoint is undocumented and unsupported.

**Commit-before-run.** The resolved `divisionId` / `tradingGroupId`, the evidence used, and the
precedence level it came from must be **committed to version control before the first financing
request**. A run executed against the committed division **is** the single evaluation run of
Section 9 and consumes it. A post-run challenge to the division is admissible **only** when it
rests on a **dated external event** (a change of account entity, or a correction issued by
OANDA) — never on re-reading evidence that was already available at commit time — and the
finding must itself be committed. Where admissible, the verdict becomes **UNDETERMINED** and no
re-run is permitted; otherwise the verdict stands as produced. This closes the route by which an
unwelcome PASS or FAIL could be erased by re-examining old evidence.

Until both prerequisites hold, this document is a locked plan and nothing else.

---

## 3. Data sources

| Role | Source | Status |
|---|---|---|
| Target | OANDA `GET labs-api.oanda.com/v1/financing-rates?divisionId=&tradingGroupId=&time=` | Rolling ~12-month window; **calibration/development data** |
| Primary proxy (P1) | BIS Data Portal, **central bank policy rates dataset `WS_CBPOL`, daily frequency (`D`)**, one series per currency's issuing central bank | Deep history, homogeneous administration |

**Pinned implementations.** `scipy.stats.kendalltau(..., variant='b')` with `scipy>=1.11,<2`;
`arch.bootstrap.StationaryBootstrap` and `arch.bootstrap.optimal_block_length` (stationary
column) with `arch>=7.2,<8`; `numpy>=1.24,<3`. The exact installed versions of `scipy`, `arch`
and `numpy` must be **committed before the run** (a lockfile or pinned exact versions), not
merely recorded afterwards: `optimal_block_length` output can differ across patch releases. No alternative implementation of the block-length
selector or the bootstrap may be substituted.

**No splicing.** Heterogeneous rate definitions (secured vs unsecured RFRs) are not spliced into
the primary series. Depth is never traded for comparability.

**P2 removed.** An RFR-differential diagnostic was considered and is **not part of this study**:
it had no acceptance role, and specifying it fully would add sources without affecting any
verdict. It is neither computed nor reported here.

### 3.1 Calibration window (deterministic)

The calibration window is **the maximal contiguous span of dates the financing endpoint accepts
(does not reject) as of the first successful request** — not the subset of dates that return
rows, which would collapse at every weekend. It is discovered by a preregistered bisection on
the endpoint's own `"Time parameter must be equal or less than 1 year from today"` rejection
boundary. Only the exact quoted rejection string counts as a rejection; any transient response
(HTTP 429, any 5xx, timeout, or malformed body) is retried up to three times with fixed 5-second
waits, and if it still does not resolve to either a rejection or a rows payload, the study
returns **UNDETERMINED**. If the rolling boundary advances mid-bisection (the endpoint accepts a
date it previously rejected), the bisection is void and the study returns **UNDETERMINED**. Its
resolved endpoints and the UTC timestamp of that first request must be **committed before any
`tau_D` is computed**. The window is never extended, shortened, shifted, or re-discovered on a
later date.

**CBPOL is an economic proxy, not tradable carry.** It is administratively consistent but not
economically identical across currencies or through time; policy instruments differ by country
and long BIS series may contain documented instrument changes (Section 8).

---

## 4. Eligible-universe rule (deterministic, performance-blind)

Evaluated once, before any fidelity quantity is computed. No returns, prices, volatility or
performance are inspected.

**Eligible business days.** `D` denotes the set of **eligible business days**: the dates within
the calibration window on which the endpoint returns rows. This is the broker's own financing
calendar, used purely to define which dates exist. No assumed calendar is used anywhere in this
study, and the per-row `days` multiplier plays no role in defining or weighting them.

**FX instrument.** An endpoint row qualifies as an FX instrument iff its `instrument` field has
the form `XXX/YYY` where both `XXX` and `YYY` are ISO-4217 **national currency** codes —
explicitly excluding the non-national `X` codes for metals and special drawing rights (`XAU`,
`XAG`, `XPT`, `XPD`, `XDR`). All other rows (indices, commodities, CFDs) are discarded before
rule 1. This syntactic test is only a prefilter; **rule 1 is the binding filter**, since any code
without a BIS CBPOL series — including supranational codes such as `XOF`, `XAF`, `XCD`, `XPF` —
cannot survive it.

Retain instrument *i* if and only if:

1. **Both** of its currencies have a BIS CBPOL daily series whose first observation is
   a value that is **usable under Section 6** on the first eligible business day of the
   calibration window; and
2. OANDA financing rows exist for *i* on **every** eligible business day in the calibration
   window.

**CBPOL alignment (last observation carried forward).** Policy rates are step functions, so the
value in force on a date is the most recent observation satisfying the causal rule of Section 6.
Formally, `CBPOL_c(D) :=` the latest observation of currency *c*'s series that is usable at *D*
under Section 6. This is the correct semantics for a step process, not a gap-filling device, and
it makes the earlier "five consecutive business days" gap tolerance unnecessary — that clause is
**removed**. If no usable prior observation exists for any eligible currency on any eligible
business day, the study returns **UNDETERMINED**.

**Minimum cross-section.** `N` is whatever the rule yields, subject to a preregistered floor:
**if `N < 5`, the study returns UNDETERMINED.** This is a **conservative structural minimum on
cross-sectional width, adopted by convention** — it is *not* a requirement derived from the
bootstrap inference of Section 7.3, and no such derivation is claimed. The floor itself **is** binding via Section 9;
what follows is motivation only, and is not itself a criterion: below `N = 5` the daily statistic takes very few
distinct values, so one sustained ordering can saturate `tau_D` across the whole window. The
exact-Kendall figure `2/N!` cited in an earlier draft is a property of a per-day permutation
test that this study does not run, and is **withdrawn as a justification**.

The instrument list is recorded before measurement and is not revised afterwards.

If, after universe construction, any admitted instrument is found to be missing a row on any
eligible business day, the study returns **UNDETERMINED** (data-integrity failure). Silent day-dropping
or pair-dropping is prohibited.

---

## 5. Target quantity

For instrument *i* on day *D*, the endpoint quotes `longRate` and `shortRate`. Define:

- **Financing midpoint:** `m_i = (longRate_i - shortRate_i) / 2`
- **Half-sum drag diagnostic:** `f_i = -(longRate_i + shortRate_i) / 2`

`m_i` is used as the **side-neutral OANDA financing target**. **No claim is made that `m_i`
equals pure tom-next carry.** `f_i` is an **algebraic half-sum/drag diagnostic only**; it is
**not identified as the broker admin fee** without independent evidence. `f_i` is reported and
belongs exclusively to the later financing-cost work (Section 10), never to fidelity.

**Why not directed opportunities.** A `2N` directed (pair × side) formulation was considered and
**rejected before any measurement**: long and short legs are mechanical mirrors
(`shortRate ≈ -longRate - drag`), so most cross-block comparisons are near-identities that would
inflate rank agreement without measuring fidelity. The rejection is on algebraic structure, not
on observed fit.

The proxy value for instrument *i* is the CBPOL differential
`p_i = CBPOL_base(i) - CBPOL_quote(i)`.

---

## 6. Causal timestamp rule

**Decision stamp (locked).** For eligible business day `D`, the decision stamp `T(D)` is
**00:00 America/New_York on `D`** — the same instant the endpoint itself keys a historical date
to, expressed in UTC as `D` at 04:00Z or 05:00Z, whichever is midnight New York on that date.
That exact value is what is passed as the endpoint's `time=` parameter. No other stamp is used.

**Why a fixed lag is not sufficient.** An earlier draft made a CBPOL observation usable one
financing day after the date it is recorded against. That rule is **withdrawn**: it proves
nothing about availability. BIS distributes CBPOL on a **weekly (mid-week) release cycle** and
the published daily series is **retrospective**, so a value carrying effective date `d` need not
have been obtainable from BIS on `d + 1` at all. **No claim that `effective_date + 1 financing
day` makes CBPOL point-in-time safe survives in this document.**

**Locked causal rule — availability must be observable, not assumed.** For each eligible
currency `c`, every CBPOL level in force during the calibration window must be matched to two
observable dates:

- `avail_ts(v)` — the **earliest demonstrable public availability** of value `v`, taken from
  the first of these that can be established: (i) a dated BIS release/publication in which `v`
  demonstrably appeared; failing that, (ii) the **issuing central bank's own authoritative dated
  publication** (policy announcement, press release, or official statistical release) carrying
  `v`. One designated source per currency, named in advance (see the artifact requirement).
- `effective_date(v)` — the date from which `v` is economically in force.

`avail_ts(v)` is a **UTC instant**. Where the evidence is date-granular only (the usual case
for a press release or statistical release), it resolves to the **end of that date in the
publishing source's own timezone**, converted to UTC — so a date-only publication is usable only
from the *next* decision stamp. Coercing a date-only publication to 00:00 is prohibited: it
would reintroduce exactly the unproven availability the fixed-lag rule was withdrawn for.

A value is usable at decision stamp `T(D)` **iff**:

```
avail_ts(v) <= T(D)   AND   effective_date(v) <= date(D)
```

**The usable timestamp is the later of public availability and economic effectiveness.** No
retrospective backdating under any circumstance. `CBPOL_c(D)` is the latest value usable at
`T(D)`.

**Fail-closed.** If, for any eligible currency, any in-window value cannot be matched to an
`avail_ts` under (i) or (ii), historical availability is **not proven** and the study returns
**UNDETERMINED**. It is never approximated by a lag, a nominal release-day assumption, or the
BIS file's own timestamps.

**Level integrity.** BIS supplies the levels; availability is established solely from the dated
publication above. If a BIS level for an in-window date disagrees with the authoritative
central-bank publication for that date, the study returns **UNDETERMINED** (data-integrity
failure) rather than selecting between them.

**Artifact requirement (both axes pinned).** The designated per-currency availability source,
and the resulting `(v, avail_ts, effective_date)` table, must be **committed before the first
financing request** — so no availability judgment can be made after seeing any fidelity
quantity. Because the calibration window is not yet known at commit time, coverage is pinned in
absolute terms on both axes:

- **currency axis:** every currency for which a BIS CBPOL series exists;
- **date axis:** every level in force from `commit_date - 400 days` through `commit_date`
  (400 days strictly covers any rolling ~12-month window the endpoint can serve).

Any in-window value absent from the committed table returns **UNDETERMINED**. **Post-hoc
supplementation of the table is prohibited** — a missing row is never filled in after the window
or any target value has been seen.

OANDA financing values serve **only** as the target, never as a proxy input. Their point-in-time
semantics are **unresolved** — a finalized date-D value may embed information not public before
D 17:00 ET. This is disclosed as a limitation on target measurement, not assumed away.

---

## 7. Estimator and inference (fully locked)

### 7.1 Estimand

**Equal weight per eligible business day.** `tau_bar` is the plain arithmetic mean of the daily
`tau_D` over the eligible business days of Section 4; **every eligible business day carries
weight exactly 1**. Days on which the endpoint returns no rows do not exist for this study and
are not imputed.

**The OANDA `days` field (the financing/rollover multiplier) is never used as a weight**, in
this or any other quantity of this study. It is a property of the accrual calendar, not of
ordering fidelity. (Earlier prose named the estimand "financing-day-weighted", which risked
exactly that misreading; the weighting itself is and always was one-per-day.)

```
tau_D   = Kendall tau-b( p , m )  over the N eligible instruments on business day D
tau_bar = (1 / n) * sum over eligible business days D of tau_D
n       = number of eligible business days
```

Regime-weighting is **rejected**: a long-lived rank regime legitimately dominates the sample
because it is the prevailing condition. Its serial dependence is handled in the variance, not in
the weighting.

### 7.2 Ties and undefined daily values (deterministic, pre-observation)

- **Ties:** Kendall **tau-b** is used precisely because it carries a tie-corrected denominator.
  CBPOL differentials tie frequently (policy rates are step functions). No tie-breaking, no
  jitter, no rank perturbation. Reference implementation: `scipy.stats.kendalltau(..., variant='b')`.
- **Undefined days (fail-closed):** if either vector is constant across all eligible instruments
  on day `D`, `tau_D` is undefined (zero denominator). Pre-registered handling: **any undefined
  `tau_D` makes the study UNDETERMINED.** No dropping, no imputation, no substitution — the
  earlier `tau_D := 0` convention is **withdrawn**, because a substituted value silently biases
  `tau_bar` toward the acceptance boundary and is not an observation.
- **Non-finite values** arising from any other cause make the study **UNDETERMINED**.
- **Degenerate series:** if the resulting `{tau_D}` series has **zero sample variance**, the
  bootstrap interval collapses to zero width and no inference is possible. This returns
  **UNDETERMINED**, never PASS. (This alone closes the route by which a frozen cross-section
  could manufacture `LCB = UCB = tau_bar`; the `N >= 5` floor of Section 4 is a separate,
  independently adopted structural minimum and is not part of this argument.)

### 7.3 Uncertainty procedure

The `{tau_D}` series is a scalar, weakly dependent time series. It is resampled with the
**stationary bootstrap of Politis & Romano (1994)**, with expected block length chosen by the
**corrected Patton, Politis & White (2009) automatic block-length selector** — the corrected
2009 formulation, **not** the unqualified Politis & White (2004) algorithm. Because independent
implementations of that selector differ in their internal constants, the implementation is
pinned in Section 3: `arch.bootstrap.optimal_block_length` (stationary column) and
`arch.bootstrap.StationaryBootstrap`, `arch>=7.2,<8`. No substitute is permitted, and the
installed version is recorded in the report.

Locked settings:

- `B = 10_000` bootstrap replicates, each of length `n`
- `seed = 20260807`, RNG `numpy.random.default_rng(20260807)`
- Resampled object: the `tau_D` series (a scalar series), preserving serial dependence
- Statistic recomputed per replicate: `tau_bar`

**CI construction (locked before data): equal-tail percentile interval.** From the `B` replicate
values of `tau_bar`, take the **5th percentile as LCB** and the **95th percentile as UCB**, i.e.
a two-sided 90% interval whose tails are each 95% one-sided bounds. The percentile method is
chosen ex ante on a structural ground: `tau_bar` is bounded in `[-1, 1]`, and the percentile
interval is transformation-respecting and cannot leave the parameter space. Basic, studentized
and BCa intervals are **not** used.

**Degenerate block selection (deterministic, fail-closed).** Let `b_opt` be the selector output
and `n` the number of days:

- selector fails, or `b_opt` non-finite, or `b_opt < 1` → **UNDETERMINED**
- `b_opt > n / 2` → **UNDETERMINED** (dependence too strong relative to series length)
- otherwise `b = max(1, floor(b_opt + 0.5))` — explicit **round-half-up**, not Python's
  banker's rounding

**No manual post-data block-length substitution is permitted under any circumstance.**

### 7.4 Stated inferential assumptions

Inference assumes the weak-dependence (strong-mixing, stationarity) conditions required for
validity of the stationary bootstrap. These are **assumed, not verified**, and are preregistered
as such. **No method switching after seeing results** — if the assumptions are judged
unsatisfied, the correct outcome is to report the limitation, not to substitute a different
estimator, interval or test.

### 7.5 Ex-ante power calculation withdrawn

Estimating σ from the observed window and reusing that same σ to certify the window's ex-ante
power is circular. It is **withdrawn**. A separate minimum-sample rule is **not needed**: the
decision rule in Section 9 is fail-closed by construction, because insufficient information
mechanically widens the interval into a straddle and yields UNDETERMINED.

---

## 8. Source discontinuities (fail-closed)

**Source (named):** the BIS Data Portal documentation for dataset `WS_CBPOL` — the *Central bank
policy rates: data documentation* note and the per-country series metadata/comments published
with it.

**Qualifying events (enumerated, closed list).** For an eligible currency, any of the following
dated inside the calibration window triggers the fail-closed outcome:

1. a change in **which policy instrument** the series represents (e.g. target rate → corridor
   rate, or a change of the remunerated facility);
2. a change in the **rate concept** represented by the series;
3. any **splice or series linkage** documented by BIS within the window;
4. **discontinuation or suspension** of the currency's CBPOL series within the window (without
   this, unbounded last-observation-carried-forward would silently propagate a terminated
   series' final value across the remainder of the window).

A level change of an unchanged instrument (an ordinary policy decision) is **not** a qualifying
event.

**Artifact requirement (both axes pinned).** The reading must be **committed before the first
financing request**, so its strictness is fixed in advance of any measurement. Coverage is pinned
in absolute terms exactly as in Section 6: **every currency for which a BIS CBPOL series
exists**, over **`commit_date - 400 days` through `commit_date`**. Any eligible currency with no
committed reading, or any in-window qualifying event absent from it, returns **UNDETERMINED**.
Post-hoc supplementation is prohibited.

If any qualifying event falls inside the calibration window for **any** eligible currency, the
study returns **UNDETERMINED**.

There is **no** `±W` exclusion window, **no** maximum exclusion fraction, and **no**
currency-dropping rule. A triggered source-quality problem yields UNDETERMINED, never post-hoc
universe shrinkage.

---

## 9. Acceptance rule

**Fidelity threshold: `tau_min = 0.50`, adopted as a fixed conservative scientific convention.**

Stated plainly: this is a **convention, not a derivation**. `tau = P(concordant) - P(discordant)`,
so `tau = 0.50` corresponds to 3:1 concordance odds. Deriving a threshold from ranking-error
tolerance would require assuming a basket size `k` and an acceptable basket-corruption rate,
importing exactly the strategy assumptions Section 1.2 forbids. The convention is justified by
being (a) strictly stronger than mere non-zero association, (b) frozen before observation, and
(c) never revised.

| Outcome | Condition |
|---|---|
| **PASS** | `LCB(tau_bar) > 0.50` |
| **FAIL** | `UCB(tau_bar) < 0.50` |
| **UNDETERMINED** | **everything else** — i.e. not PASS and not FAIL (including exact boundary hits, which tied rank data makes possible), **or** any trigger in Sections 2, 3.1, 4, 6, 7.2, 7.3, 8 |

**Trigger precedence.** The three outcomes are exhaustive **and** mutually exclusive: **any
fired fail-closed trigger dominates**. If a trigger in Sections 2, 3.1, 4, 6, 7.2, 7.3 or 8 has
fired, the verdict is UNDETERMINED regardless of any interval that may also have been computed.

**Order of operations (locked).** Every fail-closed check in Sections 2, 3.1, 4, 6 and 8 —
including Section 6's level-integrity comparison of BIS levels against the authoritative
central-bank publication — is executed, recorded and committed **before `tau_bar` or its
confidence interval is computed**. No fail-closed check may be run, re-run, or selectively
applied after any fidelity quantity has been seen.

**UNDETERMINED is a mandatory stop.** It is never reinterpreted as PASS, never resolved by
extending the window (impossible — the anchor is rolling), never resolved by relaxing
`tau_min`, and never resolved by re-running.

**Exactly one evaluation run.**

---

## 10. Cost-model boundary

Three strictly separate artifacts:

1. **This ordering-fidelity test.** Makes no cost claim whatsoever.
2. **Historical realized-financing approximation.** A later, separately preregistered design.
   **Presently unresolved.** Deep-history broker financing does not exist (the endpoint is a
   rolling ~12-month archive), so realized financing must be treated as an interval, not a value.
3. **Sensitivity / stress analysis.** A preregistered multiplier grid applied at
   strategy-evaluation time, extending the existing `spread_mult` / `swap_mult` discipline.

Any multiplier derived from the calibration window is an **empirical calibration level observed
in one ~12-month window** — explicitly **not** a proven historical bound or worst case.

**Infeasibility condition (to be quantified in artifact 2, not here).** If the sign of an
instrument's financing contribution flips across the stress range for more than a threshold
fraction of the window, historical financing uncertainty exceeds the signal and proxy-based
carry research is **infeasible**, not merely stressed. That fraction is **not** fixed by this
document and must be preregistered in artifact 2 before it is evaluated. It has no bearing on
the verdict of the present study.

---

## 11. Locked anti-overfit and hygiene rules

1. **P1 (CBPOL) is the only proxy in this study**, immovably. There is no alternative proxy,
   no diagnostic proxy, no "qualitative contradiction" test and no promotion path.
2. No proxy substitution, re-specification or threshold change after observing agreement.
3. No per-currency or per-instrument parameters. No smoothing or lookback variants.
4. All constants are frozen in this document before the first request.
5. One run. Fixed seed. The result is reported whatever it is.
6. **The calibration window is permanently development data.** On first use it can never serve
   as carry validation or confirmation. Any later strategy research interval must end before the
   calibration window begins, and the calibration window is barred from any confirmation segment.
7. Nothing in this document locks a strategy universe, candidate set, benchmark, null,
   performance split, rebalance frequency or confirmation segment. Those remain open and require
   their own preregistration.

---

## 12. Deliverable

A single report stating: the resolved division and the evidence precedence level used; the
calibration window endpoints and the UTC timestamp of the first request; the eligible instrument
list and `N`; `n`; the selected block length `b`; `tau_bar` and its equal-tail percentile
interval; the per-instrument `f_i` diagnostic; explicit confirmation that no `tau_D` was
undefined; the committed `scipy` / `arch` / `numpy`
versions; and the verdict (PASS / FAIL / UNDETERMINED) with the triggering condition named.

**Research-only. No deployment, paper-trading or live-trading permission follows from any
outcome.**
