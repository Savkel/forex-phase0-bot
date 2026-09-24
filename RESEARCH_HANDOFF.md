# Research handoff

## IDENTITY

- Repo: `E:\Claude\forex_bot`
- Branch: `main`
- Last state verification: 2026-09-24, during `TOKYO_FIX_CLOSE_PUSH_SAVE`.
- HEAD observed before this update: `0a0872c79cd754601ee4f1fe16f21d16f454f428`.
- Before closure, `main` is two commits ahead of `origin/main` and verified remote main (`ad5fd8146265661a6ba502ac8fa2571690c2c2a2`), zero behind. The user authorizes a normal closure commit and push, then SAVE MEMORY. The containing commit persists the final Tokyo baseline closure; final live Git/push identity is verified after push and recorded in local continuity notes without a recursive handoff edit. Unrelated artifacts remain preserved.

Current HEAD, `origin/main`, ahead/behind, and dirty state are always read from live Git at session start. Stored observations in this file are audit context only and never supersede live Git. A commit containing a handoff update does not require another edit solely to record its own hash.

## GOVERNANCE

- Permanent constitution: `CLAUDE.md`
- Approved general intraday amendment: [governance/2026-09-24-intraday-passive-benchmark-amendment.md](governance/2026-09-24-intraday-passive-benchmark-amendment.md), frozen in the commit containing this update. It preserves the verbatim pre-economics human approval and binds exact local `CLAUDE.md` SHA-256 `e46730ea21f97b896ee646556b15c7ccffd0694a902176ef8f9c4a870459635f`; the ignored local constitution remains authoritative.
- Closed Stage-A specification: `prereg/2026-08-14-tms-carry-no-try-direct-gbp-kill-test-prereg.md`
- Closed Family-1 specification: `prereg/2026-08-21-tms-carry-unlevered-family-1-universe-prereg.md`
- Authoritative Family-1 closure: `FAMILY1_UNIVERSE_FINAL_RESULTS.md`
- Closed Family-2 specification: `prereg/2026-08-22-tms-carry-unlevered-family-2-rank-hysteresis-prereg.md`
- Authoritative Family-2 closure: `FAMILY2_RANK_HYSTERESIS_FINAL_RESULTS.md`
- Closed Family-3 specification: `prereg/2026-08-22-tms-carry-unlevered-family-3-carry-strength-weighting-prereg.md`
- Authoritative Family-3 closure: `FAMILY3_CARRY_STRENGTH_WEIGHTING_FINAL_RESULTS.md`
- Closed Family-4 specification: `prereg/2026-09-19-tms-carry-unlevered-family-4-rebalance-cadence-prereg.md`
- Authoritative Family-4 closure: `FAMILY4_REBALANCE_CADENCE_FINAL_RESULTS.md`
- Closed Family-5 specification: `prereg/2026-09-20-tms-carry-unlevered-family-5-portfolio-breadth-prereg.md`
- Authoritative Family-5 closure: `FAMILY5_PORTFOLIO_BREADTH_FINAL_RESULTS.md`
- Family-5 operational recovery authority: `prereg/2026-09-20-tms-carry-unlevered-family-5-portfolio-breadth-operational-recovery-authorization.json`
- Closed Family-6 specification: `prereg/2026-09-22-tms-carry-unlevered-family-6-carry-cost-hurdle-prereg.md`
- Authoritative Family-6 closure: `FAMILY6_CARRY_COST_HURDLE_FINAL_RESULTS.md`
- Family-6 one-shot authority: `prereg/2026-09-22-tms-carry-unlevered-family-6-carry-cost-hurdle-execution-authorization.json`
- Agent entrypoint: `AGENTS.md`

Precedence: constitution; committed preregistration/artifacts; verified Git/code/artifact state; this handoff; tool-specific memories; local `CODEX_HANDOFF.md` migration snapshot. Material conflicts are never silently reconciled.

## CLOSED RESEARCH

- Phase 0: `CLOSED_FAIL`
- Phase 1: `CLOSED_FAIL`
- Phase 2A: `CLOSED_FAIL`
- Tokyo pre-fixing USD-demand baseline: `CLOSED_FAIL`; [authoritative closure](TOKYO_FIX_BASELINE_FINAL_RESULTS.md).

## ACTIVE RESEARCH

Direct OANDA TMS `.pro` cross-sectional carry Stage A is CLOSED with valid frozen disposition `STAGE_A_SURVIVES_KILL_TEST`. Attempt 3 was the single valid auditable execution; structural adjudication established that the 3,600-second Codex supervisory timeout did not terminate it. This is robust historical DEVELOPMENT evidence, not prospective OOS and not trading permission. Authoritative closure: `STAGE_A_CARRY_FINAL_RESULTS.md`.

Family 1 of the separate unlevered historical DEVELOPMENT optimization programme is CLOSED. External adjudication retains U14 (`N=14,k=4`) for next research. G10 (`N=10,k=3`) and U8 (`N=8,k=2`) remain valid DEVELOPMENT results but are not selected. Liquidity restriction reduced spread cost and routed turnover but worsened CAGR, RAP, and positive-return Calmar versus U14; U8 also weakened drawdown, IC, and robustness evidence. All results remain immutable and preserved.

Family 2 is CLOSED. External adjudication selects rank-hysteresis `H2` (`h=2`) as the historical DEVELOPMENT configuration for subsequent optimization. H0/H1/H2/H3 remain valid and immutable; H1 and H3 are not selected. Versus H0, H2 improved CAGR, RAP, Calmar, MaxDD, turnover/costs, stresses, and LOCO tails under both D360/D365. B2 remained negative and stays documented. Diagnostic thresholds were not automatic gates. H2 does not replace the original frozen Stage-A/H0 strategy for prospective Stage B.

Family 3 is CLOSED. External adjudication retains equal-weight `EQ_H2` (`tau=0`) as the historical DEVELOPMENT configuration. `CS_MILD` (`tau=0.10`) and `CS_STRONG` (`tau=0.20`) remain valid and immutable but are not selected. Stronger carry weighting increased financing but worsened net CAGR, RAP, Calmar, MaxDD, stress performance, turnover/costs, and concentration; B2 remained negative and worsened with larger `tau`. No automatic gate selected or rejected candidates. `EQ_H2` does not replace the original frozen Stage-A/H0 strategy for prospective Stage B.

Family 4 is CLOSED. External adjudication retains `M1_CONTROL` (weekly cadence) as the historical DEVELOPMENT configuration. M2 and M4 remain valid and immutable but are not selected. Slower cadence reduced trade count and M4 reduced spread/routed turnover, but both worsened CAGR, RAP, Calmar, MaxDD, stresses, spot P&L, and B2; financing remained broadly stable and LOCO benchmark-relative RAP stayed positive in 14/14 cases under both denominators. No automatic gate selected or rejected candidates. The original frozen Stage-A/H0 prospective Stage B remains isolated.

Family 5 is CLOSED. External adjudication retains `K4_CONTROL` (`k=4`) for DEVELOPMENT. K3 and K5 remain valid immutable results but are not selected. DEVELOPMENT remains **U14 + H2 (h=2) + EQ + M1 weekly cadence + k=4**, long +1/short -1, currency gross 2. K3 worsened drawdown, B2 and stress tails; K5 improved drawdown/concentration/costs and matched RAP excess but reduced CAGR, raw RAP, financing and full-sample stress returns versus K4. B2 remains negative for all candidates; negative LOCO stress evidence is preserved. This is an external decision, not an automatic winner/rejection gate. The original frozen Stage-A U14/k4/H0 strategy and prospective Stage B remain unchanged and isolated.

Family 6 is CLOSED. External adjudication retains `HURDLE_OFF_CONTROL`, identical to Family-5 `K4_CONTROL`, for DEVELOPMENT. `HURDLE_1X` and `HURDLE_2X` remain valid immutable results but are not selected. Both hurdles reduced turnover, fills and spread cost; 2X also improved MaxDD, Calmar and B2. Neither improved net CAGR or RAP because avoided rotations lost more spot value than the costs saved. DEVELOPMENT therefore remains **U14 + H2 (`h=2`) + EQ + M1 weekly cadence + `k=4`**, long +1/short -1, currency gross 2, without a carry-cost hurdle. This external decision does not alter the original frozen Stage-A/H0 prospective Stage-B strategy.

Further sequential unlevered optimization is **STOPPED** pending a separately authorized new research stage. Family 7 is not defined and must not be opened or inferred.

### Strategy 2: Tokyo frozen baseline CLOSED_FAIL; one-shot consumed

The user authorized final closure in `TOKYO_FIX_CLOSE_PUSH_SAVE` on 2026-09-24. [TOKYO_FIX_BASELINE_FINAL_RESULTS.md](TOKYO_FIX_BASELINE_FINAL_RESULTS.md) is authoritative for closure and exact emitted evidence hashes. Original specification/governance/DAILY-venue freeze: `36e786b36e0c6ea038f4548c95cd92c2691b0816`; complete-case mask/implementation/readiness freeze: `0a0872c79cd754601ee4f1fe16f21d16f454f428`. Those frozen files and all generated evidence remain unchanged.

One scientific attempt completed in `reports/forex/tokyo_fix/economics_once_complete_case_20260924/`. Result SHA-256: `e76505e55be0b746ab48284ab9999cc005d76aa1fc198fa7d0e8d0951df32c7b`; completion SHA-256: `c63d40e07b211f1cdc8cd22977d27714de830e544c7deaac9d57f830288207c3`. The exclusive attempt directory and `STARTED_NO_RETRY` marker remain present, with valid completion and no failure artifact. **One-shot consumed: do not rerun, reset or remove its guard.** Raw result remains `CLOSED_FAIL`; raw completion remains `ECONOMICS_COMPLETED_PENDING_EXTERNAL_ADJUDICATION`. This handoff and the closure document record the subsequent external decision without rewriting emitted statuses.

All three frozen economic requirements FAILED (0/3): base normalized alpha `-0.17392391157247847`; doubled-half-spread alpha `-0.3889184609759322`; base primary MaxDD `-0.18969730258440576` is deeper than matched-passive `-0.014085867344707959`. Primary cumulative net return is -18.014368339491% base and -40.783151582552% stress. All three fixed chronological blocks have negative returns and alpha under both costs; block evidence has no extra automatic gates.

Preserve positive timing evidence: mean primary-minus-average-controls contrast is `0.00012255136631729967` base and `0.00014838683104991757` stress; both one-sided bootstrap p-values are exactly `1/10001`. This is **relative timing evidence only, not profitability** or proof of fixing-specific causation. No significance gate was prescribed and timing evidence cannot override economic failure.

Calendar eligibility remains 2,446 dates, with one original envelope exclusion and 44 pre-economics common data exclusions (1.799591% of 2,445), yielding 2,401 paired dates. The full 983-absence map, earlier failures, calendar provenance, permitted cache and complete-case amendment remain immutable. Missingness may be nonrandom. Actual account mode is UNKNOWN; the zero-financing model is conditional on the declared DAILY venue. Historical DEVELOPMENT results establish neither untouched OOS nor trading/account execution permission.

Readiness recorded 125 passing focused tests, independent hand-ledger/bootstrap checks and quote integrity. Closure reverified immutable hashes and frozen bindings; no tests, readiness computation, strategy/bootstrap economics, source fetch, sealed-data or Stage-B access was rerun. Emitted results/readiness/archives remain local/gitignored; source/specification/closure and hash bindings are tracked. Existing unrelated untracked artifacts remain preserved.

**No rescue:** no post-hoc timing/day/filter/cost/threshold/mask changes, tuning or replay of this baseline. Broader Tokyo-fixing mechanisms remain eligible only as separately authorized and independently preregistered research; closure selects no successor. Carry DEVELOPMENT remains **U14 + H2 + EQ + M1 + k=4 + HURDLE_OFF_CONTROL**, with no Family 7; Phase-2A confirmation and carry Stage B remain sealed.

## ACTIVE LOCKED SPEC

- Prior preregistrations: original `2026-08-08` and no-TRY EUR_GBP-execution commit/spec `2c81d140` — both `SUPERSEDED_UNEXECUTED`; neither produced a performance result.
- Active preregistration: `prereg/2026-08-14-tms-carry-no-try-direct-gbp-kill-test-prereg.md`
- Universe: `prereg/2026-08-14-tms-carry-no-try-direct-gbp-universe.json`
- Financing/data-availability mask: `prereg/2026-08-14-tms-carry-no-try-direct-gbp-mask.json`
- Price readiness: `prereg/2026-08-14-tms-carry-no-try-direct-gbp-price-readiness.json`
- Financing readiness: `prereg/2026-08-14-tms-carry-financing-readiness.json`
- Persistent Stage-A lineage: `prereg/2026-08-14-tms-carry-stage-a-lineage.json`

Frozen revised essentials: certified source remains intact; active grid excludes TRY and has 35 financing pairs, 14 currencies, `k=4`, and 13 cost-blind routed price legs. GBP routes directly and exclusively through `GBP_USD`; `EUR_GBP` remains financing evidence but is not an execution leg. The causal mask remains 167 defined/157 evaluable rebalances; common OANDA v20 practice H1 bid/ask timestamps and candle OPEN semantics are unchanged. Historical execution remains explicitly hybrid: TMS `.pro` financing with v20 practice prices.

Family-1 immutable evidence:

- Execution: `prereg/2026-08-21-tms-carry-unlevered-family-1-execution.json`, SHA-256 `6025492cb2b8ba79af02ab614e128a4ba850953b337f91b89ff6f18f0c4c0a0e`.
- Result: `reports/forex/family1/family1-universe-result.json`, SHA-256 `ec0d85614928d6a1357c575ddfe0421d1499b24cbb005b985790d092934bbb1f`.
- Completion: `reports/forex/family1/family1-universe-completion.json`, SHA-256 `558003ddfee8a9e58e5b61115bab70d242b4991fc685bf5078ed23866a0d2867`.

Family-2 immutable evidence:

- Execution: `prereg/2026-08-22-tms-carry-unlevered-family-2-rank-hysteresis-execution.json`, SHA-256 `705e6ab6b3863a726dad77d2665a10f0c0c6e6e76308feb738f3879426a36f2d`.
- Result: `reports/forex/family2/family2-rank-hysteresis-result.json`, SHA-256 `04c7d5bf34fef2b8a80dccf9e1cce2543bb1a49f32482e745526311bc754247c`.
- Completion: `reports/forex/family2/family2-rank-hysteresis-completion.json`, SHA-256 `3f23c7a02bcfb5f003f0882d25fabe739e3c5f5f0b48c1091f530d000154abb0`.
- Readiness: SHA-256 `68c45ee6f162d84a033ce25aeea2de02a8187f484d4f2faf34a495055427e4a7`.
- H0 parity: SHA-256 `0ced81728ed3678877b63cd8008f05a8436802aba072c35f50c0456863669641`.

Family-3 immutable evidence:

- Execution: `prereg/2026-08-22-tms-carry-unlevered-family-3-carry-strength-weighting-execution.json`, SHA-256 `3e231b9f94bdf5b8c8328b7d5af0a5115224c24829f5a8c4a95acc1cb72bd490`.
- Result: `reports/forex/family3/family3-carry-strength-weighting-result.json`, SHA-256 `88f00d40db42b568952c9866973d94e44ce7df481ddb0b8bdfe901a5419e86ac`.
- Completion: `reports/forex/family3/family3-carry-strength-weighting-completion.json`, SHA-256 `922eb763a35abfbee2973b253e17cff42433578168ca051871fcca326f45f17a`.
- Readiness: SHA-256 `9afc7f1140e48a3ff2f7ce5f181f56138c4e753f2a396a0d1ddc302c12b88890`.
- EQ_H2 parity: SHA-256 `6060e8aa81c2b17a12536abe46028159076fba959dac069fb636841c131a91e0`.
- Execution provenance: one user-run frozen one-shot command completed; Codex did not run Family-3 candidate economics; no network access occurred.

Family-4 immutable evidence:

- Execution: `prereg/2026-09-19-tms-carry-unlevered-family-4-rebalance-cadence-execution.json`, SHA-256 `eb2b97d96924e694e868bf087506070a5953860c1766bc2880f179366300927e`.
- Result: `reports/forex/family4/family4-rebalance-cadence-result.json`, SHA-256 `b92f6d12d7cd7274bf3e60dca44fc402bd7bfe6d9fa6ee8fcc78f1cb31bdb6a8`.
- Completion: `reports/forex/family4/family4-rebalance-cadence-completion.json`, SHA-256 `85469fed3c81b74c6783da40302e2548ff53f7c66794baae345ace68eaaa9547`.
- Readiness: SHA-256 `d292d6355ad27b23b515b72d8704b03b337582b5b2adf8a40b66e6bca5700e25`.
- M1 parity: SHA-256 `a7528e78462dd48ea3f6124c161d5882c521b501e6a7d3a43628f22963c5ebfa`.
- Execution provenance: one user-run frozen one-shot command completed; Codex did not run M2/M4 economics; no network access occurred.

Family-5 immutable evidence:

- Closure: `FAMILY5_PORTFOLIO_BREADTH_FINAL_RESULTS.md` (complete artifact ledger, results and negative evidence).
- Prereg freeze: `f41f8524c30cd45ae48000127d2452baca1795af`; infrastructure: `2c64264ea9d7618c258bc81c69b5fbe3c63e0e5b`; original authorization: `69e78605dddf45a1bf23a514393d71fb6c825c12`; operational recovery authorization: `7f07e54ad21aed9aadcdbd9b47e8f7bbfdbfdbe4`.
- `prereg/2026-09-20-tms-carry-unlevered-family-5-portfolio-breadth-readiness.json`, SHA-256 `b24d796cb889d771d2be4540e55d68cbadfafaa62e6a792d39b20900f0da61e0`.
- `prereg/2026-09-20-tms-carry-unlevered-family-5-portfolio-breadth-k4-parity.json`, SHA-256 `eafe337788f6f67ed08a77abd95e335c57243fbb2ee98ab8ebb49c9b504e7a9b`.
- `prereg/2026-09-20-tms-carry-unlevered-family-5-portfolio-breadth-operational-recovery-authorization.json`, SHA-256 `91f9c5d73065e63eebc3e9fdbeccc0b4fcc77b55383f564b2da926efd7290fee`.
- `prereg/2026-09-20-tms-carry-unlevered-family-5-portfolio-breadth-execution.json`, SHA-256 `eb7cdf5c484e6b235d3e88c688d6efb40d3245c73357a345fe0f5c4f56708600`.
- `reports/forex/family5/family5-k4-control.json`, SHA-256 `e1518d90d3e78d52c53ee125181aa25ffa779637c3605b75b6030bd64a768137`.
- `reports/forex/family5/family5-k4-paths.jsonl.gz`, SHA-256 `92a3178b9a2196539edbecd3916c4e02dd976a73a4c1b060dd44d557fd4fa430`.
- `reports/forex/family5/family5-portfolio-breadth-result.json`, SHA-256 `5b7105375bc539b22a29e4278927e7515d9808a804173f2e17b9b1deeed6c883`.
- `reports/forex/family5/family5-portfolio-breadth-completion.json`, SHA-256 `4019102689c553768813c6e5bb410dcfca1643452669f27be839c3c082fc954d`.
- `reports/forex/family5/family5-candidate-paths.jsonl.gz`, SHA-256 `a50bad8d0d8c76918003170886e38442b931a778b271dc66717d9f8cef9aa165`.
- Recovery sidecar Git-normalized SHA-256: `e1c23e49937db52ede5f7b871a3b54df91e97667187f46b2e8789695be404b7b`; local-byte difference is line endings only.
- Operational provenance: first attempt ended incomplete solely from ENOSPC, with no valid result/completion. Its hash-verified incomplete 8.47 GB archive was removed under separate external authorization; the failed marker and concise audit remain. An identical frozen clean retry completed K3 then K5, reusing K4. Two operational attempts produced one successful scientific completion, not tuning or a second scientific result.
- Successful execution/completion have `consumption_count=1`; old/new marker payloads and hashes are identical, with attempt linkage supplied by the committed recovery sidecar. No further execution is authorized.
- All K3/K5 FULL + 14 LOCO cases, 1,000 matched books/case, three scenarios, D360/D365 and B1/B2/B3 are complete. The candidate archive has 178,660 verified records, 15,789,358,836 bytes; all 1,260 report distributions and archive integrity/order checks passed in read-only post-execution verification.
- Raw result/candidate labels remain `PENDING_EXTERNAL_ADJUDICATION`; completion remains `ECONOMICS_COMPLETED_PENDING_EXTERNAL_ADJUDICATION`. External closure is recorded here and in the final-results document without editing emitted evidence.
- Reports/control/path archives remain local/gitignored; successful and failed execution markers remain local/untracked. Original authorization, readiness, parity, prereg, code and inputs remain frozen. No network/data fetch or Stage-B access occurred during execution/verification.

Family-6 immutable evidence:

- Closure: `FAMILY6_CARRY_COST_HURDLE_FINAL_RESULTS.md` (complete result summary, mechanism interpretation, LOCO tails and artifact ledger).
- Prereg freeze: `a34c0fec0ceaafd4f7fc05e9ae32fce544a8fb5d`; hurdle checkpoint: `e79facfb3a6ca3ac208382cfd5752935a7eaee66`; execution layer: `6b8823ab18521a1cecef7606f33837867bedb25d`; guard fix: `f27ec7fb9a47487a1b4e62fe1ef20245cb53b6b2`; authorization: `80d72b748ed52f8ec6836de8a955082dfe6e9f63`.
- Prereg/readiness/CONTROL-parity SHA-256: `38a75c3f821843e740401cc7255f83d621c8030ff013ba3170341ea534af6d1d`, `2494984371ff670cb91da8104b84d2675a8145dea3247b6188673fd23822a3cf`, `49e25dab4d3ae254da75f8755271baa58190c5c46fcf2a02f18d27de3fb65d38`.
- Authorization/execution/result/completion SHA-256: `ada3b7b09645ff24217c50e5cf88a72795d113f02e693b4e893609e15c949c77`, `fa45e80edcf3e768bd850b1dbe895d85305ee4d94eca78c631935d974ac2463e`, `53f4eb679fc2063231499dcf11793b8a7edb7677b6a0d6132132cc0e44a6ae6e`, `5114f2fae7cf7f9a3f532dbda5576a39d76e61fece855185587a1cdf535c64da`.
- Candidate archive: 18,372,238 bytes, 180 ordered unique records; compressed SHA-256 `db6ae7dc773495114aa82caf64ed0ee05f53e803b0291813ae1e1e64c5029199`; uncompressed-stream SHA-256 `59e7e4d093bd1a4dda78fbb5938389dc4022081e5dc730381a4360eb8291174a`.
- One operational attempt produced one completed scientific result; marker/completion scientific consumption count is 1. Candidate order was 1X then 2X; no recovery/retry occurred. FULL plus 14 LOCO cases, three scenarios, D360/D365 and B1/B2/B3 are complete.
- Exact immutable Family-5 K4 benchmark/control and IC evidence were hash-reused for all cases. CONTROL parity has zero mismatches and maximum difference 0.0 against tolerance `1e-12`; candidate accounting maximum residual was `1.0047518372857667e-14` with zero hurdle-threshold or target-path anomalies.
- Raw result labels remain `PENDING_EXTERNAL_ADJUDICATION`; completion remains `ECONOMICS_COMPLETED_PENDING_EXTERNAL_ADJUDICATION`. External closure is recorded here and in the final-results document without editing emitted evidence.
- Result/completion/archive remain local/gitignored; execution marker remains local/untracked. Frozen source/input bindings revalidated; execution/verification recorded no network or Stage-B access. No tests, parity or economics were rerun for closure.

## CERTIFIED INFRASTRUCTURE

TMS ingestion is fail-closed and certified through flattened-text/layout-geometry agreement. Latest relevant parser commit: `c9e727c`. Manifest: `provenance/tms_swap_manifest.json`. Current canonical freeze-manifest SHA-256: `586c2229de5d959bae21b780192f0ecdaa60b4bf34a00bc2e432b575aaa5f4e5`. Family-1 infrastructure passed 18 focused, 114 Stage-A boundary, and 615 full-suite tests before economics. The output-equivalent benchmark-cache optimization is pushed at `eed98da5373c9752f08a875a45af2cb39174d039`. Family-2 infrastructure passed 10 focused, 110 relevant boundary, and 626 full-suite tests; H0 parity had zero discrete/numeric mismatches and maximum numeric difference `1.4210854715202004e-14` against tolerance `1e-12`. Family-3 infrastructure passed 16 focused/relevant and 632 full-suite tests; EQ_H2 parity had zero discrete/numeric mismatches and maximum numeric difference `1.4210854715202004e-14` against tolerance `1e-12`, with IC alone hash-reused. Family-4 infrastructure passed 6 focused and 638 full-suite tests; M1 parity had zero discrete/numeric mismatches and maximum numeric difference `1.4210854715202004e-14` against tolerance `1e-12`, with IC hash-reused.

Family-5 checkpoint records 75 focused and 697 full-suite passing tests (historical, not rerun for closure). K4 parity covered 1,349,231,725 numeric and 540,074,611 discrete comparisons; numeric/discrete/shape mismatches were zero, maximum delta `1.4210854715202004e-14` versus `1e-12`. Successful K4 control/archive were hash-reused. Closure reverified 13 evidence hashes and 35 source hashes; no tests, parity or economics were rerun.

Family-6 infrastructure was approved at checkpoint `e79facfb3a6ca3ac208382cfd5752935a7eaee66` after its required focused, boundary, causality and full-suite checks. CONTROL parity compared 1,538,278 numeric and 738,984 discrete values across 15 cases and 90 strategy paths, with zero numeric/discrete/shape mismatches and maximum difference 0.0 at tolerance `1e-12`; benchmark and IC evidence were exact hash reuse. The later execution guard path passed its focused checks before authorization. No tests or parity were rerun during economics verification or closure.

## DATA STATE

The certified corpus and reproducibility aids now have a stable project-local, gitignored home at `data/tms_swap_archive/`. Relocation was verified network-free and byte-preserving: all 226 source files were classified; 222 retained source records mapped exactly by size and SHA-256 to 218 unique destination files; all 171 manifest-backed documents matched committed provenance; and `parsed_all.json` was copied byte-for-byte. The old Claude session-temporary corpus remains intact at `C:\Users\Savvas\AppData\Local\Temp\claude\E--Claude-forex-bot\6f68a067-3cdf-4b0c-8ea3-b6a846c47d3c\scratchpad\`, but it is no longer the required working dependency. Raw and derived data remain local and gitignored.

Price readiness is certified in the active committed artifact: all 13 routed OANDA v20 practice H1 bid/ask caches cover the frozen range with deterministic SHA-256 evidence (5 reused, 8 newly fetched). All 168 frozen transaction targets resolve to the first eligible synchronous all-leg H1 OPEN timestamp; maximum mechanical closure delay was 22 hours. Raw price caches remain local and gitignored.

Financing readiness is certified under the venue-evidenced held-leg model: evidence identity `7e93e702816833ba5ed2de7432c1476af576186fb52da462de2e4c48a3f26dbf`, 5,211 baseline events, 911 closed-market non-events, and 5,211/5,211 required inputs available. No synthetic or shifted holiday valuation is used.

## CURRENT STATE

Attempt 2 remains immutable `VOID_RETAINED`; its provisional disposition is not scientific evidence. Valid operational Attempt 3 used freeze `586c2229de5d959bae21b780192f0ecdaa60b4bf34a00bc2e432b575aaa5f4e5`; result SHA-256 `39838d559e36645c7910b65f5190d7b292540ed780ebe1ce3a697b8dbec9e6b8`. All G1-G5 requirements passed under the frozen rules. Absolute post-hoc baseline performance was modest at approximately 2.3% CAGR. Stage A is closed; no tuning, rerun, or trading permission follows.

Family-1 closure remains committed and pushed at `fb557e15dc7c2b740d1dcd0d232c0cfd2b17c30d`. Family-2 closure remains committed and pushed at `53521229316bf18eef951452c3fca6fb46dcd96b`. Family-3 closure remains committed and pushed at `103aadb268cf732c588b89b68c766402c315d691`. Family-4 closure remains committed and pushed at `5ae6e9a3c14aafc379f44521ff1a22ca7976a6ee`. Family-5 closure remains committed and pushed at `d8c1127261295635682e0de92edc4ad8b32c76b0`. Family-6 now retains HURDLE_OFF_CONTROL with valid unselected 1X/2X results. Before this closure/handoff commit, local `main`, `origin/main` and verified remote HEAD matched `80d72b748ed52f8ec6836de8a955082dfe6e9f63` at `0/0`; only expected local/generated evidence and prior untracked files remained. The authorized closure/handoff commit is pushed normally and its exact resulting HEAD is recorded in local memories after push verification, without a recursive handoff edit. Stage A remains immutable and closed.

## NEXT GATE

Family 6 is CLOSED. Further sequential unlevered carry optimization is STOPPED. No Family 7 is defined or authorized.

Tokyo baseline is CLOSED_FAIL and its one-shot is consumed. No next research gate is selected. Await a separately authorized, independently preregistered new research proposal; broader Tokyo-fixing mechanisms are not blanket-banned, but no post-hoc rescue, tuning or replay of this baseline is authorized. Positive timing evidence is relative only. Preserve all evidence; do not access credentials, sealed Phase-2A data or carry Stage B.

Prospective Stage B for the original frozen Stage-A strategy remains isolated and untouched; it is not opened by Family-6 closure and would require separate external authorization.

## MEMORY SYNCHRONIZATION

Three deliberate continuity layers are maintained: this tracked tool-neutral handoff; Claude `MEMORY.md` plus only the relevant active linked memory; and `C:\Users\Savvas\.codex\project_notes\forex_bot.md`. Tool-specific memory never overrides governance, locked artifacts, or verified repo state.

On explicit `SAVE MEMORY`: first verify live Git identity/state, latest completed gate/result, relevant tests, and committed versus local/generated state. Update durable verified research/project state here; current Git identity remains a live verification, and a handoff commit does not trigger a recursive edit to store its own hash. Update Claude's index and only the active linked memory, then the Codex checkpoint; after an authorized handoff commit, those out-of-repo memories may record its exact HEAD. Cross-check all layers for active phase, latest verdict, frozen decisions, blocker, next gate, and push status; cross-check exact current HEAD between live Git and local memories. If any requested layer cannot be updated, report that and do not claim synchronization. `SAVE MEMORY` alone authorizes neither strategy/data execution, commit, nor push.
