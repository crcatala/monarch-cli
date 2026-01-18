---
id: mc-7e2e
status: open
deps: [mc-4c28, mc-8d99]
links: []
created: 2026-01-18T16:05:23Z
type: task
priority: 0
assignee: cc-vps
parent: mc-beee
tags: [phase-3, commands, accounts]
---
# Account Commands

Implement account CLI commands: list and refresh.

## Location
`src/monarch_cli/commands/accounts.py`

## Commands

### `monarch accounts list`
List all linked financial accounts.

```python
@app.command("list")
@handle_errors
def list_accounts(
    format: OutputFormat = typer.Option(OutputFormat.JSON, "--format", "-f"),
    ndjson: bool = typer.Option(False, "--ndjson"),
    raw: bool = typer.Option(False, "--raw"),
):
    """List all linked financial accounts."""
    with spinner("Fetching accounts..."):
        if raw:
            client = get_authenticated_client()
            result = run_async(client.get_accounts())
        else:
            result = account_service.list_accounts()
    output(result, format, ndjson=ndjson, raw=raw)
```

### `monarch accounts refresh`
Trigger account refresh from financial institutions.

```python
@app.command()
@handle_errors
def refresh(
    account_id: Optional[list[str]] = typer.Option(
        None, "--account", "-a",
        help="Specific account ID(s) to refresh. Default: all."
    ),
):
    """Trigger account refresh from financial institutions."""
    with spinner("Requesting account refresh..."):
        result = account_service.refresh_accounts(account_id)
    output(result)
```

## CLI Examples
```bash
# List accounts
monarch accounts list                    # JSON output
monarch accounts list -f table           # Table output
monarch accounts list -f csv > accounts.csv  # Export to CSV
monarch accounts list --raw              # Raw API response
monarch accounts list --ndjson           # Stream one per line

# Filter with jq
monarch accounts list | jq '[.[] | select(.balance > 1000)]'
monarch accounts list | jq '.[] | .name'

# Refresh accounts
monarch accounts refresh                 # Refresh all
monarch accounts refresh -a ACC123       # Specific account
monarch accounts refresh -a ACC1 -a ACC2 # Multiple accounts
```

## Help Text
Each command should have clear help text with examples in the docstring.

## Options
| Option | Type | Default | Description |
|--------|------|---------|-------------|
| --format, -f | choice | json | Output format |
| --ndjson | bool | false | Stream as NDJSON |
| --raw | bool | false | Raw API response |
| --account, -a | list | None | Account IDs for refresh |

## Acceptance Criteria

- [ ] `monarch accounts list` returns account data
- [ ] Supports --format (json, table, csv, compact)
- [ ] Supports --ndjson for streaming
- [ ] Supports --raw for unprocessed data
- [ ] Shows spinner during fetch
- [ ] `monarch accounts refresh` triggers bank sync
- [ ] Refresh supports specific account IDs
- [ ] Help text includes examples
- [ ] Live test: real accounts returned

