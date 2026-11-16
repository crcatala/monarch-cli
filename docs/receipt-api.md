# Scanned receipt inbox and matching

## Commands

```bash
monarch receipts inbox --limit 25 --offset 0 --json
monarch receipts inbox --status pending_matches --order-by upload_date --json
monarch receipts show RECEIPT_ID --json
monarch receipts match RECEIPT_ID TRANSACTION_ID --dry-run --json
monarch receipts match RECEIPT_ID TRANSACTION_ID --json
monarch receipts match RECEIPT_ID TRANSACTION_ID --retail-transaction RETAIL_TRANSACTION_ID --dry-run --json
```

`RECEIPT_ID` is the inbox `id`. `RETAIL_TRANSACTION_ID` comes from
`orders[].retailTransactions[].id` in `show`. The target is an existing Monarch
transaction ID. Preview reads both records without matching them.

Inbox output has `results`, `total_count`, `offset`, `limit`, and `next_offset`.
Use `next_offset` until it is null. Each receipt keeps the API's field names.
Statuses: `pending`, `in_progress`, `pending_matches`, `completed`, `failed`.
Filtering and ordering run on the server. The command returns one page, not all
receipts. Offset pages can shift when new receipts arrive.

The inbox includes image uploads and forwarded emails. Amazon and Target retail
sync records are excluded, matching Monarch's Receipts tab. `receipts upload`
still attaches a file to a transaction; it does not submit a scan to this inbox.

## Matching behavior

Matching can change notes, categories, and splits under Monarch's receipt settings.
The preview reports current records, not a simulation of Monarch's changes.

The CLI checks both IDs before writing. Only completed receipts and receipts
awaiting matches are eligible. Multiple retail transactions require explicit
selection. Existing links to other transactions are rejected. Repeating the same
link returns `already_matched` without writing.

The CLI sends one match mutation, then reads the receipt again. Success requires
the selected retail transaction to link to the requested Monarch transaction.
This checks the link, not every note, category, or split change. No automatic retry
is made. After a timeout, connection error, or readback failure, inspect `show`
before retrying: the write may have completed. A link that is not immediately
visible is reported as unverified.

## Observed API contract

These are private GraphQL operations. Source: Monarch web app `v1.0.6163`,
observed November 15, 2026:

- [Main bundle](https://static.monarch.com/static/js/main.230d5aed.js): generated query documents and enums.
- [InAppRoutes bundle](https://static.monarch.com/static/js/InAppRoutes.33c2c744.chunk.js): receipt filters, pagination, and match selection.
- [Web app](https://app.monarch.com): public bundle entry point.

| Operation | Variables | Response |
| --- | --- | --- |
| `Common_RetailSyncsQueryWithTotal` | `filters: RetailSyncFilterInput!`, `offset: Int!`, `limit: Int!`, `includeTotalCount: Boolean`, `orderBy: RetailSyncOrdering!` | `retailSyncsWithTotal { totalCount results }` |
| `Common_RetailSyncQuery` | `syncId: ID!` | `retailSync(id: $syncId)` |
| `Common_MatchRetailTransaction` | `retailTransactionId: ID!`, `transactionId: ID!` | `matchRetailTransaction { retailSync { id status } errors { message code fieldErrors { field messages } } }` |

Filters use `vendors: ["user_import", "email_import"]` and optional `status`.
Ordering: `receipt_date` or `upload_date`. Queries include orders, line items,
attachments, and current links. Query selections live in
`src/monarch_cli/core/receipt_queries.py`; validation and matching live in
`src/monarch_cli/core/receipt_api.py`. No new dependency is required.

Validation rejects missing pages, malformed records, stalled pagination, missing
link data, non-null mutation errors, and ambiguous IDs.

## Verification

Read-only live checks returned a 74-receipt inbox, validated the implementation's
detail query, and confirmed an existing link with `match --dry-run`. No live match
mutation was sent. Synthetic tests cover writes, payload errors, ambiguous
receipts, existing links, transport failure, and readback mismatch. Standard tests
make no live API calls. Private API changes may require a contract update.
