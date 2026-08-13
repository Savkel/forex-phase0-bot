# Project entrypoint

Before acting, read `CLAUDE.md`, then `RESEARCH_HANDOFF.md`, then the active preregistration and emitted artifacts referenced there. Verify current Git state before relying on point-in-time repository facts.

Source precedence is: `CLAUDE.md`; committed preregistration and emitted artifacts; verified Git/code/artifact state; `RESEARCH_HANDOFF.md`; tool-specific memory; local `CODEX_HANDOFF.md` migration snapshot. Treat preregistration as locked and never rescue `CLOSED_FAIL` research.

Never read credentials or `.env`; fetch historical OANDA data only with explicit human approval; never run live or paper orders; never push without separate explicit human approval. Work one bounded gate at a time, keep outputs token-efficient, and use real execution/tests for behavioral claims. Automatic and tool-specific memory is secondary context only.

When the user says `SAVE MEMORY`, first verify live Git state, the latest completed gate/result, relevant tests, and committed versus local/generated state. Update durable research/project state in `RESEARCH_HANDOFF.md`, then Claude `MEMORY.md` plus only the active linked memory, and `C:\Users\Savvas\.codex\project_notes\forex_bot.md`. Live Git is authoritative for current HEAD, origin, ahead/behind, and dirty state; the tracked handoff never needs a second edit merely to record the commit containing its update. After an authorized handoff commit, local Claude/Codex memories may record its exact HEAD. Cross-check scientific state and push status across all layers, and exact HEAD between live Git and local memories. Do not claim success unless all requested layers were updated. `SAVE MEMORY` does not authorize data/strategy execution, a commit, or a push.
