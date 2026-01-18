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

---

## Completed Tasks

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
