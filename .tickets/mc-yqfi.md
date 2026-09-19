---
id: mc-yqfi
status: open
deps: [mc-k48z, mc-t9o7, mc-ik8o, mc-hszv]
links: []
created: 2026-09-19T15:32:13Z
type: feature
priority: 2
assignee: cc-vps
parent: mc-cr09
tags: [p2, transactions, mutations, automation, safety]
---
# Add safe manual transaction create and delete

Provide a minimal, safe lifecycle for one manual transaction so humans and AI agents can record a cash transaction or correct a known record without using the web UI. Keep the first public lifecycle intentionally narrow: create and delete one transaction, with normalized readback and the shared mutation safety contracts. This ticket does not add idempotent upsert behavior, duplicate discovery, batch create/delete, tags, attachments, account CRUD, or budget/category workflows.

## Design

Add two explicit transaction commands:

- `transactions create --date YYYY-MM-DD --account-id ACCOUNT_ID --amount AMOUNT --merchant MERCHANT --category-id CATEGORY_ID [--notes NOTES]`
- `transactions delete --transaction-id TXN_ID --yes`

The create command uses the released public `create_transaction` capability for one manual transaction. Required IDs are opaque non-empty strings; the date uses the shared strict parser; the amount is a finite decimal value; and the merchant is non-empty after trimming. The first version does not expose tags, dedupe keys, an upsert mode, or an `--update-balance` convenience option. Callers can use the existing tag workflow separately after creation. Account/category existence may be reported by the upstream mutation, but local validation must complete before authentication or mutation authorization is checked.

Both operations are remote mutations. They require global per-invocation `--allow-mutations`, use the single-attempt mutation executor, and emit `mutation-outcome.v1` with stable operations `transactions.create` and `transactions.delete`. Dry-run is supported for both commands and performs local validation only: it never authenticates, reads remote records, or writes state. Mutation output is always JSON according to the existing output policy.

After create, the command must extract the returned transaction ID and perform bounded detail readback with no silent pending-to-posted redirect. Success requires that the requested transaction identity and core fields are observed; a missing ID, malformed response, timeout, disconnect, or verification mismatch is not reported as an ordinary success and must provide safe recovery guidance. A response may have created the transaction even when the ID or response is lost, so the caller must never blindly retry an ambiguous create.

Delete is single-target only and never accepts bulk IDs. It requires explicit destructive confirmation through the shared confirmation policy (`--yes` bypasses the prompt but never authorizes the mutation). The command reads the exact target before deletion, performs one delete attempt, and verifies absence when the released API permits a bounded detail check. A successful delete is never claimed solely because a transport request returned without an observable result.

This ticket intentionally does not claim idempotency. Upsert/dedupe requires a separate match-key, race, and false-positive design; duplicate detection is separately out of scope. Manual account creation, account balance changes, and transaction tags/attachments remain separate workflows.

## Acceptance Criteria

- [ ] `transactions create` and `transactions delete` are discoverable commands with documentation and examples.
- [ ] Create requires `--date`, `--account-id`, `--amount`, `--merchant`, and `--category-id`; delete requires `--transaction-id`; neither command accepts positional mutation targets.
- [ ] Local validation rejects empty IDs/merchant, invalid dates, non-finite amounts, and malformed option combinations before authentication lookup, mutation authorization, or any API call.
- [ ] The create command uses the released public upstream create capability through the adapter/service boundary and does not use private upstream methods or command-local GraphQL.
- [ ] The first version does not expose tags, dedupe/upsert, duplicate detection, batch operations, `--update-balance`, attachments, or account CRUD; these boundaries are documented rather than silently implied.
- [ ] Both commands are classified `remote_mutation`, require global `--allow-mutations`, and use the shared retry-safe mutation executor rather than the read executor.
- [ ] `--dry-run` performs local validation only, makes no authentication/client/network call, and reports the planned target and normalized input without claiming a remote effect.
- [ ] Create uses stable operation identity `transactions.create`, delete uses `transactions.delete`, and both emit the generic `mutation-outcome.v1` envelope without command-specific top-level fields.
- [ ] Create performs one remote attempt, extracts a returned transaction ID, and performs bounded exact-ID detail readback without silently redirecting a pending ID.
- [ ] Successful create output verifies the requested date, amount, account, category, merchant/description, and notes where the released detail response exposes them; missing or mismatched verification is never reported as success.
- [ ] A create timeout, disconnect, cancellation, missing identity after dispatch, malformed response, or verification failure is classified as ambiguous or otherwise non-success with actionable verification guidance; the command never retries blindly.
- [ ] Delete is single-target only, requires destructive confirmation through shared policy, and `--yes` never substitutes for `--allow-mutations`.
- [ ] Delete reads the exact target before mutation, performs one attempt, and verifies absence where the released read capability supports it; a lost or contradictory result is ambiguous/non-success rather than a claimed deletion.
- [ ] Delete output and diagnostics never include credentials, raw request bodies, or arbitrary upstream exception text.
- [ ] No command claims that create is idempotent or that delete is recoverable; documentation explains ambiguity and safe verification before retry.
- [ ] Unit and CLI tests cover validation-before-call behavior, dry-run isolation, authorization, confirmation, exact API argument mapping, successful readback, malformed/missing IDs, definite failures, transport ambiguity, cancellation, verification mismatch, output contracts, and command discovery.
- [ ] Existing normalized transaction schemas, mutation outcome tests, help-contract tests, and live-test policy remain aligned; no live financial API call is required by the default suite.
- [ ] User-facing documentation and repository verification are complete.

