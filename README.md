# Monarch CLI

[![PyPI version](https://badge.fury.io/py/monarch-cli.svg)](https://badge.fury.io/py/monarch-cli)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A command-line interface for [Monarch Money](https://www.monarchmoney.com/), a personal finance platform that helps you track spending, manage budgets, and monitor your net worth across all your accounts in one place.

> **Disclaimer:** This is an unofficial, community-maintained project and is not affiliated with, endorsed by, or connected to Monarch Money in any way.

## Features

- 🔐 **Secure authentication** with session persistence (keyring or file storage)
- 📊 **Multiple output formats** (plain, JSON, table, CSV, NDJSON) for flexible processing
- 🔧 **Scriptable** - structured JSON output auto-detected when piped
- 📅 **Smart date presets** (`--preset this-month`, `--preset ytd`)
- ✏️ **Transaction updates** with dry-run preview support
- 🔄 **Account refresh** to sync latest data from institutions

## Installation

### With pip

```bash
pip install monarch-cli
```

### With uv (recommended)

```bash
uv tool install monarch-cli
```

### With pipx

```bash
pipx install monarch-cli
```

### Verify installation

```bash
monarch --version
```

## Quick Start

### 1. Authenticate

```bash
# Interactive login (prompts for email/password)
monarch auth login

# Check authentication status
monarch auth status
```

### 2. List your accounts

```bash
# Human-readable format
monarch accounts list

# JSON format for scripting
monarch accounts list --json
```

### 3. View transactions

```bash
# Recent transactions
monarch transactions list

# This month's transactions
monarch transactions list --preset this-month

# Search for specific transactions
monarch transactions list --search "coffee" --limit 20
```

### 4. Check your budget

```bash
# Current budget status
monarch budgets list

# As JSON for processing
monarch budgets list --json
```

## Command Reference

### Global Options

| Option | Short | Description |
|--------|-------|-------------|
| `--version` | `-v` | Show version and exit |
| `--verbose` | `-V` | Show operational progress messages |
| `--debug` | | Show stack traces on errors |
| `--json` | | Output in JSON format |
| `--quiet` | `-q` | Output only IDs, one per line |
| `--no-color` | | Disable colored output |
| `--help` | | Show help and exit |

### auth

Authentication management commands.

```bash
monarch auth login               # Interactive login
monarch auth login -s keyring    # Use system keyring storage
monarch auth login -s file       # Use file-based storage

monarch auth status              # Check authentication status
monarch auth logout              # Log out and clear credentials
monarch auth ping                # Test API connectivity
monarch auth doctor              # Diagnose authentication setup
monarch auth setup               # Show setup instructions
```

### accounts

```bash
monarch accounts list            # List all linked accounts
monarch accounts list --json     # JSON format
monarch accounts list --format table  # Table format
monarch accounts list --raw      # Raw API response

monarch accounts refresh         # Refresh all account data
monarch accounts refresh ACC123  # Refresh specific account
```

### transactions

```bash
# List with filters
monarch transactions list
monarch transactions list --limit 50 --offset 0
monarch transactions list --preset this-month
monarch transactions list --start 2024-01-01 --end 2024-01-31
monarch transactions list --account ACC123
monarch transactions list --search "grocery"

# Update a transaction
monarch transactions update TXN123 --amount 25.50
monarch transactions update TXN123 --description "Coffee Shop"
monarch transactions update TXN123 --category CAT456
monarch transactions update TXN123 --notes "Business expense"
monarch transactions update TXN123 --date 2024-01-15
monarch transactions update TXN123 --dry-run --amount 30.00  # Preview

# Batch update multiple transactions
monarch transactions batch-update TXN1 TXN2 TXN3 --category CAT456
```

**Date Presets:**
- `today`, `yesterday`
- `this-week`, `last-week`
- `this-month`, `last-month`
- `last-30-days`, `last-90-days`
- `this-year`, `last-year`, `ytd`
- `all`

### budgets

```bash
monarch budgets list             # Budget status with spent/remaining
monarch budgets list --json      # JSON format
monarch budgets list --format table
```

### cashflow

```bash
monarch cashflow summary                      # Current period
monarch cashflow summary --preset this-month  # This month
monarch cashflow summary --preset ytd         # Year to date
monarch cashflow summary -s 2024-01-01 -e 2024-12-31  # Date range
```

### categories

```bash
monarch categories list          # All transaction categories
monarch categories list --json   # JSON format
```

## Output Formats

Monarch CLI supports multiple output formats for different use cases:

| Format | Description | Best For |
|--------|-------------|----------|
| `plain` | Human-readable text | Terminal display |
| `json` | Pretty-printed JSON | Scripts, parsing |
| `table` | Rich table format | Terminal display |
| `csv` | Comma-separated values | Spreadsheets |
| `compact` | Minimal JSON | Compact storage |
| `ndjson` | Newline-delimited JSON | Stream processing |

```bash
# Explicit format selection
monarch accounts list --format json
monarch accounts list --format table
monarch accounts list --format csv

# Shorthand for JSON
monarch accounts list --json

# Auto-detection: JSON when piped
monarch accounts list | jq '.[0]'
```

## Configuration

Monarch CLI uses a **layered configuration system** (similar to Git, kubectl, Docker):

```
Config File → Environment Variables → CLI Flags
(lowest precedence)                  (highest precedence)
```

Each layer overrides the previous, giving you flexible control over defaults and per-command behavior.

### Config File

Create `~/.config/monarch-cli/config.toml` to set persistent defaults:

```toml
# Output format: plain, json, table, csv, compact
format = "plain"

# Enable colored output (respects NO_COLOR env var)
color = true

# Show operational progress messages
verbose = false

# API request timeout in seconds
timeout = 30

# Number of retry attempts for transient failures
max_retries = 3
```

### Environment Variables

Environment variables override config file values:

| Variable | Description | Default |
|----------|-------------|---------|
| `MONARCH_TOKEN` | Session token for authentication | - |
| `MONARCH_CONFIG_DIR` | Directory for config files | `~/.config/monarch-cli` |
| `MONARCH_SESSION_PATH` | Path to session file | `<config_dir>/session.json` |
| `MONARCH_FORMAT` | Default output format (`plain`, `json`, `table`, `csv`, `compact`) | `plain` |
| `MONARCH_VERBOSE` | Enable verbose output (`1`, `true`, `yes`) | `false` |
| `MONARCH_DEBUG` | Enable debug mode with stack traces | `false` |
| `MONARCH_QUIET` | Output only IDs, one per line | `false` |
| `MONARCH_TIMEOUT` | API timeout in seconds | `30` |
| `MONARCH_MAX_RETRIES` | Max API retry attempts | `3` |
| `MONARCH_NO_COLOR` | Disable colored output | `false` |
| `NO_COLOR` | Standard color disable ([no-color.org](https://no-color.org)) | - |

### CLI Flags

CLI flags override both config file and environment variables:

```bash
# Override format for this command
monarch accounts list --json

# Override timeout for slow connections  
monarch transactions list --timeout 60

# Disable color for this command
monarch accounts list --no-color

# Enable verbose output
monarch accounts list --verbose
```

### Authentication Priority

Session credentials are resolved in this order:
1. `MONARCH_TOKEN` environment variable
2. System keyring (if available)
3. Session file (`~/.config/monarch-cli/session.json`)

Legacy pickle session files (`~/.mm/mm_session.pickle`) are not a credential
source and are never read (see [Troubleshooting](#troubleshooting)). On POSIX,
the session file is created with mode `0600` (owner read/write only); on
Windows it inherits the default NTFS ACLs of your profile directory.

## Scripting & Automation

Monarch CLI is designed for scripting and automation. When output is piped (non-TTY), it automatically outputs JSON:

```bash
# Auto-JSON when piped
ACCOUNTS=$(monarch accounts list | jq '.')

# Explicit JSON mode
monarch transactions list --json --preset this-month

# Quiet mode for IDs only
monarch accounts list --quiet
# Output:
# ACC123456
# ACC789012
```

### Example: Python Integration

```python
import subprocess
import json


def get_transactions(preset="this-month"):
    result = subprocess.run(
        ["monarch", "transactions", "list", "--preset", preset, "--json"],
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def categorize_transaction(transaction_id, category_id):
    subprocess.run(["monarch", "transactions", "update", transaction_id, "--category", category_id])


# Get this month's transactions for analysis
transactions = get_transactions("this-month")
print(f"Found {len(transactions)} transactions")
```

### Stable Schema Fields

These output fields are guaranteed stable across versions:

**Accounts:** `id`, `name`, `balance`, `type`, `is_active`, `institution`, `last_synced`

**Transactions:** `id`, `date`, `amount`, `description`, `category`, `account_id`, `is_pending`, `notes`

## Shell Completions

Enable tab completion for commands, options, and arguments:

### Bash

```bash
monarch --install-completion bash
source ~/.bashrc
```

### Zsh

```bash
monarch --install-completion zsh
source ~/.zshrc
```

### Fish

```bash
monarch --install-completion fish
source ~/.config/fish/completions/monarch.fish
```

### Verify

```bash
monarch <TAB>
# Shows: accounts  auth  budgets  cashflow  categories  transactions
```

## Troubleshooting

### Authentication Issues

Run the diagnostic command to identify problems:

```bash
monarch auth doctor
```

This checks:
- Session file existence and permissions
- Token validity
- API connectivity
- Keyring availability

### Common Issues

**"Not authenticated" error:**
```bash
# Re-authenticate
monarch auth login

# Or check status first
monarch auth status
```

**Connection timeout:**
```bash
# Increase timeout
MONARCH_TIMEOUT=60 monarch accounts list

# Or check connectivity
monarch auth ping
```

**Keyring not available (headless systems):**
```bash
# Use file storage instead
monarch auth login -s file
```

**Legacy pickle session file (`~/.mm/mm_session.pickle`):**

Older releases stored sessions as a pickle file at `~/.mm/mm_session.pickle`.
Pickle files can execute arbitrary code when loaded, so this CLI never reads
them: a legacy file is **not** an active credential and is ignored during
credential lookup. If one exists, `auth status` and `auth doctor` will report
its presence and ask you to re-authenticate:

```bash
monarch auth login

# Optionally remove the legacy file once you have re-authenticated
rm ~/.mm/mm_session.pickle
```

The CLI never reads, migrates, or deletes this file; cleanup is always an
explicit user action.

### Debug Mode

For detailed error information:

```bash
monarch --debug accounts list
```

## Development

### Setup

```bash
git clone https://github.com/crcatala/monarch-cli.git
cd monarch-cli

# Install with dev dependencies
make setup
# Or manually:
uv sync --all-extras
```

### Testing

```bash
make test          # Run tests (live tests excluded)
make lint          # Lint and type check
make verify        # All checks (format, lint, types, tests)
```

#### Local live API tests

The live suite is an opt-in, read-only smoke test for local development. It
requires an authenticated Monarch account and an active internet connection;
use a dedicated test account rather than personal financial data. Credentials
and API responses must never be committed or used in CI.

The suite runs bounded checks for authentication status/ping, accounts,
transactions (limited to five records), categories, budgets, and cashflow:

```bash
# Authenticate first with `monarch auth login`, then:
MONARCH_LIVE_TESTS=1 make test-live
```

`make test-live` is the only supported runner. Tests are marked `live`, are
skipped unless `MONARCH_LIVE_TESTS=1` is set, and wait at least one second
between API calls by default (`MONARCH_LIVE_DELAY` can increase that delay).
The ordinary `make test` and CI command explicitly select `-m "not live"`.
Live failures usually indicate missing/expired authentication or API contract
drift; do not rerun repeatedly when a service or rate-limit error occurs.

### Pre-commit hooks

Git hooks are managed with [prek](https://github.com/j178/prek):

```bash
uv run prek install  # Install hooks
```

### Releasing

Releases are a two-step process:

1. **Create GitHub Release** (tags, changelog, artifacts):
   ```bash
   make release-dry  # Preview first
   make release      # Create release
   ```

2. **Publish to PyPI** (separate step):
   ```bash
   uv run twine upload dist/*
   ```

See [docs/RELEASING.md](docs/RELEASING.md) for full instructions including TestPyPI setup and troubleshooting.

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run `make verify` to ensure all checks pass
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## License

MIT License - see [LICENSE](LICENSE) for details.

## Acknowledgments

- [monarchmoney](https://github.com/hammem/monarchmoney) - The community Python library for Monarch Money API
- [Typer](https://typer.tiangolo.com/) - CLI framework
- [Rich](https://rich.readthedocs.io/) - Terminal formatting
