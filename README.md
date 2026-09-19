# Monarch CLI

[![PyPI version](https://badge.fury.io/py/monarch-cli.svg)](https://badge.fury.io/py/monarch-cli)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A command-line interface for [Monarch Money](https://www.monarchmoney.com/),
the personal-finance platform for tracking spending, budgets, investments, and
net worth.

> **Disclaimer:** This is an unofficial, community-maintained project. It is
> not affiliated with, endorsed by, or connected to Monarch Money.

## Features

- Secure authentication with keyring, file, or environment-token storage
- Normalized JSON output for scripts and AI agents, with `--raw` passthrough
- Plain, JSON, table, CSV, compact JSON, and NDJSON output modes
- TTY-aware output: human-readable in a terminal and JSON when piped
- Date presets such as `this-month`, `last-30-days`, and `ytd`
- Read-only access to accounts, transactions, budgets, cashflow, holdings,
  institutions, subscriptions, categories, and balance history
- Guarded transaction, tag, split, and account-refresh mutations with dry-run
  previews and structured mutation outcomes

## Installation

### pip

```bash
pip install monarch-cli
```

### uv (recommended)

```bash
uv tool install monarch-cli
```

### pipx

```bash
pipx install monarch-cli
```

Verify the installation:

```bash
monarch --version
```

## Upgrading

Version-specific migration guides, including breaking-change notes, are in
[docs/migrations/](docs/migrations/).

## Quick start

Authenticate interactively:

```bash
monarch auth login
monarch auth status
```

List accounts:

```bash
monarch accounts list
monarch accounts list --json
```

Explore transactions:

```bash
monarch transactions list
monarch transactions list --preset this-month --search "coffee" --limit 20
```

Review the current budget:

```bash
monarch budgets list --format table
```

## Common workflows

### Accounts and net worth

```bash
# Human-readable account table
monarch accounts list --format table

# Discover authoritative account-type identifiers
monarch accounts types --json

# Inspect balance history and net-worth snapshots
monarch accounts history ACC_ID --json
monarch accounts snapshots \
  --start 2024-01-01 \
  --end 2024-12-31 \
  --json

# Check whether an institution refresh is still in progress
monarch accounts refresh-status --account ACC_ID --json
```

### Transactions

```bash
# Review this month's non-pending coffee transactions
monarch transactions list \
  --preset this-month \
  --search "coffee" \
  --no-pending \
  --needs-review \
  --json

# Inspect one transaction without pending-to-posted redirection
monarch transactions get TXN_ID --strict --json

# Stream IDs into another command
monarch --quiet transactions list --search "Coffee" | sort -u
```

The transaction list supports repeatable account, category, and tag filters,
pagination, visibility controls, text search, and tri-state filters such as
`--pending`/`--no-pending` and `--has-notes`/`--no-has-notes`.

### Reports and portfolio

```bash
# Year-to-date income and expense summary
monarch cashflow summary --preset ytd --json

# Category, merchant, and group detail
monarch cashflow detail --preset this-month --json

# Group investment rows by security
monarch investments holdings --aggregate --json

# Diagnose linked institution connections
monarch institutions list --include-deleted --json

# Check trial and premium entitlement state
monarch subscription show --json
```

### Safe mutations

The CLI is read-only by default. Remote writes require the global
`--allow-mutations` flag, which must appear before the command path. Use
`--dry-run` to validate and preview supported changes without writing.

```bash
# Preview; no authorization flag is required
monarch transactions update \
  --transaction-id TXN_ID \
  --category CAT_ID \
  --dry-run

# Apply a change
monarch --allow-mutations transactions update \
  --transaction-id TXN_ID \
  --category CAT_ID

# Batch update IDs from a pipeline
monarch --quiet transactions list --search "Coffee" | \
  monarch --allow-mutations transactions batch-update \
    --stdin \
    --category CAT_ID

# Add or replace transaction tags
monarch --allow-mutations transactions tags add \
  --transaction-id TXN_ID \
  --tag-name "Travel"

# Attach a receipt (preview offline, then upload)
monarch transactions attachments add \
  --transaction-id TXN_ID \
  --file ./receipt.pdf \
  --dry-run
monarch --allow-mutations transactions attachments add \
  --transaction-id TXN_ID \
  --file ./receipt.pdf

# Replace a transaction's complete split set
monarch --allow-mutations --yes transactions splits replace \
  --transaction-id TXN_ID \
  --splits-file ./splits.json
```

`--yes` skips a destructive confirmation; it never authorizes a write.
Remote mutation results always use the machine-readable
`mutation-outcome.v1` contract. See [Mutation outcomes](docs/mutation-outcomes.md)
for ambiguity, retry, verification, exit-code, and dry-run behavior.
Third-party uploads (for example, attachment media) use a credential-safe
adapter boundary that never forwards Monarch credentials, cookies, or session
state; see [Credential-safe upload transport](docs/upload-transport.md).

## Output and automation

Every command supports `--help`. Most read commands support:

```text
-f, --format plain|json|table|csv|compact
--json
```

The root `--json` option must appear before the command path:

```bash
monarch --json accounts list
monarch accounts list --json
```

The two forms are equivalent for commands that provide a local `--json`
shortcut. `--ndjson` is available on account and transaction list commands.
`--quiet` emits IDs only, which is useful for pipelines. See
[Output contracts](docs/output-contracts.md) for normalization, raw output,
field guarantees, and scripting behavior.

## Configuration and authentication

Configuration is layered as:

```text
config file → environment variables → CLI flags
```

The default configuration directory is platform-specific; on Linux it is
normally `~/.config/monarch-cli`. Use `MONARCH_CONFIG_DIR` or
`monarch auth setup` to locate it. Authentication checks credentials in this
order:

1. `MONARCH_TOKEN`
2. system keyring
3. JSON session file

See [Configuration](docs/configuration.md) for supported settings,
environment variables, retry behavior, and non-interactive automation.

## Command reference

The concise workflow examples above cover the most common use cases. The
complete command and option inventory is maintained in
[docs/commands.md](docs/commands.md). The CLI itself is also the authoritative
source for command-specific help:

```bash
monarch --help
monarch transactions list --help
monarch transactions tags add --help
```

## Shell completion

```bash
monarch --install-completion bash
monarch --install-completion zsh
monarch --install-completion fish
```

Use `--show-completion` to print completion code without installing it.

## Troubleshooting

Check authentication and connectivity:

```bash
monarch auth status
monarch auth doctor
monarch auth ping
```

On a headless system without a usable keyring, use file storage:

```bash
monarch auth login --storage file
```

For CI or containers, inject `MONARCH_TOKEN` through the platform's secret
manager rather than committing it or printing it in logs.

If an old `~/.mm/mm_session.pickle` file exists, it is detected for diagnostic
purposes but never read. Authenticate again with `monarch auth login`, then
remove the legacy file manually if desired.

## Development

From the repository root, set up the development environment and run the
checkout directly with `uv run`:

```bash
make setup
uv run monarch --help
uv run monarch accounts list --json
```

`uv run` uses the project's environment and the current source tree, so no
separate global CLI installation is needed while developing. Run the checks
before releasing changes:

```bash
make verify
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for development workflow and
[docs/testing.md](docs/testing.md) for live-test safeguards. Release
instructions are in [docs/RELEASING.md](docs/RELEASING.md).

## Contributing

This is a personally maintained project and is not currently accepting code
contributions, pull requests, or feature requests. See
[CONTRIBUTING.md](CONTRIBUTING.md) for bug-reporting, security, and fork
information.

## License

MIT License. See [LICENSE](LICENSE).

## Acknowledgments

- [monarchmoney](https://github.com/hammem/monarchmoney) — community Python
  library used to communicate with the Monarch Money API
- [Typer](https://typer.tiangolo.com/) — CLI framework
- [Rich](https://rich.readthedocs.io/) — terminal formatting
