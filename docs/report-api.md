# Saved reports

`monarch report` manages saved views inside Monarch. It does not export report
data or charts. Use `monarch cashflow` for income/expense data.

## Commands

```bash
monarch report list --json
monarch report show REPORT_ID --json

monarch report create --name "Tagged cash flow" \
  --url 'https://app.monarch.com/reports/cash-flow?tags=253277239843441604' \
  --dry-run --json

# Remove --dry-run to save the report in Monarch.
monarch report rename REPORT_ID --name "New name" --dry-run --json
monarch report delete REPORT_ID --dry-run --json
monarch report delete REPORT_ID --yes --json
```

Use IDs from `report list`. `show` returns one exact ID from the same complete
list. The observed list operation has no pagination parameters.

The example URL is a filtered cash-flow view, not a saved report ID. Create saves
its URL-encoded settings as a new report. It cannot infer settings kept only in
browser state. Supported tabs: `cash-flow`, `spending`, and `income`.

URL support includes comma-separated or repeated ID filters, exclude filters,
search, boolean filters, amount bounds, dates, relative timeframes, and supported
chart/group settings. Unknown parameters and settings that do not apply to the
selected chart are rejected. Explicit dates cannot be combined with a relative
timeframe. False boolean values are preserved.

For explicit API input, use JSON objects:

```json
{"tags": ["253277239843441604"], "transactionVisibility": "non_hidden_transactions_only"}
```

```json
{"analysisScope": "cash_flow", "chartType": "sankey", "chartCalculation": "sum", "dimensions": ["category", "category_group"]}
```

```bash
monarch report create --name "Tagged cash flow" \
  --filters-file filters.json --view-file view.json --dry-run --json
```

Do not combine `--url` with JSON files. Without a URL or files, create defaults to
a cash-flow Sankey with non-hidden transactions. Without a view file, JSON filters
also use that chart. Supported fields are validated in `core/report_config.py`;
unknown keys, duplicate JSON keys, invalid types, and unsupported view settings
are rejected. These files are input objects, not raw `report show` output.

## Write behavior

Create preview validates input offline and needs no authentication. Rename/delete
previews read the current report without writing. Live creation rejects an
existing report name. Rename changes only the name; unchanged names make no
write. Delete requires `--yes` unless previewing.

Writes make no automatic retries. Create verifies the new ID, name, requested
filters, and view against a fresh list. Rename verifies the name and preserves
the filters/view. Delete verifies the ID is absent. Payload errors, missing
responses, and readback mismatches are failures. After an uncertain result,
inspect `report list` or `report show` before retrying. No automatic rollback is
attempted. A concurrent edit can cause verification to fail.

The current web app updates saved reports by renaming them. Editing an existing
report's filters/view in place is not exposed here. Create a new report with the
desired settings, inspect it, then explicitly delete the old one if needed.

## API contract and evidence

Private GraphQL operations observed in Monarch web app `v1.0.6163` on
November 15, 2026:

| Operation | Input | Response |
| --- | --- | --- |
| `Common_GetReportConfigurations` | No variables | `reportConfigurations[]` |
| `Common_CreateReportConfiguration` | `input: CreateReportConfigurationInput!` with `displayName`, `transactionFilters`, `reportView` | `createReportConfiguration { reportConfiguration errors }` |
| `Common_UpdateReportConfiguration` | `input: UpdateReportConfigurationInput!` with `id`, `displayName` | `updateReportConfiguration { reportConfiguration errors }` |
| `Common_DeleteReportConfiguration` | `id: ID!` | `deleteReportConfiguration { deleted errors }` |

Each report includes `id`, `displayName`, `transactionFilterSet`, and `reportView`.
View fields: `analysisScope`, `chartType`, `chartCalculation`, `chartLayout`,
`chartDensity`, `dimensions`, and `timeframe`. Filter outputs contain related
objects; filter inputs use ID arrays. Exclusion inputs use `excludeTags` and
similar names, while outputs use `excludedTags`.

Sources:

- [Main bundle](https://static.monarch.com/static/js/main.230d5aed.js): query documents, filter input conversion, enums, chart identifiers.
- [InAppRoutes bundle](https://static.monarch.com/static/js/InAppRoutes.33c2c744.chunk.js): create/rename/delete calls, chart conversion, URL filter conversion.
- [Example view](https://app.monarch.com/reports/cash-flow?tags=253277239843441604): cash-flow route and tag filter.

Read-only live list returned 10 saved reports. Mutation input shapes were validated
with literal GraphQL `@skip(if: true)` on every mutation root field; no write
resolver executed. CLI list/show and previews are checked separately. Synthetic
tests cover writes, API errors, malformed input, uncertain results, and readback
failures. No live saved-report mutation was performed. These private operations
may change. No new dependency is required.
