# Stage-A direct-TMS carry final results

## Disposition

`STAGE_A_SURVIVES_KILL_TEST`

Stage A is CLOSED. The valid frozen execution was operational Attempt 3 under freeze manifest
`586c2229de5d959bae21b780192f0ecdaa60b4bf34a00bc2e432b575aaa5f4e5`. Its immutable result
artifact has SHA-256 `39838d559e36645c7910b65f5190d7b292540ed780ebe1ce3a697b8dbec9e6b8`.
The 3,600-second Codex supervisory timeout did not terminate execution: structural adjudication
`ATTEMPT3_VALID_LATE_COMPLETION` established one authorized execution and a complete, auditable,
hash-linked result. Attempt 2 remains immutable `VOID_RETAINED`; its provisional outcome is not
scientific evidence.

## Frozen gates

| Gate | D360 | D365 | Verdict |
|---|---|---|---|
| G1 | RAP 0.0699083432; benchmark -0.0635755237; excess +0.1334838669 | RAP 0.0691903010; benchmark -0.0628203305; excess +0.1320106315 | PASS both |
| G3 | strategy MDD -8.316682%; benchmark -9.833850% | strategy MDD -8.334000%; benchmark -9.832407% | PASS both |
| G4 | stressed total return +2.482391% | stressed total return +2.433974% | PASS both |
| G5 | 14/14 LOCO; worst JPY, excess +0.1092092679 | 14/14 LOCO; worst JPY, excess +0.1080677603 | PASS both |

G2 PASS: mean cross-sectional Spearman IC `0.0541051305`; one-sided 95% bootstrap lower bound
`0.0120795128 > 0`; stationary-bootstrap block length `1`, `10,000` replicates, seed `20260808`.

Non-gating spread-times-three sensitivity: D360 `+2.528988%`; D365 `+2.443305%`.

## Post-hoc descriptive — non-gating

These values were computed read-only from the exact frozen baseline strategy accounting paths,
without benchmarks, LOCO, bootstrap, or stress, and did not modify files. They are not gates.
Window: 2023-04-03 through 2026-08-03 (`3.334702` years), 157 accounting periods.

| Scenario | Total return | CAGR | Final equity | Spread cost | Financing |
|---|---:|---:|---:|---:|---:|
| D360 | +8.016506% | +2.339411% | 1.0801650638 | 0.0264791950 | +0.0621592826 |
| D365 | +7.926257% | +2.313762% | 1.0792625720 | 0.0264683925 | +0.0612822888 |

## Scientific interpretation

Carry demonstrated robust historical DEVELOPMENT evidence across both accounting denominators,
the static benchmark, predictive IC, drawdown, adverse stress, and every LOCO case. This was not
prospective OOS and grants no deployment or trading permission. Absolute baseline performance is
modest at approximately 2.3% CAGR despite the strong robustness evidence. No further tuning belongs
inside closed Stage A. Any improvement research must be a separate preregistered development phase,
initially unlevered and preserving the current baseline risk scale. Prospective Stage B remains the
proper untouched validation path.
