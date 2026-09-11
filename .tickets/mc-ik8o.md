---
id: mc-ik8o
status: open
deps: [mc-t9o7]
links: []
created: 2026-09-11T11:58:14Z
type: feature
priority: 0
assignee: cc-vps
parent: mc-cr09
tags: [p0, safety, mutations, contracts, automation]
---
# Define and adopt a shared mutation outcome contract

Give human and automated callers one stable machine-readable contract for the result of single-step and multi-step remote mutations. Retry safety and ambiguous transport classification are established by `mc-t9o7`; this ticket normalizes success, definitive failure, ambiguity, and partial completion so domain commands do not invent incompatible response shapes.

## Design

Adopt the same versioned envelope for every current single and batch remote mutation after remote execution is attempted. Pre-execution authorization and input-validation failures continue to use the structured error contract.

Top-level statuses are:

- `succeeded`: every requested effect is known to have succeeded.
- `failed`: no requested effect succeeded and all failures are known to be definitive.
- `ambiguous`: no effect is known to have succeeded, but at least one request may have changed remote state.
- `partial`: item outcomes contain a mixture of succeeded, failed, or ambiguous states.

Per-item statuses are `succeeded`, `failed`, or `ambiguous`. Use the following normative v1 envelope for both single and batch mutations:

```json
{
  "schema_version": "mutation-outcome.v1",
  "operation": "transactions.update",
  "status": "succeeded",
  "summary": {
    "total": 1,
    "succeeded": 1,
    "failed": 0,
    "ambiguous": 0
  },
  "items": [
    {
      "entity": "transaction",
      "id": "txn_123",
      "status": "succeeded",
      "result": {},
      "error": null
    }
  ],
  "verification": null
}
```

Contract rules:

- `schema_version`, `operation`, `status`, `summary`, `items`, and `verification` are always present.
- `operation` is a stable namespaced identifier supplied by the shared operation descriptor, not inferred from an upstream method or GraphQL operation name.
- Atomic single-effect operations use an `items` array containing exactly one item. Batch items preserve normalized input order.
- A multi-stage workflow uses one ordered item per remote effect that was actually attempted or became observable. Unattempted later effects are omitted. Each effect item uses a stable effect-specific `entity` and the best available remote identity; this lets the existing aggregation rules express partial completion without adding command-specific envelope fields or new statuses.
- Every item always contains `entity`, `id`, `status`, `result`, and `error`.
- `result` is a normalized JSON object on success and `null` otherwise. `error` is `null` on success and otherwise contains stable `code`, `message`, and object-valued `details`; `result` and `error` must never both be non-null.
- `summary.total` equals `len(items)`, and each status count exactly matches `items`.
- `verification` is `null` when no follow-up is needed. If any item is ambiguous it contains `required: true`, an actionable `message`, and a tokenized `command` array when the CLI can provide a safe verification command.
- Additional fields are additive. Removing/changing required fields, status values, or their semantics requires a new schema version.

Migrate current account refresh, transaction update, and transaction batch update outputs to this contract. Errors must be structured and sanitized rather than copied from arbitrary exception strings. Do not claim rollback or transactionality that the upstream API does not provide.

All-succeeded outcomes exit `0`. Definitive failed outcomes use the normal operation/API nonzero exit. Partial or ambiguous outcomes exit `4`. Stdout contains only the requested mutation outcome format; diagnostics and incidental progress remain off stdout.

`mc-cpzi` will publish the formal machine-readable schema for this contract rather than redesigning it.

## Key Decisions

- **One envelope for atomic, batch, and multi-stage operations.** Atomic operations use one item, batches use one item per input, and multi-stage workflows use one ordered item per attempted/observable remote effect.
- **Stable nullable fields over shape variation.** Required keys do not appear and disappear based on outcome.
- **Ambiguity requires recovery guidance.** Callers must be told how to inspect potentially changed state.
- **Nonzero partial outcomes.** A workflow with any failed or ambiguous item is not successful automation.
- **Schema publication remains separate.** This ticket defines and adopts runtime behavior; `mc-cpzi` publishes formal schemas and compatibility documentation.

## Acceptance Criteria

- [ ] Account refresh, transaction update, and transaction batch update return the normative `mutation-outcome.v1` envelope after remote execution is attempted.
- [ ] Pre-execution authorization and validation failures continue to use the structured error contract and are not misrepresented as mutation outcomes.
- [ ] Every outcome includes all required top-level and item fields with the documented status values and nullability.
- [ ] Atomic single-effect operations use one item; batch results preserve normalized input order; multi-stage workflows preserve remote-effect order and omit effects that were never attempted or observed.
- [ ] Multi-stage items use documented stable effect entities and available remote identities so mixed effect outcomes aggregate to `partial` without a command-specific top-level envelope extension.
- [ ] Contract tests enforce mutually exclusive non-null `result`/`error` values, summary-count consistency, required fields, atomic/batch/multi-stage behavior, and stable ordering.
- [ ] Top-level aggregation is deterministic: all succeeded → `succeeded`; no success and only definitive failures → `failed`; no success with any ambiguity → `ambiguous`; mixed item outcomes → `partial`.
- [ ] Every ambiguous outcome includes the required verification object and a tokenized command when a safe verification command is available; outcomes needing no follow-up use `null`.
- [ ] Error objects contain stable `code`, `message`, and object-valued `details` without credentials, raw request bodies, or arbitrary upstream exception text.
- [ ] All-succeeded outcomes exit `0`; definitive failures use the documented normal nonzero error exit; partial and ambiguous outcomes exit `4`.
- [ ] JSON, compact, and human-readable rendering preserve the same semantics, while stdout remains free of progress and diagnostic text.
- [ ] Documentation identifies `mutation-outcome.v1`, defines additive versus breaking runtime changes, and explains recovery without claiming transactionality or rollback.
- [ ] Repository verification passes.
