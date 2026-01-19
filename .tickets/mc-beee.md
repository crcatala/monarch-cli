---
id: mc-beee
status: closed
deps: [mc-0e26]
links: []
created: 2026-01-18T16:04:18Z
type: epic
priority: 0
assignee: cc-vps
tags: [phase-3, commands, mvp]
---
# Epic 3: Core Commands (MVP)

Implement all Priority 1 (MVP) commands: accounts, transactions, budgets, cashflow, categories.

## Background
With authentication complete and output system in place, we can now implement the core commands that cover 90% of what users do in Monarch Money.

## Scope - Priority 1 Commands

### Accounts
- `monarch accounts list` - List all linked accounts
- `monarch accounts refresh` - Sync from banks

### Transactions
- `monarch transactions list` - List/filter transactions
- `monarch transactions update` - Recategorize, add notes

### Budgets
- `monarch budgets list` - Budget status with spent/remaining

### Cashflow
- `monarch cashflow summary` - Income/expense totals

### Categories
- `monarch categories list` - List categories (needed for IDs)

### Configuration
- Environment-based config system (TOML file deferred to v1.1)

## Architecture Layers
1. **Commands** (`commands/*.py`): Thin handlers for CLI args, delegate to services/client
2. **Services** (`services/*.py`): Business logic, orchestration (only when needed)
3. **Transformers** (`transformers/*.py`): API response → CLI-friendly format
4. **Adapter** (`core/adapter.py`): Isolates upstream library details

## Design Decision: Service Layer vs Direct Client
| Pattern | When to Use | Example |
|---------|-------------|---------|
| Direct client call | Simple fetch + transform | transactions list, categories list |
| Service layer | Multi-step logic | accounts refresh (fetches IDs, then refreshes) |

Most commands do a single API call followed by transformation - these call the client directly.

## Global Options
| Flag | Description |
|------|-------------|
| `--format, -f` | Output format (json, table, csv, compact) |
| `--ndjson` | Stream as newline-delimited JSON |
| `--raw` | Output raw API response |
| `--quiet, -q` | Minimal output (IDs only) |
| `--dry-run` | Preview mutation without executing |

## Date Filtering
Transaction and cashflow commands support:
- `--start` / `--end`: Explicit date range (YYYY-MM-DD)
- `--preset`: Date presets (this-month, last-30-days, ytd, etc.)
- Explicit dates override presets

## Acceptance Criteria

- [ ] `monarch accounts list` returns real account data
- [ ] `monarch accounts refresh` triggers bank sync
- [ ] `monarch transactions list` with date filtering works
- [ ] `monarch transactions update` can recategorize
- [ ] `monarch budgets list` shows budget status
- [ ] `monarch cashflow summary` shows income/expenses
- [ ] `monarch categories list` returns category IDs
- [ ] All output formats work (json, table, csv)
- [ ] Date presets work correctly
- [ ] `--dry-run` previews mutations
- [ ] Error handling consistent across commands


## Notes

**2026-01-19T01:05:05Z**

Verified complete: All child command tickets implemented and tested (484 tests pass)
