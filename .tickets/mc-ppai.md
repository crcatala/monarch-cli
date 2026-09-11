---
id: mc-ppai
status: open
deps: [mc-h3cl]
links: []
created: 2026-09-11T01:21:50Z
type: feature
priority: 1
assignee: cc-vps
parent: mc-cr09
tags: [p1, investments, holdings, read-only, normalization]
---
# Add normalized investment holdings views

Give users a useful portfolio view across investment accounts rather than requiring them to understand nested API payloads or query each account manually. This enables portfolio inventory, account-level inspection, and allocation analysis while remaining read-only.

## Design

Add `investments holdings` through an investment-focused service for normalized holdings across brokerage or similarly eligible accounts. Released `monarchmoneycommunity` 1.5.2 has no all-account holdings method: perform one account-discovery request, select eligible accounts, then issue per-account holdings reads with configurable bounded concurrency and per-call timeout/retry behavior in the service layer. Do not depend on the unreleased upstream `get_all_holdings` helper or use `typedmonarchmoney`, whose missing-number sentinel values can corrupt financial totals.

Annotate every non-aggregated row with the source account ID/name from the request context because the holdings payload response does not preserve it. Missing quantity, basis, price, or value remains `null`; never substitute sentinels or recompute authoritative value as quantity times price.

Optional aggregation groups only by non-null upstream security ID. Rows without a reliable security ID remain separate and retain source context rather than being merged by ticker or name. Aggregate authoritative total values only when the payload's household-display-currency assumption is applicable, and report distinct contributing account IDs/count. Keep ticker, name, and raw node ID as descriptive fields, not fallback cross-account identity.

Default account discovery excludes hidden accounts; explicit account IDs are validated and retain deliberate caller selection semantics. Document separately that the released upstream method always includes hidden holdings within a selected account and offers no public switch. For multi-account raw mode, return a deterministic CLI envelope keyed by account ID whose payload values are untouched per-account upstream responses; do not call the composed envelope itself an upstream response.

## Key Decisions

- **Released fallback is bounded per-account fanout.** Bulk retrieval is not available in a released supported dependency.
- **Security ID is the sole cross-account aggregation key.** Missing identifiers never cause speculative ticker/name merging.
- **Missing financial values remain null.** The typed upstream wrapper and sentinel defaults are not used.
- **Raw multi-call output is a CLI envelope.** Each enclosed upstream payload remains unmodified.

## Acceptance Criteria

- [ ] Users can list normalized holdings across accounts determined eligible from one account-discovery response.
- [ ] Eligibility rules use released account metadata, are documented with representative brokerage/manual-investment cases, and avoid calls for accounts known to have zero holdings.
- [ ] Users can restrict retrieval to one or more non-empty opaque account IDs; unknown-ID and ineligible-account behavior is explicit and tested.
- [ ] Hidden accounts are excluded from automatic discovery by default and included only by explicit option/selection; documentation states that hidden holdings inside a selected account cannot be excluded through the released client.
- [ ] Non-aggregated rows retain source account ID/name, upstream security ID, raw holding/node ID, descriptive security fields, quantity, basis, price, total value, and last-synced time where available.
- [ ] Missing ticker, security metadata, quantity, basis, price, value, or timestamps remain null and never crash the command, become sentinel values, or trigger invented calculations.
- [ ] Optional aggregation groups only rows with the same non-null security ID, leaves unkeyed rows separate, sums only authoritative compatible values, and reports contributing account IDs/count.
- [ ] Household display-currency limitations and the absence of per-holding currency metadata are documented; the CLI does not claim currency conversion.
- [ ] Retrieval performs account discovery once and uses a tested configurable concurrency bound, per-call timeout/retry policy, deterministic output ordering, and documented partial/fail-fast behavior.
- [ ] The implementation uses the base upstream client through adapter/service/transformer boundaries; command handlers perform no direct client calls and `typedmonarchmoney` is not used.
- [ ] JSON, table/plain, empty-result, aggregation, per-account failure, and raw-envelope behavior are tested; raw envelope values preserve each upstream response unchanged.
- [ ] The released dependency floor is verified and no unreleased source revision is required.
- [ ] User-facing documentation and repository verification are complete.


## Notes

**2026-09-11T01:47:49Z**

P3 planning originally requested evaluation of a bulk holdings operation.

**2026-09-11T12:20:08Z**

Research decision: no released version through `monarchmoneycommunity` 1.5.2 provides an all-account holdings method. A bounded per-account service fanout is therefore the supported implementation. Do not depend on the unreleased `get_all_holdings` development method; reevaluate only after a compatible release exists.
