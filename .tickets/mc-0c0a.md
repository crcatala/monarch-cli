---
id: mc-0c0a
status: open
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

Update the main CLI entry point to register all command groups.

## Location
`src/monarch_cli/main.py`

## Implementation
```python
import typer

app = typer.Typer(
    name="monarch",
    help="CLI for Monarch Money - AI agent friendly financial data access",
    no_args_is_help=True,
)

# Import and register all command groups
from .commands import auth, accounts, transactions, budgets, cashflow, categories

app.add_typer(auth.app, name="auth")
app.add_typer(accounts.app, name="accounts")
app.add_typer(transactions.app, name="transactions")
app.add_typer(budgets.app, name="budgets")
app.add_typer(cashflow.app, name="cashflow")
app.add_typer(categories.app, name="categories")
# Note: config commands deferred to v1.1

if __name__ == "__main__":
    app()
```

## Command Structure After Update
```
monarch
├── auth
│   ├── login
│   ├── status
│   ├── logout
│   ├── doctor
│   ├── ping
│   └── setup
├── accounts
│   ├── list
│   └── refresh
├── transactions
│   ├── list
│   └── update
├── budgets
│   └── list
├── cashflow
│   └── summary
└── categories
    └── list
```

## Verification
```bash
monarch --help                 # Shows all command groups
monarch accounts --help        # Shows account commands
monarch transactions --help    # Shows transaction commands
monarch budgets --help         # Shows budget commands
monarch cashflow --help        # Shows cashflow commands
monarch categories --help      # Shows category commands
```

## Global Callback (Optional Enhancement)
Could add a global callback for verbose flag:
```python
@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """CLI for Monarch Money - AI agent friendly financial data access."""
    from .output import set_verbose
    set_verbose(verbose)
```

This is optional for MVP - individual commands handle --verbose if needed.

## Acceptance Criteria

- [ ] All command groups registered
- [ ] `monarch --help` shows all groups
- [ ] Each command group's --help works
- [ ] Commands can be invoked: `monarch accounts list`
- [ ] All commands use @handle_errors
- [ ] Version shown with `monarch --version`

