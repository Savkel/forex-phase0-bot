# Research handoff

## IDENTITY

- Repo: `E:\Claude\forex_bot`
- Branch: `main`
- Last state verification: 2026-08-13, before this handoff repair.
- Project-state commit observed before the handoff update: `0926f557f91355042dd48322f0ac096fa5a93fe7`.
- Push status observed then: local `main` was 9 ahead / 0 behind `origin/main`; commits were unpushed.

Current HEAD, `origin/main`, ahead/behind, and dirty state are always read from live Git at session start. Stored observations in this file are audit context only and never supersede live Git. A commit containing a handoff update does not require another edit solely to record its own hash.

## GOVERNANCE

- Permanent constitution: `CLAUDE.md`
- Active specification: `prereg/2026-08-08-tms-carry-kill-test-prereg.md`
- Emitted locked artifacts: the universe, mask, and price-readiness JSON files named below.
- Agent entrypoint: `AGENTS.md`

Precedence: constitution; committed preregistration/artifacts; verified Git/code/artifact state; this handoff; tool-specific memories; local `CODEX_HANDOFF.md` migration snapshot. Material conflicts are never silently reconciled.

## CLOSED RESEARCH

- Phase 0: `CLOSED_FAIL`
- Phase 1: `CLOSED_FAIL`
- Phase 2A: `CLOSED_FAIL`

## ACTIVE RESEARCH

Direct OANDA TMS `.pro` cross-sectional carry. Stage A is a historical DEVELOPMENT kill-test with no historical OOS claim and has not executed. A valid FAIL means `CLOSED_FAIL`; all gates passing means only `SURVIVES_KILL_TEST` and permits prospective Stage B, not research PASS or trading permission.

## ACTIVE LOCKED SPEC

- Preregistration: `prereg/2026-08-08-tms-carry-kill-test-prereg.md`
- Universe: `prereg/2026-08-08-tms-carry-universe.json`
- Financing/data-availability mask: `prereg/2026-08-08-tms-carry-mask.json`
- Price readiness: `prereg/2026-08-08-tms-carry-price-readiness.json`

Frozen essentials: 36 financing pairs, 15 currencies, 14 cost-blind routed price legs; 167 defined and 157 evaluable rebalances; common book-level OANDA v20 practice H1 bid/ask timestamps; candle OPEN fills/returns; no universe, routing, window, or rule substitution. Historical execution is explicitly hybrid: TMS `.pro` financing with v20 practice prices.

## CERTIFIED INFRASTRUCTURE

TMS ingestion is fail-closed and certified through flattened-text/layout-geometry agreement. Latest relevant parser commit: `c9e727c`. Manifest: `provenance/tms_swap_manifest.json`. Latest full-suite verification: 501 passed on 2026-08-13 at project-state commit `c6fff17`; subsequent continuity changes were documentation only, so the suite was not rerun.

## DATA STATE

Certified financing provenance and emitted artifacts exist. The raw corpus, parsed output, and generation scripts remain under `C:\Users\Savvas\AppData\Local\Temp\claude\E--Claude-forex-bot\6f68a067-3cdf-4b0c-8ea3-b6a846c47d3c\scratchpad\` (verified present 2026-08-13: 183 PDFs, 7 archive ZIPs, `parsed_all.json`, and named scripts). This session-temporary path must not silently become a permanent dependency. Raw data remains local and gitignored; no relocation occurred.

## CURRENT BLOCKER

Frozen price readiness is blocked: 0/14 routed legs have verified H1 bid/ask coverage. Seven previously unverified exotic legs are `USD_CZK`, `EUR_HUF`, `EUR_NOK`, `EUR_PLN`, `EUR_SEK`, `EUR_TRY`, and `EUR_ZAR`. Historical OANDA access requires explicit human approval.

## NEXT GATE

Stable relocation of the certified temporary TMS corpus to a project-local gitignored location, without refetching or reparsing.

## MEMORY SYNCHRONIZATION

Three deliberate continuity layers are maintained: this tracked tool-neutral handoff; Claude `MEMORY.md` plus only the relevant active linked memory; and `C:\Users\Savvas\.codex\project_notes\forex_bot.md`. Tool-specific memory never overrides governance, locked artifacts, or verified repo state.

On explicit `SAVE MEMORY`: first verify live Git identity/state, latest completed gate/result, relevant tests, and committed versus local/generated state. Update durable verified research/project state here; current Git identity remains a live verification, and a handoff commit does not trigger a recursive edit to store its own hash. Update Claude's index and only the active linked memory, then the Codex checkpoint; after an authorized handoff commit, those out-of-repo memories may record its exact HEAD. Cross-check all layers for active phase, latest verdict, frozen decisions, blocker, next gate, and push status; cross-check exact current HEAD between live Git and local memories. If any requested layer cannot be updated, report that and do not claim synchronization. `SAVE MEMORY` alone authorizes neither strategy/data execution, commit, nor push.
