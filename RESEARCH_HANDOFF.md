# Research handoff

## IDENTITY

- Repo: `E:\Claude\forex_bot`
- Branch: `main`
- Last state verification: 2026-08-14, before this handoff update.
- Project-state commit observed before the handoff update: `d4159b60e6466825a95cfe2af455c0a2bc54fa05`.
- Push status observed then: local `main` was 32 ahead / 0 behind `origin/main`; commits were unpushed.

Current HEAD, `origin/main`, ahead/behind, and dirty state are always read from live Git at session start. Stored observations in this file are audit context only and never supersede live Git. A commit containing a handoff update does not require another edit solely to record its own hash.

## GOVERNANCE

- Permanent constitution: `CLAUDE.md`
- Closed Stage-A specification: `prereg/2026-08-14-tms-carry-no-try-direct-gbp-kill-test-prereg.md`
- Closed Family-1 specification: `prereg/2026-08-21-tms-carry-unlevered-family-1-universe-prereg.md`
- Authoritative Family-1 closure: `FAMILY1_UNIVERSE_FINAL_RESULTS.md`
- Agent entrypoint: `AGENTS.md`

Precedence: constitution; committed preregistration/artifacts; verified Git/code/artifact state; this handoff; tool-specific memories; local `CODEX_HANDOFF.md` migration snapshot. Material conflicts are never silently reconciled.

## CLOSED RESEARCH

- Phase 0: `CLOSED_FAIL`
- Phase 1: `CLOSED_FAIL`
- Phase 2A: `CLOSED_FAIL`

## ACTIVE RESEARCH

Direct OANDA TMS `.pro` cross-sectional carry Stage A is CLOSED with valid frozen disposition `STAGE_A_SURVIVES_KILL_TEST`. Attempt 3 was the single valid auditable execution; structural adjudication established that the 3,600-second Codex supervisory timeout did not terminate it. This is robust historical DEVELOPMENT evidence, not prospective OOS and not trading permission. Authoritative closure: `STAGE_A_CARRY_FINAL_RESULTS.md`.

Family 1 of the separate unlevered historical DEVELOPMENT optimization programme is CLOSED. External adjudication retains U14 (`N=14,k=4`) for next research. G10 (`N=10,k=3`) and U8 (`N=8,k=2`) remain valid DEVELOPMENT results but are not selected. Liquidity restriction reduced spread cost and routed turnover but worsened CAGR, RAP, and positive-return Calmar versus U14; U8 also weakened drawdown, IC, and robustness evidence. All results remain immutable and preserved.

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

## CERTIFIED INFRASTRUCTURE

TMS ingestion is fail-closed and certified through flattened-text/layout-geometry agreement. Latest relevant parser commit: `c9e727c`. Manifest: `provenance/tms_swap_manifest.json`. Current canonical freeze-manifest SHA-256: `586c2229de5d959bae21b780192f0ecdaa60b4bf34a00bc2e432b575aaa5f4e5`. Family-1 infrastructure passed 18 focused, 114 Stage-A boundary, and 615 full-suite tests before economics.

## DATA STATE

The certified corpus and reproducibility aids now have a stable project-local, gitignored home at `data/tms_swap_archive/`. Relocation was verified network-free and byte-preserving: all 226 source files were classified; 222 retained source records mapped exactly by size and SHA-256 to 218 unique destination files; all 171 manifest-backed documents matched committed provenance; and `parsed_all.json` was copied byte-for-byte. The old Claude session-temporary corpus remains intact at `C:\Users\Savvas\AppData\Local\Temp\claude\E--Claude-forex-bot\6f68a067-3cdf-4b0c-8ea3-b6a846c47d3c\scratchpad\`, but it is no longer the required working dependency. Raw and derived data remain local and gitignored.

Price readiness is certified in the active committed artifact: all 13 routed OANDA v20 practice H1 bid/ask caches cover the frozen range with deterministic SHA-256 evidence (5 reused, 8 newly fetched). All 168 frozen transaction targets resolve to the first eligible synchronous all-leg H1 OPEN timestamp; maximum mechanical closure delay was 22 hours. Raw price caches remain local and gitignored.

Financing readiness is certified under the venue-evidenced held-leg model: evidence identity `7e93e702816833ba5ed2de7432c1476af576186fb52da462de2e4c48a3f26dbf`, 5,211 baseline events, 911 closed-market non-events, and 5,211/5,211 required inputs available. No synthetic or shifted holiday valuation is used.

## CURRENT STATE

Attempt 2 remains immutable `VOID_RETAINED`; its provisional disposition is not scientific evidence. Valid operational Attempt 3 used freeze `586c2229de5d959bae21b780192f0ecdaa60b4bf34a00bc2e432b575aaa5f4e5`; result SHA-256 `39838d559e36645c7910b65f5190d7b292540ed780ebe1ce3a697b8dbec9e6b8`. All G1-G5 requirements passed under the frozen rules. Absolute post-hoc baseline performance was modest at approximately 2.3% CAGR. Stage A is closed; no tuning, rerun, or trading permission follows.

Family-1 closure is committed and pushed at `fb557e15dc7c2b740d1dcd0d232c0cfd2b17c30d`. At verification immediately before this handoff update, local `main`, local `origin/main`, and real remote `main` all matched that commit with ahead/behind `0/0`; only expected untracked `CODEX_HANDOFF.md` and `review.txt` remained. Stage A and all Family-1 code, specifications, and results are unchanged.

## NEXT GATE

`PERFORMANCE_OPTIMIZATION_BEFORE_FAMILY2`

Any new optimization family requires a separate preregistered gate. Prospective Stage B for the original frozen Stage-A strategy remains isolated and untouched.

## MEMORY SYNCHRONIZATION

Three deliberate continuity layers are maintained: this tracked tool-neutral handoff; Claude `MEMORY.md` plus only the relevant active linked memory; and `C:\Users\Savvas\.codex\project_notes\forex_bot.md`. Tool-specific memory never overrides governance, locked artifacts, or verified repo state.

On explicit `SAVE MEMORY`: first verify live Git identity/state, latest completed gate/result, relevant tests, and committed versus local/generated state. Update durable verified research/project state here; current Git identity remains a live verification, and a handoff commit does not trigger a recursive edit to store its own hash. Update Claude's index and only the active linked memory, then the Codex checkpoint; after an authorized handoff commit, those out-of-repo memories may record its exact HEAD. Cross-check all layers for active phase, latest verdict, frozen decisions, blocker, next gate, and push status; cross-check exact current HEAD between live Git and local memories. If any requested layer cannot be updated, report that and do not claim synchronization. `SAVE MEMORY` alone authorizes neither strategy/data execution, commit, nor push.
