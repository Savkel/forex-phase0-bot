# Family-4 rebalance-cadence final results

## Execution provenance

The user manually ran the frozen one-shot command:

`python -B run_family4_cadence.py execute-candidates`

Codex did not run M2/M4 economics. The single execution completed as
`FAMILY4_ECONOMICS_COMPLETE`; `consumption_count=1`, all integrity links match, and no network
access occurred.

## External adjudication

Family 4 is closed. Retain `M1_CONTROL` (weekly cadence) as the historical DEVELOPMENT
configuration. M2 and M4 remain valid DEVELOPMENT results but are not selected. All results remain
preserved unchanged. This is external adjudication, not an automatic gate decision.

Slower cadence materially reduced trade count, and M4 reduced spread cost and routed turnover,
but both reduced CAGR, RAP, positive-return Calmar, and stress performance while worsening MaxDD.
Financing stayed broadly stable while spot P&L deteriorated: lost signal/membership refresh value
outweighed execution-cost savings. B2 remained negative and worsened under M2/M4. All configurations
retained positive benchmark-relative RAP in 14/14 LOCO cases under D360 and D365.

| Configuration | D360 CAGR / RAP / Calmar / MaxDD | D365 CAGR / RAP / Calmar / MaxDD | Trades | Routed turnover D360 | Spread cost D360 | Financing / spot D360 | Adverse return D360/D365 | B2 return D360/D365 |
|---|---|---|---:|---:|---:|---:|---:|---:|
| `M1_CONTROL` retained | 3.1238% / 0.09498 / 0.5118 / -6.1033% | 3.0971% / 0.09421 / 0.5059 / -6.1218% | 1,284 | 47.9579 | 2.2729% | 6.4947% / 6.5802% | 5.7483% / 5.6924% | -1.4919% / -1.5157% |
| `M2` | 3.0255% / 0.09200 / 0.4691 / -6.4494% | 2.9989% / 0.09124 / 0.4636 / -6.4680% | 713 | 47.1968 | 2.3026% | 6.4722% / 6.2807% | 5.3816% / 5.3260% | -1.8376% / -1.8614% |
| `M4` | 2.8994% / 0.08824 / 0.4503 / -6.4387% | 2.8727% / 0.08747 / 0.4448 / -6.4582% | 409 | 44.4331 | 2.1501% | 6.4794% / 5.6708% | 5.1305% / 5.0742% | -1.8170% / -1.8417% |

This is exposed historical DEVELOPMENT evidence, not prospective OOS or trading permission.
`M1_CONTROL` does not replace the original frozen Stage-A/H0 strategy on its isolated prospective
Stage-B path.

## Immutable evidence

- Execution SHA-256: `eb2b97d96924e694e868bf087506070a5953860c1766bc2880f179366300927e`.
- Result SHA-256: `b92f6d12d7cd7274bf3e60dca44fc402bd7bfe6d9fa6ee8fcc78f1cb31bdb6a8`.
- Completion SHA-256: `85469fed3c81b74c6783da40302e2548ff53f7c66794baae345ace68eaaa9547`.
- Readiness SHA-256: `d292d6355ad27b23b515b72d8704b03b337582b5b2adf8a40b66e6bca5700e25`.
- M1 parity SHA-256: `a7528e78462dd48ea3f6124c161d5882c521b501e6a7d3a43628f22963c5ebfa`.

## Next gate

`FAMILY5_PORTFOLIO_BREADTH_DESIGN`
