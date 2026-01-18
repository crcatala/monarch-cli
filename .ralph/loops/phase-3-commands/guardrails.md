# Phase 3 Commands Guardrails

## ⚠️ CRITICAL: No Write Operations During Testing

**The local machine has personal Monarch Money credentials. Do NOT execute any write or mutating operations against the live API.**

Safe to test live:
- ✅ `monarch accounts list`
- ✅ `monarch transactions list`
- ✅ `monarch budgets list`
- ✅ `monarch cashflow summary`
- ✅ `monarch categories list`

Do NOT test live:
- ❌ `monarch accounts refresh` - triggers bank sync
- ❌ `monarch transactions update` - modifies transaction data

**For testing write commands:**
- Use mocks in unit tests
- Test `--dry-run` flag to verify logic without applying changes
- Verify code compiles and type-checks correctly
- Test with `--help` to verify CLI structure

## Command Structure Pattern

Every command follows this pattern:
```python
@app.command("name")
@handle_errors
def command_name(
    # Required args first
    id: str = typer.Argument(..., help="..."),
    # Then options with defaults
    format: OutputFormat = typer.Option(OutputFormat.JSON, "--format", "-f"),
):
    """Docstring with examples in help text."""
    with spinner("Doing something..."):
        result = do_the_thing()
    output(result, format)
```

## Help Text Requirements

Every command should have:
1. Clear one-line description
2. Examples in docstring:
```python
"""List all transactions.

Examples:
    monarch transactions list
    monarch transactions list --preset this-month
    monarch transactions list --format table
"""
```

## Flag Conventions

| Flag | Short | Type | Purpose |
|------|-------|------|---------|
| --format | -f | OutputFormat | Output format |
| --ndjson | | bool | Stream as NDJSON |
| --raw | | bool | Raw API response |
| --dry-run | | bool | Preview without executing |
| --limit | -l | int | Pagination limit |
| --offset | -o | int | Pagination offset |
| --start | -s | str | Start date |
| --end | -e | str | End date |
| --preset | -p | DatePreset | Date range preset |
| --account | -a | str | Account ID filter |

## Testing Commands

After implementing each command, test manually:
```bash
# Must be authenticated first
monarch auth status

# Then test commands
monarch accounts list
monarch accounts list --format table
monarch transactions list --preset this-month
```

## Reference

- Plan: `plans/monarch-cli-implementation-plan.md` (Phase 3 section)
- Tickets: `.tickets/mc-7e2e.md`, `.tickets/mc-0136.md`, `.tickets/mc-ff18.md`, `.tickets/mc-a185.md`, `.tickets/mc-57e8.md`
