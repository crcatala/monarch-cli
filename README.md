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
| `--allow-mutations` | | Authorize remote mutations for this invocation only; place before the command path |
| `--non-interactive` | | Fail before prompting; useful for CI and agents |
| `--help` | | Show help and exit |

### Mutation safety

The CLI is **read-only by default**. Every command has explicit operation
metadata. Read commands make no state changes; `--dry-run` is a validated
`preview`; `remote_authentication` and `local_credential_change` cover login
and logout; and `remote_mutation` covers transaction updates and account
refreshes. The effect taxonomy is `read_only`, `preview`,
`remote_authentication`, `remote_mutation`, and `local_credential_change`.

Remote mutations require the global `--allow-mutations` option on that
invocation. Put it before the command path; it is never persisted in config and
there is no environment-variable equivalent:

```bash
# Blocked safely before authentication or any API call:
monarch transactions update TXN123 --notes "Review"

# Explicitly authorized for this invocation only:
monarch --allow-mutations transactions update TXN123 --notes "Review"
monarch --allow-mutations accounts refresh -a ACC123

# Safe preview; no client or mutation API call is made:
monarch transactions update TXN123 --dry-run --notes "Review"
```

A blocked mutation exits with code `3` and structured `MUTATION_BLOCKED`
output. Mutation authorization is separate from any destructive confirmation
or `--yes` requirement: authorization is checked first, then the second layer
applies. Login and logout remain available without the flag so users can
recover credentials.

### Transaction tags

Tag discovery is read-only:
`monarch transactions tags list` lists available tags and
`monarch transactions tags show TRANSACTION_ID` inspects one assignment.
Authorized tag creation uses `--name` and a six-digit `#RRGGBB` `--color`.
Tag replacement and clearing are explicit full-set operations:
`monarch --allow-mutations --yes transactions tags replace TRANSACTION_ID TAG_ID...`
and `monarch --allow-mutations --yes transactions tags clear TRANSACTION_ID`.
The CLI validates IDs from a read-only discovery request, removes duplicate IDs
in first-seen order, and never exposes incremental add/remove or batch tagging.
An already-equal set is a deterministic no-op. The released client provides no
conditional-write or idempotency guarantee, so concurrent assignments can still
change between discovery and replacement; verify an ambiguous or mismatched
write with `transactions tags show` before retrying.

### Transaction splits

`monarch transactions splits show TRANSACTION_ID` is read-only and displays the
parent amount and current split rows. Replace is a complete-set operation:

```bash
monarch --allow-mutations --yes transactions splits replace TXN123 \\
  --splits-json '[{"merchantName":"Store","amount":-10.00,"categoryId":"CAT1"}]'
monarch --allow-mutations --yes transactions splits replace TXN123 \\
  --splits-file ./splits.json
monarch --allow-mutations --yes transactions splits clear TXN123
```

Exactly one source is required. Inline and file JSON are bounded to 64 KiB;
replacement arrays contain 1–100 records, each with exactly non-empty
`merchantName`, finite `amount`, and opaque non-empty `categoryId`. Amounts use
signed decimal dollars with precision 18 and scale 2 (at most two fractional
digits, maximum absolute value `9999999999999999.99`). Expenses and their
splits are negative; income and its splits are positive; a zero parent may only
have zero-valued rows. A replacement must contain at least one row and its
signed total must equal the parent amount at two-decimal precision. Clear is
the only way to send the canonical empty list; pending/unsupported server
responses remain explicit failures rather than being simulated locally.

Split writes read the parent before mutation, inspect payload-level errors, and
read the resulting splits back. Never retry an ambiguous or verification-
mismatched write until `transactions splits show` confirms remote state.
Merge, per-split edits, notes/tags/goals, merchant IDs, and multi-transaction
split updates are intentionally not exposed.

After remote execution is attempted, every remote mutation returns the shared
`mutation-outcome.v1` envelope on stdout (see
[docs/mutation-outcomes.md](docs/mutation-outcomes.md)): top-level
`succeeded` (exit `0`), `failed` (normal nonzero error exit), `ambiguous` and
`partial` (both exit `4`), ordered per-item outcomes with sanitized error
objects, and a required `verification` object whenever any item is ambiguous.
Pre-execution authorization and validation failures keep the structured error
contract and are never misrepresented as mutation outcomes.

### Non-interactive automation

Use `--non-interactive` when stdin is unavailable or a command must never wait
for input. The same policy can be enabled with `MONARCH_NON_INTERACTIVE=1` or
`non_interactive = true` in the config file. A blocked prompt is rejected
before stdin, `/dev/tty`, password, MFA, storage-choice, or confirmation input
is read. It exits with stable code `5`; errors are one JSON object on stderr
with code `PROMPT_BLOCKED` and an actionable `details.remedy` (stdout remains
empty). For example:

```bash
monarch --non-interactive auth login
# exit 5; stderr: {"error": true, "code": "PROMPT_BLOCKED", ...}
```

Non-interactive mode does not authorize mutations and never answers a
confirmation automatically. Pass explicit values or use deliberate channels
such as `transactions batch-update --stdin`; use `--allow-mutations`
separately when a remote mutation is authorized.

### Configuration

The default config file is `~/.config/monarch-cli/config.toml` (or the path
selected by `MONARCH_CONFIG_DIR`). Automation may set:

```toml
non_interactive = true
```

The CLI flag and environment variable are convenient per-invocation choices;
all three sources enable the same shared prompt policy.

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

monarch --allow-mutations accounts refresh         # Refresh all account data
monarch --allow-mutations accounts refresh -a ACC123  # Refresh specific account
```

### transactions

```bash
# List with filters
monarch transactions list
monarch transactions list --limit 50 --offset 0
monarch transactions list --preset this-month
monarch transactions list --start 2024-01-01 --end 2024-01-31
monarch transactions list --account ACC123
monarch transactions list --category CAT123 --tag TAG456
monarch transactions list --pending              # Tri-state filter
monarch transactions list --no-pending           # Explicit negative filter
monarch transactions list --needs-review
monarch transactions list --visibility all_transactions
monarch transactions list --search "grocery"
# Repeat --account, --category, and --tag for multiple IDs.
# --limit accepts 1-1000; use --offset for subsequent pages.
# Normal output is a backward-compatible list; --raw preserves totalCount
# and the complete upstream pagination envelope.

# Inspect one transaction (redirects pending IDs by default)
monarch transactions get TXN123 --json
monarch transactions get TXN123 --strict --json  # Disable posted redirect

# Update a transaction
monarch --allow-mutations transactions update TXN123 --amount 25.50
monarch --allow-mutations transactions update TXN123 --description "Coffee Shop"
monarch --allow-mutations transactions update TXN123 --category CAT456
monarch --allow-mutations transactions update TXN123 --notes "Business expense"
monarch --allow-mutations transactions update TXN123 --date 2024-01-15
monarch transactions update TXN123 --dry-run --amount 30.00  # Preview; no flag needed

# Batch update multiple transactions
monarch --allow-mutations transactions batch-update TXN1 TXN2 TXN3 --category CAT456
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

# Number of retry attempts for transient failures on read commands only
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
| `MONARCH_MAX_RETRIES` | Max API retry attempts for read commands | `3` |
| `MONARCH_NO_COLOR` | Disable colored output | `false` |
| `NO_COLOR` | Standard color disable ([no-color.org](https://no-color.org)) | - |

### Read retries and mutation ambiguity

The configured `timeout` is a timeout **per API attempt**. Read commands may
retry transient transport failures up to `max_retries` times. Current remote
mutations—account refresh, transaction update, and each item of batch
update—always make one attempt; they never inherit the read retry setting.
There is no generic retry override because a request that times out or loses
its connection may already have changed remote state.

Every remote mutation returns the versioned `mutation-outcome.v1` envelope on
stdout after the request is attempted (see
[docs/mutation-outcomes.md](docs/mutation-outcomes.md) for the full contract).
Account refresh and single transaction updates report one item; batch updates
report one ordered item per requested transaction. All-succeeded outcomes
exit `0`; a definitive failure with no successes is a `failed` outcome on the
normal nonzero error exit; any ambiguity or mixture of outcomes is an
`ambiguous` or `partial` outcome and exits `4`.

If a mutation request may have been dispatched but its result is unknown, the
affected items are reported `ambiguous`, the envelope's `verification` object
is required (with a tokenized safe command when one exists), and the CLI
exits `4`. Verify the record or refresh status before retrying; never retry an
ambiguous mutation blindly. Interrupting a mutation (Ctrl-C) is also treated
as ambiguous and reported the same way — a mid-batch interrupt reports every
requested transaction as ambiguous. Error objects are sanitized: stable
`code`, `message`, and object-valued `details`, never credentials, raw request
bodies, or arbitrary upstream exception text.

Authentication is intentionally outside this financial mutation executor:
`auth login` is recorded as remote authentication plus local credential change,
and local credential writes/deletes are not covered by these mutation retry
semantics.

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

**Transactions:** `id`, `date`, `amount`, `description`, `category`, `account_id`, `is_pending`, `needs_review`, `review_status`, `notes`

#### Normalization semantics (v1)

Normalized output is produced by `monarch_cli.transformers`; `--raw` bypasses
it and returns the upstream structure verbatim (including null containers and
unknown fields).

- Unavailable non-boolean values normalize to `null`. Financial values are
  never invented: a missing balance or transaction amount is `null`, not `0`.
- `is_active`, `is_manual`, and `is_pending` are always booleans. Absent or
  `null` sources default to `is_active=true` (not hidden), `is_manual=false`,
  and `is_pending=false`. `is_pending` reads the upstream `pending` field.
- `description` falls back deterministically: non-empty `merchant.name`,
  then `plaidName`, then `null`.
- `needs_review` and opaque `review_status` are independent fields. List
  responses preserve `review_status` when supplied; detail `review_status` is
  nullable because the released public detail query may omit it.
- Unknown additive upstream fields are ignored by normalized output.
- Cashflow period aggregates are the one documented numeric-default
  exception: a period with no data reports `0` totals.

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

#### Gated live mutation contract suite

`make test-live-mutation` is a separately gated, disposable-fixture mutation
contract suite. It mutates only a uniquely named manual account and uniquely
marked manual transaction that the suite itself creates for that run, then
deletes both. Existing household records are never mutation targets.

Request limits and runtime: the suite spaces CLI subprocess invocations with
the same one-second default delay as the read-only suite (`MONARCH_LIVE_DELAY`
can increase it), and bounds every CLI call with a 60-second timeout. A full
lifecycle run (create account, create transaction, update notes, read back,
delete both) typically completes in under a minute of wall time plus the
per-call delays; expect roughly ten CLI/API calls per run.

```bash
# 1. Authenticate with the exact installed CLI used by the suite:
uv run monarch auth login
# 2. Export the exact opaque ID of the owner-approved disposable household
#    (never commit or persist it):
export MONARCH_LIVE_MUTATION_HOUSEHOLD_ID=<approved-household-id>
# 3. Run the gated suite locally:
MONARCH_LIVE_MUTATION_TESTS=1 make test-live-mutation
```

Layered gating: mutation nodes carry both `live` and `live_mutation` markers;
`make test-live` selects `-m "live and not live_mutation"` so mutation nodes
are never collected by read-only runs; a collection guard additionally
deselects `live_mutation` nodes unless `MONARCH_LIVE_MUTATION_TESTS=1`; and an
independent runtime guard fails closed before fixture setup. Before the first
mutation, the suite performs a minimal read-only `myHousehold { id }` lookup
and refuses to proceed unless it exactly matches the exported approved ID.
Only the transaction-notes update runs through the installed public CLI with
the global `--allow-mutations` authorization.

Residual risks and manual recovery: each run journals its intended and
observed fixture effects to a git-ignored `.monarch-live-mutation-recovery/<run-id>.json`
manifest (directory mode `0700`, file mode `0600`). The manifest contains only
operation names, the high-entropy run marker, fixture remote IDs, statuses,
and recovery steps — never credentials, household IDs, financial values, or
raw payloads. Cleanup is conservative and single-attempt: a timed-out or
disconnected create/delete is never retried automatically. If a delete does
not definitively succeed, the manifest is preserved and the failure message
prints its absolute path; inspect the disposable household and delete only
records matching the manifest's run marker (`mc584r-<run-id>`). A manifest is
removed only after both fixture deletions are definitively confirmed. If
`monarch` is not installed in the pytest environment's scripts directory, the
suite fails closed with setup guidance rather than falling back to a
different environment (`uv run --no-sync monarch` is a manual fallback only).
The dedicated live mutation run is an explicit human gate: merge evidence
must not claim the contract is live-proven until an operator-authenticated
gated run succeeds.

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
