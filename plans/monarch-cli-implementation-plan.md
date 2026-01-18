# Monarch CLI Implementation Plan

> A Python CLI wrapper around [`monarchmoneycommunity`](https://github.com/bradleyseanf/monarchmoneycommunity) for AI agent integration with Monarch Money financial data.

## Project Overview

### Background

The [`monarchmoneycommunity`](https://github.com/bradleyseanf/monarchmoneycommunity) library is an actively maintained fork of the original `monarchmoney` Python client. It provides 43 API methods for Monarch Money and fixes critical issues in the upstream library. This project creates a CLI wrapper that enables non-interactive, scriptable access to Monarch Money for AI agents.

#### Why `monarchmoneycommunity`?

The original [`monarchmoney`](https://github.com/hammem/monarchmoney) library is no longer maintained and has breaking issues:
- ❌ API endpoint broken (`api.monarchmoney.com` → `api.monarch.com` domain change)
- ❌ Auth persistence broken (#139)
- ❌ `get_budgets()` query broken (legacy goals removal)

The community fork fixes all these and is actively maintained (last commit: Jan 2026).

#### Why Direct Library Instead of MCP Server?

We initially considered wrapping [`monarch-mcp-server`](https://github.com/robcerda/monarch-mcp-server), but analysis revealed:

| Factor | MCP Server | Direct Library |
|--------|-----------|----------------------|
| API Coverage | 10 methods | **43 methods** |
| Maintenance | gql<4.0 conflict, stale | Active community fork |
| Dependencies | MCP protocol (not needed) | Clean |
| Added Value | MCP wrapper only | Direct access |

The MCP server is just a thin wrapper (~300 LOC) around `monarchmoney` with keyring auth. We can port and extend the auth pattern (~120 LOC with dual-backend support) and get 4x the API coverage with fewer dependencies.

### Goals
- Provide CLI access to commonly-used `monarchmoney` API methods (prioritized subset of 43 available)
- Optimize for AI agent consumption (structured JSON output, error codes, schema support)
- Flexible authentication: OS keyring (secure, default) or session file (portable)
- Minimal new code - thin wrapper only
- Enable automation and scripting for personal finance workflows
- Robust error handling with retries and clear feedback

### Non-Goals (v1)
- TUI or interactive mode
- New API functionality beyond what `monarchmoney` provides
- Multi-user OAuth flows
- Local caching or offline mode (deferred to v1.1)
- Priority 4 methods (account creation/deletion, splits, etc. - web UI better)

### Tech Stack
- **Language**: Python 3.12+
- **CLI Framework**: Typer (auto-generated help, rich integration)
- **API Client**: `monarchmoneycommunity` library (imported as `monarchmoney`)
- **Auth**: Dual-backend token storage - OS keyring (secure, default) or session file (portable)
- **Output**: JSON (default), table, CSV, compact, NDJSON for streaming
- **Config**: Environment variables with XDG/platformdirs support
- **Testing**: pytest with CliRunner (live tests for local dev only)

---

## CLI Design Principles

Based on [clig.dev](https://clig.dev) guidelines and the [TypeScript CLI Playbook](./cli-playbook.md).

### I/O Contract

| Stream | Purpose | Examples |
|--------|---------|----------|
| **stdout** | Primary output (data, results) | JSON output, account lists |
| **stderr** | Progress, warnings, errors | "Fetching accounts...", "Warning: token expiring" |

**Why?** Allows piping: `monarch accounts list --json | jq '.[] | .balance'`

### Exit Codes

| Code | Meaning | When |
|------|---------|------|
| 0 | Success | Command completed |
| 1 | General error | API error, auth failure |
| 2 | Usage error | Bad arguments, missing required flags |
| 130 | Interrupted | User pressed Ctrl-C |

### Config Precedence (highest to lowest)

1. CLI flags (`--format json`)
2. Environment variables (`MONARCH_FORMAT=json`)
3. Defaults

> **Note:** TOML config file support (`~/.config/monarch-cli/config.toml`) deferred to v1.1. Environment variables are sufficient for MVP.

### Global Flags (all commands)

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `-h, --help` | bool | - | Show help |
| `--version` | bool | - | Show version |
| `-v, --verbose` | bool | false | Verbose output (to stderr) |
| `--format, -f` | choice | json | Output format: json, table, csv, compact |
| `--ndjson` | bool | false | Stream results as newline-delimited JSON |
| `--raw` | bool | false | Output raw API response without transforms |
| `--no-color` | bool | false | Disable colors (also respects `NO_COLOR` env) |
| `--quiet, -q` | bool | false | Minimal output (IDs only) |
| `--dry-run` | bool | false | Preview operation without executing (mutations) |

> **Deferred to v1.1:** `--no-cache` (when caching is implemented)

### Secrets Handling ⚠️

**Never accept secrets via command-line flags.** They appear in:
- Shell history (`~/.bash_history`, `~/.zsh_history`)
- Process listings (`ps aux`)

**Our approach:**
- Store auth token in OS keyring (secure, default) or session file (portable, JSON with strict perms)
- Interactive login via `monarch auth login` (prompts for password and storage choice)
- Support `MONARCH_TOKEN` env var as fallback (documented risk)

```bash
# ✅ Good: Interactive login
monarch auth login

# ✅ Good: Token from env (for CI/automation)
export MONARCH_TOKEN="..."
monarch accounts list

# ❌ Bad: Token as flag (NEVER do this)
monarch --token "..." accounts list  # DON'T IMPLEMENT THIS
```

### TTY Detection

| Context | Behavior |
|---------|----------|
| TTY (interactive terminal) | Colors, progress spinners, prompts allowed |
| Non-TTY (piped/scripted) | No colors, no spinners, no prompts, JSON preferred |

```python
import sys
if sys.stdout.isatty():
    # Interactive: show spinner, colors
else:
    # Scripted: minimal output, no prompts
```

### Response Time

Print something to stderr within 100ms, especially before network I/O:

```python
# ✅ Good: Immediate feedback with spinner
with spinner("Fetching accounts..."):
    accounts = await client.get_accounts()

# ❌ Bad: Silent for 2+ seconds while fetching
accounts = await client.get_accounts()  # User thinks it's frozen
```

### Signal Handling

| Signal | Behavior |
|--------|----------|
| SIGINT (Ctrl-C) | Print "Interrupted", exit 130 |
| SIGTERM | Print "Terminated", exit 143 |

```python
import signal
import sys

def handle_sigint(signum, frame):
    print("\nInterrupted.", file=sys.stderr)
    sys.exit(130)

signal.signal(signal.SIGINT, handle_sigint)
```

### Help Text with Examples

Every command should have examples in its help:

```
$ monarch transactions list --help

List transactions with optional filters.

Usage: monarch transactions list [OPTIONS]

Options:
  -l, --limit INTEGER   Max transactions to return [default: 100]
  -s, --start TEXT      Start date (YYYY-MM-DD)
  -e, --end TEXT        End date (YYYY-MM-DD)
  -p, --preset TEXT     Date preset: today, this-week, this-month, last-30-days, ytd
  -a, --account TEXT    Filter by account ID
  -q, --search TEXT     Search transactions
  -f, --format TEXT     Output format [default: json]

Examples:
  monarch transactions list
  monarch transactions list --preset this-month
  monarch transactions list --limit 50 --start 2024-12-01
  monarch transactions list --account ACC123 --format table
  monarch transactions list --json | jq '.[].amount'
```

---

## Architecture

### Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        CLI Layer                            │
│  (Typer commands with argument parsing)                     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     Service Layer                           │
│  services/*.py: business logic, retries, error mapping      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  Adapter / Client Layer                     │
│  adapter.py: isolates upstream library private details      │
│  session.py: dual-backend auth (keyring + file)             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 MonarchMoney Community Library              │
│  43 async methods, GraphQL client for Monarch Money API     │
└─────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

1. **Adapter Pattern**: All access to `monarchmoneycommunity` private attributes (`_headers`, `_token`) is isolated in `adapter.py`. This protects against upstream changes.

2. **Service Layer**: Business logic (transforms, retries, error mapping) lives in `services/*.py`, not in command handlers. Commands stay thin.

3. **Transformers**: Data transformation from raw API responses to stable CLI schemas lives in `transformers/*.py`, making it testable in isolation.

---

## Source Code Analysis

### Auth Pattern (Dual Storage Support)

We support two token storage backends, letting users choose during login:

| Storage | Location | Security | Use Case |
|---------|----------|----------|----------|
| **Keyring** (default) | OS credential store | ✅ Encrypted at rest | Recommended for most users |
| **Session file (JSON)** | `~/.config/monarch-cli/session.json` | ⚠️ Plain file (0600 perms) | Portability, containers |
| **Session file (compat)** | `~/.mm/mm_session.pickle` | ❌ Unsafe (pickle) | Only for library interop (opt-in) |

**Security Note**: The default session file uses JSON with atomic writes and 0600 permissions, not pickle. Pickle is only available as explicit opt-in (`--storage file-compat`) for users who need compatibility with the `monarchmoney` library's session file.

**Load order:** When loading a token, we check keyring first, then JSON session file, then (if enabled) compat pickle. This allows seamless migration and compatibility.

### Available `monarchmoney` Methods (43 total)

The library provides async methods that return Python dicts. We prioritize based on typical user needs:

#### Priority 1: Core Daily Use (MVP) ✅
These cover 90% of what users do in Monarch Money:

| Method | CLI Command | Description |
|--------|-------------|-------------|
| `login()` | `monarch auth login` | Interactive auth with MFA support |
| `get_accounts()` | `monarch accounts list` | List all linked accounts |
| `get_transactions()` | `monarch transactions list` | List/filter transactions |
| `get_budgets()` | `monarch budgets list` | Budget status with spent/remaining |
| `get_cashflow_summary()` | `monarch cashflow summary` | Income/expense totals |
| `get_transaction_categories()` | `monarch categories list` | List categories (needed for IDs) |
| `update_transaction()` | `monarch transactions update` | Recategorize, add notes, etc. |
| `request_accounts_refresh()` | `monarch accounts refresh` | Sync from banks |

#### Priority 2: Power User Features 🔧
Useful for automation and detailed tracking:

| Method | CLI Command | Description |
|--------|-------------|-------------|
| `create_transaction()` | `monarch transactions create` | Manual transaction entry |
| `delete_transaction()` | `monarch transactions delete` | Remove transactions |
| `get_transaction_tags()` | `monarch tags list` | List available tags |
| `set_transaction_tags()` | `monarch transactions tag` | Apply tags to transactions |
| `get_recurring_transactions()` | `monarch recurring list` | Upcoming bills/subscriptions |
| `get_account_holdings()` | `monarch accounts holdings` | Investment positions |
| `set_budget_amount()` | `monarch budgets set` | Adjust budget amounts |
| `get_cashflow()` | `monarch cashflow detailed` | Full breakdown by category/merchant |

#### Priority 3: Account Management 📊
Less frequent but important for setup:

| Method | CLI Command | Description |
|--------|-------------|-------------|
| `get_account_history()` | `monarch accounts history` | Balance over time |
| `get_recent_account_balances()` | `monarch accounts balances` | Daily balance snapshots |
| `update_account()` | `monarch accounts update` | Rename, hide, etc. |
| `get_institutions()` | `monarch institutions list` | Connection status |
| `get_aggregate_snapshots()` | `monarch networth history` | Net worth over time |

#### Priority 4: Rarely Used / Admin ⚙️
Power-user only, consider omitting from v1:

| Method | Description | Recommendation |
|--------|-------------|----------------|
| `create_manual_account()` | Create manual accounts | Defer (web UI better) |
| `delete_account()` | Delete accounts | Defer (destructive) |
| `get_transaction_details()` | Single txn deep details | Covered by list |
| `get_transaction_splits()` | Split transaction info | Niche use case |
| `update_transaction_splits()` | Modify splits | Complex, defer |
| `create_transaction_category()` | Create new categories | Defer (web UI better) |
| `delete_transaction_category()` | Delete categories | Defer (destructive) |
| `create_transaction_tag()` | Create new tags | Defer |
| `get_transaction_category_groups()` | Category group metadata | Internal use |
| `get_account_type_options()` | Account type enum | Internal use |
| `get_account_snapshots_by_type()` | Snapshots by type | Niche analytics |
| `upload_account_balance_history()` | CSV upload | Niche, complex |
| `get_subscription_details()` | Monarch subscription info | Rarely needed |
| `get_transactions_summary()` | Aggregate stats | Covered by cashflow |

### Recommended MVP Scope

**Phase 1 (MVP):** Priority 1 (8 commands) - covers core daily workflow
**Phase 2:** Priority 2 (8 commands) - power user automation  
**Phase 3:** Priority 3 (5 commands) - account analytics
**Defer/Omit:** Priority 4 (14 methods) - rarely needed, web UI better

---

## Python Ecosystem Conventions

Modern Python tooling for 2024-2026. This section helps coding agents follow best practices.

### Toolchain Overview

| Tool | Purpose | Replaces |
|------|---------|----------|
| **uv** | Package manager, venv, build | pip, pip-tools, virtualenv, pyenv |
| **Ruff** | Linting + formatting | black, isort, flake8, pylint |
| **mypy** | Static type checking | (none, but pyright is alternative) |
| **pytest** | Testing | unittest |

**Why these tools?**
- **uv**: 10-100x faster than pip, by Astral (same team as Ruff)
- **Ruff**: Single tool, 100x faster than alternatives, catches most issues
- **mypy**: Catches type bugs before runtime, well-integrated with editors
- **pytest**: Simple syntax, great plugins, industry standard

### Complete pyproject.toml

```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "monarch-cli"
version = "0.1.0"
description = "CLI for Monarch Money - AI agent friendly financial data access"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.12"
authors = [{name = "Your Name", email = "you@example.com"}]
keywords = ["monarch-money", "cli", "finance", "budgeting", "ai-agent"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Environment :: Console",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3.12",
    "Topic :: Office/Business :: Financial",
    "Typing :: Typed",
]
dependencies = [
    "typer[all]>=0.9.0",
    "monarchmoneycommunity>=1.0.0",
    "keyring>=24.0.0",
    "rich>=13.0.0",
    "platformdirs>=4.0.0",
    "httpx>=0.27.0",  # For retry/timeout handling
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.0.0",

    "ruff>=0.4.0",
    "mypy>=1.10.0",
]

[project.scripts]
monarch = "monarch_cli.main:app"

[project.urls]
Homepage = "https://github.com/yourname/monarch-cli"
Repository = "https://github.com/yourname/monarch-cli"
Issues = "https://github.com/yourname/monarch-cli/issues"

[tool.setuptools.packages.find]
where = ["src"]

# ============================================
# Ruff - Linting & Formatting
# ============================================
[tool.ruff]
target-version = "py312"
line-length = 100
src = ["src", "tests"]

[tool.ruff.lint]
select = [
    "E",      # pycodestyle errors
    "W",      # pycodestyle warnings
    "F",      # pyflakes
    "I",      # isort (import sorting)
    "B",      # flake8-bugbear
    "C4",     # flake8-comprehensions
    "UP",     # pyupgrade (modern Python syntax)
    "ARG",    # flake8-unused-arguments
    "SIM",    # flake8-simplify
]
ignore = [
    "E501",   # line too long (formatter handles this)
]

[tool.ruff.lint.isort]
known-first-party = ["monarch_cli"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"

# ============================================
# Mypy - Type Checking
# ============================================
[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
warn_unused_ignores = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
check_untyped_defs = true
disallow_untyped_decorators = true
no_implicit_optional = true
warn_redundant_casts = true
warn_unused_configs = true

[[tool.mypy.overrides]]
module = ["monarchmoney.*", "keyring.*"]
ignore_missing_imports = true

# ============================================
# Pytest - Testing
# ============================================
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = [
    "-v",
    "--tb=short",
    "--strict-markers",
]
markers = [
    "live: marks tests that call real APIs (deselect with '-m \"not live\"')",
]

[tool.coverage.run]
source = ["src/monarch_cli"]
branch = true
omit = ["*/tests/*"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "raise NotImplementedError",
]
fail_under = 70
```

### Project Structure (src layout)

```
monarch-cli/
├── src/
│   └── monarch_cli/
│       ├── __init__.py          # Package init, exports __version__
│       ├── py.typed             # Marker for type hints (empty file)
│       ├── main.py              # Typer app entry point
│       ├── commands/            # CLI command handlers (thin)
│       │   ├── __init__.py
│       │   ├── auth.py          # login, status, logout, setup, doctor, ping
│       │   ├── accounts.py
│       │   ├── transactions.py
│       │   ├── budgets.py
│       │   ├── cashflow.py
│       │   └── categories.py
│       ├── core/                # Infrastructure
│       │   ├── __init__.py
│       │   ├── adapter.py       # Isolates monarchmoney private details
│       │   ├── session.py       # Dual-backend session management
│       │   ├── async_utils.py   # run_async() helper
│       │   ├── config.py        # Configuration system
│       │   ├── exceptions.py    # Exception hierarchy
│       │   ├── error_handler.py # Error handling decorator
│       │   ├── retry.py         # Retry with exponential backoff
│       │   ├── cache.py         # TTL caching (v1.1)
│       │   └── dates.py         # Date utilities and presets
│       ├── services/            # Business logic layer
│       │   ├── __init__.py
│       │   ├── accounts.py
│       │   ├── transactions.py
│       │   ├── budgets.py
│       │   └── cashflow.py
│       ├── transformers/        # API response → CLI output
│       │   ├── __init__.py
│       │   ├── accounts.py
│       │   ├── transactions.py
│       │   └── budgets.py
│       └── output/
│           ├── __init__.py      # JSON, table, CSV, compact, NDJSON
│           ├── formatters.py
│           └── progress.py      # Spinners and progress bars
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # Shared fixtures
│   ├── test_auth.py
│   ├── test_accounts.py
│   ├── test_transactions.py
│   ├── test_output.py
│   └── live/                    # Real API tests (local dev only)
│       ├── __init__.py
│       └── test_live_api.py
├── pyproject.toml               # ALL config in one file
├── uv.lock                      # Lockfile (committed)
├── README.md
├── LICENSE
├── CHANGELOG.md
└── .github/
    └── workflows/
        └── ci.yml
```

**Why src layout?**
- Prevents `import monarch_cli` from accidentally importing local folder instead of installed package
- Required for proper editable installs (`uv pip install -e .`)
- Industry standard for publishable packages

### Verification Script

Create a single command that runs all checks. Coding agents should run this after every change.

#### Option A: Parallel Runner (Recommended for Agents)

Use the [`run-parallel`](https://gist.github.com/mitsuhiko/a4b6b70e96c8075b92a4de00b340cc52) script by Armin Ronacher for parallel execution with live status:

```bash
# Download to project
curl -o scripts/run-parallel.py https://gist.githubusercontent.com/mitsuhiko/a4b6b70e96c8075b92a4de00b340cc52/raw

# Make executable
chmod +x scripts/run-parallel.py
```

**Create `scripts/verify.py`:**
```python
#!/usr/bin/env -S uv run --script
"""Run all verification checks in parallel."""
import subprocess
import sys

# Use run-parallel for parallel execution with pretty output
result = subprocess.run([
    "uv", "run", "scripts/run-parallel.py",
    "--fail-fast",
    "format",    "uv run ruff format --check .",
    "lint",      "uv run ruff check .",
    "typecheck", "uv run mypy src/",
    "test",      "uv run pytest -x",
])
sys.exit(result.returncode)
```

**Usage:**
```bash
uv run scripts/verify.py    # Parallel with live status display
```

**Output looks like:**
```
✓ format
✓ lint  
⠹ typecheck  Checking src/monarch_cli/commands/accounts.py...
● test        test_accounts.py::test_list PASSED
```

**Why this is good for agents:**
- **Parallel** = faster feedback loop
- **Live output** = agent sees progress, not silence
- **`--fail-fast`** = stops early on first failure
- **On failure** = shows full output of what broke

#### Option B: Makefile (Simple, Sequential)

```makefile
# Makefile
.PHONY: verify test lint typecheck format

# Run ALL checks sequentially
verify: format-check lint typecheck test
	@echo "✅ All checks passed"

format:
	uv run ruff format .

format-check:
	uv run ruff format --check .

lint:
	uv run ruff check . --fix

typecheck:
	uv run mypy src/

test:
	uv run pytest

test-cov:
	uv run pytest --cov --cov-report=term-missing

# Live tests - LOCAL DEV ONLY (requires auth, not for CI)
test-live:
	MONARCH_LIVE_TESTS=1 uv run pytest tests/live/ -m live
```

**Usage:**
```bash
make verify    # Run everything sequentially
make test      # Just tests
make lint      # Just linting
```

### Testing Patterns

#### CLI-Level Tests with CliRunner (Preferred)

```python
# tests/test_accounts_cli.py
import json
from typer.testing import CliRunner
from unittest.mock import patch

from monarch_cli.main import app

runner = CliRunner()


class TestAccountsCLI:
    """CLI-level tests using Typer's CliRunner."""

    def test_accounts_list_json_output(self):
        """Should output accounts as JSON."""
        mock_accounts = [
            {"id": "ACC1", "name": "Checking", "balance": 1000.00}
        ]

        with patch("monarch_cli.services.accounts.list_accounts") as mock_svc:
            mock_svc.return_value = mock_accounts
            result = runner.invoke(app, ["accounts", "list", "--format", "json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data[0]["id"] == "ACC1"

    def test_accounts_list_requires_auth(self):
        """Should error when not authenticated."""
        with patch("monarch_cli.services.accounts.list_accounts") as mock_svc:
            from monarch_cli.core.exceptions import AuthenticationError
            mock_svc.side_effect = AuthenticationError()

            result = runner.invoke(app, ["accounts", "list"])

        assert result.exit_code == 1
        assert "AUTH_REQUIRED" in result.stdout or "not authenticated" in result.stdout.lower()
```

#### Contract Tests for Stable Output Schema

```python
# tests/test_schemas.py
"""Ensure output schemas remain stable for AI agents."""

def test_account_schema_has_required_fields():
    """Account output must have these fields for agent compatibility."""
    from monarch_cli.transformers.accounts import transform_account

    raw = {
        "id": "123",
        "displayName": "Test",
        "currentBalance": 100.0,
        "type": {"display": "Checking"},
        "institution": {"name": "Bank"},
        "isHidden": False,
    }

    result = transform_account(raw)

    # These fields MUST exist - breaking change if removed
    assert "id" in result
    assert "name" in result
    assert "balance" in result
    assert "type" in result
    assert "is_active" in result
```

#### Shared Fixtures (conftest.py)

```python
# tests/conftest.py
import pytest
from unittest.mock import AsyncMock


@pytest.fixture
def mock_monarch_client():
    """Create a mock MonarchMoney client."""
    client = AsyncMock()

    # Default responses
    client.get_accounts.return_value = {"accounts": []}
    client.get_transactions.return_value = {"allTransactions": {"results": []}}
    client.get_budgets.return_value = {"budgetData": {}}

    return client


@pytest.fixture
def sample_accounts():
    """Sample account data for tests."""
    return {
        "accounts": [
            {
                "id": "acc_123",
                "displayName": "Checking",
                "currentBalance": 5000.00,
                "type": {"name": "checking", "display": "Checking"},
                "institution": {"name": "Chase"},
                "isHidden": False,
            },
        ]
    }


```

#### Live Tests (Local Development Only)

Live tests hit the real Monarch Money API. These are for **local development only** - they should NOT run in CI since they require real credentials and make actual API calls.

**Why not in CI?**
- Requires real Monarch Money credentials
- API responses vary per user (account names, balances, etc.)
- Could hit rate limits
- API compatibility is the responsibility of `monarchmoneycommunity` library

**When to use:**
- Verifying your authenticated client works
- Testing new commands during development
- Debugging API response handling

```python
# tests/live/test_live_api.py
import os
import pytest

# Only run if explicitly enabled via environment variable
pytestmark = pytest.mark.live

LIVE_ENABLED = os.environ.get("MONARCH_LIVE_TESTS") == "1"


@pytest.mark.skipif(not LIVE_ENABLED, reason="Live tests disabled (set MONARCH_LIVE_TESTS=1)")
class TestLiveAPI:
    """Tests against real Monarch Money API.
    
    ⚠️  LOCAL DEVELOPMENT ONLY - Do not run in CI!

    Prerequisites:
    - Authenticated via `monarch auth login`, OR
    - MONARCH_TOKEN environment variable set
    
    Run with:
        MONARCH_LIVE_TESTS=1 uv run pytest tests/live/ -m live
    """

    def test_get_accounts_returns_data(self):
        """Should fetch real accounts."""
        from monarch_cli.core.adapter import get_authenticated_client
        from monarch_cli.core.async_utils import run_async

        client = get_authenticated_client()
        accounts = run_async(client.get_accounts())

        assert "accounts" in accounts
        # Don't assert specific data - it varies per user
```

### CI Workflow

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4

      - name: Install dependencies
        run: uv sync

      - name: Format check
        run: uv run ruff format --check .

      - name: Lint
        run: uv run ruff check .

      - name: Type check
        run: uv run mypy src/

      - name: Test (excluding live tests)
        run: uv run pytest --cov --cov-report=xml -m "not live"

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          files: coverage.xml
```

### Quick Reference: Common Commands

```bash
# Setup
uv sync                      # Install all dependencies

# Development
uv run monarch --help        # Run CLI
uv run pytest               # Run tests
uv run pytest -x            # Stop on first failure
uv run pytest -k "test_accounts"  # Run specific tests
uv run pytest --cov         # With coverage

# Quality
uv run ruff check .         # Lint
uv run ruff check . --fix   # Lint + auto-fix
uv run ruff format .        # Format code
uv run mypy src/            # Type check

# All-in-one (agents should use this)
make verify                 # Format + lint + typecheck + test

# Build & publish
uv build                    # Create wheel + sdist
uv publish --repository testpypi  # Publish to test PyPI
```

### Editor Setup (VS Code)

```json
// .vscode/settings.json
{
    "python.defaultInterpreterPath": ".venv/bin/python",
    "[python]": {
        "editor.formatOnSave": true,
        "editor.defaultFormatter": "charliermarsh.ruff",
        "editor.codeActionsOnSave": {
            "source.fixAll.ruff": "explicit",
            "source.organizeImports.ruff": "explicit"
        }
    },
    "python.analysis.typeCheckingMode": "basic"
}
```

```json
// .vscode/extensions.json
{
    "recommendations": [
        "charliermarsh.ruff",
        "ms-python.python",
        "ms-python.mypy-type-checker"
    ]
}
```

---

## Phase 0: Project Setup
**Priority**: P0 (Blocker)

### 0.1 Repository Initialization
- [ ] Create new repository: `monarch-cli`
- [ ] Initialize with `uv init` or `poetry init`
- [ ] Set up Python 3.12+ requirement
- [ ] Add `.gitignore` for Python projects
- [ ] Create initial README with project description

### 0.2 Dependencies & Configuration

Use the complete `pyproject.toml` from the [Python Ecosystem Conventions](#python-ecosystem-conventions) section above. Key points:

- **Runtime deps:** typer, monarchmoneycommunity, keyring, rich, platformdirs, httpx
- **Dev deps:** pytest, pytest-asyncio, pytest-cov, ruff, mypy
- **Tool configs:** All in pyproject.toml (ruff, mypy, pytest, coverage)

> **Note:** Install `monarchmoneycommunity` from PyPI, but import as `monarchmoney`:
> ```python
> from monarchmoney import MonarchMoney  # imports from monarchmoneycommunity package
> ```

### 0.3 Project Structure

Use the src layout from [Python Ecosystem Conventions](#project-structure-src-layout).

### 0.4 Deliverables
- [ ] `uv run monarch --help` shows help text
- [ ] `uv run monarch --version` shows version
- [ ] Project structure matches above

---

## Phase 1: Auth Foundation
**Priority**: P0 (Blocker)

> **Why Auth First?** By implementing authentication early, you can authenticate once and then live-test every subsequent feature as it's built. This enables coding agents to write integration tests alongside implementation.

### 1.1 Async Utilities

The async utility runs async code from sync Typer commands using `asyncio.run()`, which is the standard approach for CLI applications.

```python
# src/monarch_cli/core/async_utils.py
import asyncio
from typing import TypeVar, Coroutine, Any

T = TypeVar("T")

def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """Run async coroutine in sync context.
    
    Uses asyncio.run() which is the standard approach for CLI applications.
    Properly handles cleanup and exception propagation.
    """
    try:
        return asyncio.run(coro)
    except KeyboardInterrupt:
        raise
    except asyncio.CancelledError:
        raise RuntimeError("Operation was cancelled")
```

### 1.2 Exception Hierarchy

Centralized exceptions for consistent error handling:

```python
# src/monarch_cli/core/exceptions.py
"""Centralized exception hierarchy for consistent error handling."""

from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    """Error codes for AI agent consumption."""
    AUTH_REQUIRED = "AUTH_REQUIRED"
    AUTH_EXPIRED = "AUTH_EXPIRED"
    AUTH_FAILED = "AUTH_FAILED"
    NOT_FOUND = "NOT_FOUND"
    INVALID_INPUT = "INVALID_INPUT"
    API_ERROR = "API_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    NETWORK_ERROR = "NETWORK_ERROR"
    TIMEOUT = "TIMEOUT"
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class MonarchCLIError(Exception):
    """Base exception for all CLI errors."""

    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.UNKNOWN,
        details: dict[str, Any] | None = None,
        exit_code: int = 1,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}
        self.exit_code = exit_code

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict for AI agents."""
        result = {
            "error": True,
            "code": self.code.value,
            "message": self.message,
        }
        if self.details:
            result["details"] = self.details
        return result


class AuthenticationError(MonarchCLIError):
    """Not authenticated."""

    def __init__(self, message: str = "Not authenticated. Run 'monarch auth login' first."):
        super().__init__(message, ErrorCode.AUTH_REQUIRED, exit_code=1)


class AuthExpiredError(MonarchCLIError):
    """Session token expired."""

    def __init__(self):
        super().__init__(
            "Session expired. Run 'monarch auth login' to re-authenticate.",
            ErrorCode.AUTH_EXPIRED,
            exit_code=1,
        )


class NotFoundError(MonarchCLIError):
    """Resource not found."""

    def __init__(self, resource_type: str, resource_id: str):
        super().__init__(
            f"{resource_type} '{resource_id}' not found",
            ErrorCode.NOT_FOUND,
            details={"resource_type": resource_type, "resource_id": resource_id},
            exit_code=1,
        )


class ValidationError(MonarchCLIError):
    """Input validation error."""

    def __init__(self, message: str, field: str | None = None):
        details = {"field": field} if field else {}
        super().__init__(message, ErrorCode.INVALID_INPUT, details, exit_code=2)


class APIError(MonarchCLIError):
    """Monarch Money API error."""

    def __init__(self, message: str, status_code: int | None = None):
        details = {"status_code": status_code} if status_code else {}
        super().__init__(message, ErrorCode.API_ERROR, details, exit_code=1)


class RateLimitError(MonarchCLIError):
    """Rate limit exceeded."""

    def __init__(self, retry_after: int | None = None):
        details = {"retry_after_seconds": retry_after} if retry_after else {}
        super().__init__(
            "Rate limit exceeded. Please wait before retrying.",
            ErrorCode.RATE_LIMITED,
            details,
            exit_code=1,
        )


class NetworkError(MonarchCLIError):
    """Network connectivity error."""

    def __init__(self, message: str = "Network error. Check your internet connection."):
        super().__init__(message, ErrorCode.NETWORK_ERROR, exit_code=1)
```

### 1.3 Error Handler Decorator

```python
# src/monarch_cli/core/error_handler.py
"""Decorator for consistent error handling across commands."""

import functools
import typer
from typing import Callable, TypeVar, ParamSpec

from .exceptions import (
    MonarchCLIError,
    AuthenticationError,
    AuthExpiredError,
    APIError,
    NetworkError,
    RateLimitError,
)
from ..output import output_error, is_verbose

P = ParamSpec("P")
R = TypeVar("R")


def handle_errors(func: Callable[P, R]) -> Callable[P, R]:
    """Decorator that catches exceptions and outputs consistent errors.
    
    Uses typer.Exit() instead of sys.exit() for better testability.
    """

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return func(*args, **kwargs)
        except MonarchCLIError as e:
            output_error(e)
            raise typer.Exit(e.exit_code)
        except Exception as e:
            if is_verbose():
                import traceback
                traceback.print_exc()
            output_error(MonarchCLIError(f"Unexpected error: {e}"))
            raise typer.Exit(1)

    return wrapper
```

### 1.4 Session Management

Secure, dual-backend session storage:

```python
# src/monarch_cli/core/session.py
import json
import os
import tempfile
from enum import Enum
from pathlib import Path
from typing import Optional

import keyring
import platformdirs

class StorageBackend(str, Enum):
    KEYRING = "keyring"
    FILE = "file"              # Safe JSON with 0600 perms
    FILE_COMPAT = "file-compat"  # Legacy pickle (opt-in only)

# Keyring constants
KEYRING_SERVICE = "com.monarch-cli"
KEYRING_USERNAME = "monarch-token"

# File paths via platformdirs
def get_config_dir() -> Path:
    """Get config directory, respecting XDG/platformdirs."""
    override = os.environ.get("MONARCH_CONFIG_DIR")
    if override:
        return Path(override)
    return Path(platformdirs.user_config_dir("monarch-cli"))

def get_session_path() -> Path:
    """Get session file path."""
    override = os.environ.get("MONARCH_SESSION_PATH")
    if override:
        return Path(override)
    return get_config_dir() / "session.json"

# Legacy compat path (pickle, unsafe)
COMPAT_SESSION_PATH = Path.home() / ".mm" / "mm_session.pickle"


def save_session_token(token: str, backend: StorageBackend = StorageBackend.KEYRING) -> None:
    """Save token to specified backend."""
    if backend == StorageBackend.KEYRING:
        keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, token)
    elif backend == StorageBackend.FILE:
        # Safe JSON with atomic write and strict permissions
        session_path = get_session_path()
        session_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Atomic write: write to temp, then rename
        fd, tmp_path = tempfile.mkstemp(dir=session_path.parent, suffix=".tmp")
        try:
            os.fchmod(fd, 0o600)  # Strict permissions before writing
            with os.fdopen(fd, "w") as f:
                json.dump({"token": token}, f)
            os.replace(tmp_path, session_path)  # Atomic replace
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
    elif backend == StorageBackend.FILE_COMPAT:
        # Legacy pickle - explicit opt-in only
        import pickle
        COMPAT_SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(COMPAT_SESSION_PATH, "wb") as f:
            pickle.dump({"token": token}, f)


def get_session_token() -> str | None:
    """Retrieve token.

    Precedence (highest to lowest):
      1) MONARCH_TOKEN env var (best for CI/agents)
      2) Keyring
      3) JSON session file
      4) Legacy compat pickle (if enabled)
    """
    # 1) Env var (explicit override for CI/agents)
    env_token = os.environ.get("MONARCH_TOKEN")
    if env_token:
        return env_token

    # 2) Try keyring
    try:
        token = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
        if token:
            return token
    except Exception:
        pass  # Keyring may not be available

    # Try safe JSON session file
    session_path = get_session_path()
    if session_path.exists():
        try:
            with open(session_path) as f:
                data = json.load(f)
                return data.get("token")
        except (json.JSONDecodeError, OSError):
            pass

    # Fall back to legacy compat pickle (only if it exists)
    if COMPAT_SESSION_PATH.exists():
        import pickle
        try:
            with open(COMPAT_SESSION_PATH, "rb") as f:
                data = pickle.load(f)
                return data.get("token")
        except Exception:
            pass

    return None


def get_storage_info() -> dict:
    """Get info about where token is stored."""
    env_token = os.environ.get("MONARCH_TOKEN")
    
    keyring_token = None
    try:
        keyring_token = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
    except Exception:
        pass

    session_path = get_session_path()
    file_exists = session_path.exists()
    compat_exists = COMPAT_SESSION_PATH.exists()

    # Determine active backend (matches get_session_token() precedence)
    if env_token:
        active = "env"
    elif keyring_token:
        active = StorageBackend.KEYRING
    elif file_exists:
        active = StorageBackend.FILE
    elif compat_exists:
        active = StorageBackend.FILE_COMPAT
    else:
        active = None

    return {
        "has_env_token": env_token is not None,
        "has_keyring_token": keyring_token is not None,
        "has_file_token": file_exists,
        "has_compat_token": compat_exists,
        "active_backend": active if isinstance(active, str) else (active.value if active else None),
        "file_path": str(session_path),
        "compat_path": str(COMPAT_SESSION_PATH),
    }


def delete_session_token(backend: StorageBackend | None = None) -> None:
    """Remove token from specified backend, or all backends if None."""
    if backend is None or backend == StorageBackend.KEYRING:
        try:
            keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
        except Exception:
            pass

    if backend is None or backend == StorageBackend.FILE:
        session_path = get_session_path()
        if session_path.exists():
            session_path.unlink()

    if backend is None or backend == StorageBackend.FILE_COMPAT:
        if COMPAT_SESSION_PATH.exists():
            COMPAT_SESSION_PATH.unlink()


def has_valid_session() -> bool:
    """Check if a session token exists in any backend."""
    return get_session_token() is not None
```

### 1.5 Adapter (Isolates Upstream Library Details)

```python
# src/monarch_cli/core/adapter.py
"""Adapter to isolate monarchmoneycommunity private details.

All access to private attributes (_headers, _token) is confined here.
This protects against upstream library changes.
"""

from monarchmoney import MonarchMoney
from .session import get_session_token
from .exceptions import AuthenticationError

_client: MonarchMoney | None = None


def get_authenticated_client() -> MonarchMoney:
    """Get authenticated MonarchMoney client."""
    global _client
    if _client is not None:
        return _client

    token = get_session_token()
    if not token:
        raise AuthenticationError()

    _client = MonarchMoney()
    # Private attribute access isolated here
    _client._headers["Authorization"] = f"Bearer {token}"
    return _client


def extract_token_from_client(client: MonarchMoney) -> str | None:
    """Extract token from client after login. Private access isolated here."""
    return getattr(client, "_token", None)


def reset_client() -> None:
    """Reset cached client (for logout)."""
    global _client
    _client = None
```

### 1.6 Retry Logic

```python
# src/monarch_cli/core/retry.py
"""Retry logic with exponential backoff."""

import asyncio
import random
from typing import TypeVar, Callable, Awaitable, Any

from .exceptions import NetworkError, RateLimitError

T = TypeVar("T")

# Exceptions that should trigger retry
RETRYABLE_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    OSError,
)


async def with_retry(
    coro_factory: Callable[[], Awaitable[T]],
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    jitter: bool = True,
) -> T:
    """Execute an async operation with exponential backoff retry."""
    last_exception: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return await coro_factory()
        except RETRYABLE_EXCEPTIONS as e:
            last_exception = e

            if attempt == max_retries:
                break

            delay = min(base_delay * (2 ** attempt), max_delay)
            if jitter:
                delay = delay * (0.75 + random.random() * 0.5)

            await asyncio.sleep(delay)

    if last_exception:
        raise NetworkError(f"Operation failed after {max_retries} retries: {last_exception}")
    raise RuntimeError("Unexpected retry state")
```

### 1.7 Date Utilities

```python
# src/monarch_cli/core/dates.py
"""Date utilities and presets."""

from datetime import date, timedelta
from enum import Enum


class DatePreset(str, Enum):
    """Common date range presets."""
    TODAY = "today"
    YESTERDAY = "yesterday"
    THIS_WEEK = "this-week"
    LAST_WEEK = "last-week"
    THIS_MONTH = "this-month"
    LAST_MONTH = "last-month"
    LAST_30_DAYS = "last-30-days"
    LAST_90_DAYS = "last-90-days"
    THIS_YEAR = "this-year"
    LAST_YEAR = "last-year"
    YTD = "ytd"
    ALL = "all"


def resolve_preset(preset: DatePreset) -> tuple[date | None, date | None]:
    """Convert a preset to (start_date, end_date) tuple."""
    today = date.today()

    match preset:
        case DatePreset.TODAY:
            return (today, today)
        case DatePreset.YESTERDAY:
            return (today - timedelta(days=1), today - timedelta(days=1))
        case DatePreset.THIS_WEEK:
            start = today - timedelta(days=today.weekday())
            return (start, today)
        case DatePreset.LAST_WEEK:
            this_monday = today - timedelta(days=today.weekday())
            return (this_monday - timedelta(days=7), this_monday - timedelta(days=1))
        case DatePreset.THIS_MONTH:
            return (today.replace(day=1), today)
        case DatePreset.LAST_MONTH:
            first = today.replace(day=1)
            last_of_prev = first - timedelta(days=1)
            return (last_of_prev.replace(day=1), last_of_prev)
        case DatePreset.LAST_30_DAYS:
            return (today - timedelta(days=30), today)
        case DatePreset.LAST_90_DAYS:
            return (today - timedelta(days=90), today)
        case DatePreset.THIS_YEAR | DatePreset.YTD:
            return (today.replace(month=1, day=1), today)
        case DatePreset.LAST_YEAR:
            return (
                today.replace(year=today.year - 1, month=1, day=1),
                today.replace(year=today.year - 1, month=12, day=31),
            )
        case DatePreset.ALL:
            return (None, None)

    return (None, None)


def parse_date_range(
    preset: DatePreset | None = None,
    start: str | None = None,
    end: str | None = None,
) -> tuple[str | None, str | None]:
    """Parse date range from preset or explicit dates.
    
    Explicit dates take precedence over preset.
    """
    if start is not None or end is not None:
        return (start, end)

    if preset is not None:
        start_date, end_date = resolve_preset(preset)
        return (
            start_date.isoformat() if start_date else None,
            end_date.isoformat() if end_date else None,
        )

    return (None, None)
```

### 1.8 Minimal Output Helpers

For Phase 1, we only need basic output for auth commands. Full output system comes in Phase 2.

```python
# src/monarch_cli/output/__init__.py (minimal version for Phase 1)
import json
import sys
from enum import Enum
from typing import Any
from rich.console import Console

from ..core.exceptions import MonarchCLIError

class OutputFormat(str, Enum):
    JSON = "json"
    TABLE = "table"
    CSV = "csv"
    COMPACT = "compact"

console = Console()
_verbose = False

def set_verbose(v: bool) -> None:
    global _verbose
    _verbose = v

def is_verbose() -> bool:
    return _verbose

def output(data: Any, format: OutputFormat = OutputFormat.JSON) -> None:
    """Output data in specified format. Table/CSV support added in Phase 2."""
    if format == OutputFormat.COMPACT:
        print(json.dumps(data, default=str))
    else:
        print(json.dumps(data, indent=2, default=str))

def output_error(error: MonarchCLIError) -> None:
    """Output structured error for AI agents to stderr."""
    print(json.dumps(error.to_dict(), indent=2), file=sys.stderr)

def error(message: str, exit_code: int = 1) -> None:
    """Print error and exit."""
    console.print(f"[red]Error:[/red] {message}", file=sys.stderr)
    sys.exit(exit_code)
```

> **Note:** This is a minimal bootstrap version for Phase 1. Phase 2 expands this with table/CSV/NDJSON support.

### 1.9 Main Entry Point (Auth Only)

```python
# src/monarch_cli/main.py
import typer

app = typer.Typer(
    name="monarch",
    help="CLI for Monarch Money - AI agent friendly financial data access",
    no_args_is_help=True,
)

# Phase 1: Only auth commands registered
from .commands import auth
app.add_typer(auth.app, name="auth")

# Phase 3 will add: accounts, transactions, budgets, cashflow, categories, config

if __name__ == "__main__":
    app()
```

### 1.10 Authentication Commands

```python
# src/monarch_cli/commands/auth.py
import typer
from getpass import getpass
from ..core.session import (
    has_valid_session, delete_session_token, save_session_token,
    get_storage_info, StorageBackend
)
from ..core.adapter import extract_token_from_client, reset_client
from ..core.async_utils import run_async
from ..core.error_handler import handle_errors
from ..output import output, OutputFormat, console
from monarchmoney import MonarchMoney, RequireMFAException

app = typer.Typer(help="Authentication management")


@app.command()
def login(
    storage: StorageBackend = typer.Option(
        None,
        "--storage", "-s",
        help="Token storage backend: keyring (secure, default), file (portable), or file-compat (legacy pickle)"
    ),
):
    """Interactive login to Monarch Money.
    
    Examples:
        monarch auth login
        monarch auth login --storage file
    """
    console.print("\n[bold]Monarch Money Login[/bold]\n")

    email = input("Email: ")
    password = getpass("Password: ")

    if storage is None:
        console.print("\n[dim]How would you like to store your session token?[/dim]")
        console.print("  1. [green]Keyring[/green] (recommended) - Secure OS credential store")
        console.print("  2. [yellow]Session file[/yellow] - JSON file with strict permissions")
        choice = input("\nChoice [1]: ").strip() or "1"
        storage = StorageBackend.FILE if choice == "2" else StorageBackend.KEYRING

    mm = MonarchMoney()

    try:
        run_async(mm.login(email, password, save_session=False))
    except RequireMFAException:
        mfa_code = input("MFA Code: ")
        run_async(mm.multi_factor_authenticate(email, password, mfa_code))
    except Exception as e:
        console.print(f"[red]Login failed:[/red] {e}")
        raise typer.Exit(1)

    token = extract_token_from_client(mm)
    if not token:
        console.print("[red]Login succeeded but no token was returned[/red]")
        raise typer.Exit(1)

    save_session_token(token, storage)
    backend_name = storage.value
    console.print(f"[green]✓ Logged in successfully. Token saved to {backend_name}.[/green]")

    try:
        accounts = run_async(mm.get_accounts())
        count = len(accounts.get("accounts", []))
        console.print(f"[dim]Found {count} linked accounts.[/dim]")
    except Exception:
        pass


@app.command()
@handle_errors
def status(
    format: OutputFormat = typer.Option(OutputFormat.JSON, "--format", "-f")
):
    """Check authentication status."""
    is_authenticated = has_valid_session()
    storage_info = get_storage_info()
    result = {
        "authenticated": is_authenticated,
        "storage_backend": storage_info["active_backend"],
        "message": "Ready to use" if is_authenticated else "Run 'monarch auth login' to authenticate"
    }
    output(result, format)


@app.command()
def logout(
    storage: StorageBackend = typer.Option(
        None,
        "--storage", "-s",
        help="Only clear token from specific backend. Default: clear all."
    ),
):
    """Remove stored authentication token.
    
    Examples:
        monarch auth logout              # Clear all stored tokens
        monarch auth logout -s keyring   # Only clear keyring
    """
    delete_session_token(storage)
    reset_client()

    if storage:
        console.print(f"[green]Logged out from {storage.value}[/green]")
    else:
        console.print("[green]Logged out successfully (cleared all backends)[/green]")


@app.command()
def doctor():
    """Diagnose environment and auth storage.
    
    Checks keyring availability, session files, and token validity.
    """
    console.print("\n[bold]Monarch CLI Doctor[/bold]\n")

    # Check keyring
    try:
        import keyring
        backend = keyring.get_keyring()
        console.print(f"[green]✓[/green] Keyring available: {type(backend).__name__}")
    except Exception as e:
        console.print(f"[red]✗[/red] Keyring error: {e}")

    # Check storage info
    info = get_storage_info()
    console.print(f"\n[bold]Token Storage:[/bold]")
    console.print(f"  Env var: {'[green]set[/green]' if info['has_env_token'] else '[dim]not set[/dim]'} (MONARCH_TOKEN)")
    console.print(f"  Keyring: {'[green]present[/green]' if info['has_keyring_token'] else '[dim]empty[/dim]'}")
    console.print(f"  File: {'[green]present[/green]' if info['has_file_token'] else '[dim]empty[/dim]'} ({info['file_path']})")
    console.print(f"  Compat: {'[yellow]present[/yellow]' if info['has_compat_token'] else '[dim]empty[/dim]'} ({info['compat_path']})")
    console.print(f"  Active: {info['active_backend'] or '[red]none[/red]'}")

    # Test API connectivity if authenticated
    if has_valid_session():
        console.print(f"\n[bold]API Connectivity:[/bold]")
        try:
            from ..core.adapter import get_authenticated_client
            client = get_authenticated_client()
            accounts = run_async(client.get_accounts())
            count = len(accounts.get("accounts", []))
            console.print(f"  [green]✓[/green] API accessible ({count} accounts)")
        except Exception as e:
            console.print(f"  [red]✗[/red] API error: {e}")


@app.command()
@handle_errors
def ping():
    """Check basic API connectivity (no sensitive output)."""
    from ..core.adapter import get_authenticated_client

    client = get_authenticated_client()
    run_async(client.get_accounts())
    output({"status": "ok", "message": "API is reachable"})


@app.command()
def setup():
    """Show setup instructions."""
    console.print("""
[bold]Monarch CLI Setup Instructions[/bold]

1. Run the login command:
   [cyan]monarch auth login[/cyan]

2. Enter your Monarch Money credentials when prompted

3. If you have MFA enabled, enter the code when prompted

4. Choose your token storage method:
   • [green]Keyring[/green] (recommended) - Secure OS credential store
   • [yellow]Session file[/yellow] - JSON with strict permissions

[dim]Note: Credentials are never stored - only the session token.[/dim]

[bold]Troubleshooting:[/bold]
   [cyan]monarch auth doctor[/cyan] - Diagnose storage and connectivity
   [cyan]monarch auth ping[/cyan] - Test API connectivity
""")
```

**CLI Usage:**
```bash
monarch auth login               # Interactive login
monarch auth login -s file       # Login with file storage
monarch auth status              # Check if authenticated
monarch auth logout              # Remove stored tokens (all backends)
monarch auth doctor              # Diagnose issues
monarch auth ping                # Test API connectivity
monarch auth setup               # Show setup instructions
```

### 1.11 Deliverables
- [ ] `monarch --help` shows auth command group
- [ ] `monarch auth login` works with both storage backends
- [ ] `monarch auth status` shows authentication state and backend
- [ ] `monarch auth logout` clears tokens
- [ ] `monarch auth doctor` diagnoses issues
- [ ] `monarch auth ping` tests connectivity
- [ ] Session management: keyring first, file fallback

---

## 🔑 User Checkpoint: Authenticate Now

**After Phase 1 is complete, authenticate before continuing:**

```bash
monarch auth login
```

Once authenticated, the token is stored and all subsequent phases can:
- Make live API calls during development
- Write integration tests that verify real behavior
- Validate output formats against actual data

---

## Phase 2: Output System
**Priority**: P0 (Required for MVP)

### 2.1 Full Output Formatters

```python
# src/monarch_cli/output/__init__.py (full version)
import csv
import json
import sys
from enum import Enum
from io import StringIO
from typing import Any
from rich.console import Console
from rich.table import Table

from ..core.exceptions import MonarchCLIError

class OutputFormat(str, Enum):
    JSON = "json"
    TABLE = "table"
    CSV = "csv"
    COMPACT = "compact"

console = Console()
_verbose = False

def set_verbose(v: bool) -> None:
    global _verbose
    _verbose = v

def is_verbose() -> bool:
    return _verbose

def is_interactive() -> bool:
    """Check if we're in an interactive terminal."""
    return sys.stdout.isatty()

def output(
    data: Any,
    format: OutputFormat = OutputFormat.JSON,
    ndjson: bool = False,
    raw: bool = False,
) -> None:
    """Output data in specified format."""
    # Raw mode: pass through without transformation
    if raw:
        print(json.dumps(data, indent=2, default=str))
        return

    # NDJSON mode: stream items line by line
    if ndjson and isinstance(data, list):
        for item in data:
            print(json.dumps(item, default=str))
        return

    if format == OutputFormat.JSON:
        print(json.dumps(data, indent=2, default=str))
    elif format == OutputFormat.COMPACT:
        print(json.dumps(data, default=str))
    elif format == OutputFormat.TABLE:
        if isinstance(data, list):
            print_table(data)
        else:
            print(json.dumps(data, indent=2, default=str))
    elif format == OutputFormat.CSV:
        if isinstance(data, list):
            print_csv(data)
        else:
            print_csv([data] if isinstance(data, dict) else [{"value": data}])

def print_table(items: list[dict]) -> None:
    """Print list of dicts as rich table."""
    if not items:
        console.print("[dim]No results[/dim]")
        return

    table = Table()
    for key in items[0].keys():
        table.add_column(key)

    for item in items:
        table.add_row(*[str(v) for v in item.values()])

    console.print(table)

def print_csv(items: list[dict]) -> None:
    """Print list of dicts as CSV."""
    if not items:
        return

    output_io = StringIO()
    writer = csv.DictWriter(output_io, fieldnames=items[0].keys())
    writer.writeheader()
    writer.writerows(items)
    print(output_io.getvalue(), end="")

def output_error(error: MonarchCLIError) -> None:
    """Output structured error for AI agents to stderr.
    
    Errors go to stderr to preserve clean stdout for piping.
    """
    print(json.dumps(error.to_dict(), indent=2), file=sys.stderr)

def error(message: str, exit_code: int = 1) -> None:
    """Print error and exit."""
    console.print(f"[red]Error:[/red] {message}", file=sys.stderr)
    sys.exit(exit_code)
```

### 2.2 Progress Indicators

```python
# src/monarch_cli/output/progress.py
"""Progress indicators for long-running operations."""

import sys
from contextlib import contextmanager
from typing import Generator

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

console = Console(stderr=True)


def is_interactive() -> bool:
    """Check if we're in an interactive terminal."""
    return sys.stderr.isatty()


@contextmanager
def spinner(message: str) -> Generator[None, None, None]:
    """Show a spinner while an operation is in progress.
    
    Only shows spinner in interactive terminals.
    """
    if not is_interactive():
        console.print(f"[dim]{message}[/dim]")
        yield
        return

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task(description=message, total=None)
        yield
```

### 2.3 Deliverables
- [ ] JSON output (default, pretty-printed)
- [ ] Compact output (single-line JSON for piping)
- [ ] Table output (rich tables for human reading)
- [ ] CSV output (for spreadsheet import)
- [ ] NDJSON streaming (for large lists)
- [ ] Progress spinners (TTY-aware)
- [ ] Error messages to stderr with exit codes

> **Note:** JMESPath query support (`--query` flag) deferred to v1.1. Use `jq` for JSON filtering instead:
> ```bash
> monarch accounts list | jq '[.[] | select(.balance > 1000)]'
> ```

---

## Phase 3: Core Commands
**Priority**: P0 (Required for MVP)

> **Note:** With authentication complete, all commands can be live-tested as they're implemented.

### 3.1 Transformers

```python
# src/monarch_cli/transformers/accounts.py
"""Transform account API responses to CLI-friendly format."""

from typing import Any


def transform_account(raw: dict[str, Any]) -> dict[str, Any]:
    """Transform a single account."""
    return {
        "id": raw.get("id"),
        "name": raw.get("displayName"),
        "type": raw.get("type", {}).get("display"),
        "subtype": raw.get("subtype", {}).get("display"),
        "balance": raw.get("currentBalance"),
        "institution": raw.get("institution", {}).get("name"),
        "is_active": not raw.get("isHidden", False),
        "is_manual": raw.get("isManual", False),
        "last_updated": raw.get("updatedAt"),
    }


def transform_accounts(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Transform accounts API response."""
    return [transform_account(acc) for acc in raw.get("accounts", [])]
```

```python
# src/monarch_cli/transformers/transactions.py
"""Transform transaction API responses to CLI-friendly format."""

from typing import Any


def transform_transaction(raw: dict[str, Any]) -> dict[str, Any]:
    """Transform a single transaction."""
    return {
        "id": raw.get("id"),
        "date": raw.get("date"),
        "amount": raw.get("amount"),
        "description": raw.get("merchant", {}).get("name") or raw.get("plaidName"),
        "category": raw.get("category", {}).get("name"),
        "account": raw.get("account", {}).get("displayName"),
        "is_pending": raw.get("pending", False),
        "notes": raw.get("notes"),
    }


def transform_transactions(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Transform transactions API response."""
    results = raw.get("allTransactions", {}).get("results", [])
    return [transform_transaction(txn) for txn in results]
```

### 3.2 Services

```python
# src/monarch_cli/services/accounts.py
"""Account service - business logic for account operations."""

from ..core.adapter import get_authenticated_client
from ..core.async_utils import run_async
from ..transformers.accounts import transform_accounts


def list_accounts() -> list[dict]:
    """Get all accounts, transformed to CLI format."""
    client = get_authenticated_client()
    raw = run_async(client.get_accounts())
    return transform_accounts(raw)


def refresh_accounts() -> dict:
    """Request account refresh from financial institutions."""
    client = get_authenticated_client()
    run_async(client.request_accounts_refresh())
    return {
        "status": "refresh_requested",
        "message": "Account refresh requested. Balances will update shortly."
    }
```

### 3.3 Account Commands

```python
# src/monarch_cli/commands/accounts.py
import typer
from typing import Optional
from ..core.error_handler import handle_errors
from ..services import accounts as account_service
from ..output import output, OutputFormat
from ..output.progress import spinner

app = typer.Typer(help="Account management")


@app.command("list")
@handle_errors
def list_accounts(
    format: OutputFormat = typer.Option(OutputFormat.JSON, "--format", "-f"),
    ndjson: bool = typer.Option(False, "--ndjson", help="Stream as newline-delimited JSON"),
    raw: bool = typer.Option(False, "--raw", help="Output raw API response"),
):
    """List all linked financial accounts.
    
    Examples:
        monarch accounts list
        monarch accounts list -f table
        monarch accounts list | jq '[.[] | select(.is_active)]'
    """
    with spinner("Fetching accounts..."):
        if raw:
            from ..core.adapter import get_authenticated_client
            from ..core.async_utils import run_async
            client = get_authenticated_client()
            result = run_async(client.get_accounts())
        else:
            result = account_service.list_accounts()

    output(result, format, ndjson=ndjson, raw=raw)


@app.command()
@handle_errors
def refresh():
    """Trigger account refresh from financial institutions."""
    with spinner("Requesting account refresh..."):
        result = account_service.refresh_accounts()
    output(result)
```

**CLI Usage:**
```bash
monarch accounts list                    # List all accounts (JSON)
monarch accounts list -f table           # List as table
monarch accounts list -f csv > accounts.csv  # Export to CSV
monarch accounts list | jq '[.[] | select(.balance > 1000)]'  # Filter with jq
monarch accounts refresh                 # Trigger bank sync
```

### 3.4 Transaction Commands

```python
# src/monarch_cli/commands/transactions.py
import typer
from typing import Optional
from ..core.error_handler import handle_errors
from ..core.adapter import get_authenticated_client
from ..core.async_utils import run_async
from ..core.dates import DatePreset, parse_date_range
from ..transformers.transactions import transform_transactions
from ..output import output, OutputFormat
from ..output.progress import spinner

app = typer.Typer(help="Transaction management")


@app.command("list")
@handle_errors
def list_transactions(
    limit: int = typer.Option(100, "--limit", "-l", help="Max transactions to return"),
    offset: int = typer.Option(0, "--offset", "-o", help="Pagination offset"),
    start_date: Optional[str] = typer.Option(None, "--start", "-s", help="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = typer.Option(None, "--end", "-e", help="End date (YYYY-MM-DD)"),
    preset: Optional[DatePreset] = typer.Option(
        None, "--preset", "-p", help="Date range preset (overridden by --start/--end)"
    ),
    account_id: Optional[str] = typer.Option(None, "--account", "-a", help="Filter by account ID"),
    search: Optional[str] = typer.Option(None, "--search", help="Search transactions"),
    format: OutputFormat = typer.Option(OutputFormat.JSON, "--format", "-f"),
    ndjson: bool = typer.Option(False, "--ndjson", help="Stream as newline-delimited JSON"),
    raw: bool = typer.Option(False, "--raw", help="Output raw API response"),
):
    """List transactions with optional filters.
    
    Examples:
        monarch transactions list
        monarch transactions list --preset this-month
        monarch transactions list --limit 50 --start 2024-12-01
        monarch transactions list --account ACC123 --format table
        monarch transactions list --search "Amazon" --preset ytd
    """
    resolved_start, resolved_end = parse_date_range(preset, start_date, end_date)

    with spinner("Fetching transactions..."):
        client = get_authenticated_client()
        result = run_async(client.get_transactions(
            limit=limit,
            offset=offset,
            start_date=resolved_start,
            end_date=resolved_end,
            search=search,
            account_ids=[account_id] if account_id else None,
        ))

    if not raw:
        result = transform_transactions(result)

    output(result, format, ndjson=ndjson, raw=raw)


@app.command()
@handle_errors
def update(
    transaction_id: str = typer.Argument(..., help="Transaction ID to update"),
    amount: Optional[float] = typer.Option(None, "--amount", help="New amount"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="New description"),
    category_id: Optional[str] = typer.Option(None, "--category", "-c", help="New category ID"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without applying"),
    format: OutputFormat = typer.Option(OutputFormat.JSON, "--format", "-f"),
):
    """Update an existing transaction.
    
    Examples:
        monarch transactions update TXN123 --category CAT456
        monarch transactions update TXN123 --amount -50.00 --dry-run
    """
    update_kwargs = {}
    if amount is not None:
        update_kwargs["amount"] = amount
    if description is not None:
        update_kwargs["merchant_name"] = description
    if category_id is not None:
        update_kwargs["category_id"] = category_id

    if dry_run:
        output({
            "dry_run": True,
            "operation": "update_transaction",
            "transaction_id": transaction_id,
            "changes": update_kwargs,
            "message": "No changes made (dry run)"
        }, format)
        return

    client = get_authenticated_client()
    run_async(client.update_transaction(transaction_id=transaction_id, **update_kwargs))
    output({
        "status": "updated",
        "transaction_id": transaction_id,
        "changes": update_kwargs,
    }, format)
```

**CLI Usage:**
```bash
# List transactions
monarch transactions list
monarch transactions list --preset this-month
monarch transactions list --limit 50 --start 2024-12-01
monarch transactions list -a ACC123 -f table
monarch transactions list --search "Groceries" --ndjson

# Update transaction
monarch transactions update TXN456 --category CAT789
monarch transactions update TXN456 --category CAT789 --dry-run
```

### 3.5 Budget Commands

```python
# src/monarch_cli/commands/budgets.py
import typer
from ..core.error_handler import handle_errors
from ..core.adapter import get_authenticated_client
from ..core.async_utils import run_async
from ..output import output, OutputFormat
from ..output.progress import spinner

app = typer.Typer(help="Budget tracking")


@app.command("list")
@handle_errors
def list_budgets(
    format: OutputFormat = typer.Option(OutputFormat.JSON, "--format", "-f")
):
    """Get budget status with spent/remaining amounts."""
    with spinner("Fetching budgets..."):
        client = get_authenticated_client()
        budgets = run_async(client.get_budgets())

    result = []
    for budget in budgets.get("budgetData", {}).get("budgetItems", []):
        result.append({
            "id": budget.get("id"),
            "category": budget.get("category", {}).get("name"),
            "budgeted": budget.get("budgetAmount"),
            "spent": abs(budget.get("spentAmount", 0)),
            "remaining": budget.get("remainingAmount"),
        })

    output(result, format)
```

### 3.6 Cashflow Commands

```python
# src/monarch_cli/commands/cashflow.py
import typer
from typing import Optional
from ..core.error_handler import handle_errors
from ..core.adapter import get_authenticated_client
from ..core.async_utils import run_async
from ..core.dates import DatePreset, parse_date_range
from ..output import output, OutputFormat
from ..output.progress import spinner

app = typer.Typer(help="Cashflow analysis")


@app.command("summary")
@handle_errors
def cashflow_summary(
    start_date: Optional[str] = typer.Option(None, "--start", "-s", help="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = typer.Option(None, "--end", "-e", help="End date (YYYY-MM-DD)"),
    preset: Optional[DatePreset] = typer.Option(None, "--preset", "-p", help="Date range preset"),
    format: OutputFormat = typer.Option(OutputFormat.JSON, "--format", "-f")
):
    """Get income/expense analysis for date range.
    
    Examples:
        monarch cashflow summary
        monarch cashflow summary --preset this-month
        monarch cashflow summary --start 2024-10-01 --end 2024-12-31
    """
    resolved_start, resolved_end = parse_date_range(preset, start_date, end_date)

    with spinner("Calculating cashflow..."):
        client = get_authenticated_client()
        cashflow = run_async(client.get_cashflow_summary(
            start_date=resolved_start,
            end_date=resolved_end,
        ))

    output(cashflow, format)
```

### 3.7 Categories Commands

```python
# src/monarch_cli/commands/categories.py
import typer
from ..core.error_handler import handle_errors
from ..core.adapter import get_authenticated_client
from ..core.async_utils import run_async
from ..output import output, OutputFormat
from ..output.progress import spinner

app = typer.Typer(help="Category management")


@app.command("list")
@handle_errors
def list_categories(
    format: OutputFormat = typer.Option(OutputFormat.JSON, "--format", "-f")
):
    """List all transaction categories.
    
    Examples:
        monarch categories list
        monarch categories list -f table
    """
    with spinner("Fetching categories..."):
        client = get_authenticated_client()
        data = run_async(client.get_transaction_categories())

    # Transform to stable CLI format
    result = []
    for group in data.get("categories", []):
        for cat in group.get("children", []):
            result.append({
                "id": cat.get("id"),
                "name": cat.get("name"),
                "group": group.get("name"),
                "icon": cat.get("icon"),
            })

    output(result, format)
```

### 3.8 Config Commands (Deferred to v1.1)

> **Note:** `monarch config` commands (show, set, path) deferred to v1.1 along with TOML config file support.
> For MVP, use environment variables for configuration.

### 3.9 Configuration System (Environment-based for MVP)

```python
# src/monarch_cli/core/config.py
"""Configuration via environment variables (MVP).

TOML config file support deferred to v1.1.
"""

import os
from dataclasses import dataclass
from pathlib import Path

import platformdirs

from ..output import OutputFormat


def get_config_dir() -> Path:
    """Get config directory via platformdirs."""
    override = os.environ.get("MONARCH_CONFIG_DIR")
    if override:
        return Path(override)
    return Path(platformdirs.user_config_dir("monarch-cli"))


@dataclass
class Config:
    """CLI configuration with defaults."""

    format: OutputFormat = OutputFormat.JSON
    color: bool = True
    verbose: bool = False
    timeout_seconds: int = 30
    max_retries: int = 3
    confirm_destructive: bool = True

    @classmethod
    def load(cls) -> "Config":
        """Load config from environment variables."""
        config = cls()

        if fmt := os.environ.get("MONARCH_FORMAT"):
            try:
                config.format = OutputFormat(fmt.lower())
            except ValueError:
                pass

        if os.environ.get("NO_COLOR"):
            config.color = False
        elif os.environ.get("MONARCH_NO_COLOR") == "1":
            config.color = False

        if os.environ.get("MONARCH_VERBOSE") == "1":
            config.verbose = True

        if timeout := os.environ.get("MONARCH_TIMEOUT"):
            try:
                config.timeout_seconds = int(timeout)
            except ValueError:
                pass

        if retries := os.environ.get("MONARCH_MAX_RETRIES"):
            try:
                config.max_retries = int(retries)
            except ValueError:
                pass

        return config


_config: Config | None = None


def get_config() -> Config:
    """Get the global config instance."""
    global _config
    if _config is None:
        _config = Config.load()
    return _config
```

### 3.10 Update Main Entry Point

```python
# src/monarch_cli/main.py (updated)
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

### 3.11 Shell Completions

Typer has built-in completion support - no code changes needed:

```bash
# Install completions
monarch --install-completion bash  # or zsh, fish, powershell

# After reloading shell:
monarch tr<TAB>          # → monarch transactions
monarch transactions li<TAB>  # → monarch transactions list
monarch transactions list --<TAB>  # Shows all options
```

**Add to README:**
```markdown
## Shell Completions

Enable tab completion for your shell:

```bash
# Bash
monarch --install-completion bash
source ~/.bashrc

# Zsh  
monarch --install-completion zsh
source ~/.zshrc

# Fish
monarch --install-completion fish
```

### 3.12 Deliverables
- [ ] All Priority 1 commands implemented and live-tested
- [ ] `monarch accounts list` returns real account data
- [ ] `monarch transactions list` returns real transactions
- [ ] `monarch budgets list` returns real budget data
- [ ] `monarch cashflow summary` returns real cashflow
- [ ] `monarch categories list` returns categories
- [ ] JSON, table, CSV output working
- [ ] Date presets working (`--preset this-month`)
- [ ] Dry run mode working
- [ ] Error messages are helpful with error codes

---

## Phase 4: AI Agent Optimization
**Priority**: P1 (Core use case)

### 4.1 Quiet Mode

Add `--quiet` flag for minimal output (IDs only):

```bash
monarch accounts list --quiet
# Output: ACC123
#         ACC456
#         ACC789
```

### 4.2 Batch Operations with Concurrency Control

```python
# Add to transactions.py
@app.command("batch-update")
@handle_errors
def batch_update(
    category_id: Optional[str] = typer.Option(None, "--category", "-c"),
    stdin: bool = typer.Option(False, "--stdin", help="Read transaction IDs from stdin"),
    max_concurrency: int = typer.Option(4, "--max-concurrency", help="Max parallel operations"),
    dry_run: bool = typer.Option(False, "--dry-run"),
):
    """Update multiple transactions.
    
    Examples:
        echo -e "TXN001\\nTXN002" | monarch transactions batch-update --stdin --category CAT123
        monarch transactions batch-update --stdin --category CAT123 --dry-run
    """
    # Implementation with concurrency control
    ...
```

### 4.3 Deliverables
- [ ] `--quiet` mode works
- [ ] Stdin batch operations work
- [ ] Concurrency control with `--max-concurrency`

---

## Phase 5: Testing & Documentation
**Priority**: P1

### 5.1 Unit Tests

Use CliRunner pattern (see [Testing Patterns](#testing-patterns) section above).

### 5.2 Documentation

README should include:

1. **Installation** - pip install, uv install, pipx install
2. **Quick Start** - Login and first commands
3. **Command Reference** - All commands with examples
4. **AI Agent Integration** - How to use with Claude, GPT, etc.
5. **Shell Completions** - How to enable
6. **Configuration** - Environment variables and config file
7. **Troubleshooting** - Common issues + `monarch auth doctor`

### 5.3 Deliverables
- [ ] Test coverage >70%
- [ ] README is comprehensive
- [ ] Examples for AI agent usage

---

## Command Reference Summary

### MVP Commands (Priority 1)

| Command | Description | `monarchmoney` Method |
|---------|-------------|----------------------|
| `monarch auth login` | Interactive authentication | `login()` / `multi_factor_authenticate()` |
| `monarch auth status` | Check authentication status | (session check) |
| `monarch auth logout` | Remove stored credentials | (session delete) |
| `monarch auth doctor` | Diagnose environment | (storage + API check) |
| `monarch auth ping` | Test API connectivity | `get_accounts()` |
| `monarch accounts list` | List all linked accounts | `get_accounts()` |
| `monarch accounts refresh` | Sync accounts from banks | `request_accounts_refresh()` |
| `monarch transactions list` | List transactions with filters | `get_transactions()` |
| `monarch transactions update <id>` | Recategorize, add notes | `update_transaction()` |
| `monarch categories list` | List categories (for IDs) | `get_transaction_categories()` |
| `monarch budgets list` | Get budget status | `get_budgets()` |
| `monarch cashflow summary` | Income/expense totals | `get_cashflow_summary()` |

> **Deferred to v1.1:** `monarch config` commands

### Global Options

| Option | Description |
|--------|-------------|
| `--format, -f` | Output format: json (default), table, csv, compact |
| `--ndjson` | Stream results as newline-delimited JSON |
| `--raw` | Output raw API response without transforms |
| `--quiet` | Minimal output (IDs only) |
| `--dry-run` | Preview operation without executing |
| `--help` | Show help for any command |
| `--version` | Show version |

> **Deferred to v1.1:** `--query` (use `jq` instead), `--no-cache`

---

## Implementation Order

```
Phase 0 (Setup) ──► Phase 1 (Auth + Core Utils) ──► 🔑 USER AUTH
                                                          │
                                                          ▼
                                                Phase 2 (Output)
                                                          │
                                                          ▼
                                                Phase 3 (Commands)
                                                          │
                                                          ▼
                                               Phase 4 (AI Optimization)
                                                          │
                                                          ▼
                                               Phase 5 (Testing/Docs)
                                                          │
                                                          ▼
                                                     MVP COMPLETE
```

**Key insight:** Auth and core utilities (exceptions, error handler, retry, dates) come first so that all subsequent phases benefit from consistent error handling and can be live-tested.

### MVP Definition (Phases 0-3)
- Login and authentication works (dual-backend: keyring + file)
- Priority 1 commands: accounts, transactions, budgets, cashflow, categories
- JSON, table, CSV output formats
- Date presets (use `jq` for JSON filtering)
- Robust error handling with error codes
- Progress spinners for long operations
- Shell completions
- **14 commands total**

### v1.0 Definition (Phases 0-5)
- All the above plus:
- AI agent optimizations (quiet mode, batch operations)
- Comprehensive tests (unit + live tests for local dev)
- Full documentation

### v1.1+ (Future)
- Priority 2: create/delete transactions, tags, recurring, holdings, budget set
- Priority 3: account history, balances, institutions, networth
- Caching for stable data
- **21+ commands total**

---

## Release Readiness Checklist

### 🔴 P0: Must Fix Before PyPI Publish

1. **Add LICENSE File** ⏱️ 5 min
2. **Control Package Contents** ⏱️ 5 min
3. **Verify Package Metadata** ⏱️ 5 min  
4. **Dynamic Version** ⏱️ 10 min
5. **Verify Build & Install** ⏱️ 5 min
6. **Secure CI for Open Source** ⏱️ 15 min

### 🟠 P1: Strongly Recommended

7. **README Quality** ⏱️ 30 min
8. **Add CHANGELOG.md** ⏱️ 15 min
9. **Add CONTRIBUTING.md** ⏱️ 20 min
10. **Basic CI Workflow** ⏱️ 10 min
11. **pipx/uvx Compatibility** ⏱️ 2 min
12. **Type Hints & py.typed** ⏱️ 5 min
13. **Shell Completions** - Already supported by Typer

### 🟡 P2: Post-Release (v0.2.0+)

- [ ] `CODE_OF_CONDUCT.md`
- [ ] `SECURITY.md` (vulnerability reporting)
- [ ] GitHub issue/PR templates
- [ ] PyPI publish workflow (on version tags)
- [ ] Coverage thresholds in CI
- [ ] Man page generation

---

## Configuration Reference

### Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `MONARCH_TOKEN` | Auth token (for CI/automation) | `eyJ...` |
| `MONARCH_FORMAT` | Default output format | `table` |
| `MONARCH_TIMEOUT` | Request timeout in seconds | `60` |
| `MONARCH_MAX_RETRIES` | Max retry attempts | `5` |
| `MONARCH_VERBOSE` | Enable verbose output | `1` |
| `MONARCH_CONFIG_DIR` | Override config directory | `/custom/path` |
| `MONARCH_SESSION_PATH` | Override session file path | `/custom/session.json` |
| `NO_COLOR` | Disable colors (standard) | `1` |

### Config File (Deferred to v1.1)

> **Note:** TOML config file support deferred to v1.1. Use environment variables above for MVP configuration.

---

## Open Questions

1. **Package name**: Is `monarch-cli` available on PyPI? Alternatives: `monarch-money-cli`, `mmcli`

2. **Rate limiting**: Does Monarch Money API have rate limits we need to handle?

3. **Keyring service ID**: Use `com.monarch-cli` or stay compatible with MCP server's `com.mcp.monarch-mcp-server`?

---

## References

### Libraries
- [monarchmoneycommunity](https://github.com/bradleyseanf/monarchmoneycommunity) - Python library (primary dependency)
- [Typer](https://typer.tiangolo.com/) - CLI framework
- [Rich](https://rich.readthedocs.io/) - Terminal formatting
- [Keyring](https://keyring.readthedocs.io/) - Credential storage
- [platformdirs](https://platformdirs.readthedocs.io/) - Cross-platform paths

### Python Tooling
- [uv](https://docs.astral.sh/uv/) - Fast Python package manager
- [Ruff](https://docs.astral.sh/ruff/) - Fast linter & formatter
- [mypy](https://mypy.readthedocs.io/) - Static type checker
- [pytest](https://docs.pytest.org/) - Testing framework

### CLI Design Guidelines
- [clig.dev](https://clig.dev) - Command Line Interface Guidelines
