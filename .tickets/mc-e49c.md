---
id: mc-e49c
status: open
deps: [mc-k48z, mc-ik8o, mc-hszv]
links: []
created: 2026-09-11T01:36:40Z
type: feature
priority: 2
assignee: cc-vps
parent: mc-cr09
tags: [p2, transactions, review, mutations, safety]
---
# Add explicit transaction review-state mutations

Allow a user or automated workflow to deliberately mark a transaction reviewed or return it to the review queue. Review state is operationally important for transaction triage, but the upstream `reviewed` and `needsReview` inputs have distinct semantics. The CLI must expose intent-oriented actions and verify observed fields rather than overloading an ambiguous boolean.

## Design

Expose two explicit operations for one transaction:

- mark reviewed: send `reviewed=True` and omit `needs_review`;
- return to review queue: send `needs_review=True` and omit `reviewed`.

Do not use `reviewed=False` or `needs_review=False` for these intents without new verified upstream evidence. Before writing, read transaction detail to validate identity and determine whether the requested state is already observed. After writing, read detail again and report the actual `needs_review`, `reviewed_at`, and `reviewed_by_user` fields. Do not invent an observed `reviewed` boolean when the upstream response does not provide one.

The mutation request must contain only the transaction ID and the one intended review-state field. The verified upstream 1.5.2 helper currently serializes unrelated `category: null` and `name: null`. Resolve that gap in this order: prefer an upstream client release that omits unrelated fields; otherwise accept the helper only with controlled contract evidence that the nulls cannot alter data; only as a last resort maintain a narrow local GraphQL adapter and its query-shape compatibility tests. Do not transparently monkeypatch or intercept the upstream `gql_call`, which would couple the CLI to private operation and variable structure without making that maintenance burden explicit. Verification also checks that category and merchant identity were not changed.

Use centralized mutation authorization, retry-safe remote execution, and `mutation-outcome.v1`. Never route the write through the read executor that automatically retries timeout/disconnect failures. No-op, definitive failure, ambiguity, and verification mismatch remain distinct.

## Key Decisions

- **Intent-oriented operations.** Users never provide a pair of review booleans.
- **Exact input mapping.** Reviewed sends only `reviewed=True`; return-to-queue sends only `needsReview=True`.
- **No inferred reviewed boolean.** Stable output reports the actual observed review fields.
- **Read before and after write.** Pre-read supports no-op handling; post-read verifies outcome and unrelated-field integrity.
- **No unrelated nullable inputs.** Prefer an upstream fix or verified safe public helper; a local maintained GraphQL adapter is an explicit last resort, not hidden interception.

## Acceptance Criteria

- [ ] Users can explicitly mark one transaction reviewed and explicitly return one transaction to the review queue through distinct intent-oriented command paths/options.
- [ ] Mark-reviewed maps to `reviewed=True` while omitting `needsReview`; return-to-queue maps to `needsReview=True` while omitting `reviewed`.
- [ ] `reviewed=False`, `needsReview=False`, and contradictory review-state combinations are not accepted by this surface.
- [ ] The serialized mutation input contains only transaction identity and the one intended review-state field; full-variable tests fail if unrelated category, merchant, or other mutable fields are sent.
- [ ] Implementation records which ordered resolution was used: a compatible upstream fix, controlled evidence that the public helper's nulls are harmless, or a last-resort local narrow GraphQL adapter with explicit query-shape compatibility tests and documented maintenance ownership.
- [ ] A pre-read verifies transaction identity and returns a deterministic no-op outcome when the requested state is already observed.
- [ ] Every write is blocked by default and requires shared per-invocation mutation authorization before authentication, client construction, prompting, or network access.
- [ ] The review write uses the retry-safe mutation executor and is never automatically repeated after timeout, disconnect, or another potentially dispatched failure.
- [ ] Successful output uses `mutation-outcome.v1`, identifies requested intent, and reports observed `needs_review`, `reviewed_at`, and `reviewed_by_user` without inventing a reviewed boolean.
- [ ] Post-write detail verification confirms the intended review state and that category and merchant identity were unchanged.
- [ ] If verification cannot complete, the outcome is ambiguous with a tokenized safe transaction-detail verification command.
- [ ] No-op, not-found, permission, server rejection, timeout, disconnect, ambiguity, verification mismatch, and unrelated-field mismatch paths are deterministic and sanitized.
- [ ] Read-only pending/posted and needs-review filters remain semantically aligned and separate from review mutation behavior.
- [ ] Unit/CLI tests cover authorization, both exact mappings, pre/post reads, no-op behavior, invalid input, output modes, no automatic retries, and all negative paths.
- [ ] Any controlled live semantic probe is separately opt-in, uses explicit mutation authorization and a restorable test record, and is not part of the default suite.
- [ ] User-facing workflow/recovery documentation is complete and repository verification passes.
