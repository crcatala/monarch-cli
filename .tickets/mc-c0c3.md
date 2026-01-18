---
id: mc-c0c3
status: closed
deps: [mc-9441]
links: []
created: 2026-01-18T16:02:10Z
type: task
priority: 1
assignee: cc-vps
parent: mc-a23d
tags: [phase-1, core, dates]
---
# Date Utilities and Presets

Implement date utilities and preset parsing for transaction/cashflow filtering.

## Location
`src/monarch_cli/core/dates.py`

## Date Presets (DatePreset enum)
Common date ranges for financial queries:
| Preset | Description |
|--------|-------------|
| today | Today only |
| yesterday | Yesterday only |
| this-week | Monday to today |
| last-week | Last Monday to Sunday |
| this-month | 1st of month to today |
| last-month | Full previous month |
| last-30-days | Rolling 30 days |
| last-90-days | Rolling 90 days |
| this-year | Jan 1 to today |
| last-year | Full previous year |
| ytd | Year to date (alias for this-year) |
| all | No date filtering |

## Key Functions
```python
def resolve_preset(preset: DatePreset) -> tuple[date | None, date | None]:
    """Convert a preset to (start_date, end_date) tuple."""

def parse_date_range(
    preset: DatePreset | None = None,
    start: str | None = None,
    end: str | None = None,
) -> tuple[str | None, str | None]:
    """Parse date range from preset or explicit dates.
    
    Explicit dates take precedence over preset.
    Returns ISO format strings (YYYY-MM-DD) or None.
    """
```

## Implementation Notes
- Use Python's `datetime.date` for calculations
- Week starts on Monday (ISO standard)
- Return ISO 8601 format strings for API compatibility
- Explicit --start/--end override any preset

## Usage in Commands
```python
@app.command()
def list_transactions(
    start_date: Optional[str] = typer.Option(None, "--start", "-s"),
    end_date: Optional[str] = typer.Option(None, "--end", "-e"),
    preset: Optional[DatePreset] = typer.Option(None, "--preset", "-p"),
):
    resolved_start, resolved_end = parse_date_range(preset, start_date, end_date)
    # Use resolved dates for API call
```

## CLI Examples
```bash
monarch transactions list --preset this-month
monarch transactions list --preset last-30-days
monarch transactions list --start 2024-01-01 --end 2024-03-31
monarch transactions list --preset ytd  # Overridden by --start if both given
```

## Acceptance Criteria

- [ ] DatePreset enum with all preset values
- [ ] resolve_preset() handles all presets correctly
- [ ] parse_date_range() returns ISO format strings
- [ ] Explicit dates override presets
- [ ] Week calculations use Monday as start
- [ ] 'all' preset returns (None, None)
- [ ] Unit tests for each preset calculation

