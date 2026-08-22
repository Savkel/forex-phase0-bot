# Family-1 universe final results

## External adjudication

Family 1 is closed. Retain the immutable U14 Stage-A control for next research. G10 and U8
remain valid historical DEVELOPMENT results but are not selected. This is not prospective OOS,
deployment, paper-trading, or live-trading evidence.

Liquidity restriction reduced spread cost and routed turnover (U8 also reduced currency
turnover; G10 currency turnover was slightly higher), but did not improve the primary economic
objective. Relative to U14, G10 and U8 had lower CAGR, RAP, and positive-return Calmar. U8 also
had deeper MaxDD, a negative Bonferroni 97.5% IC lower bound, and weaker LOCO/stress robustness.
All configurations, diagnostics, and adverse results remain preserved unchanged.

| Candidate | D360 CAGR / RAP / Calmar / MaxDD | D365 CAGR / RAP / Calmar / MaxDD | Spread cost D360/D365 | Currency / routed turnover D360 |
|---|---|---|---|---:|
| U14 control | 2.3394% / 0.06991 / 0.2813 / -8.3167% | 2.3138% / 0.06919 / 0.2776 / -8.3340% | 2.6479% / 2.6468% | 62.5 / 63.4107 |
| G10 | 1.5977% / 0.04867 / 0.2019 / -7.9125% | 1.5775% / 0.04811 / 0.1990 / -7.9289% | 1.2155% / 1.2152% | 63.3333 / 57.7517 |
| U8 | 0.8141% / 0.02367 / 0.0754 / -10.8029% | 0.7834% / 0.02295 / 0.0724 / -10.8268% | 0.4726% / 0.4724% | 56.0 / 44.7696 |

G10 mean IC was `0.057788071800810664` with Bonferroni one-sided 97.5% lower bound
`0.0020440069484655467`. U8 mean IC was `0.042462845010615716` with lower bound
`-0.016985138004246284`. Omitting JPY was the sole negative-return LOCO case for both new
candidates. Thresholds and flags remain diagnostic; this disposition is the external review.

## Immutable evidence

- Execution: `prereg/2026-08-21-tms-carry-unlevered-family-1-execution.json`, SHA-256
  `6025492cb2b8ba79af02ab614e128a4ba850953b337f91b89ff6f18f0c4c0a0e`.
- Result: `reports/forex/family1/family1-universe-result.json`, SHA-256
  `ec0d85614928d6a1357c575ddfe0421d1499b24cbb005b985790d092934bbb1f`.
- Completion: `reports/forex/family1/family1-universe-completion.json`, SHA-256
  `558003ddfee8a9e58e5b61115bab70d242b4991fc685bf5078ed23866a0d2867`.
- Frozen preregistration SHA-256:
  `e7579ac48f9051e6dc8b133b44522a2f3cdb5c01d52efb58e72fef7fbbe7614e`.
- U14 parity SHA-256:
  `526b0e6e12b978c2d1fcad0b176e92765b09c77d9a4cc6cb56de6921dab31707`.

## Next gate

`PERFORMANCE_OPTIMIZATION_BEFORE_FAMILY2`
