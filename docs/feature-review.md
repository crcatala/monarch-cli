# Monarch feature review — November 15, 2026

Sources: [official release notes](https://www.monarch.com/whats-new),
[July update](https://www.monarch.com/blog/july-product-update), and the installed
`monarchmoneycommunity` wrapper. Product availability does not establish API support.

## Shipped in this change

- `receipts upload`: the existing attachment workflow under a discoverable group.
- `receipts list TRANSACTION_ID`: attachment metadata, including asset URLs.
- `receipts missing`: a paginated queue of transactions without attachments.
- `receipts inbox` and `receipts show`: scanned image/email receipts and processing status.
- `receipts match`: explicit matching with preview, conflict checks, and verified link readback.

Attachment uploads do not submit documents to the scanned receipt inbox or trigger
OCR. Inbox commands read existing receipts; matching uses Monarch's native receipt
match mutation. See [API details and validation](receipt-api.md).
Monarch's email forwarding feature can do those operations. Forwarding sends an
email and can change transaction categories and splits; the CLI does not send it.

## Recommended next features

| Priority | Feature | Reason and prerequisite |
| --- | --- | --- |
| 1 | Scanned receipt submission and controlled removal of links | Inbox, detail, and explicit matching are implemented. Next investigate submission and link removal contracts. |
| 2 | Transaction activity log | Explains pending-to-posted transitions and edits. Verify the query and pagination before exposing it. |
| 3 | Exclude filters for accounts, categories, tags | Useful for focused reports. Confirm server filter semantics; do not filter one fetched page and imply complete results. |
| 4 | Recurring merchant management | The wrapper already exposes `update_reoccuring`; add validated flags, preview, error checks, and readback before shipping writes. |
| 5 | Goals v2 list and progress | Product is out of beta; the wrapper exposes budget goal allocations but no dedicated public goal management methods. |
| 6 | Complete transaction export and ID-based CSV update | Monarch now supports these workflows. Preserve hidden rows, paginate completely, and preview changes before importing. |

Forecasting, investment allocation overrides, retail sync, and business tracking
need separate API investigation. The CLI already has an optional MCP server;
Monarch also announced its own MCP integration. Compare coverage before adding
another integration layer.

## Validation limits

Inbox and detail queries were checked live with read-only calls, including a preview
of an existing link. New matching writes use synthetic tests; no live mutation,
scan submission, or email forwarding was performed. See [receipt API verification](receipt-api.md).
