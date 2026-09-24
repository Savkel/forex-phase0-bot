# General intraday passive benchmark amendment

- Record date: `2026-09-24`.
- Gate: `INTRADAY_BENCHMARK_GOVERNANCE_PERSISTENCE`.
- Status: human-approved before economics; frozen by the authorized local commit containing this update. Execution readiness remains subject to the applicable preregistration checks.
- Repository HEAD at recording: `ad5fd8146265661a6ba502ac8fa2571690c2c2a2`.
- Authoritative local source: `CLAUDE.md`, section **Intraday passive benchmark rule**.
- SHA-256 of the current local `CLAUDE.md` bytes: `e46730ea21f97b896ee646556b15c7ccffd0694a902176ef8f9c4a870459635f`.

## Approved rule (verbatim)

For rollover-flat strategies, use identical instruments/dates. Rollover: venue-confirmed 17:00 America/New_York, with DST. Enter first grid open strictly after preceding rollover; exit last strictly before current rollover; cash otherwise. Constant fraction f=G/q uses strategy/unit-benchmark full-grid mean gross exposures. q≤0 or f>1 blocks readiness; never cap or rescale strategy. Preserve bid/ask turnover costs, alpha/drawdown gates and separate timing null. Freeze before economics; prohibit searches.

## Approval provenance and scope

The approval authority is the user's explicit instructions in this research conversation, before any Strategy-2 implementation or economics. After the general rule's no-leverage and rollover-boundary revision, the user instructed: "Apply the approved GENERAL intraday benchmark governance patch to CLAUDE.md exactly as reviewed." The user subsequently confirmed "The Tokyo design itself is approved" and authorized this persistence record under the gate named above. These quotations identify the approval sequence; no unavailable message identifier or exact approval timestamp is asserted.

The amendment applies generally to **all rollover-flat intraday strategies**, subject to its venue-confirmation and readiness conditions. It is not a Tokyo-specific exception, and must be frozen before economics for each applicable experiment. It does not revise closed research, reopen carry optimization, change any historical verdict, or authorize retrospective benchmark selection.

The user's subsequent `TOKYO_FIX_FREEZE_AND_READINESS` authorization permits a single local freeze commit and implementation/readiness, never economics or a push. The latest explicit research-venue-assumption instruction is recorded in [Tokyo venue provenance](../provenance/tokyo_v20_daily_research_venue.md): official v20 DAILY is the declared research convention, while actual demo-account mode remains unknown. This conditional research scope does not change the verbatim general rule or assert actual account readiness.

## Relationship to local authority

`CLAUDE.md` remains the authoritative local constitution under `AGENTS.md`; it remains deliberately Git-ignored. This version-controlled record preserves the approved amendment and binds the local constitution snapshot without changing that precedence or tracking the rest of `CLAUDE.md`. The SHA-256 covers exact local bytes, including line endings, not a hypothetical Git-normalized copy. A future hash mismatch requires checking the actual constitutional changes; material conflicts must not be silently reconciled.

The [research handoff](../RESEARCH_HANDOFF.md) records current project state. The [Tokyo preregistration draft](../prereg/2026-09-23-tokyo-fix-baseline-prereg-draft.md) applies this general rule without changing its approved scientific design. Commit review and any later implementation/readiness or economic execution require their respective explicit authorization. This record grants no network, sealed-data, trading, memory-update, commit or push permission.
