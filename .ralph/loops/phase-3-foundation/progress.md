# Phase 3 Foundation: Progress Log

This file tracks completed work and patterns learned during this loop.

---

## Codebase Patterns

### Transformer Pattern
- Use `.get()` with fallback for optional fields
- Use `raw.get("key") or []` for list fields that might be None (not just missing)
- Field names are snake_case, flattened from nested API structures
- Transformers are pure functions - easy to unit test

---

## Completed Tasks

## [2026-01-18 11:06] - Account Service Layer (mc-4c28)
- Implemented `list_accounts()` - fetches and transforms accounts using the transformer
- Implemented `get_account_ids()` - returns list of account ID strings
- Implemented `refresh_accounts(account_ids=None)` - orchestrates refresh, fetches all IDs if none provided
- Returns dict with status ('ok', 'no_accounts', 'failed'), account_count, message
- Uses `get_authenticated_client()` from adapter and `run_async()` for all async calls
- Files changed:
  - `src/monarch_cli/services/accounts.py` (new)
  - `tests/services/__init__.py` (new)
  - `tests/services/test_accounts.py` (new - 12 tests with mocks)
- **Learnings:** Unused mock parameters should be prefixed with `_` to satisfy linter (ARG002)
---

## [2026-01-18 11:05] - Transaction Transformer (mc-f913)
- Implemented `transform_transaction()` and `transform_transactions()` functions
- Handles all required fields: id, date, amount, description, category, category_id, account, account_id, is_pending, notes
- `description` prefers `merchant.name`, falls back to `plaidName` (also handles empty string/None merchant name)
- `transform_transactions()` processes `raw['allTransactions']['results']` list
- Gracefully handles missing/None nested fields at all levels
- Files changed:
  - `src/monarch_cli/transformers/transactions.py` (new)
  - `tests/transformers/test_transactions.py` (new)
- **Learnings:** Use `raw.get("key") or {}` for nested dict access when the key might be None (not just missing)
---

## [2026-01-18 11:03] - Account Transformer (mc-78e5)
- Implemented `transform_account()` and `transform_accounts()` functions
- Handles all required fields: id, name, type, subtype, balance, institution, is_active, is_manual, last_updated
- Gracefully handles missing nested fields (returns None, not KeyError)
- `is_active` correctly inverts `isHidden`
- Files changed: 
  - `src/monarch_cli/transformers/accounts.py` (new)
  - `tests/transformers/__init__.py` (new)
  - `tests/transformers/test_accounts.py` (new)
- **Learnings:** Use `raw.get("key") or []` instead of `raw.get("key", [])` when the key might exist with value None
---

## Patterns & Decisions

(recorded as tasks complete)

## Issues Encountered

(recorded as tasks complete)
