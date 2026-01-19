---
id: mc-0c0a
status: closed
deps: [mc-7e2e, mc-0136, mc-ff18, mc-a185, mc-57e8]
links: []
created: 2026-01-18T16:07:03Z
type: task
priority: 0
assignee: cc-vps
parent: mc-beee
tags: [phase-3, cli, entrypoint]
---
# Update Main Entry Point (All Commands)

Update the main CLI entry point to register all command groups and fix global flags per CLI best practices.

## Location
`src/monarch_cli/main.py`

## Implementation

### Register All Command Groups
```python
import typer

from .commands import auth, accounts, transactions, budgets, cashflow, categories

app = typer.Typer(
    name="monarch",
    help="CLI for Monarch Money - AI agent friendly financial data access",
    no_args_is_help=True,
)

app.add_typer(auth.app, name="auth")
app.add_typer(accounts.app, name="accounts")
app.add_typer(transactions.app, name="transactions")
app.add_typer(budgets.app, name="budgets")
app.add_typer(cashflow.app, name="cashflow")
app.add_typer(categories.app, name="categories")
```

### Fix Global Flags (CLI Best Practices)

**Problem**: Current flags violate CLI conventions:
- `-v` is used for `--version` (should be `--verbose`)
- `-V` is used for `--verbose` (non-standard)
- Missing `--no-color` global flag
- Missing `--json` global shortcut
- No `--debug` mode separate from `--verbose`

**Solution**: Update the callback to follow clig.dev guidelines:

```python
@app.callback()
def main(
    version: bool = typer.Option(
        None,
        "--version",  # NO short flag - version should be --version only
        callback=version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
    verbose: bool = typer.Option(
        False,
        "-v", "--verbose",  # -v is standard for verbose
        help="Show operational progress messages.",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Show debug info and stack traces (implies --verbose).",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output as JSON (global shortcut for --format json).",
    ),
    no_color: bool = typer.Option(
        False,
        "--no-color",
        help="Disable colored output.",
    ),
) -> None:
    """CLI for Monarch Money - AI-agent friendly financial data access."""
    if debug:
        set_verbose(True)
        set_debug(True)
    elif verbose:
        set_verbose(True)
    if json_output:
        set_default_format(OutputFormat.JSON)
    if no_color:
        from rich.console import Console
        # Rich respects NO_COLOR env, but we also need explicit flag
        import os
        os.environ["NO_COLOR"] = "1"
```

### Required Changes to output module

Add these to `src/monarch_cli/output/__init__.py`:

```python
_debug = False
_default_format = OutputFormat.JSON

def set_debug(d: bool) -> None:
    global _debug
    _debug = d

def is_debug() -> bool:
    return _debug

def set_default_format(fmt: OutputFormat) -> None:
    global _default_format
    _default_format = fmt

def get_default_format() -> OutputFormat:
    return _default_format
```

## Command Structure After Update
```
monarch
├── auth
│   ├── login, status, logout, doctor, ping, setup
├── accounts
│   ├── list, refresh
├── transactions
│   ├── list, update
├── budgets
│   └── list
├── cashflow
│   └── summary
└── categories
    └── list
```

## Global Flags Summary

| Flag | Short | Description |
|------|-------|-------------|
| `--version` | (none) | Show version and exit |
| `--verbose` | `-v` | Show operational progress |
| `--debug` | (none) | Debug info + stack traces (implies -v) |
| `--json` | (none) | JSON output globally |
| `--no-color` | (none) | Disable colored output |

## Verification
```bash
monarch --help                 # Shows all command groups
monarch --version              # Shows version (no -v shortcut)
monarch -v accounts list       # Verbose mode
monarch --debug accounts list  # Debug mode with stack traces
monarch --json accounts list   # JSON output
monarch --no-color auth doctor # No colors
monarch accounts --help        # Shows account commands
```

## Acceptance Criteria

### Command Registration
- [ ] All command groups registered (auth, accounts, transactions, budgets, cashflow, categories)
- [ ] `monarch --help` shows all groups
- [ ] Each command group's --help works
- [ ] Commands can be invoked: `monarch accounts list`
- [ ] All commands use @handle_errors

### Global Flags (CLI Best Practices)
- [ ] `--version` works (NO `-v` shortcut)
- [ ] `-v, --verbose` shows progress messages
- [ ] `--debug` shows stack traces and implies verbose
- [ ] `--json` sets default output format to JSON
- [ ] `--no-color` disables colored output
- [ ] `NO_COLOR` env var is still respected

### Output Module Updates
- [ ] `set_debug()` / `is_debug()` functions added
- [ ] `set_default_format()` / `get_default_format()` functions added
- [ ] Error handler uses `is_debug()` for stack traces (instead of `is_verbose()`)

## Notes

**2026-01-19T01:05:00Z**

Verified complete: main.py registers all 6 command groups with global flags
