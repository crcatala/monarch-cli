# Review of Monarch CLI Implementation Plan

After careful analysis, I've identified several areas of unnecessary complexity that don't add proportional value for an MVP. Here are my recommendations, organized by impact:

---

## 1. Remove JMESPath Query Support - Use `jq` Instead

### Analysis
JMESPath adds a dependency (`jmespath>=1.0.0`) and requires users to learn a query language that's less common than `jq`. Since output is JSON by default, users can already do:

```bash
monarch accounts list | jq '[.[] | select(.balance > 1000)]'
```

JMESPath provides no capability that `jq` doesn't have, and `jq` is:
- More widely known
- More powerful
- Already installed on most dev machines
- Has better documentation and community

The `--query` flag adds complexity to every command for marginal benefit.

### Diff
```diff
--- a/plans/monarch-cli-implementation-plan.md
+++ b/plans/monarch-cli-implementation-plan.md
@@ dependencies section
 dependencies = [
     "typer[all]>=0.9.0",
     "monarchmoneycommunity>=1.0.0",
     "keyring>=24.0.0",
     "rich>=13.0.0",
     "platformdirs>=4.0.0",
     "tomli>=2.0.0;python_version<'3.11'",
     "tomli-w>=1.0.0",
     "httpx>=0.27.0",  # For retry/timeout handling
-    "jmespath>=1.0.0",  # For --query support
 ]

@@ Global Flags section
 | `--ndjson` | bool | false | Stream results as newline-delimited JSON |
 | `--raw` | bool | false | Output raw API response without transforms |
-| `--no-color` | bool | false | Disable colors (also respects `NO_COLOR` env) |
-| `--quiet, -q` | bool | false | Minimal output (IDs only) |
-| `--no-cache` | bool | false | Bypass cache for this request |
+| `--no-color` | bool | false | Disable colors (respects `NO_COLOR` env) |
 | `--dry-run` | bool | false | Preview operation without executing (mutations) |

@@ Remove output/query.py entirely
-# src/monarch_cli/output/query.py
-"""JMESPath query support for flexible data extraction."""
-
-import jmespath
-from typing import Any
-
-
-def apply_query(data: Any, query: str | None) -> Any:
-    """Apply JMESPath query to data if provided."""
-    if query is None:
-        return data
-    return jmespath.search(query, data)

@@ Update commands to remove --query flag (example: accounts.py)
 @app.command("list")
 @handle_errors
 def list_accounts(
     format: OutputFormat = typer.Option(OutputFormat.JSON, "--format", "-f"),
-    query: Optional[str] = typer.Option(None, "--query", "-q", help="JMESPath query"),
     ndjson: bool = typer.Option(False, "--ndjson", help="Stream as newline-delimited JSON"),
     raw: bool = typer.Option(False, "--raw", help="Output raw API response"),
 ):
     """List all linked financial accounts.
     
     Examples:
         monarch accounts list
         monarch accounts list -f table
-        monarch accounts list --query "[?is_active].{name:name, balance:balance}"
+        monarch accounts list | jq '[.[] | select(.is_active)]'
     """
```

---

## 2. Remove Legacy Pickle Compatibility Storage

### Analysis
The `FILE_COMPAT` storage backend for pickle files:
- Is a **security risk** (pickle deserialization is unsafe)
- Targets users migrating from the `monarchmoney` library's session file
- These users are a tiny minority (most people use the library programmatically, not for CLI auth)
- Adds code paths that need testing and maintenance

Two backends (keyring + JSON file) is sufficient. Users who have pickle sessions can simply re-login.

### Diff
```diff
--- a/plans/monarch-cli-implementation-plan.md
+++ b/plans/monarch-cli-implementation-plan.md
@@ Session Management section
 class StorageBackend(str, Enum):
     KEYRING = "keyring"
     FILE = "file"              # Safe JSON with 0600 perms
-    FILE_COMPAT = "file-compat"  # Legacy pickle (opt-in only)
 
 # Keyring constants
 KEYRING_SERVICE = "com.monarch-cli"
 KEYRING_USERNAME = "monarch-token"

-# Legacy compat path (pickle, unsafe)
-COMPAT_SESSION_PATH = Path.home() / ".mm" / "mm_session.pickle"
-
 
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
             os.chmod(fd, 0o600)  # Strict permissions before writing
             with os.fdopen(fd, "w") as f:
                 json.dump({"token": token}, f)
             os.rename(tmp_path, session_path)
         except Exception:
             if os.path.exists(tmp_path):
                 os.unlink(tmp_path)
             raise
-    elif backend == StorageBackend.FILE_COMPAT:
-        # Legacy pickle - explicit opt-in only
-        import pickle
-        COMPAT_SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
-        with open(COMPAT_SESSION_PATH, "wb") as f:
-            pickle.dump({"token": token}, f)
 

 def get_session_token() -> str | None:
-    """Retrieve token, checking keyring first, then file, then compat."""
+    """Retrieve token, checking keyring first, then file."""
     # Try keyring first
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
 
-    # Fall back to legacy compat pickle (only if it exists)
-    if COMPAT_SESSION_PATH.exists():
-        import pickle
-        try:
-            with open(COMPAT_SESSION_PATH, "rb") as f:
-                data = pickle.load(f)
-                return data.get("token")
-        except Exception:
-            pass
-
     return None
 
@@ Auth table update
-| **Session file (compat)** | `~/.mm/mm_session.pickle` | ❌ Unsafe (pickle) | Only for library interop (opt-in) |
-
-**Security Note**: The default session file uses JSON with atomic writes and 0600 permissions, not pickle. Pickle is only available as explicit opt-in (`--storage file-compat`) for users who need compatibility with the `monarchmoney` library's session file.
-
-**Load order:** When loading a token, we check keyring first, then JSON session file, then (if enabled) compat pickle. This allows seamless migration and compatibility.
+**Load order:** When loading a token, we check keyring first, then JSON session file.
```

---

## 3. Remove Service Layer for MVP - Commands Call Adapter Directly

### Analysis
The current architecture has:
```
Commands → Services → Adapter → Library
```

But looking at the service implementations, they're extremely thin:
```python
def list_accounts() -> list[dict]:
    client = get_authenticated_client()
    raw = run_async(client.get_accounts())
    return transform_accounts(raw)
```

This is just 3 lines that could live in the command. The service layer adds:
- Extra files to maintain
- Indirection without abstraction benefit
- No actual business logic (that's in transformers)

For MVP, simplify to:
```
Commands → Adapter → Library
           ↓
       Transformers
```

Services can be added later if commands get complex.

### Diff
```diff
--- a/plans/monarch-cli-implementation-plan.md
+++ b/plans/monarch-cli-implementation-plan.md
@@ Project Structure
 │       ├── core/                # Infrastructure
 │       │   ├── __init__.py
 │       │   ├── adapter.py       # Isolates monarchmoney private details
 │       │   ├── session.py       # Dual-backend session management
 │       │   ├── async_utils.py   # run_async() helper
 │       │   ├── config.py        # Configuration system
 │       │   ├── exceptions.py    # Exception hierarchy
 │       │   ├── error_handler.py # Error handling decorator
-│       │   ├── retry.py         # Retry with exponential backoff
-│       │   ├── cache.py         # TTL caching (v1.1)
 │       │   └── dates.py         # Date utilities and presets
-│       ├── services/            # Business logic layer
-│       │   ├── __init__.py
-│       │   ├── accounts.py
-│       │   ├── transactions.py
-│       │   ├── budgets.py
-│       │   └── cashflow.py
 │       ├── transformers/        # API response → CLI output
 │       │   ├── __init__.py
 │       │   ├── accounts.py
 │       │   ├── transactions.py
 │       │   └── budgets.py

@@ Architecture diagram
 ┌─────────────────────────────────────────────────────────────┐
 │                        CLI Layer                            │
-│  (Typer commands with argument parsing)                     │
+│  Commands + Transformers                                    │
 └─────────────────────────────────────────────────────────────┘
                               │
                               ▼
 ┌─────────────────────────────────────────────────────────────┐
-│                     Service Layer                           │
-│  services/*.py: business logic, retries, error mapping      │
-└─────────────────────────────────────────────────────────────┘
-                              │
-                              ▼
-┌─────────────────────────────────────────────────────────────┐
 │                  Adapter / Client Layer                     │
-│  adapter.py: isolates upstream library private details      │
-│  session.py: dual-backend auth (keyring + file)             │
+│  adapter.py + session.py                                    │
 └─────────────────────────────────────────────────────────────┘

-### Key Design Decisions
-
-1. **Adapter Pattern**: All access to `monarchmoneycommunity` private attributes (`_headers`, `_token`) is isolated in `adapter.py`. This protects against upstream changes.
-
-2. **Service Layer**: Business logic (transforms, retries, error mapping) lives in `services/*.py`, not in command handlers. Commands stay thin.
-
-3. **Transformers**: Data transformation from raw API responses to stable CLI schemas lives in `transformers/*.py`, making it testable in isolation.
+**Design:** Commands are intentionally thin - they parse args, call adapter, transform with `transformers/*.py`, and output. The adapter isolates upstream library private details.

@@ Remove services section entirely (3.2) and update accounts command
-### 3.2 Services
-
-```python
-# src/monarch_cli/services/accounts.py
-...
-```

 ### 3.3 Account Commands
 
 ```python
 # src/monarch_cli/commands/accounts.py
 import typer
 from typing import Optional
 from ..core.error_handler import handle_errors
-from ..services import accounts as account_service
+from ..core.adapter import get_authenticated_client
+from ..core.async_utils import run_async
+from ..transformers.accounts import transform_accounts
 from ..output import output, OutputFormat
 from ..output.progress import spinner
-from ..output.query import apply_query
 
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
     """
     with spinner("Fetching accounts..."):
-        if raw:
-            from ..core.adapter import get_authenticated_client
-            from ..core.async_utils import run_async
-            client = get_authenticated_client()
-            result = run_async(client.get_accounts())
-        else:
-            result = account_service.list_accounts()
+        client = get_authenticated_client()
+        result = run_async(client.get_accounts())
 
-    result = apply_query(result, query)
+    if not raw:
+        result = transform_accounts(result)
+    
     output(result, format, ndjson=ndjson, raw=raw)
 
 
 @app.command()
 @handle_errors
 def refresh():
     """Trigger account refresh from financial institutions."""
     with spinner("Requesting account refresh..."):
-        result = account_service.refresh_accounts()
-    output(result)
+        client = get_authenticated_client()
+        run_async(client.request_accounts_refresh())
+    
+    output({
+        "status": "refresh_requested",
+        "message": "Account refresh requested. Balances will update shortly."
+    })
```

---

## 4. Remove Retry Module Until Actually Integrated

### Analysis
The `retry.py` module with `with_retry()` is defined but never used in any command implementation. It's speculative infrastructure:
- Adds code to maintain
- Async retry pattern but commands are sync
- No evidence Monarch API needs retry logic

Add retry when you have evidence it's needed (e.g., you see transient failures in practice).

### Diff
```diff
--- a/plans/monarch-cli-implementation-plan.md
+++ b/plans/monarch-cli-implementation-plan.md
@@ Remove entire section 1.6 Retry Logic
-### 1.6 Retry Logic
-
-```python
-# src/monarch_cli/core/retry.py
-"""Retry logic with exponential backoff."""
-
-import asyncio
-import random
-from typing import TypeVar, Callable, Awaitable, Any
-
-from .exceptions import NetworkError, RateLimitError
-
-T = TypeVar("T")
-
-# Exceptions that should trigger retry
-RETRYABLE_EXCEPTIONS = (
-    ConnectionError,
-    TimeoutError,
-    OSError,
-)
-
-
-async def with_retry(
-    coro_factory: Callable[[], Awaitable[T]],
-    max_retries: int = 3,
-    base_delay: float = 1.0,
-    max_delay: float = 30.0,
-    jitter: bool = True,
-) -> T:
-    """Execute an async operation with exponential backoff retry."""
-    ...
-```
+> **Note:** Retry logic deferred to v1.1 - add when transient failures are observed in practice.

@@ Remove httpx from dependencies (only used for retry)
 dependencies = [
     "typer[all]>=0.9.0",
     "monarchmoneycommunity>=1.0.0",
     "keyring>=24.0.0",
     "rich>=13.0.0",
     "platformdirs>=4.0.0",
     "tomli>=2.0.0;python_version<'3.11'",
     "tomli-w>=1.0.0",
-    "httpx>=0.27.0",  # For retry/timeout handling
 ]
```

---

## 5. Simplify Config System - Defer TOML File to v1.1

### Analysis
The config system has three layers: CLI flags → env vars → TOML file → defaults.

For a CLI tool used mostly ad-hoc:
- Users typically set flags per-invocation
- Env vars in `.bashrc` cover persistent preferences
- A TOML config file adds complexity with minimal benefit

The full config system requires:
- `tomli` (read) + `tomli_w` (write) dependencies
- Config parsing and validation
- `config show` / `config set` commands
- Migration concerns

**For MVP:** Just use env vars + flags. Add file config later if users request it.

### Diff
```diff
--- a/plans/monarch-cli-implementation-plan.md
+++ b/plans/monarch-cli-implementation-plan.md
@@ Dependencies
 dependencies = [
     "typer[all]>=0.9.0",
     "monarchmoneycommunity>=1.0.0",
     "keyring>=24.0.0",
     "rich>=13.0.0",
     "platformdirs>=4.0.0",
-    "tomli>=2.0.0;python_version<'3.11'",
-    "tomli-w>=1.0.0",
 ]

@@ Config Precedence - simplify
-### Config Precedence (highest to lowest)
-
-1. CLI flags (`--format json`)
-2. Environment variables (`MONARCH_FORMAT=json`)
-3. User config (`~/.config/monarch-cli/config.toml` via platformdirs)
-4. Defaults
+### Config Precedence (highest to lowest)
+
+1. CLI flags (`--format json`)
+2. Environment variables (`MONARCH_FORMAT=json`)
+3. Defaults
+
+> **Note:** TOML config file support deferred to v1.1 based on user feedback.

@@ Replace 3.9 Configuration System with simplified version
-### 3.9 Configuration System
-
-```python
-# src/monarch_cli/core/config.py
-"""Configuration management with proper precedence."""
-
-import os
-from dataclasses import dataclass
-from pathlib import Path
-from typing import Any
-
-import platformdirs
-
-try:
-    import tomllib
-except ImportError:
-    import tomli as tomllib
-
-import tomli_w
-... (entire config.py)
-```
+### 3.9 Configuration (Simplified for MVP)
+
+```python
+# src/monarch_cli/core/config.py
+"""Configuration via environment variables."""
+
+import os
+from dataclasses import dataclass
+from ..output import OutputFormat
+
+
+@dataclass
+class Config:
+    """CLI configuration from environment."""
+    format: OutputFormat = OutputFormat.JSON
+    color: bool = True
+    verbose: bool = False
+    timeout_seconds: int = 30
+
+    @classmethod
+    def from_env(cls) -> "Config":
+        """Load config from environment variables."""
+        config = cls()
+        
+        if fmt := os.environ.get("MONARCH_FORMAT"):
+            try:
+                config.format = OutputFormat(fmt.lower())
+            except ValueError:
+                pass
+        
+        if os.environ.get("NO_COLOR") or os.environ.get("MONARCH_NO_COLOR") == "1":
+            config.color = False
+        
+        if os.environ.get("MONARCH_VERBOSE") == "1":
+            config.verbose = True
+        
+        if timeout := os.environ.get("MONARCH_TIMEOUT"):
+            try:
+                config.timeout_seconds = int(timeout)
+            except ValueError:
+                pass
+        
+        return config
+
+
+_config: Config | None = None
+
+
+def get_config() -> Config:
+    global _config
+    if _config is None:
+        _config = Config.from_env()
+    return _config
+```

@@ Remove config commands section (3.8)
-### 3.8 Config Commands
-
-```python
-# src/monarch_cli/commands/config.py
-"""Configuration management commands."""
-... (entire config.py commands)
-```
+> **Note:** `monarch config` commands deferred to v1.1 with TOML file support.

@@ Update main.py to remove config commands
-from .commands import auth, accounts, transactions, budgets, cashflow, categories, config
+from .commands import auth, accounts, transactions, budgets, cashflow, categories
 
 app.add_typer(auth.app, name="auth")
 app.add_typer(accounts.app, name="accounts")
 app.add_typer(transactions.app, name="transactions")
 app.add_typer(budgets.app, name="budgets")
 app.add_typer(cashflow.app, name="cashflow")
 app.add_typer(categories.app, name="categories")
-app.add_typer(config.app, name="config")
```

---

## 6. Move Batch Operations to v1.1 - Not MVP

### Analysis
Phase 4 "AI Agent Optimization" includes batch operations with concurrency control. This is complex:
- Stdin parsing for IDs
- Async concurrency with semaphores
- Error aggregation across batch
- Partial failure handling

For MVP, single-item operations are sufficient. AI agents can loop:
```bash
for id in TXN001 TXN002 TXN003; do
  monarch transactions update $id --category CAT123
done
```

Add batch operations when there's evidence of need.

### Diff
```diff
--- a/plans/monarch-cli-implementation-plan.md
+++ b/plans/monarch-cli-implementation-plan.md
@@ Phase 4: AI Agent Optimization - simplify significantly
 ## Phase 4: AI Agent Optimization
-**Priority**: P1 (Core use case)
-
-### 4.1 Quiet Mode
-
-Add `--quiet` flag for minimal output (IDs only):
-
-```bash
-monarch accounts list --quiet
-# Output: ACC123
-#         ACC456
-#         ACC789
-```
-
-### 4.2 Batch Operations with Concurrency Control
-
-```python
-# Add to transactions.py
-@app.command("batch-update")
-@handle_errors
-def batch_update(
-    category_id: Optional[str] = typer.Option(None, "--category", "-c"),
-    stdin: bool = typer.Option(False, "--stdin", help="Read transaction IDs from stdin"),
-    max_concurrency: int = typer.Option(4, "--max-concurrency", help="Max parallel operations"),
-    dry_run: bool = typer.Option(False, "--dry-run"),
-):
-    """Update multiple transactions.
-    
-    Examples:
-        echo -e "TXN001\\nTXN002" | monarch transactions batch-update --stdin --category CAT123
-        monarch transactions batch-update --stdin --category CAT123 --dry-run
-    """
-    # Implementation with concurrency control
-    ...
-```
-
-### 4.3 Deliverables
-- [ ] `--quiet` mode works
-- [ ] Stdin batch operations work
-- [ ] Concurrency control with `--max-concurrency`
+**Priority**: P2 (Deferred to v1.1)
+
+The following are deferred to v1.1 based on actual usage patterns:
+
+- **`--quiet` mode** - Minimal output (IDs only)
+- **Batch operations** - Update multiple items via stdin
+- **Concurrency control** - `--max-concurrency` for batch ops
+
+For MVP, AI agents can use shell loops:
+```bash
+for id in $(monarch transactions list --preset today | jq -r '.[].id'); do
+  monarch transactions update "$id" --category CAT123
+done
+```
```

---

## 7. Simplify Exception Hierarchy - Remove Speculative Types

### Analysis
The exception hierarchy includes `RateLimitError` and separate `NetworkError` vs `APIError`, but:
- No evidence Monarch Money API has rate limiting
- Network errors and API errors could be the same class with different codes
- `AuthExpiredError` vs `AuthenticationError` distinction may not be detectable

Keep it simple: one base error, a few common cases. Expand if needed.

### Diff
```diff
--- a/plans/monarch-cli-implementation-plan.md
+++ b/plans/monarch-cli-implementation-plan.md
@@ Exception hierarchy - simplify
 class ErrorCode(str, Enum):
     """Error codes for AI agent consumption."""
     AUTH_REQUIRED = "AUTH_REQUIRED"
-    AUTH_EXPIRED = "AUTH_EXPIRED"
     AUTH_FAILED = "AUTH_FAILED"
     NOT_FOUND = "NOT_FOUND"
     INVALID_INPUT = "INVALID_INPUT"
     API_ERROR = "API_ERROR"
-    RATE_LIMITED = "RATE_LIMITED"
     NETWORK_ERROR = "NETWORK_ERROR"
-    TIMEOUT = "TIMEOUT"
-    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
     UNKNOWN = "UNKNOWN"
 
 
 class MonarchCLIError(Exception):
     """Base exception for all CLI errors."""
     # ... (keep as is)
 
 
 class AuthenticationError(MonarchCLIError):
-    """Not authenticated."""
+    """Not authenticated or session expired."""
 
     def __init__(self, message: str = "Not authenticated. Run 'monarch auth login' first."):
         super().__init__(message, ErrorCode.AUTH_REQUIRED, exit_code=1)
 
 
-class AuthExpiredError(MonarchCLIError):
-    """Session token expired."""
-
-    def __init__(self):
-        super().__init__(
-            "Session expired. Run 'monarch auth login' to re-authenticate.",
-            ErrorCode.AUTH_EXPIRED,
-            exit_code=1,
-        )
-
-
 class NotFoundError(MonarchCLIError):
     """Resource not found."""
     # ... (keep as is)
 
 
 class ValidationError(MonarchCLIError):
     """Input validation error."""
     # ... (keep as is)
 
 
 class APIError(MonarchCLIError):
-    """Monarch Money API error."""
-    # ... (keep as is)
-
-
-class RateLimitError(MonarchCLIError):
-    """Rate limit exceeded."""
-
-    def __init__(self, retry_after: int | None = None):
-        details = {"retry_after_seconds": retry_after} if retry_after else {}
-        super().__init__(
-            "Rate limit exceeded. Please wait before retrying.",
-            ErrorCode.RATE_LIMITED,
-            details,
-            exit_code=1,
-        )
-
-
-class NetworkError(MonarchCLIError):
-    """Network connectivity error."""
-
-    def __init__(self, message: str = "Network error. Check your internet connection."):
-        super().__init__(message, ErrorCode.NETWORK_ERROR, exit_code=1)
+    """Monarch Money API or network error."""
+    
+    def __init__(self, message: str, status_code: int | None = None, is_network: bool = False):
+        code = ErrorCode.NETWORK_ERROR if is_network else ErrorCode.API_ERROR
+        details = {"status_code": status_code} if status_code else {}
+        super().__init__(message, code, details, exit_code=1)
```

---

## 8. Drop Parallel Verify Script - Use Simple Makefile

### Analysis
The plan recommends downloading `run-parallel.py` from a GitHub gist for parallel task execution. This:
- Adds an external dependency
- Requires curl during setup
- Is non-standard (most projects use Make or shell scripts)

A simple Makefile is more portable, widely understood, and sufficient. For parallel, developers can use `make -j4`.

### Diff
```diff
--- a/plans/monarch-cli-implementation-plan.md
+++ b/plans/monarch-cli-implementation-plan.md
@@ Verification Script section - simplify
 ### Verification Script
 
-Create a single command that runs all checks. Coding agents should run this after every change.
-
-#### Option A: Parallel Runner (Recommended for Agents)
-
-Use the [`run-parallel`](https://gist.github.com/mitsuhiko/a4b6b70e96c8075b92a4de00b340cc52) script by Armin Ronacher for parallel execution with live status:
-
-```bash
-# Download to project
-curl -o scripts/run-parallel.py https://gist.githubusercontent.com/mitsuhiko/a4b6b70e96c8075b92a4de00b340cc52/raw
-
-# Make executable
-chmod +x scripts/run-parallel.py
-```
-
-**Create `scripts/verify.py`:**
-```python
-#!/usr/bin/env -S uv run --script
-"""Run all verification checks in parallel."""
-import subprocess
-import sys
-
-# Use run-parallel for parallel execution with pretty output
-result = subprocess.run([
-    "uv", "run", "scripts/run-parallel.py",
-    "--fail-fast",
-    "format",    "uv run ruff format --check .",
-    "lint",      "uv run ruff check .",
-    "typecheck", "uv run mypy src/",
-    "test",      "uv run pytest -x",
-])
-sys.exit(result.returncode)
-```
-
-**Usage:**
-```bash
-uv run scripts/verify.py    # Parallel with live status display
-```
-
-... (rest of parallel runner docs)
-
-#### Option B: Makefile (Simple, Sequential)
+Use a simple Makefile that coding agents run after every change:
 
 ```makefile
 # Makefile
 .PHONY: verify test lint typecheck format
 
-# Run ALL checks sequentially
+# Run all checks
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
-
-# Live tests - LOCAL DEV ONLY (requires auth, not for CI)
-test-live:
-	MONARCH_LIVE_TESTS=1 uv run pytest tests/live/ -m live
 ```
 
 **Usage:**
 ```bash
-make verify    # Run everything sequentially
-make test      # Just tests
-make lint      # Just linting
+make verify    # Run all checks (agents should use this)
+make -j4 verify  # Parallel if needed
 ```
```

---

## 9. Remove `--no-cache` Global Flag - Cache Not Implemented

### Analysis
The global flags include `--no-cache` but caching is explicitly listed as "deferred to v1.1". Including flags for unimplemented features:
- Confuses users
- Requires handling code even if it does nothing
- Creates documentation debt

Remove it until cache is implemented.

### Diff
```diff
--- a/plans/monarch-cli-implementation-plan.md
+++ b/plans/monarch-cli-implementation-plan.md
@@ Global Flags table
 | Flag | Type | Default | Description |
 |------|------|---------|-------------|
 | `-h, --help` | bool | - | Show help |
 | `--version` | bool | - | Show version |
 | `-v, --verbose` | bool | false | Verbose output (to stderr) |
 | `--format, -f` | choice | json | Output format: json, table, csv, compact |
 | `--ndjson` | bool | false | Stream results as newline-delimited JSON |
 | `--raw` | bool | false | Output raw API response without transforms |
 | `--no-color` | bool | false | Disable colors (also respects `NO_COLOR` env) |
-| `--quiet, -q` | bool | false | Minimal output (IDs only) |
-| `--no-cache` | bool | false | Bypass cache for this request |
 | `--dry-run` | bool | false | Preview operation without executing (mutations) |
+
+> **Deferred to v1.1:** `--quiet` (minimal output), `--no-cache` (when caching added)
```

---

## 10. Trim Release Readiness Checklist - Move to Separate Doc

### Analysis
The "Release Readiness Checklist" at the end of the plan is forward-looking and includes 15+ items. It's useful but:
- Distracts from implementation focus
- Will change as project evolves
- Belongs in a separate `RELEASE.md` or GitHub issue

Keep a minimal reference, move details elsewhere.

### Diff
```diff
--- a/plans/monarch-cli-implementation-plan.md
+++ b/plans/monarch-cli-implementation-plan.md
@@ Release Readiness Checklist - condense
-## Release Readiness Checklist
-
-### 🔴 P0: Must Fix Before PyPI Publish
-
-1. **Add LICENSE File** ⏱️ 5 min
-2. **Control Package Contents** ⏱️ 5 min
-3. **Verify Package Metadata** ⏱️ 5 min  
-4. **Dynamic Version** ⏱️ 10 min
-5. **Verify Build & Install** ⏱️ 5 min
-6. **Secure CI for Open Source** ⏱️ 15 min
-
-### 🟠 P1: Strongly Recommended
-
-7. **README Quality** ⏱️ 30 min
-8. **Add CHANGELOG.md** ⏱️ 15 min
-9. **Add CONTRIBUTING.md** ⏱️ 20 min
-10. **Basic CI Workflow** ⏱️ 10 min
-11. **pipx/uvx Compatibility** ⏱️ 2 min
-12. **Type Hints & py.typed** ⏱️ 5 min
-13. **Shell Completions** - Already supported by Typer
-
-### 🟡 P2: Post-Release (v0.2.0+)
-
-- [ ] `CODE_OF_CONDUCT.md`
-- [ ] `SECURITY.md` (vulnerability reporting)
-- [ ] GitHub issue/PR templates
-- [ ] PyPI publish workflow (on version tags)
-- [ ] Coverage thresholds in CI
-- [ ] Man page generation
+## Pre-Release Checklist
+
+Before publishing to PyPI:
+- [ ] LICENSE file (MIT)
+- [ ] README with installation, quick start, examples
+- [ ] CHANGELOG.md
+- [ ] `py.typed` marker file
+- [ ] Verify: `uv build && uv pip install dist/*.whl && monarch --version`
+
+See `docs/RELEASE.md` for detailed checklist.
```

---

## Summary of Proposed Changes

| Change | Complexity Removed | Impact |
|--------|-------------------|--------|
| Remove JMESPath | 1 dependency, query parsing | Low - use `jq` |
| Remove pickle compat | Security risk, code paths | Low - re-login |
| Remove service layer | ~4 files, indirection | None - just restructure |
| Remove retry module | 1 file, async complexity | Low - add when needed |
| Simplify config | 2 deps, TOML parsing, commands | Low - env vars sufficient |
| Defer batch ops | Concurrency, error aggregation | Low - shell loops work |
| Simplify exceptions | Speculative error types | None |
| Drop parallel runner | External gist dependency | None - use Make |
| Remove `--no-cache` | Unused flag handling | None |
| Trim release checklist | Doc noise | None |

**Net result:**
- **4 fewer dependencies** (jmespath, httpx, tomli, tomli-w)
- **~6 fewer files** (services/*, retry.py, config commands)
- **Simpler architecture** (commands → adapter → library)
- **Same functionality** for 95% of use cases
