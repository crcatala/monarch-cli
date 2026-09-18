---
id: mc-h3cl
status: in_progress
deps: [mc-43s0]
links: [mc-cd12, mc-c165, mc-kzp9]
created: 2026-09-11T01:21:50Z
type: feature
priority: 1
assignee: cc-vps
parent: mc-cr09
tags: [p1, architecture, transformers, api-contract, reliability]
---
# Harden normalization at upstream API boundaries

Make read-only and future mutation commands resilient to incomplete, nullable, or evolving API response shapes. External financial APIs may return null nested objects, omit optional collections, or add fields over time. Commands should not crash merely because an optional merchant, category, account, institution, or similar relationship is absent. A dependable normalization boundary enables a stable CLI contract for humans, scripts, and agents while keeping upstream response quirks out of presentation code.

## Design

Keep normalization in `monarch_cli/transformers`; adapters isolate the upstream client, services orchestrate calls, and command handlers must not grow ad hoc defensive traversal. Introduce a small reusable null-safe nested-access pattern rather than scattering `raw.get("field", {}).get(...)`, which still crashes when a present field is `null`.

This ticket is intentionally limited to the existing account, transaction, and cashflow transformer contracts. Similar command-local budget, category, and authentication normalization should be handled separately rather than silently broadening this PR. The transformer and schema-contract test suites described by the now-closed `mc-c165` and `mc-cd12` already exist; this ticket owns the remaining upstream-boundary cases they did not cover.

Preserve the current stable key set. Unavailable identifiers, relationships, dates, names, balances, and amounts normalize to `null`, never fabricated numeric values. Existing boolean fields remain booleans for v1 compatibility, with explicit documented defaults for absent or null source values. Fix the current transaction pending mapping to use the actual upstream `pending` field; compatibility aliases may be accepted only if precedence is deterministic and tested. Raw mode bypasses normalization entirely and preserves the upstream data structure, including null containers.

Do not add a schema library or other runtime dependency for this work.

## Key Decisions

- **Transformers are the normalization boundary.** Commands and services consume normalized domain values rather than interpreting upstream nesting themselves.
- **Financial values are never invented.** Missing balances and transaction amounts are `null`, not zero or sentinel values. Cashflow period aggregates retain their existing documented zero-for-no-data convention.
- **Boolean compatibility is explicit.** `is_active`, `is_manual`, and `is_pending` remain non-null booleans in the v1 contract; their missing/null defaults are documented and tested.
- **Real upstream names are authoritative.** Transaction pending state comes from `pending`, not the currently incorrect `isPending` fixture convention.
- **Malformed roots fail deliberately.** A non-object top-level payload produces a stable typed contract/API error; nullable or absent collection containers normalize to empty collections.

## Acceptance Criteria

- [ ] Account, transaction, and cashflow normalization handles present-but-null or missing nested relationships, summary blocks, and list containers without raising incidental exceptions.
- [ ] Absent or null account and transaction collection containers normalize to empty lists; non-object top-level payloads produce a stable typed error rather than `AttributeError` or `TypeError`.
- [ ] Every existing normalized schema key remains present, with unavailable non-boolean account/transaction values represented as `null`; cashflow's existing zero-for-no-data aggregate convention is documented as the only in-scope numeric-default exception.
- [ ] `is_active`, `is_manual`, and `is_pending` are always booleans, and their behavior for absent and null upstream values is documented and enforced by contract tests.
- [ ] Transaction pending normalization reads the upstream `pending` field; representative fixtures use the real upstream shape and tests prevent the current always-false regression.
- [ ] Description fallback remains deterministic: non-empty `merchant.name`, then `plaidName`, then `null`.
- [ ] Unknown additive upstream fields are ignored by normalized v1 output unless deliberately added and documented.
- [ ] Raw output bypasses normalization and preserves upstream null, empty, and unknown fields without repair or filtering.
- [ ] Null-safe traversal is reusable within `transformers` and is not duplicated in account, transaction, or cashflow command handlers or services.
- [ ] Focused tests cover complete, missing, present-but-null, empty, malformed-root, manual-account, merchant-less transaction, and null/partial cashflow payloads.
- [ ] Existing normalized field names and documented semantics remain backward compatible except for the explicit correction of the pending-state source mapping.
- [ ] No new runtime dependency is introduced and repository verification passes.


## Notes

**2026-09-18T02:05:24Z**

Started implementation on branch feat/mc-h3cl-harden-normalization. Added reusable null-safe traversal helper in transformers/nesting.py (nested_get, list_or_empty, mapping_or_empty, bool_or_default, number_or_zero, require_object -> typed APIError for non-object roots). Hardened account/transaction/cashflow transformers; corrected is_pending to read upstream pending with lower-precedence isPending alias; deterministic description fallback; documented boolean defaults and cashflow zero-for-no-data exception. Expanded transformer/schema/command contract tests (raw passthrough, malformed roots, null/coll containers). make verify passes.

**2026-09-18T02:06:26Z**

Implementation complete on feat/mc-h3cl-harden-normalization. PR #59 opened: https://github.com/crcatala/monarch-cli/pull/59. make verify passed (format, lint, typecheck, 795 tests). No new runtime dependency; raw passthrough and stable v1 key set preserved.
