# Tokyo research venue: explicit OANDA v20 DAILY convention

- Recorded: 2026-09-24, before Strategy-2 implementation or economics.
- Purpose: bind a research venue assumption; not certify an actual demo/live account.
- User-provided non-secret facts: the v20 practice account is unused and has never
  held positions; the price endpoint is `api-fxpractice.oanda.com`; the original
  regional evidence supplied is `help.oanda.com/eu/en/`.
- Empty transaction history supplies no financing-mode evidence. No credential,
  account identifier, private API response or transaction history was accessed.

## Official documentation reviewed

1. https://developer.oanda.com/rest-live-v20/development-guide/
   identifies the practice host as the fxTrade Practice environment. The host alone
   does not identify its user's legal entity or financing mode.
2. https://developer.oanda.com/rest-live-v20/account-df/#AccountFinancingMode
   defines DAILY as financing charged/credited daily at 17:00 New York. It also
   defines NO_FINANCING and SECOND_BY_SECOND; neither is inferred for this account.
3. https://developer.oanda.com/rest-live-v20/account-ep/ and
   https://developer.oanda.com/rest-live-v20/primitives-df/#InstrumentFinancing
   do not document a direct account-summary/instrument financing-mode field.
   Instrument financing contains rates and weekday multipliers; its clock is set
   in the client's DivisionTradingGroup. No documented public retrieval route
   for that setting was established. Portal mode availability is unverified.
4. https://developer.oanda.com/rest-live-v20/transaction-df/#PositionFinancing
   exposes accountFinancingMode on financing transactions, but this unused
   account supplies no such evidence. No trade may be created to obtain it.
5. https://www.oanda.com/uk-en/trading/standard-account/differences/
   explicitly relates the end of the trading day to 17:00 ET and New York DST.
   This corroborates the clock, not the user's account/entity applicability.
6. https://help.oanda.com/eu/en/faqs/oanda-division.htm identifies the EU help
   division as OANDA TMS. It does not map this user's v20 practice account to UK
   financing terms. No such mapping is claimed or required for the model below.

## Pre-economics authority and bounded interpretation

The user's latest instruction explicitly asks whether the GENERAL benchmark can
be bound to the official v20 DAILY rollover convention as a frozen research venue
assumption and authorizes continuation if scientifically/governance-valid.
The adopted assessment is YES for conditional historical DEVELOPMENT research:
the research venue is explicitly **OANDA v20 DAILY financing at 17:00
America/New_York, with historical DST**. Official documentation confirms this
venue convention. The actual unused account's mode remains UNKNOWN.

The distinction is material and must accompany any eventual result. The model
uses existing practice bid/ask candle proxies; it does not establish executable
account-specific performance or historical deployment feasibility. No universal
claim about OANDA account modes or their history is made. Zero financing follows
only from zero exposure across every rollover under this declared DAILY model;
flatness alone would not eliminate SECOND_BY_SECOND financing.

This explicit user-authorized pre-economics scope clarification replaces the
draft's demand for actual account-mode certification for this research run. It
does not amend the general benchmark's clock, holding windows, costs, matching,
no-leverage, alpha, drawdown or separate timing-null protections. The general rule
remains verbatim in CLAUDE.md. Any future execution claim still requires actual
venue/account verification, outside this research gate.

All original seal, calendar, timestamp/quote support, missingness, accounting and
readiness checks remain mandatory. No missing quotes, failed checks or adverse
economics may be rescued using this assumption. No historical financing series,
imputed rate, account activity, private-data access or economics is authorized.
