## Change 1 — Fix the core async architecture (replace per-call ThreadPoolExecutor + asyncio.run)

### Rationale

Your current `run_async()` spins up a new `ThreadPoolExecutor(max_workers=1)` and calls `asyncio.run()` **for every API call**. That is expensive (thread creation, event loop creation/destruction) and can behave poorly if commands ever run inside an environment that already has an event loop (common in agent runtimes, notebooks, or future integrations). It also complicates cancellation and signal handling.

A more robust architecture is:

- Create **one** background thread with a persistent asyncio loop.
- Submit coroutines via `asyncio.run_coroutine_threadsafe`.
- Support clean shutdown and better SIGINT semantics.
- Optionally allow a direct `asyncio.run()` path when safe (no running loop).

This improves performance and reduces “event loop already running” edge cases.

### Diff

````diff
@@
-### 1.1 Async Utilities
-
-Port the `run_async()` helper from server.py:
-
-```python
-# src/monarch_cli/core/async_utils.py
-import asyncio
-from concurrent.futures import ThreadPoolExecutor
-
-def run_async(coro):
-    """Run async coroutine in sync context."""
-    with ThreadPoolExecutor(max_workers=1) as executor:
-        future = executor.submit(asyncio.run, coro)
-        return future.result()
-```
+### 1.1 Async Utilities
+
+Replace the per-call ThreadPoolExecutor pattern with a single, long-lived event loop
+running in a dedicated background thread. This is faster and avoids nested-event-loop issues.
+
+Key properties:
+- Reuses one asyncio loop for the whole CLI process
+- Supports cancellation and consistent signal handling
+- Avoids creating threads/loops on every API call
+
+```python
+# src/monarch_cli/core/async_utils.py
+import asyncio
+import threading
+from typing import Any, Coroutine, Optional
+
+_loop: Optional[asyncio.AbstractEventLoop] = None
+_thread: Optional[threading.Thread] = None
+
+def _ensure_loop() -> asyncio.AbstractEventLoop:
+    global _loop, _thread
+    if _loop is not None:
+        return _loop
+
+    loop = asyncio.new_event_loop()
+
+    def runner() -> None:
+        asyncio.set_event_loop(loop)
+        loop.run_forever()
+
+    t = threading.Thread(target=runner, name="monarch-cli-async", daemon=True)
+    t.start()
+    _loop = loop
+    _thread = t
+    return loop
+
+def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
+    """Run an async coroutine from sync Typer commands."""
+    loop = _ensure_loop()
+    fut = asyncio.run_coroutine_threadsafe(coro, loop)
+    return fut.result()
+```
````

---

## Change 2 — Introduce a “service layer” and a client adapter (stop touching private `_headers` / `_token` directly)

### Rationale

The current `get_client()` writes `Authorization` into a private `_headers` dict and the auth command reads a private `mm._token`. That is brittle: upstream library changes can silently break you.

Instead:

- Create `core/adapter.py` (or `core/monarch_adapter.py`) to encapsulate all library-private interactions in one place.
- Add a `services/` layer (e.g., `services/accounts.py`, `services/transactions.py`) that:
  - Calls the adapter
  - Applies transformations
  - Implements retries/backoff and error mapping (later changes)

This improves maintainability, testability, and isolates upstream churn.

### Diff

```diff
@@
-### Key Insight
-
-The `monarchmoney` library methods return Python dicts. The CLI wrapper just needs to:
-1. Parse CLI arguments
-2. Get authenticated client from keyring
-3. Call the async method with `run_async()`
-4. Print the result as JSON (or format it)
+### Key Insight
+
+The `monarchmoneycommunity` client returns Python dicts, but we should **not** couple the CLI
+directly to private attributes or exact response shapes. Instead:
+1. CLI parses args
+2. Service layer calls an adapter (single integration point with upstream client)
+3. Adapter handles auth/header/token details in one place
+4. Service layer transforms outputs into stable CLI schemas
+5. Output layer renders JSON/table/ndjson and structured errors
@@
 ### Project Structure (src layout)
@@
 │       ├── core/
 │       │   ├── __init__.py
 │       │   ├── client.py        # MonarchMoney client wrapper
+│       │   ├── adapter.py       # Encapsulates monarchmoneycommunity integration details
 │       │   ├── session.py       # Dual-backend session management (keyring + file)
 │       │   └── async_utils.py   # run_async() helper
+│       ├── services/            # Business logic: retries, transforms, stable schemas
+│       │   ├── __init__.py
+│       │   ├── accounts.py
+│       │   ├── transactions.py
+│       │   ├── budgets.py
+│       │   └── cashflow.py
 │       └── output/
```

---

## Change 3 — Replace pickle-based session file with safe JSON + permissions + atomic writes (keep “compat pickle” as optional)

### Rationale

Using `pickle` for session storage is a security risk: unpickling a tampered file can execute arbitrary code. Even if you “only ever pickle your own dict,” any local compromise or shared volume scenario becomes dangerous.

You can preserve portability while improving safety:

- Default file backend uses `session.json` with strict permissions (0600).
- Use atomic write (temp file + rename) to prevent corruption.
- If compatibility with the library’s `.mm/mm_session.pickle` is truly needed, make it an explicit opt-in backend (e.g., `file-compat`), clearly labeled as unsafe.

### Diff

```diff
@@
-### Auth Pattern (Dual Storage Support)
+### Auth Pattern (Dual Storage Support)
@@
-| **Session file** | `~/.mm/mm_session.pickle` | ⚠️ Plain file | Portability, containers, compatibility with `monarchmoney` library |
+| **Session file (JSON)** | `~/.config/monarch-cli/session.json` | ⚠️ Plain file (0600) | Portability, containers |
+| **Session file (compat pickle)** | `~/.mm/mm_session.pickle` | ❌ Unsafe (pickle) | Only if user needs library compatibility |
@@
-# File constants (matches monarchmoney library default)
-SESSION_DIR = ".mm"
-SESSION_FILE = f"{SESSION_DIR}/mm_session.pickle"
+# File constants
+# Default: safe JSON in app config dir
+# Optional: legacy compat pickle (explicit opt-in)
+SESSION_JSON_PATH = "~/.config/monarch-cli/session.json"
+SESSION_PICKLE_COMPAT_PATH = "~/.mm/mm_session.pickle"
@@
-class StorageBackend(str, Enum):
-    KEYRING = "keyring"
-    FILE = "file"
+class StorageBackend(str, Enum):
+    KEYRING = "keyring"
+    FILE = "file"                 # safe JSON
+    FILE_COMPAT = "file-compat"   # legacy pickle (opt-in)
@@
-def save_session_token(token: str, backend: StorageBackend = StorageBackend.KEYRING) -> None:
+def save_session_token(token: str, backend: StorageBackend = StorageBackend.KEYRING) -> None:
@@
-    else:
-        SESSION_DIR.mkdir(parents=True, exist_ok=True)
-        with open(SESSION_FILE, "wb") as f:
-            pickle.dump({"token": token}, f)
+    elif backend == StorageBackend.FILE:
+        # Write JSON with 0600 perms and atomic rename
+        ...
+    else:
+        # FILE_COMPAT: explicit opt-in legacy pickle compatibility
+        # Documented as unsafe; only for users needing library interoperability
+        ...
@@
-def get_session_token() -> str | None:
-    """Retrieve token, checking keyring first, then file."""
+def get_session_token() -> str | None:
+    """Retrieve token, checking keyring first, then safe JSON, then optional compat pickle."""
@@
-    # Fall back to session file
-    if SESSION_FILE.exists():
-        with open(SESSION_FILE, "rb") as f:
-            data = pickle.load(f)
-            return data.get("token")
+    # Fall back to safe JSON session
+    ...
+
+    # Final fallback: compat pickle (explicit backend, still readable if present)
+    # Preferably avoid unpickling; if we must, do it only when explicitly enabled via config.
+    ...
```

---

## Change 4 — Use `platformdirs` for config/session paths and add path overrides

### Rationale

Hardcoding `~/.config/...` and `~/.mm/...` is Unix-centric. `platformdirs` is the standard way to select OS-appropriate locations (Windows/macOS/Linux). Also, container/CI setups often need overrides.

Add:

- `MONARCH_CONFIG_DIR`
- `MONARCH_SESSION_PATH`
- `MONARCH_TOKEN` already exists (fine)

This improves portability and reduces user support issues.

### Diff

```diff
@@
 ### Config Precedence (highest to lowest)
@@
 3. User config (`~/.config/monarch-cli/config.json`)
@@
+### Cross-platform Paths
+
+Use `platformdirs` to select OS-appropriate config/state locations:
+- Config: `platformdirs.user_config_dir("monarch-cli")`
+- State/session: `platformdirs.user_state_dir("monarch-cli")`
+
+Support overrides for containers/CI:
+- `MONARCH_CONFIG_DIR`
+- `MONARCH_SESSION_PATH`
```

---

## Change 5 — Add retries/backoff/timeouts and structured API error mapping in one place

### Rationale

The plan currently treats “API error” as a generic exception string. For a financial CLI and agent integration, you want predictable behavior under:

- transient network failures
- 429 rate limits
- 5xx upstream issues
- token expiry (401)

Introduce:

- a `core/errors.py` with normalized error codes
- a `core/retry.py` with exponential backoff + jitter
- a `services/*` approach where all calls go through `call_api()` wrapper

This improves reliability and agent determinism.

### Diff

```diff
@@
 ## Phase 4: AI Agent Optimization
 **Priority**: P1 (Core use case)
@@
 ### 4.1 Structured Error Output
@@
 **Error Codes:**
 - `AUTH_REQUIRED` - Not authenticated
 - `AUTH_EXPIRED` - Session expired
 - `NOT_FOUND` - Resource not found
 - `INVALID_INPUT` - Bad parameters
 - `API_ERROR` - Monarch API error
 - `RATE_LIMITED` - Too many requests
+ - `NETWORK_ERROR` - DNS/TLS/connection issues
+ - `TIMEOUT` - Request exceeded timeout
+ - `UPSTREAM_UNAVAILABLE` - 5xx from API
+
+### 4.0 Reliability Foundation (New)
+
+Before adding agent polish, implement a single API-call wrapper responsible for:
+- timeouts
+- retries with exponential backoff (esp. 429, transient network, 5xx)
+- mapping library exceptions into stable error codes
+- redacting secrets from error messages in verbose logs
+
+Add:
+- `src/monarch_cli/core/errors.py`
+- `src/monarch_cli/core/retry.py`
+- use it from `services/*` modules (not from command modules)
```

---

## Change 6 — Formalize a stable output contract: `--raw`, `--schema`, and NDJSON streaming

### Rationale

Right now you “transform to cleaner structure,” which is good for humans but can be risky for agents if it changes over time. Provide explicit modes:

- Default: stable “CLI schema” output (your cleaned structure)
- `--raw`: passthrough raw API response for power users
- `--ndjson`: stream items line-by-line (critical for large transaction lists and agent pipelines)
- `--schema`: print the JSON schema (or at least a documented schema blob) for deterministic agent integration

This makes the CLI more compelling and more “agent-native.”

### Diff

```diff
@@
 ### Global Flags (all commands)
@@
 | `--format, -f` | choice | json | Output format: json, table, compact |
+| `--ndjson` | bool | false | Stream results as newline-delimited JSON (lists only) |
+| `--raw` | bool | false | Output raw API response without CLI transformations |
+| `--schema` | bool | false | Print the output schema for the command and exit |
@@
 ## Phase 2: Output System
@@
-### 2.1 Full Output Formatters
+### 2.1 Full Output Formatters
@@
 class OutputFormat(str, Enum):
@@
 def output(data: Any, format: OutputFormat = OutputFormat.JSON) -> None:
@@
+def output_ndjson(items: list[dict]) -> None:
+    """Stream newline-delimited JSON for large lists."""
+    ...
+
+def output_schema(schema: dict) -> None:
+    """Print command schema for agent integration."""
+    ...
```

---

## Change 7 — Replace `--field` with a more general `--query` (JMESPath) and keep `--field` as sugar

### Rationale

`--field amount,category` is helpful, but it is a limited extraction mechanism and will grow ad hoc. A better approach:

- Add `--query` supporting JMESPath (widely used, easy to learn, works on JSON)
- Keep `--field` as sugar for simple top-level extraction
- Enables powerful agent workflows without adding many bespoke flags

This improves usability and reduces future feature sprawl.

### Diff

````diff
@@
 ## Phase 4: AI Agent Optimization
@@
 ### 4.3 Specific Field Extraction
@@
 monarch transactions list --limit 1 --field amount,category
 # Output: {"amount": -49.99, "category": "Groceries"}
+
+### 4.3 Query/Projection (Recommended)
+
+Add `--query` (JMESPath) for general JSON projection/filtering:
+
+```bash
+monarch transactions list --query "[:10].{id:id, amt:amount, cat:category}"
+monarch accounts list --query "[?is_active].{id:id, name:name, bal:balance}"
+```
+
+`--field` remains as convenience sugar for common cases.
````

---

## Change 8 — Add safe, scalable batch operations with concurrency control

### Rationale

Batch updates via stdin are great, but if you run them sequentially you can be slow; if you run them unbounded you can trip rate limits. Add:

- `--max-concurrency` (default small, e.g., 4)
- rate-limit-aware retry wrapper (from Change 5)
- NDJSON progress events on stderr (optional) for agents

This improves performance and reliability under load.

### Diff

```diff
@@
 ### 4.4 Stdin Support for Batch Operations
@@
 echo -e "TXN001\nTXN002\nTXN003" | monarch transactions update --stdin --category CAT123
+
+Add:
+- `--max-concurrency` to control parallelism safely
+- Batch mode emits per-item status events to stderr (human readable) and optionally NDJSON events for agents
```

---

## Change 9 — Add a `monarch doctor` command for diagnostics and a `monarch ping` command for connectivity

### Rationale

CLI projects fail in the “last mile” due to environment issues:

- keyring backend missing or locked
- session file permissions
- token present but invalid/expired
- network/DNS/TLS issues

A `doctor` command reduces support burden dramatically and makes the project feel professional.

### Diff

```diff
@@
 ## Phase 1: Auth Foundation
@@
 ### 1.6 Authentication Commands
@@
 app = typer.Typer(help="Authentication management")
@@
 @app.command()
 def setup():
@@
 """)
+
+@app.command()
+def doctor():
+    """Diagnose environment and auth storage.
+
+    Checks:
+    - keyring availability and backend name
+    - session file location, permissions, readability
+    - whether a token is present in any backend
+    - whether token appears valid by making a lightweight API call (optional)
+    """
+    ...
+
+@app.command()
+def ping():
+    """Check basic API connectivity (no sensitive output)."""
+    ...
```

---

## Change 10 — Correct inconsistencies and missing pieces (categories command, refresh method name, method table)

### Rationale

There are a few internal contradictions / omissions that will cause churn during implementation:

- You list `monarch categories list` as MVP but Phase 3 never implements `commands/categories.py`.
- The method name for refresh varies (`request_accounts_refresh()` vs `request_accounts_refresh_all()`).
- The plan alternates “monarchmoney” vs “monarchmoneycommunity”; for clarity, stick to one naming convention: “monarchmoneycommunity package, imported as monarchmoney.”

Fixing these now prevents wasted implementation cycles.

### Diff

````diff
@@
 ### 3.1 Account Commands
@@
 def refresh():
@@
-        run_async(client.request_accounts_refresh_all())
+        # Use the library’s supported refresh method name; keep an adapter shim for compatibility.
+        run_async(client.request_accounts_refresh())
@@
 ## Phase 3: Core Commands
@@
 ### 3.5 Update Main Entry Point
@@
 from .commands import auth, accounts, transactions, budgets, cashflow, categories
@@
 app.add_typer(categories.app, name="categories")
+
+### 3.6 Categories Commands (Missing in original plan)
+
+Implement `monarch categories list` (MVP dependency for transaction recategorization).
+
+```python
+# src/monarch_cli/commands/categories.py
+import typer
+from ..core.client import get_client
+from ..core.async_utils import run_async
+from ..output import output, OutputFormat, error
+
+app = typer.Typer(help="Category management")
+
+@app.command("list")
+def list_categories(format: OutputFormat = typer.Option(OutputFormat.JSON, "--format", "-f")):
+    """List transaction categories."""
+    try:
+        client = get_client()
+        data = run_async(client.get_transaction_categories())
+        # Transform to a stable CLI shape
+        ...
+        output(result, format)
+    except Exception as e:
+        error(str(e))
+```
````

---

## Change 11 — Strengthen config semantics: switch to TOML and document env var mapping explicitly

### Rationale

You currently reference `config.json`. JSON works, but TOML is more ergonomic for humans and is now standard for Python config. Also, agents benefit from an explicit mapping of env vars → config keys.

Add:

- `~/.config/monarch-cli/config.toml` (via platformdirs)
- Document each env var, its type, and precedence
- Provide `monarch config show` to print resolved config (redacting secrets)

### Diff

```diff
@@
-3. User config (`~/.config/monarch-cli/config.json`)
+3. User config (`~/.config/monarch-cli/config.toml`)
@@
+### Configuration Surface (Document Explicitly)
+
+Config keys (TOML) and environment variables:
+- `output.format` ↔ `MONARCH_FORMAT`
+- `output.no_color` ↔ `NO_COLOR` / `MONARCH_NO_COLOR`
+- `auth.preferred_backend` ↔ `MONARCH_AUTH_BACKEND`
+- `network.timeout_seconds` ↔ `MONARCH_TIMEOUT`
+- `network.max_retries` ↔ `MONARCH_MAX_RETRIES`
+
+Add a command:
+`monarch config show` → prints resolved config with secrets redacted.
```

---

## Change 12 — Upgrade the testing strategy: prefer Typer’s CliRunner + contract tests for schemas

### Rationale

The existing unit test examples mix sync/async mocking patterns that are likely to break:

- Using `MagicMock(return_value=...)` on an async method is incorrect unless you wrap it or mock at the `run_async` boundary.
- Testing command functions directly bypasses Typer parsing and global options behavior.

Use:

- `typer.testing.CliRunner` for CLI-level tests (covers args, exit codes, stdout/stderr separation)
- “schema/contract tests” that assert stable keys and types for transformed outputs
- Keep “live tests” gated, but ensure they never print secrets and can be excluded in CI forks

### Diff

````diff
@@
 ### Testing Patterns
@@
-#### Basic Test Structure
+#### Basic Test Structure (Preferred: CLI-level with Typer CliRunner)
@@
-# tests/test_accounts.py
-import pytest
-from unittest.mock import AsyncMock, patch
-
-from monarch_cli.commands.accounts import list_accounts
-
-
-class TestListAccounts:
-    """Tests for monarch accounts list command."""
-
-    def test_list_accounts_json_output(self, capsys):
-        """Should output accounts as JSON."""
-        mock_accounts = {
-            "accounts": [
-                {"id": "ACC1", "displayName": "Checking", "currentBalance": 1000.00}
-            ]
-        }
-
-        with patch("monarch_cli.commands.accounts.get_client") as mock_get_client:
-            mock_client = AsyncMock()
-            mock_client.get_accounts.return_value = mock_accounts
-            mock_get_client.return_value = mock_client
-
-            list_accounts(format="json")
-
-        captured = capsys.readouterr()
-        assert "ACC1" in captured.out
-        assert "Checking" in captured.out
-        assert "1000" in captured.out
+```python
+# tests/test_accounts_cli.py
+import json
+from typer.testing import CliRunner
+from unittest.mock import patch
+
+from monarch_cli.main import app
+
+runner = CliRunner()
+
+def test_accounts_list_outputs_json():
+    mock_api = {"accounts": [{"id": "ACC1", "displayName": "Checking", "currentBalance": 1000.0}]}
+    with patch("monarch_cli.services.accounts.list_accounts_api") as svc:
+        svc.return_value = [{"id": "ACC1", "name": "Checking", "balance": 1000.0}]
+        res = runner.invoke(app, ["accounts", "list", "--format", "json"])
+    assert res.exit_code == 0
+    data = json.loads(res.stdout)
+    assert data[0]["id"] == "ACC1"
+```
````

---

# Net effect: what you gain

- **Architecture**: a clear separation (commands → services → adapter → output) and a single async runtime that won’t fight agent environments.
- **Security**: no default pickle storage; strict perms + atomic writes; less fragile handling of upstream private fields.
- **Reliability**: retries/backoff/timeouts + normalized error mapping.
- **Agent value**: `--raw`, `--schema`, `--ndjson`, and `--query` make it genuinely “agent-native.”
- **Practical usability**: `doctor`/`ping` reduces support and frustration.
- **Implementation efficiency**: fix missing categories command and refresh inconsistency now, avoiding rework.
