# Investment holdings

`monarch investments holdings` is a read-only portfolio inventory command.
It performs one account-discovery request, selects eligible accounts, and
reads each selected account through the shared read timeout/retry executor.
Holdings reads are bounded to four concurrent requests; there is no
holdings-specific concurrency or retry setting.

## Selection

Automatic discovery excludes hidden accounts and accounts whose released
metadata reports `holdingsCount: 0`. Use `--include-hidden` to include hidden
eligible accounts. Brokerage/investment account types and investment subtypes
are eligible. Manual investment accounts are eligible only when
`manualInvestmentsTrackingMethod` explicitly indicates holdings/securities
tracking; balance-only manual accounts are not queried. An explicitly
repeated `--account` is validated against the single discovery response,
including hidden accounts, and unknown or ineligible IDs fail before any
holdings request. A reported zero holdings count is never queried.

The released upstream `get_account_holdings` method always requests hidden
holdings within a selected account (`includeHiddenHoldings: true`) and offers
no public switch. Therefore `--include-hidden` controls account discovery only;
holdings hidden inside an explicitly selected account cannot be excluded by
this CLI.

## Normalized output

Each non-aggregated row contains `account_id`, `account_name`, `security_id`,
`holding_id`, `ticker`, `name`, `security_type`, `security_type_display`,
`quantity`, `basis`, `price`, `total_value`, and `last_synced_at`. Missing
metadata and financial values remain JSON `null`; the CLI does not use typed
wrapper sentinels or calculate value from quantity and price.

`--aggregate` groups only rows with the same non-null `security_id`. Rows
without that ID remain independent and retain source account context. An
aggregated row reports sorted `account_ids` and `account_count`, sums quantity
only when every quantity is present, and retains `account_contributions` with
per-account quantity/basis/price/value. It never emits an aggregate basis,
price, total value, currency total, or conversion. The released account and
holdings payloads expose no verifiable per-account currency metadata, so the
CLI makes no currency-compatibility assumption.

## Raw mode and failure behavior

`--raw` returns a deterministic JSON object keyed by sorted account ID. Each
value is the untouched upstream response for that account; the enclosing
object is a CLI envelope, not an upstream response. Raw mode bypasses
normalization and aggregation.

A failure for any selected account fails the whole operation with the typed
read error. No partial normalized or raw result is emitted. Output ordering is
deterministic by account ID and holding ID.

Examples:

```console
monarch investments holdings --json
monarch investments holdings --include-hidden --format table
monarch investments holdings --account ACC123 --account ACC456 --json
monarch investments holdings --aggregate --json
monarch investments holdings --raw --json
```
