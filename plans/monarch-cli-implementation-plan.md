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
- Optimize for AI agent consumption (structured JSON output)
- Flexible authentication: OS keyring (secure, default) or session file (portable)
- Minimal new code - thin wrapper only
- Enable automation and scripting for personal finance workflows

### Non-Goals (v1)
- TUI or interactive mode
- New API functionality beyond what `monarchmoney` provides
- Multi-user OAuth flows
- Local caching or offline mode
- Priority 4 methods (account creation/deletion, splits, etc. - web UI better)

### Tech Stack
- **Language**: Python 3.12+
- **CLI Framework**: Typer (auto-generated help, rich integration)
- **API Client**: `monarchmoney` library (direct dependency)
- **Auth**: Dual-backend token storage - OS keyring (secure, default) or session file (portable)
- **Output**: JSON (default), with optional table formatting via `rich`
- **Testing**: pytest

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
3. User config (`~/.config/monarch-cli/config.json`)
4. Defaults

### Global Flags (all commands)

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `-h, --help` | bool | - | Show help |
| `--version` | bool | - | Show version |
| `-v, --verbose` | bool | false | Verbose output (to stderr) |
| `--format, -f` | choice | json | Output format: json, table, compact |
| `--no-color` | bool | false | Disable colors (also respects `NO_COLOR` env) |
| `--quiet, -q` | bool | false | Minimal output (IDs only) |

### Secrets Handling ⚠️

**Never accept secrets via command-line flags.** They appear in:
- Shell history (`~/.bash_history`, `~/.zsh_history`)
- Process listings (`ps aux`)

**Our approach:**
- Store auth token in OS keyring (secure, default) or session file (portable)
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
# ✅ Good: Immediate feedback
console.print("[dim]Fetching accounts...[/dim]", file=sys.stderr)
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
  -a, --account TEXT    Filter by account ID
  -f, --format TEXT     Output format [default: json]

Examples:
  monarch transactions list
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
│                   Session Management                        │
│  session.py: dual-backend auth (keyring + file, ~120 LOC)   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   MonarchMoney Library                      │
│  43 async methods, GraphQL client for Monarch Money API     │
└─────────────────────────────────────────────────────────────┘
```

### Key Insight

The `monarchmoney` library methods return Python dicts. The CLI wrapper just needs to:
1. Parse CLI arguments
2. Get authenticated client from keyring
3. Call the async method with `run_async()`
4. Print the result as JSON (or format it)

---

## Source Code Analysis

### Auth Pattern (Dual Storage Support)

We support two token storage backends, letting users choose during login:

| Storage | Location | Security | Use Case |
|---------|----------|----------|----------|
| **Keyring** (default) | OS credential store | ✅ Encrypted at rest | Recommended for most users |
| **Session file** | `~/.mm/mm_session.pickle` | ⚠️ Plain file | Portability, containers, compatibility with `monarchmoney` library |

```python
# src/monarch_cli/core/session.py (~120 LOC)
from enum import Enum

class StorageBackend(str, Enum):
    KEYRING = "keyring"
    FILE = "file"

# Keyring constants
KEYRING_SERVICE = "com.monarch-cli"
KEYRING_USERNAME = "monarch-token"

# File constants (matches monarchmoney library default)
SESSION_DIR = ".mm"
SESSION_FILE = f"{SESSION_DIR}/mm_session.pickle"

# Core functions to implement
def save_token(token: str, backend: StorageBackend) -> None
def load_token() -> Optional[str]           # Tries keyring first, then file
def delete_token(backend: StorageBackend | None = None) -> None
def get_storage_backend() -> StorageBackend | None  # Which backend has a token?
def get_authenticated_client() -> MonarchMoney
```

**Load order:** When loading a token, we check keyring first, then fall back to session file. This allows seamless migration and compatibility with users who already have the `monarchmoney` library's session file.

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
│       ├── commands/
│       │   ├── __init__.py
│       │   ├── auth.py          # login, status, logout, setup
│       │   ├── accounts.py
│       │   ├── transactions.py
│       │   ├── budgets.py
│       │   ├── cashflow.py
│       │   └── categories.py
│       ├── core/
│       │   ├── __init__.py
│       │   ├── client.py        # MonarchMoney client wrapper
│       │   ├── session.py       # Dual-backend session management (keyring + file)
│       │   └── async_utils.py   # run_async() helper
│       └── output/
│           ├── __init__.py
│           └── formatters.py    # JSON, table, compact formatters
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # Shared fixtures
│   ├── test_auth.py
│   ├── test_accounts.py
│   ├── test_transactions.py
│   ├── test_output.py
│   └── live/                    # Real API tests (gated)
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

# Live tests (requires MONARCH_TOKEN)
test-live:
	uv run pytest tests/live/ -m live
```

**Usage:**
```bash
make verify    # Run everything sequentially
make test      # Just tests
make lint      # Just linting
```

### Testing Patterns

#### Basic Test Structure

```python
# tests/test_accounts.py
import pytest
from unittest.mock import AsyncMock, patch

from monarch_cli.commands.accounts import list_accounts


class TestListAccounts:
    """Tests for monarch accounts list command."""

    def test_list_accounts_json_output(self, capsys):
        """Should output accounts as JSON."""
        mock_accounts = {
            "accounts": [
                {"id": "ACC1", "displayName": "Checking", "currentBalance": 1000.00}
            ]
        }

        with patch("monarch_cli.commands.accounts.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_accounts.return_value = mock_accounts
            mock_get_client.return_value = mock_client

            list_accounts(format="json")

        captured = capsys.readouterr()
        assert "ACC1" in captured.out
        assert "Checking" in captured.out
        assert "1000" in captured.out

    def test_list_accounts_requires_auth(self):
        """Should error when not authenticated."""
        with patch("monarch_cli.commands.accounts.get_client") as mock_get_client:
            mock_get_client.side_effect = RuntimeError("Not authenticated")

            with pytest.raises(SystemExit) as exc_info:
                list_accounts(format="json")

            assert exc_info.value.code == 1
```

#### Shared Fixtures (conftest.py)

```python
# tests/conftest.py
import pytest
from unittest.mock import AsyncMock, MagicMock


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
def mock_session(mock_monarch_client):
    """Mock the session to return our mock client."""
    with patch("monarch_cli.core.client.get_client") as mock:
        mock.return_value = mock_monarch_client
        yield mock_monarch_client


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
            },
            {
                "id": "acc_456",
                "displayName": "Savings",
                "currentBalance": 10000.00,
                "type": {"name": "savings", "display": "Savings"},
                "institution": {"name": "Chase"},
            },
        ]
    }


@pytest.fixture
def sample_transactions():
    """Sample transaction data for tests."""
    return {
        "allTransactions": {
            "results": [
                {
                    "id": "txn_001",
                    "date": "2026-01-15",
                    "amount": -49.99,
                    "merchant": {"name": "Amazon"},
                    "category": {"name": "Shopping"},
                },
            ]
        }
    }
```

#### Testing CLI Output (stdout/stderr)

```python
# tests/test_output.py
import json
import pytest
from io import StringIO
from unittest.mock import patch

from monarch_cli.output.formatters import output_json, output_table


def test_json_output_is_valid():
    """JSON output should be parseable."""
    data = {"id": "123", "name": "Test"}

    with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
        output_json(data)
        result = mock_stdout.getvalue()

    # Should be valid JSON
    parsed = json.loads(result)
    assert parsed["id"] == "123"


def test_error_goes_to_stderr(capsys):
    """Errors should go to stderr, not stdout."""
    from monarch_cli.output.formatters import output_error

    output_error("Something went wrong")

    captured = capsys.readouterr()
    assert captured.stdout == ""  # Nothing on stdout
    assert "Something went wrong" in captured.stderr
```

#### Live Tests (Gated)

```python
# tests/live/test_live_api.py
import os
import pytest

# Only run if explicitly enabled
pytestmark = pytest.mark.live

LIVE_ENABLED = os.environ.get("MONARCH_LIVE_TESTS") == "1"


@pytest.mark.skipif(not LIVE_ENABLED, reason="Live tests disabled")
class TestLiveAPI:
    """Tests against real Monarch Money API.

    Run with: MONARCH_LIVE_TESTS=1 uv run pytest tests/live/ -m live

    Requires MONARCH_TOKEN environment variable.
    """

    def test_get_accounts_returns_data(self):
        """Should fetch real accounts."""
        from monarch_cli.core.client import get_client
        from monarch_cli.core.async_utils import run_async

        client = get_client()
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

      - name: Test
        run: uv run pytest --cov --cov-report=xml

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

- **Runtime deps:** typer, monarchmoneycommunity, keyring, rich
- **Dev deps:** pytest, pytest-asyncio, pytest-cov, ruff, mypy
- **Tool configs:** All in pyproject.toml (ruff, mypy, pytest, coverage)

> **Note:** Install `monarchmoneycommunity` from PyPI, but import as `monarchmoney`:
> ```python
> from monarchmoney import MonarchMoney  # imports from monarchmoneycommunity package
> ```

### 0.3 Project Structure

Use the src layout from [Python Ecosystem Conventions](#project-structure-src-layout). Key files:

```
monarch-cli/
├── src/monarch_cli/         # Package code
│   ├── __init__.py          # Exports __version__
│   ├── py.typed             # Type hints marker
│   ├── main.py              # Typer app
│   ├── commands/            # Command modules
│   ├── core/                # Client, session, utils
│   └── output/              # Formatters
├── tests/                   # Test files
│   ├── conftest.py          # Shared fixtures
│   └── live/                # Gated live tests
├── pyproject.toml           # ALL config
├── Makefile                 # verify, test, lint commands
└── uv.lock                  # Committed lockfile
```

### 0.4 Deliverables
- [ ] `uv run monarch --help` shows help text
- [ ] `uv run monarch --version` shows version
- [ ] Project structure matches above

---

## Phase 1: Auth Foundation
**Priority**: P0 (Blocker)

> **Why Auth First?** By implementing authentication early, you can authenticate once and then live-test every subsequent feature as it's built. This enables coding agents to write integration tests alongside implementation.

### 1.1 Async Utilities

Port the `run_async()` helper from server.py:

```python
# src/monarch_cli/core/async_utils.py
import asyncio
from concurrent.futures import ThreadPoolExecutor

def run_async(coro):
    """Run async coroutine in sync context."""
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(asyncio.run, coro)
        return future.result()
```

### 1.2 Session Management

Dual-backend session storage (keyring + file):

```python
# src/monarch_cli/core/session.py
import os
import pickle
from enum import Enum
from pathlib import Path
from typing import Optional

import keyring

class StorageBackend(str, Enum):
    KEYRING = "keyring"
    FILE = "file"

# Keyring constants
KEYRING_SERVICE = "com.monarch-cli"
KEYRING_USERNAME = "monarch-token"

# File constants (matches monarchmoney library default)
SESSION_DIR = Path.home() / ".mm"
SESSION_FILE = SESSION_DIR / "mm_session.pickle"


def save_session_token(token: str, backend: StorageBackend = StorageBackend.KEYRING) -> None:
    """Save token to specified backend."""
    if backend == StorageBackend.KEYRING:
        keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, token)
    else:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        with open(SESSION_FILE, "wb") as f:
            pickle.dump({"token": token}, f)


def get_session_token() -> str | None:
    """Retrieve token, checking keyring first, then file."""
    # Try keyring first
    token = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
    if token:
        return token
    
    # Fall back to session file
    if SESSION_FILE.exists():
        with open(SESSION_FILE, "rb") as f:
            data = pickle.load(f)
            return data.get("token")
    
    return None


def get_storage_info() -> dict:
    """Get info about where token is stored."""
    keyring_token = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
    file_exists = SESSION_FILE.exists()
    
    return {
        "has_keyring_token": keyring_token is not None,
        "has_file_token": file_exists,
        "active_backend": StorageBackend.KEYRING if keyring_token else (
            StorageBackend.FILE if file_exists else None
        ),
        "file_path": str(SESSION_FILE),
    }


def delete_session_token(backend: StorageBackend | None = None) -> None:
    """Remove token from specified backend, or all backends if None."""
    if backend is None or backend == StorageBackend.KEYRING:
        try:
            keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
        except keyring.errors.PasswordDeleteError:
            pass
    
    if backend is None or backend == StorageBackend.FILE:
        if SESSION_FILE.exists():
            SESSION_FILE.unlink()


def has_valid_session() -> bool:
    """Check if a session token exists in any backend."""
    return get_session_token() is not None
```

### 1.3 Client Wrapper

```python
# src/monarch_cli/core/client.py
# Note: Install 'monarchmoneycommunity' package, import as 'monarchmoney'
from monarchmoney import MonarchMoney
from .session import get_session_token
from .async_utils import run_async

_client: MonarchMoney | None = None

def get_client() -> MonarchMoney:
    """Get authenticated MonarchMoney client."""
    global _client
    if _client is not None:
        return _client

    token = get_session_token()
    if not token:
        raise RuntimeError(
            "Not authenticated. Run 'monarch auth login' first."
        )

    _client = MonarchMoney()
    _client._headers["Authorization"] = f"Bearer {token}"
    return _client

async def get_client_async() -> MonarchMoney:
    """Get authenticated client for async contexts."""
    return get_client()
```

### 1.4 Minimal Output Helpers

For Phase 1, we only need basic output for auth commands. Full output system comes in Phase 2.

```python
# src/monarch_cli/output/__init__.py (minimal version for Phase 1)
import json
import sys
from enum import Enum
from typing import Any
from rich.console import Console

class OutputFormat(str, Enum):
    JSON = "json"
    TABLE = "table"
    COMPACT = "compact"

console = Console()

def output(data: Any, format: OutputFormat = OutputFormat.JSON) -> None:
    """Output data in specified format. Table support added in Phase 2."""
    if format == OutputFormat.COMPACT:
        print(json.dumps(data, default=str))
    else:
        print(json.dumps(data, indent=2, default=str))

def error(message: str, exit_code: int = 1) -> None:
    """Print error and exit."""
    console.print(f"[red]Error:[/red] {message}", file=sys.stderr)
    sys.exit(exit_code)
```

### 1.5 Main Entry Point (Auth Only)

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

# Phase 3 will add: accounts, transactions, budgets, cashflow, categories

if __name__ == "__main__":
    app()
```

### 1.6 Authentication Commands

```python
# src/monarch_cli/commands/auth.py
import typer
from getpass import getpass
from ..core.session import (
    has_valid_session, delete_session_token, save_session_token,
    get_storage_info, StorageBackend
)
from ..core.async_utils import run_async
from ..output import output, OutputFormat, console
from monarchmoney import MonarchMoney, RequireMFAException

app = typer.Typer(help="Authentication management")


@app.command()
def login(
    storage: StorageBackend = typer.Option(
        None,
        "--storage", "-s",
        help="Token storage backend: keyring (secure, default) or file (portable)"
    ),
):
    """Interactive login to Monarch Money.
    
    Prompts for email and password. If MFA is enabled, prompts for code.
    
    Examples:
        monarch auth login
        monarch auth login --storage file
    """
    console.print("\n[bold]Monarch Money Login[/bold]\n")
    
    email = input("Email: ")
    password = getpass("Password: ")
    
    # Prompt for storage backend if not specified
    if storage is None:
        console.print("\n[dim]How would you like to store your session token?[/dim]")
        console.print("  1. [green]Keyring[/green] (recommended) - Secure OS credential store")
        console.print("  2. [yellow]Session file[/yellow] - ~/.mm/mm_session.pickle (less secure, portable)")
        choice = input("\nChoice [1]: ").strip() or "1"
        storage = StorageBackend.FILE if choice == "2" else StorageBackend.KEYRING
    
    mm = MonarchMoney()
    
    try:
        # Don't let library save its own session file - we handle storage
        run_async(mm.login(email, password, save_session=False))
    except RequireMFAException:
        mfa_code = input("MFA Code: ")
        run_async(mm.multi_factor_authenticate(email, password, mfa_code))
    except Exception as e:
        console.print(f"[red]Login failed:[/red] {e}")
        raise typer.Exit(1)
    
    # Extract and save token
    token = mm._token
    if not token:
        console.print("[red]Login succeeded but no token was returned[/red]")
        raise typer.Exit(1)
    
    save_session_token(token, storage)
    backend_name = "keyring" if storage == StorageBackend.KEYRING else "session file"
    console.print(f"[green]✓ Logged in successfully. Token saved to {backend_name}.[/green]")
    
    # Verify by fetching accounts
    try:
        accounts = run_async(mm.get_accounts())
        count = len(accounts.get("accounts", []))
        console.print(f"[dim]Found {count} linked accounts.[/dim]")
    except Exception:
        pass  # Non-fatal, login already succeeded


@app.command()
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
        monarch auth logout -s file      # Only clear session file
    """
    delete_session_token(storage)
    
    if storage:
        console.print(f"[green]Logged out from {storage.value}[/green]")
    else:
        console.print("[green]Logged out successfully (cleared all backends)[/green]")


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
   • [yellow]Session file[/yellow] - Portable, compatible with monarchmoney library

[dim]Note: Credentials are never stored - only the session token.[/dim]
""")
```

**CLI Usage:**
```bash
monarch auth login               # Interactive login
monarch auth login -s file       # Login with file storage
monarch auth status              # Check if authenticated
monarch auth logout              # Remove stored tokens (all backends)
monarch auth setup               # Show setup instructions
```

### 1.7 Deliverables
- [ ] `monarch --help` shows auth command group
- [ ] `monarch auth login` works with both storage backends
- [ ] `monarch auth status` shows authentication state and backend
- [ ] `monarch auth logout` clears tokens
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

Extend the minimal output system with table support and better formatting:

```python
# src/monarch_cli/output/__init__.py (full version)
import json
import sys
from enum import Enum
from typing import Any
from rich.console import Console
from rich.table import Table

class OutputFormat(str, Enum):
    JSON = "json"
    TABLE = "table"
    COMPACT = "compact"  # Single-line JSON

console = Console()

def output(data: Any, format: OutputFormat = OutputFormat.JSON) -> None:
    """Output data in specified format."""
    if format == OutputFormat.JSON:
        print(json.dumps(data, indent=2, default=str))
    elif format == OutputFormat.COMPACT:
        print(json.dumps(data, default=str))
    elif format == OutputFormat.TABLE:
        if isinstance(data, list):
            print_table(data)
        else:
            print(json.dumps(data, indent=2, default=str))

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

def error(message: str, exit_code: int = 1) -> None:
    """Print error and exit."""
    console.print(f"[red]Error:[/red] {message}", file=sys.stderr)
    sys.exit(exit_code)
```

### 2.2 Deliverables
- [ ] JSON output (default, pretty-printed)
- [ ] Compact output (single-line JSON for piping)
- [ ] Table output (rich tables for human reading)
- [ ] Error messages to stderr with exit codes

---

## Phase 3: Core Commands
**Priority**: P0 (Required for MVP)

> **Note:** With authentication complete, all commands can be live-tested as they're implemented.

### 3.1 Account Commands

```python
# src/monarch_cli/commands/accounts.py
import typer
from typing import Optional
from ..core.client import get_client
from ..core.async_utils import run_async
from ..output import output, OutputFormat, error

app = typer.Typer(help="Account management")

@app.command("list")
def list_accounts(
    format: OutputFormat = typer.Option(OutputFormat.JSON, "--format", "-f")
):
    """List all linked financial accounts."""
    try:
        client = get_client()
        accounts = run_async(client.get_accounts())

        # Transform to cleaner structure
        result = []
        for acc in accounts.get("accounts", []):
            result.append({
                "id": acc.get("id"),
                "name": acc.get("displayName"),
                "type": acc.get("type", {}).get("display"),
                "balance": acc.get("currentBalance"),
                "institution": acc.get("institution", {}).get("name"),
                "is_active": not acc.get("isHidden", False),
            })

        output(result, format)
    except Exception as e:
        error(str(e))

@app.command()
def refresh():
    """Trigger account refresh from financial institutions."""
    try:
        client = get_client()
        run_async(client.request_accounts_refresh_all())
        output({
            "status": "refresh_requested",
            "message": "Account refresh requested from financial institutions"
        })
    except Exception as e:
        error(str(e))

@app.command()
def holdings(
    account_id: str = typer.Argument(..., help="Account ID to get holdings for"),
    format: OutputFormat = typer.Option(OutputFormat.JSON, "--format", "-f")
):
    """Get investment holdings for an account."""
    try:
        client = get_client()
        holdings_data = run_async(client.get_account_holdings(account_id))
        output(holdings_data, format)
    except Exception as e:
        error(str(e))
```

**CLI Usage:**
```bash
monarch accounts list                    # List all accounts (JSON)
monarch accounts list -f table           # List as table
monarch accounts refresh                 # Trigger bank sync
monarch accounts holdings ACC123         # Get holdings for account
```

### 3.2 Transaction Commands

```python
# src/monarch_cli/commands/transactions.py
import typer
from typing import Optional
from datetime import date
from ..core.client import get_client
from ..core.async_utils import run_async
from ..output import output, OutputFormat, error

app = typer.Typer(help="Transaction management")

@app.command("list")
def list_transactions(
    limit: int = typer.Option(100, "--limit", "-l", help="Max transactions to return"),
    offset: int = typer.Option(0, "--offset", "-o", help="Pagination offset"),
    start_date: Optional[str] = typer.Option(None, "--start", "-s", help="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = typer.Option(None, "--end", "-e", help="End date (YYYY-MM-DD)"),
    account_id: Optional[str] = typer.Option(None, "--account", "-a", help="Filter by account ID"),
    format: OutputFormat = typer.Option(OutputFormat.JSON, "--format", "-f")
):
    """List transactions with optional filters."""
    try:
        client = get_client()
        transactions = run_async(client.get_transactions(
            limit=limit,
            offset=offset,
            start_date=start_date,
            end_date=end_date,
            search=None,
            account_ids=[account_id] if account_id else None,
        ))

        # Transform to cleaner structure
        result = []
        for txn in transactions.get("allTransactions", {}).get("results", []):
            result.append({
                "id": txn.get("id"),
                "date": txn.get("date"),
                "amount": txn.get("amount"),
                "description": txn.get("merchant", {}).get("name") or txn.get("plaidName"),
                "category": txn.get("category", {}).get("name"),
                "account": txn.get("account", {}).get("displayName"),
                "is_pending": txn.get("pending", False),
            })

        output(result, format)
    except Exception as e:
        error(str(e))

@app.command()
def create(
    account_id: str = typer.Option(..., "--account", "-a", help="Account ID"),
    amount: float = typer.Option(..., "--amount", help="Amount (negative for expense)"),
    description: str = typer.Option(..., "--description", "-d", help="Transaction description"),
    date: str = typer.Option(..., "--date", help="Date (YYYY-MM-DD)"),
    category_id: Optional[str] = typer.Option(None, "--category", "-c", help="Category ID"),
    merchant_name: Optional[str] = typer.Option(None, "--merchant", "-m", help="Merchant name"),
    format: OutputFormat = typer.Option(OutputFormat.JSON, "--format", "-f")
):
    """Create a new transaction."""
    try:
        client = get_client()
        result = run_async(client.create_transaction(
            account_id=account_id,
            amount=amount,
            merchant_name=merchant_name or description,
            date=date,
            category_id=category_id,
        ))
        output({
            "status": "created",
            "transaction": result
        }, format)
    except Exception as e:
        error(str(e))

@app.command()
def update(
    transaction_id: str = typer.Argument(..., help="Transaction ID to update"),
    amount: Optional[float] = typer.Option(None, "--amount", help="New amount"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="New description"),
    category_id: Optional[str] = typer.Option(None, "--category", "-c", help="New category ID"),
    date: Optional[str] = typer.Option(None, "--date", help="New date (YYYY-MM-DD)"),
    format: OutputFormat = typer.Option(OutputFormat.JSON, "--format", "-f")
):
    """Update an existing transaction."""
    try:
        client = get_client()

        # Build update kwargs - only include non-None values
        update_kwargs = {"transaction_id": transaction_id}
        if amount is not None:
            update_kwargs["amount"] = amount
        if description is not None:
            update_kwargs["merchant_name"] = description
        if category_id is not None:
            update_kwargs["category_id"] = category_id
        # Note: date update may not be supported by monarchmoney API

        result = run_async(client.update_transaction(**update_kwargs))
        output({
            "status": "updated",
            "transaction_id": transaction_id
        }, format)
    except Exception as e:
        error(str(e))
```

**CLI Usage:**
```bash
# List transactions
monarch transactions list
monarch transactions list --limit 50 --start 2024-12-01
monarch transactions list -a ACC123 -f table

# Create transaction
monarch transactions create \
  --account ACC123 \
  --amount -50.00 \
  --description "Groceries" \
  --date 2024-12-22

# Update transaction
monarch transactions update TXN456 --category CAT789
```

### 3.3 Budget Commands

```python
# src/monarch_cli/commands/budgets.py
import typer
from ..core.client import get_client
from ..core.async_utils import run_async
from ..output import output, OutputFormat, error

app = typer.Typer(help="Budget tracking")

@app.command("list")
def list_budgets(
    format: OutputFormat = typer.Option(OutputFormat.JSON, "--format", "-f")
):
    """Get budget status with spent/remaining amounts."""
    try:
        client = get_client()
        budgets = run_async(client.get_budgets())

        # Transform to cleaner structure
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
    except Exception as e:
        error(str(e))
```

**CLI Usage:**
```bash
monarch budgets list                     # Get all budgets (JSON)
monarch budgets list -f table            # Budget status as table
```

### 3.4 Cashflow Commands

```python
# src/monarch_cli/commands/cashflow.py
import typer
from typing import Optional
from ..core.client import get_client
from ..core.async_utils import run_async
from ..output import output, OutputFormat, error

app = typer.Typer(help="Cashflow analysis")

@app.command("summary")
def cashflow_summary(
    start_date: Optional[str] = typer.Option(None, "--start", "-s", help="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = typer.Option(None, "--end", "-e", help="End date (YYYY-MM-DD)"),
    format: OutputFormat = typer.Option(OutputFormat.JSON, "--format", "-f")
):
    """Get income/expense analysis for date range."""
    try:
        client = get_client()
        cashflow = run_async(client.get_cashflow_summary(
            start_date=start_date,
            end_date=end_date,
        ))

        output(cashflow, format)
    except Exception as e:
        error(str(e))
```

**CLI Usage:**
```bash
monarch cashflow summary
monarch cashflow summary --start 2024-10-01 --end 2024-12-31
```

### 3.5 Update Main Entry Point

Add remaining command groups to main.py:

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

if __name__ == "__main__":
    app()
```

### 3.6 Deliverables
- [ ] All Priority 1 commands implemented and live-tested
- [ ] `monarch accounts list` returns real account data
- [ ] `monarch transactions list` returns real transactions
- [ ] `monarch budgets list` returns real budget data
- [ ] `monarch cashflow summary` returns real cashflow
- [ ] JSON output is clean and consistent
- [ ] Table output is human-readable
- [ ] Error messages are helpful

---

## Phase 4: AI Agent Optimization
**Priority**: P1 (Core use case)

### 4.1 Structured Error Output

```python
# Add to output/__init__.py
def error_json(code: str, message: str, details: dict | None = None) -> None:
    """Output structured error for AI agents."""
    result = {
        "error": True,
        "code": code,
        "message": message,
    }
    if details:
        result["details"] = details
    print(json.dumps(result))
    sys.exit(1)
```

**Error Codes:**
- `AUTH_REQUIRED` - Not authenticated
- `AUTH_EXPIRED` - Session expired
- `NOT_FOUND` - Resource not found
- `INVALID_INPUT` - Bad parameters
- `API_ERROR` - Monarch API error
- `RATE_LIMITED` - Too many requests

### 4.2 Quiet Mode

Add `--quiet` flag for minimal output (IDs only):

```bash
monarch accounts list --quiet
# Output: ACC123
#         ACC456
#         ACC789

monarch transactions list --quiet
# Output: TXN001
#         TXN002
```

### 4.3 Specific Field Extraction

```bash
monarch accounts list --field balance
# Output: 5000.50
#         1234.00

monarch transactions list --limit 1 --field amount,category
# Output: {"amount": -49.99, "category": "Groceries"}
```

### 4.4 Stdin Support for Batch Operations

```bash
# Update multiple transactions
echo -e "TXN001\nTXN002\nTXN003" | monarch transactions update --stdin --category CAT123
```

### 4.5 Deliverables
- [ ] JSON errors are structured with codes
- [ ] `--quiet` mode works
- [ ] `--field` extraction works
- [ ] Stdin batch operations work

---

## Phase 5: Testing & Documentation
**Priority**: P1

### 5.1 Unit Tests

```python
# tests/test_commands/test_accounts.py
import pytest
from unittest.mock import patch, MagicMock
from monarch_cli.commands.accounts import list_accounts

def test_list_accounts_json_output(capsys):
    mock_accounts = {
        "accounts": [
            {"id": "ACC1", "displayName": "Checking", "currentBalance": 1000}
        ]
    }

    with patch("monarch_cli.commands.accounts.get_client") as mock_client:
        mock_client.return_value.get_accounts = MagicMock(return_value=mock_accounts)
        list_accounts(format="json")

    captured = capsys.readouterr()
    assert "ACC1" in captured.out
    assert "Checking" in captured.out
```

### 5.2 Documentation

README should include:

1. **Installation** - pip install, uv install
2. **Quick Start** - Login and first commands
3. **Command Reference** - All commands with examples
4. **AI Agent Integration** - How to use with Claude, GPT, etc.
5. **Troubleshooting** - Common issues

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
| `monarch accounts list` | List all linked accounts | `get_accounts()` |
| `monarch accounts refresh` | Sync accounts from banks | `request_accounts_refresh()` |
| `monarch transactions list` | List transactions with filters | `get_transactions()` |
| `monarch transactions update <id>` | Recategorize, add notes | `update_transaction()` |
| `monarch categories list` | List categories (for IDs) | `get_transaction_categories()` |
| `monarch budgets list` | Get budget status | `get_budgets()` |
| `monarch cashflow summary` | Income/expense totals | `get_cashflow_summary()` |

### Phase 2 Commands (Priority 2)

| Command | Description | `monarchmoney` Method |
|---------|-------------|----------------------|
| `monarch transactions create` | Manual transaction entry | `create_transaction()` |
| `monarch transactions delete <id>` | Remove transaction | `delete_transaction()` |
| `monarch tags list` | List available tags | `get_transaction_tags()` |
| `monarch transactions tag <id>` | Apply tags to transaction | `set_transaction_tags()` |
| `monarch recurring list` | Upcoming bills/subscriptions | `get_recurring_transactions()` |
| `monarch accounts holdings <id>` | Investment positions | `get_account_holdings()` |
| `monarch budgets set` | Adjust budget amounts | `set_budget_amount()` |
| `monarch cashflow detailed` | Full breakdown | `get_cashflow()` |

### Phase 3 Commands (Priority 3)

| Command | Description | `monarchmoney` Method |
|---------|-------------|----------------------|
| `monarch accounts history <id>` | Balance over time | `get_account_history()` |
| `monarch accounts balances` | Daily balance snapshots | `get_recent_account_balances()` |
| `monarch accounts update <id>` | Rename, hide account | `update_account()` |
| `monarch institutions list` | Connection status | `get_institutions()` |
| `monarch networth history` | Net worth over time | `get_aggregate_snapshots()` |

### Global Options

| Option | Description |
|--------|-------------|
| `--format, -f` | Output format: json (default), table, compact |
| `--quiet, -q` | Minimal output (IDs only) |
| `--help` | Show help for any command |
| `--version` | Show version |

---

## Implementation Order

```
Phase 0 (Setup) ──► Phase 1 (Auth) ──► 🔑 USER AUTH ──► Phase 2 (Output)
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

**Key insight:** Auth comes first so that all subsequent phases can be live-tested.

### MVP Definition (Phases 0-3)
- Login and authentication works (dual-backend: keyring + file)
- Priority 1 commands: accounts, transactions, budgets, cashflow, categories
- JSON and table output formats
- Basic error handling
- **10 commands total**

### v1.0 Definition (Phases 0-5)
- All the above plus:
- AI agent optimizations (quiet mode, field extraction, stdin)
- Comprehensive tests (unit + integration with live API)
- Full documentation

### v1.1+ (Future)
- Priority 2: create/delete transactions, tags, recurring, holdings, budget set
- Priority 3: account history, balances, institutions, networth
- **21 commands total**

---

## Agent Workflow Stages

For coding agents building this CLI incrementally:

### Stage 1: Project Setup (Phase 0)
```
GOAL: Minimal working CLI with help and version
TASKS:
- [ ] Initialize project (pyproject.toml with dependencies)
- [ ] Create src/monarch_cli/__init__.py
- [ ] Create src/monarch_cli/main.py with Typer app
- [ ] Add --help, --version flags
- [ ] Add signal handling (SIGINT → exit 130)
- [ ] Verify: `uv run monarch --help` works
```

### Stage 2: Auth Foundation (Phase 1)
```
GOAL: Working authentication with dual-backend storage
TASKS:
- [ ] Create src/monarch_cli/core/async_utils.py (run_async helper)
- [ ] Create src/monarch_cli/core/session.py (dual-backend: keyring + file)
- [ ] Create src/monarch_cli/core/client.py (get authenticated client)
- [ ] Create src/monarch_cli/output/__init__.py (minimal: JSON + error)
- [ ] Add `monarch auth login` (interactive, with storage choice)
- [ ] Add `monarch auth status` (shows storage backend)
- [ ] Add `monarch auth logout` (can target specific backend)
- [ ] Add `monarch auth setup` (instructions)
- [ ] Verify: Can login with either storage backend
```

### 🔑 USER CHECKPOINT
```
GOAL: User authenticates to enable live testing
ACTION: User runs `monarch auth login` and provides credentials
RESULT: Token stored, all subsequent stages can make live API calls
```

### Stage 3: Output System (Phase 2)
```
GOAL: Consistent, scriptable output
TASKS:
- [ ] Extend src/monarch_cli/output/__init__.py with table support
- [ ] Implement JSON output (default, pretty-printed)
- [ ] Implement table output (rich tables)
- [ ] Implement compact output (single-line JSON)
- [ ] Add TTY detection (colors only in TTY)
- [ ] Verify: Output formatting works correctly
```

### Stage 4: Core Commands (Phase 3)
```
GOAL: Core financial commands working (can live-test each!)
TASKS:
- [ ] monarch accounts list
- [ ] monarch accounts refresh
- [ ] monarch accounts holdings
- [ ] monarch transactions list (with filters)
- [ ] monarch transactions update
- [ ] monarch categories list
- [ ] monarch budgets list
- [ ] monarch cashflow summary
- [ ] Update main.py to register all command groups
- [ ] Verify: All commands return real data, output valid JSON
```

### Stage 5: Error Handling & Polish (Phase 4)
```
GOAL: Graceful, informative errors + AI agent optimizations
TASKS:
- [ ] Structured error JSON (code, message, details)
- [ ] Human-readable errors to stderr
- [ ] Exit code 1 for errors, 2 for usage errors
- [ ] Handle API errors (rate limit, auth expired, etc.)
- [ ] Add --verbose for debug info
- [ ] Add --quiet mode (IDs only)
- [ ] Add --field extraction
- [ ] Verify: Errors don't crash, show helpful messages
```

### Stage 6: Testing & Documentation (Phase 5)
```
GOAL: Confidence + ready for users
TASKS:
- [ ] Set up pytest with pytest-asyncio
- [ ] Unit tests with mocked monarchmoney client
- [ ] Integration tests using stored auth token
- [ ] Test error handling paths
- [ ] Reach 70%+ coverage
- [ ] README with installation, quick start, examples
- [ ] Help text includes examples for each command
- [ ] Verify: New user can install and use in 5 minutes
```

### Stage 7: Power User Commands (v1.1 - Future)
```
GOAL: Extended features for power users
TASKS:
- [ ] monarch transactions create
- [ ] monarch transactions delete
- [ ] monarch tags list
- [ ] monarch transactions tag
- [ ] monarch recurring list
- [ ] monarch budgets set
- [ ] monarch cashflow detailed
- [ ] monarch accounts history
- [ ] monarch networth history
```

---

## Release Readiness Checklist

Based on the [raindrop-cli release plan](https://github.com/crcatala/raindrop-cli-spike/blob/main/plans/RELEASE-READINESS-v0.1.0.md), adapted for Python/PyPI.

### 🔴 P0: Must Fix Before PyPI Publish

These are **release blockers**.

#### 1. Add LICENSE File ⏱️ 5 min

```bash
cat > LICENSE << 'EOF'
MIT License

Copyright (c) 2026 [Your Name]

Permission is hereby granted, free of charge, to any person obtaining a copy
...
EOF
```

#### 2. Control Package Contents ⏱️ 5 min

Ensure only necessary files are included in the wheel/sdist.

**In `pyproject.toml`:**
```toml
[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
"*" = ["py.typed"]  # For type hints

# Exclude dev files
[tool.setuptools.exclude-package-data]
"*" = ["tests/*", "plans/*", "*.md"]
```

**Verify:**
```bash
uv build
tar -tzf dist/*.tar.gz | head -20  # Check contents
```

#### 3. Verify Package Metadata ⏱️ 5 min

```toml
[project]
name = "monarch-cli"
version = "0.1.0"
description = "CLI for Monarch Money - AI agent friendly financial data access"
readme = "README.md"
license = {text = "MIT"}
authors = [{name = "Your Name", email = "you@example.com"}]
keywords = ["monarch-money", "cli", "finance", "budgeting"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Environment :: Console",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3.12",
    "Topic :: Office/Business :: Financial",
]

[project.urls]
Homepage = "https://github.com/yourname/monarch-cli"
Repository = "https://github.com/yourname/monarch-cli"
Issues = "https://github.com/yourname/monarch-cli/issues"
```

#### 4. Dynamic Version ⏱️ 10 min

Don't hardcode version in multiple places.

**Option A: Single source in pyproject.toml**
```toml
[project]
version = "0.1.0"
```

```python
# src/monarch_cli/__init__.py
from importlib.metadata import version
__version__ = version("monarch-cli")
```

**Option B: Use setuptools-scm for git tags**
```toml
[build-system]
requires = ["setuptools>=61", "setuptools-scm"]

[tool.setuptools_scm]
```

#### 5. Verify Build & Install ⏱️ 5 min

```bash
# Clean build
rm -rf dist/ build/ *.egg-info
uv build

# Test install in isolated env
uv venv /tmp/test-install
source /tmp/test-install/bin/activate
pip install dist/*.whl

# Smoke test
monarch --help
monarch --version
monarch auth status  # Should show auth error, not crash
```

#### 6. Secure CI for Open Source ⏱️ 15 min

If you have CI workflows that use secrets (API tokens for live tests):

```yaml
# Only run for repo members, not forks
jobs:
  live-tests:
    if: github.event.pull_request.head.repo.full_name == github.repository
```

Or remove live test workflows before going public.

---

### 🟠 P1: Strongly Recommended

#### 7. README Quality ⏱️ 30 min

- [ ] Installation instructions (`pip install`, `pipx install`, `uv tool install`)
- [ ] Quick start with working examples
- [ ] All command examples are accurate and tested
- [ ] Document environment variables (`MONARCH_TOKEN`)
- [ ] Requirements section (Python 3.12+)
- [ ] Badges (PyPI version, license, Python versions)

```markdown
[![PyPI version](https://img.shields.io/pypi/v/monarch-cli)](https://pypi.org/project/monarch-cli/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
```

#### 8. Add CHANGELOG.md ⏱️ 15 min

```markdown
# Changelog

All notable changes documented here. Format: [Keep a Changelog](https://keepachangelog.com/).

## [0.1.0] - 2026-XX-XX

### Added
- Initial public release
- Authentication: `monarch auth login/status/logout/setup`
- Dual token storage: OS keyring (secure) or session file (portable)
- Accounts: `list`, `refresh`, `holdings`
- Transactions: `list`, `update`, `create`, `delete`
- Budgets: `list`, `set`
- Cashflow: `summary`, `detailed`
- Categories and tags management
- Output formats: `--format json|table|compact`
- AI agent optimizations: `--quiet`, structured JSON errors
```

#### 9. Add CONTRIBUTING.md ⏱️ 20 min

```markdown
# Contributing

## Setup
git clone https://github.com/yourname/monarch-cli
cd monarch-cli
uv sync

## Development
uv run pytest              # Run tests
uv run ruff check .        # Lint
uv run mypy src/           # Type check
uv run monarch --help      # Run locally

## Testing with Real Account
monarch auth login         # Interactive login, or:
export MONARCH_TOKEN=...   # Set token via environment
uv run pytest tests/live/  # Live tests (use test account!)
```

#### 10. Basic CI Workflow ⏱️ 10 min

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv sync
      - run: uv run pytest
      - run: uv run ruff check .
      - run: uv run mypy src/
```

#### 11. pipx/uvx Compatibility ⏱️ 2 min

Ensure the package works with `pipx install monarch-cli` and `uvx monarch`:

```bash
pipx install dist/*.whl
monarch --help  # Must work

uvx --from dist/*.whl monarch --help  # Must work
```

#### 12. Type Hints & py.typed ⏱️ 5 min

For library consumers who want type checking:

```bash
touch src/monarch_cli/py.typed
```

Add to package data in pyproject.toml (see P0.2).

---

### 🟡 P2: Post-Release (v0.2.0+)

- [ ] `CODE_OF_CONDUCT.md`
- [ ] `SECURITY.md` (vulnerability reporting)
- [ ] GitHub issue/PR templates
- [ ] PyPI publish workflow (on version tags)
- [ ] Coverage thresholds in CI
- [ ] Shell completions (`--install-completion`)
- [ ] Man page generation

---

### Pre-Publish Checklist

Run **in order** before `uv publish` or `twine upload`:

```bash
# 1. Clean slate
rm -rf dist/ build/ *.egg-info
uv sync

# 2. Quality gates
uv run pytest
uv run ruff check .
uv run mypy src/

# 3. Build
uv build

# 4. Smoke test
uv venv /tmp/smoke-test && source /tmp/smoke-test/bin/activate
pip install dist/*.whl
monarch --help
monarch --version
deactivate

# 5. Verify package contents
tar -tzf dist/*.tar.gz | grep -E "^[^/]+/$"  # Top-level dirs only

# 6. Final doc review
head -50 README.md
ls LICENSE
head -20 CHANGELOG.md

# 7. Publish (test PyPI first!)
uv publish --repository testpypi
pip install -i https://test.pypi.org/simple/ monarch-cli
# Verify it works, then:
uv publish
```

**Then tag:**
```bash
git tag v0.1.0
git push origin v0.1.0
```

---

## Open Questions

1. **Package name**: Is `monarch-cli` available on PyPI? Alternatives: `monarch-money-cli`, `mmcli`

2. **Keyring compatibility**: Should we support fallback to env vars for containerized environments?

3. **Rate limiting**: Does Monarch Money API have rate limits we need to handle?

4. **Keyring service ID**: Use `com.monarch-cli` or stay compatible with MCP server's `com.mcp.monarch-mcp-server`?
   - Pro compatibility: Users who have MCP server auth can reuse token
   - Pro new ID: Clean separation, avoid conflicts

5. **Transaction search**: `get_transactions()` supports `search` param - expose as `--search` flag?

---

## References

### Libraries
- [monarchmoneycommunity](https://github.com/bradleyseanf/monarchmoneycommunity) - Python library (primary dependency, actively maintained fork)
- [monarchmoney](https://github.com/hammem/monarchmoney) - Original library (unmaintained, for historical reference)
- [monarch-mcp-server](https://github.com/robcerda/monarch-mcp-server) - Reference for keyring auth pattern
- [Typer](https://typer.tiangolo.com/) - CLI framework
- [Rich](https://rich.readthedocs.io/) - Terminal formatting
- [Keyring](https://keyring.readthedocs.io/) - Credential storage

### Python Tooling
- [uv](https://docs.astral.sh/uv/) - Fast Python package manager (by Astral)
- [Ruff](https://docs.astral.sh/ruff/) - Fast linter & formatter (by Astral)
- [mypy](https://mypy.readthedocs.io/) - Static type checker
- [pytest](https://docs.pytest.org/) - Testing framework
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/) - Async test support
- [run-parallel](https://gist.github.com/mitsuhiko/a4b6b70e96c8075b92a4de00b340cc52) - Parallel task runner with live status (by Armin Ronacher)

### CLI Design Guidelines
- [clig.dev](https://clig.dev) - Command Line Interface Guidelines
- [TypeScript CLI Playbook](./cli-playbook.md) - Internal reference (language-agnostic principles apply)
- [Release Readiness Plan](https://github.com/crcatala/raindrop-cli-spike/blob/main/plans/RELEASE-READINESS-v0.1.0.md) - OSS release checklist (adapted for Python)
