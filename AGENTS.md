# AGENTS.md

Codex handoff for `monarch-cli`.

Goal: make an agent useful in this repo fast, including safe command-line
navigation of Monarch Money without opening the web UI.

## Start Here

```bash
pwd
git status --short --branch
uv sync --all-extras
uv run monarch --help
```

Rules:
- Read code/docs before edits.
- Keep changes small and reversible.
- Do not stage unrelated local files.
- Do not push unless asked.
- No destructive git commands.
- Prefer `rg` for search.

Full gate:

```bash
make verify
```

This runs format check, Ruff, mypy, and non-live tests.

## Repo Shape

- CLI entrypoint: `src/monarch_cli/main.py`
- Commands: `src/monarch_cli/commands/`
- Auth/session: `src/monarch_cli/commands/auth.py`, `src/monarch_cli/core/session.py`
- API bridge: `src/monarch_cli/core/adapter.py`, `src/monarch_cli/core/async_utils.py`
- Raw GraphQL escape hatch: `src/monarch_cli/commands/api.py`
- Tests: `tests/commands/`, `tests/core/`, `tests/live/`
- Docs: `README.md`, `CHANGELOG.md`

When changing command behavior, update tests and README/CHANGELOG if user-visible.

## Task Tracking

This repo may use `tk` tickets under `.tickets/`.

```bash
tk ready
tk show <id>
tk start <id>
tk add-note <id> "progress"
tk close <id>
```

If `tk` is unavailable, continue from the user request and say so.

## Monarch Auth: No UI

Do not open Monarch Money in a browser for normal repo work. Use the CLI and
the community API wrapper.

Credential priority:
1. `MONARCH_TOKEN`
2. system keyring
3. session file at `~/.config/monarch-cli/session.json` or `MONARCH_SESSION_PATH`

Check current auth state:

```bash
uv run monarch auth status --json
uv run monarch auth doctor
uv run monarch auth ping --json
```

Login:

```bash
uv run monarch auth login
uv run monarch auth login --storage keyring
uv run monarch auth login --storage file
```

`auth login` prompts for email/password and then MFA if Monarch requires it.
The command saves only the session token. Do not ask the user to paste tokens
unless they explicitly choose `MONARCH_TOKEN`.

### Password-Enabled Check

There is no separate unauthenticated "has password enabled" CLI command in this
repo. Validate password login by attempting `uv run monarch auth login`.

Interpretation:
- Success before or after MFA: password login is enabled and the session is valid.
- `MFA required`: password is accepted; ask the user for the MFA code.
- `Login failed: ...`: quote the exact error. If the text indicates invalid
  credentials, SSO/social-only login, or no password set, tell the user to set
  or reset a Monarch password in Monarch's account settings, then rerun login.
- Keyring errors: rerun with `--storage file`.

Never guess auth state from files alone. Confirm with `auth ping --json`.

## Post-Login Smoke Tests

After login, run quick read-only checks:

```bash
uv run monarch auth status --json
uv run monarch auth ping --json
uv run monarch accounts list --json | jq 'length'
uv run monarch categories list --json | jq 'length'
uv run monarch transactions list --limit 5 --json | jq 'length'
uv run monarch budgets list --json | jq 'length'
uv run monarch cashflow summary --preset this-month --json
```

If `jq` is unavailable, run the same commands without the pipe and inspect JSON.

For a deeper API inventory:

```bash
uv run monarch api docs
```

Use `monarch api` for endpoints not yet exposed as first-class commands.

## Safe Monarch Navigation Without UI

Prefer these commands for common workflows:

```bash
# Accounts
uv run monarch accounts list --json
uv run monarch accounts history ACCOUNT_ID --json
uv run monarch accounts recent-balances --json
uv run monarch accounts refresh --wait --timeout 300 --delay 10
uv run monarch accounts refresh-status --json

# Investments
uv run monarch investments holdings --json
uv run monarch investments holdings --account ACCOUNT_ID --json

# Transactions
uv run monarch transactions list --limit 20 --json
uv run monarch transactions list --needs-review --json
uv run monarch transactions list --has-attachments --json
uv run monarch transactions list --missing-attachments --json
uv run monarch transactions show TXN_ID --json
uv run monarch transactions duplicates --json

# Tags and splits
uv run monarch transactions tags list --json
uv run monarch transactions tags set TXN_ID --tag TAG_ID
uv run monarch transactions splits show TXN_ID --json
uv run monarch transactions splits update TXN_ID --splits-file splits.json

# Budgets/categories/reports
uv run monarch budgets list --json
uv run monarch budgets set --category CATEGORY_ID --amount 800 --start YYYY-MM-01
uv run monarch categories list --json
uv run monarch categories groups --json
uv run monarch cashflow recurring --start YYYY-MM-DD --end YYYY-MM-DD --json
```

Mutation commands require extra care:
- Use read commands first to capture IDs.
- Use `--dry-run` when available.
- Use guarded deletes only with explicit user intent and `--yes`.
- For batch edits, pipe IDs from a reviewed JSON/list, not from a broad search
  you have not inspected.

## Live Tests

Live tests hit the real Monarch API. They are local-only and opt-in.

```bash
MONARCH_LIVE_TESTS=1 make test-live
```

Prerequisites:
- Valid session from `uv run monarch auth login`
- `uv run monarch auth ping --json` returns `{"status": "ok", ...}`
- User approves live API calls

Do not run live tests in CI or casually during normal code changes.

## Common CLI Use Cases

Pattern:
1. Discover IDs with `list --json`.
2. Inspect the specific object with `show`/detail commands.
3. Mutate only after the target IDs are confirmed.
4. Re-read the object after mutation.

### Find Account IDs

```bash
uv run monarch accounts list --json | jq -r '.[] | [.id, .name, .institution, .type] | @tsv'
```

Fidelity/Vanguard holdings:

```bash
uv run monarch accounts list --json \
  | jq -r '.[] | select(.institution | test("Fidelity|Vanguard"; "i")) | [.id, .name, .institution] | @tsv'

uv run monarch investments holdings --account ACCOUNT_ID --json
uv run monarch investments holdings --account ACCOUNT_ID --format table
```

Export account balance history:

```bash
uv run monarch accounts history ACCOUNT_ID --json > account-history.json
```

Recent balances/net worth snapshots:

```bash
uv run monarch accounts recent-balances --start YYYY-MM-DD --json
uv run monarch accounts aggregate-snapshots --start YYYY-MM-DD --end YYYY-MM-DD --json
```

Refresh accounts and wait for sync:

```bash
uv run monarch accounts refresh --wait --timeout 300 --delay 10
uv run monarch accounts refresh-status --json
uv run monarch accounts recent-balances --json
```

### Transactions

Find transaction/category/tag IDs:

```bash
uv run monarch transactions list --limit 20 --json \
  | jq -r '.[] | [.id, .date, .amount, .description, .category, .account] | @tsv'

uv run monarch categories list --json | jq -r '.[] | [.id, .name, .group] | @tsv'
uv run monarch transactions tags list --json
```

Create a cash/manual transaction:

```bash
uv run monarch transactions create \
  --date YYYY-MM-DD \
  --account ACCOUNT_ID \
  --amount -25.00 \
  --merchant "Cash" \
  --category CATEGORY_ID \
  --notes "Cash transaction"
```

Delete an accidental manual transaction:

```bash
uv run monarch transactions show TXN_ID --json
uv run monarch transactions delete TXN_ID --yes
```

Review queue:

```bash
uv run monarch transactions list --needs-review --format table
uv run monarch transactions update TXN_ID --clear-review
```

Receipts attached/missing:

```bash
uv run monarch transactions list --has-attachments --format table
uv run monarch transactions list --missing-attachments --format table
uv run monarch transactions attach TXN_ID ./receipt.pdf
```

Tag reviewed transactions as Tax:

```bash
uv run monarch transactions tags list --json
uv run monarch transactions tags create --name Tax --color "#2f855a"
uv run monarch transactions tags set TXN_ID --tag TAX_TAG_ID
```

For multiple reviewed IDs:

```bash
while read -r id; do
  uv run monarch transactions tags set "$id" --tag TAX_TAG_ID
done < reviewed-transaction-ids.txt
```

Split a Costco transaction:

```bash
uv run monarch transactions show TXN_ID --json
uv run monarch transactions splits update TXN_ID --splits-file costco-splits.json
uv run monarch transactions splits show TXN_ID --json
```

Example `costco-splits.json`:

```json
[
  {"amount": 80.0, "category_id": "GROCERIES_CATEGORY_ID"},
  {"amount": 45.0, "category_id": "HOUSEHOLD_CATEGORY_ID"}
]
```

Hide reimbursement transfers from reports:

```bash
uv run monarch transactions list --search "reimbursement" --json \
  | jq -r '.[] | [.id, .date, .amount, .description] | @tsv'

uv run monarch transactions update TXN_ID --hide-from-reports
```

Batch hide only after saving reviewed IDs:

```bash
while read -r id; do
  uv run monarch transactions update "$id" --hide-from-reports
done < reimbursement-transfer-ids.txt
```

Find duplicates:

```bash
uv run monarch transactions duplicates --start YYYY-MM-DD --end YYYY-MM-DD --json
```

### Budgets And Categories

Find Dining category ID:

```bash
uv run monarch categories list --json \
  | jq -r '.[] | select(.name | test("Dining|Restaurants"; "i")) | [.id, .name, .group] | @tsv'
```

Set next month's Dining budget:

```bash
uv run monarch budgets set --category DINING_CATEGORY_ID --amount 800 --start YYYY-MM-01
uv run monarch budgets list --start YYYY-MM-01 --end YYYY-MM-31 --format table
```

Create/delete categories:

```bash
uv run monarch categories groups --json
uv run monarch categories create --group GROUP_ID --name "New Category" --icon N
uv run monarch categories delete CATEGORY_ID --yes
```

### Cashflow / Reports

List recurring subscriptions due in a date range:

```bash
uv run monarch cashflow recurring --start YYYY-MM-DD --end YYYY-MM-DD --format table
```

Cashflow detail and transaction summary:

```bash
uv run monarch cashflow summary --preset this-month --json
uv run monarch cashflow detail --start YYYY-MM-DD --end YYYY-MM-DD --json
uv run monarch cashflow transaction-summary --json
```

Plan/account metadata:

```bash
uv run monarch cashflow subscription --json
uv run monarch cashflow institutions --json
uv run monarch cashflow credit-history --json
```

## Development Flow

Before edits:

```bash
git status --short --branch
tk ready 2>/dev/null || true
```

Add failing focused tests first when behavior changes:

```bash
uv run pytest tests/commands/test_<area>.py -q
```

Then implement the smallest change and rerun:

```bash
uv run ruff format .
uv run ruff check .
uv run mypy src/
uv run pytest -m "not live"
```

Before handoff:

```bash
make verify
git status --short
```

## Git / PR

- Commit messages: conventional commits, e.g. `feat: add account history command`.
- Stage explicit paths in mixed worktrees.
- Keep local-only instruction files out of PRs unless asked.
- Use `gh-axi` for GitHub work when possible; `gh` fallback is fine.
- Draft PR by default unless user asks ready-for-review.

Useful checks:

```bash
gh auth status
gh pr view --json number,title,state,isDraft,url
gh pr checks <number>
```

## Blocker Format

When blocked, report:
- what failed
- exact command and error
- what is missing
- next concrete step
