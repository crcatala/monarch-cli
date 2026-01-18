# Phase 3 Commands: Progress Log

This file tracks completed work and patterns learned during this loop.

---

## Codebase Patterns

### Plain Output Format Pattern
The plain formatter uses emoji icons for common field names (id → 🔖, name → 📌, balance → 💰, etc.). 
To add new icons, edit `_FIELD_ICONS` dict in `src/monarch_cli/output/plain.py`.

Both camelCase and snake_case variants are supported (e.g., `currentBalance` and `current_balance` both map to 💰).

### TTY-Aware Output Default
- `get_default_format()` returns `PLAIN` for TTY, `JSON` when piped
- `should_use_color()` checks `NO_COLOR` env, `TERM=dumb`, and TTY status
- Use `output(data)` with no format arg for auto-detection
- Override with `set_default_format(OutputFormat.JSON)` for global `--json` flag

### Color in Plain Output
Plain format automatically strips ANSI color codes when:
- `NO_COLOR` env var is set (any value)
- `TERM=dumb`
- stdout is not a TTY (piped/redirected)

### Single-Command Typer Apps
When a `typer.Typer()` has only ONE command registered:
- The app "becomes" that command directly (no subcommand needed)
- Tests call `runner.invoke(app, ['--json'])` not `runner.invoke(app, ['list', '--json'])`
- `no_args_is_help=True` has no effect - the single command runs directly
- When integrated into main.py with `add_typer(app, name='budgets')`, it becomes `monarch budgets --json`

---

## Completed Tasks

## [2026-01-18 11:46] - Account Commands
- Created `src/monarch_cli/commands/accounts.py` with:
  - `accounts.app` Typer instance with `help='Account management'`
  - `list` command with --format, --json, --ndjson, --raw flags
  - `refresh` command with repeatable --account/-a flag
- Both commands use `@handle_errors` decorator and `spinner()` context manager
- `list` defaults to plain format in terminal, JSON when piped
- `list` uses `list_accounts()` service or raw client call with --raw
- `refresh` uses `refresh_accounts()` service
- Added comprehensive tests in `tests/commands/test_accounts.py`
- Files changed:
  - `src/monarch_cli/commands/accounts.py` (new)
  - `tests/commands/test_accounts.py` (new)
- **Learnings:**
  - Typer's `no_args_is_help=True` results in exit code 2, not 0
  - Rich table output may truncate columns, check for table chars rather than specific values
  - When testing help text with assertions, strip ANSI codes or use case-insensitive search

---

## [2026-01-18 11:42] - Plain Output Format (Human-Friendly Default)
- Added `OutputFormat.PLAIN` to enum in `output/__init__.py`
- Created `src/monarch_cli/output/plain.py` with:
  - `format_plain()` function for human-friendly output with emoji icons
  - `should_use_color()` for NO_COLOR/TERM/TTY detection
  - Field icon mapping for common Monarch fields
- Updated `output()` to use TTY-aware default when format=None
- Added `get_default_format()` and `set_default_format()` functions
- Files changed: 
  - `src/monarch_cli/output/__init__.py`
  - `src/monarch_cli/output/plain.py` (new)
  - `tests/output/test_plain.py` (new)
- **Learnings:** 
  - When patching `sys.stdout.isatty()` in tests, output may still have ANSI codes if the underlying formatter sees TTY=True
  - Use explicit assertions for emoji and values rather than exact formatted strings

---

## Patterns & Decisions

(recorded as tasks complete)

## Issues Encountered

(recorded as tasks complete)

## MVP Checkpoint

After this loop, the CLI should be feature-complete for MVP:
- Auth ✓ (from phase-1)
- Accounts
- Transactions  
- Budgets
- Cashflow
- Categories

## [2026-01-18 11:54] - Budget Commands
- Created `src/monarch_cli/commands/budgets.py` with:
  - `budgets.app` Typer instance with `help='Budget management'`
  - `list` command with --format, --json flags
  - Inline `_transform_budgets()` function for simple transformation
- Output includes: id, category, budgeted, spent (absolute value), remaining
- Spent amounts converted to positive using `abs()` for readability
- Extracts from `budgets['budgetData']['budgetItems']`
- Added comprehensive tests in `tests/commands/test_budgets.py`
- Files changed:
  - `src/monarch_cli/commands/budgets.py` (new)
  - `tests/commands/test_budgets.py` (new)
- **Learnings:**
  - When a Typer app has only ONE command, the app becomes that command directly (no subcommands)
  - Tests must call `runner.invoke(app, ['--json'])` not `runner.invoke(app, ['list', '--json'])`
  - `no_args_is_help=True` has no effect with a single-command app

---

## [2026-01-18 11:59] - Cashflow Commands
- Created `src/monarch_cli/commands/cashflow.py` with:
  - `cashflow.app` Typer instance with `help='Cashflow analysis'`
  - `summary` command with --start, --end, --preset, --format, --json flags
- Uses `parse_date_range()` for date handling (same pattern as transactions)
- Passes data through with minimal transformation (API response is reasonable as-is)
- Uses `@handle_errors` and `spinner('Calculating cashflow...')`
- Added comprehensive tests in `tests/commands/test_cashflow.py`
- Files changed:
  - `src/monarch_cli/commands/cashflow.py` (new)
  - `tests/commands/test_cashflow.py` (new)
- **Learnings:**
  - Single-command apps: tests must NOT include the command name (e.g., `['--json']` not `['summary', '--json']`)
  - TABLE and CSV formats fall back to JSON for dict data (only work with list[dict])

---

## [2026-01-18 12:02] - Categories Commands
- Created `src/monarch_cli/commands/categories.py` with:
  - `categories.app` Typer instance with `help='Category management'`
  - `list` command with --format, --json flags
  - Inline `_flatten_categories()` function to flatten nested structure
- Flattens nested category structure (groups with children) to flat list
- Output includes: id, name, group, icon
- Uses `client.get_transaction_categories()` API method
- Uses `@handle_errors` and `spinner('Fetching categories...')`
- Added comprehensive tests in `tests/commands/test_categories.py`
- Files changed:
  - `src/monarch_cli/commands/categories.py` (new)
  - `tests/commands/test_categories.py` (new)
- **Learnings:**
  - Category API is nested under groups, needs flattening transformation
  - Same single-command app pattern as budgets/cashflow

---

## [2026-01-18 11:55] - Transaction Commands
- Created `src/monarch_cli/commands/transactions.py` with:
  - `transactions.app` Typer instance with `help='Transaction management'`
  - `list` command with --limit, --offset, --start, --end, --preset, --account, --search, --format, --json, --ndjson, --raw flags
  - `update` command with --amount, --description, --category, --notes, --date, --dry-run flags
- Date parsing uses string input with manual conversion (Typer doesn't support `datetime.date` directly)
- `list` uses `parse_date_range()` for preset resolution and explicit date handling
- `update` with --dry-run returns preview without calling API
- `update` without changes shows error with exit code 1
- Added comprehensive tests in `tests/commands/test_transactions.py`
- Files changed:
  - `src/monarch_cli/commands/transactions.py` (new)
  - `tests/commands/test_transactions.py` (new)
- **Learnings:**
  - Typer doesn't support `datetime.date` type, only `datetime.datetime` - use `str` type and parse manually
  - When stripping ANSI codes in tests, use `re.sub(r"\x1b\[[0-9;]*m", "", text)` for complete removal
  - For tests that capture kwargs, need to use `**kwargs` not `**_`

---
