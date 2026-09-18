# Mutation outcomes (`mutation-outcome.v1`)

Every remote mutation in Monarch CLI — account refresh, transaction update,
and each item of a transaction batch update — returns one stable,
machine-readable result contract: **`mutation-outcome.v1`**. Human and
automated callers get one envelope for single-step, batch, and multi-stage
remote mutations; domain commands never invent incompatible response shapes.

This document defines the runtime behavior adopted by the CLI. The formal
machine-readable JSON schemas are published separately (see ticket `mc-cpzi`).

## Scope

The envelope is emitted for every current remote mutation **after remote
execution is attempted**:

- `accounts refresh`
- `transactions update`
- `transactions batch-update` (one item per requested transaction)
- `transactions tags create`
- `transactions tags replace`
- `transactions tags clear`
- `transactions splits replace`
- `transactions splits clear`

Pre-execution authorization and input-validation failures do **not** use this
envelope. Blocked mutations (missing `--allow-mutations`) and input-validation
failures (for example `transactions update` with no change flags) keep the
structured error contract: one JSON error object on stderr with stable `code`,
`message`, and `details` fields.

## The envelope

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

### Top-level statuses

| Status | Meaning | Exit code |
|---|---|---|
| `succeeded` | Every requested effect is known to have succeeded. | `0` |
| `failed` | No requested effect succeeded and all failures are known to be definitive. | `1` (normal operation/API error exit) |
| `ambiguous` | No effect is known to have succeeded, but at least one request may have changed remote state. | `4` |
| `partial` | Item outcomes contain a mixture of succeeded, failed, and/or ambiguous states. | `4` |

Per-item statuses are `succeeded`, `failed`, or `ambiguous`.

### Contract rules

- `schema_version`, `operation`, `status`, `summary`, `items`, and
  `verification` are **always present**.
- `operation` is a stable namespaced identifier (`accounts.refresh`,
  `transactions.update`, `transactions.batch-update`,
  `transactions.tags.create`, `transactions.tags.replace`,
  `transactions.tags.clear`) supplied by the shared operation descriptor
  registry — never inferred from an upstream method or GraphQL operation name.
- Atomic single-effect operations use an `items` array containing exactly one
  item. Batch items preserve normalized input order.
- A multi-stage workflow uses one ordered item per remote effect that was
  actually attempted or became observable. Unattempted later effects are
  omitted. Each effect item uses a stable effect-specific `entity` (for
  example `transaction`, `attachment`) and the best available remote identity,
  so mixed effect outcomes aggregate to `partial` without command-specific
  envelope fields or new statuses.
- Every item always contains `entity`, `id`, `status`, `result`, and `error`.
- `result` is a normalized JSON object on success and `null` otherwise.
  `error` is `null` on success and otherwise contains stable `code`,
  `message`, and object-valued `details`. `result` and `error` are **never
  both non-null**.
- `summary.total` equals `len(items)`, and each status count exactly matches
  `items`.
- `verification` is `null` when no follow-up is needed. If any item is
  ambiguous it contains `required: true`, an actionable `message`, and a
  tokenized `command` array when the CLI can provide a safe verification
  command (for example `["monarch", "transactions", "list"]`).
- Additional fields are **additive**. Removing or changing required fields,
  status values, or their semantics requires a new schema version.

### Additive versus breaking changes

Adding optional fields to the envelope or to item `result`/`error` objects is
**additive** and may happen without a version change. Removing or renaming
required fields, changing the meaning of a status value or exit code, or
narrowing nullability is **breaking** and requires `mutation-outcome.v2` (or
later).

### Error objects

Error objects are sanitized and structured, never copied from arbitrary
exception text:

```json
{
  "code": "API_ERROR",
  "message": "The refresh request was not accepted by the service.",
  "details": {}
}
```

They never contain credentials, raw request bodies, or arbitrary upstream
exception text. Ambiguous items always use the stable `MUTATION_AMBIGUOUS`
error code.

## Ambiguity and recovery

The upstream Monarch API provides **no transactionality, rollback, or
idempotency guarantees** for these mutations. This CLI does not claim
otherwise:

- Remote mutations make **exactly one attempt**. There are no automatic
  retries, regardless of the configured `max_retries` (which applies to reads
  only). A timed-out, disconnected, or interrupted request may already have
  been applied.
- When the outcome is unknown, affected items are reported `ambiguous`, the
  envelope's `verification` object is required, and the process exits `4`.
  The verification message tells you how to check remote state safely (read
  commands or the Monarch web UI) **before** any retry.
- **Never retry an ambiguous mutation blindly.** Verify the affected records
  first; a blind retry can duplicate an undocumented side effect.
- A batch update interrupted mid-flight reports every requested transaction
  as ambiguous, because some or all requests may have been dispatched.
- A mixture of succeeded and failed/ambiguous items aggregates to `partial`
  (exit `4`): a partially applied workflow is not a successful automation
  result, even though some effects did succeed.

Stdout contains only the requested mutation outcome format; progress and
diagnostics are written to stderr.

## Example

```console
$ monarch --allow-mutations transactions update txn_123 --notes "Review"
{
  "schema_version": "mutation-outcome.v1",
  "operation": "transactions.update",
  "status": "succeeded",
  "summary": { "total": 1, "succeeded": 1, "failed": 0, "ambiguous": 0 },
  "items": [
    {
      "entity": "transaction",
      "id": "txn_123",
      "status": "succeeded",
      "result": { "changes": { "notes": "Review" } },
      "error": null
    }
  ],
  "verification": null
}
```

On an ambiguous transport failure, or when a dispatched split mutation
returns an incomplete or malformed response, the same command exits `4` with
`status: "ambiguous"` and a required `verification` object. A nullable
`updateTransactionSplit.errors: null` is a valid upstream no-error response
when the mutation also returns its transaction result; the command then uses
its normal read-after-write verification.
