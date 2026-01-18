# Phase 2 Output Guardrails

## I/O Contract

| Stream | Purpose |
|--------|---------|
| stdout | Data output (JSON, tables, CSV) |
| stderr | Progress, warnings, errors |

**This separation is critical for piping:**
```bash
monarch accounts list --format json | jq '.[] | .balance'
```

## TTY Detection

```python
# For data output
if sys.stdout.isatty():
    # Interactive: colors OK
else:
    # Piped: no colors, no fancy formatting

# For progress
if sys.stderr.isatty():
    # Show spinner
else:
    # Just print message
```

## Output Function Signature

```python
def output(
    data: Any,
    format: OutputFormat = OutputFormat.JSON,
    ndjson: bool = False,
    raw: bool = False,
) -> None:
```

## Error Output

Errors always go to stderr as structured JSON:
```python
def output_error(error: MonarchCLIError) -> None:
    print(json.dumps(error.to_dict(), indent=2), file=sys.stderr)
```

## Testing

Test each format:
```bash
# JSON (default)
uv run monarch auth status

# Table (once commands exist)
uv run monarch accounts list --format table

# CSV
uv run monarch accounts list --format csv

# Piped (no TTY)
uv run monarch accounts list | cat
```

## Reference

- Tickets: `.tickets/mc-299b.md`, `.tickets/mc-3f7c.md`
- CLI guidelines: https://clig.dev
