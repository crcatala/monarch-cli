---
id: mc-r75q
status: open
deps: [mc-h3cl, mc-7xfl]
links: []
created: 2026-09-11T01:36:40Z
type: feature
priority: 2
assignee: cc-vps
parent: mc-cr09
tags: [p2, accounts, liabilities, debt, read-only, normalization]
---
# Expose liability and debt-service account metadata

Provide the account metadata needed to understand liabilities and debt obligations from the CLI. A balance alone is insufficient for credit and loan accounts: users need to distinguish liabilities from assets and inspect available limits, rates, payments, and debt-paydown participation without depending on raw upstream field names.

This is a stable read-only representation. It does not calculate payoff schedules, provide financial advice, or mutate liability settings.

## Design

Normalize liability metadata already present in the released `get_accounts` response. Use upstream `isAsset` as the direct asset/liability signal and reuse the stable account type/subtype names established by `mc-7xfl`; do not infer liability solely from localized display labels.

Preserve distinct upstream concepts rather than selecting or merging them:

- `credit_limit` from `limit`;
- `provider_credit_limit` from `dataProviderCreditLimit`;
- `apr` from `apr`;
- `interest_rate` from `interestRate`;
- `minimum_payment` from `minimumPayment`;
- `planned_payment` from `plannedPayment`;
- `excluded_from_debt_paydown` from `excludeFromDebtPaydown`.

All fields are nullable and remain distinguishable from zero, negative, or inapplicable values. Numeric rate values are passed through without scaling until an authoritative unit is established. Documentation labels rate units as upstream units unless a controlled live observation provides stronger evidence. Likewise, documentation must not claim that planned payments, provider limits, or minimum payments are current snapshots versus settings unless verified.

Because the released account-list response already contains these fields, add them to normalized machine-readable account output rather than inventing a new liability endpoint. Keep default human tables concise by showing only the direct asset/liability classification and a small useful subset; JSON/CSV retain the complete stable fields. Raw output remains untouched.

## Key Decisions

- **Use the direct upstream classification.** `isAsset` determines asset versus liability; display names do not.
- **Never merge provider and user-facing values.** Limits and rates remain separate fields.
- **Pass numeric values through.** No rate scaling, currency conversion, payoff math, or invented precision.
- **Use the existing account response.** No new endpoint or account-detail command is required.
- **Nullable means unavailable/inapplicable.** Missing values never become fabricated zeroes.

## Acceptance Criteria

- [ ] Normalized account output includes a documented direct asset/liability indicator sourced from `isAsset` and stable type/subtype identifiers coordinated with `mc-7xfl`.
- [ ] Normalized machine-readable output exposes distinct nullable `credit_limit`, `provider_credit_limit`, `apr`, `interest_rate`, `minimum_payment`, `planned_payment`, and `excluded_from_debt_paydown` fields.
- [ ] No precedence, fallback, or merging occurs between the two limit fields or between APR and interest rate.
- [ ] Missing, null, zero, negative, and inapplicable values remain distinguishable; unavailable financial values are never fabricated.
- [ ] Rate values preserve upstream numeric units without scaling unless authoritative evidence and fixtures establish a documented conversion.
- [ ] Currency-like values preserve upstream precision in JSON; any human formatting is documented and does not alter machine-readable values.
- [ ] Documentation accurately distinguishes confirmed fields from unknown snapshot/setting semantics and makes no unsupported financial claim.
- [ ] Manual, hidden, deactivated, credit, loan, ordinary asset, and partially populated accounts normalize without crashes or misleading liability defaults.
- [ ] JSON and CSV retain all stable liability fields; table/plain/compact remain concise according to an explicit column/display decision; quiet remains ID-only.
- [ ] Raw account output remains unmodified and no new liability endpoint, polling workflow, or remote mutation is introduced.
- [ ] Unit and CLI tests cover representative credit, loan, manual liability, non-liability, null/partial, zero/negative, hidden, and deactivated payloads across output formats.
- [ ] A controlled live observation, if used to clarify units, is separately opt-in, read-only, redacted, and records no household-specific values in fixtures or logs.
- [ ] The required upstream-client compatibility floor is declared and covered by client-interface and clean-install verification.
- [ ] Output-contract and user documentation are updated and repository verification passes.
