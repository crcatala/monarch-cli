# Monarch CLI Implementation Plan - Proposed Revisions

I've carefully reviewed the plan and identified several improvements across architecture, features, reliability, and developer experience. Here are my detailed recommendations:

---

## 1. Improved Async Execution Pattern

### Analysis
The current `run_async()` implementation creates a new `ThreadPoolExecutor` for every API call, which is:
- **Inefficient**: Thread pool creation overhead for each call
- **Unnecessary**: Python 3.12+ has improved `asyncio.run()` that handles nested event loops better
- **Error-prone**: Executor cleanup issues if exceptions occur

### Rationale
`asyncio.run()` is the standard way to run async code from sync contexts in modern Python. The ThreadPoolExecutor pattern was needed historically for Jupyter/nested loops but isn't required for CLI applications.

### Proposed Change

```diff
 # src/monarch_cli/core/async_utils.py
 import asyncio
-from concurrent.futures import ThreadPoolExecutor
+from typing import TypeVar, Coroutine, Any
+
+T = TypeVar("T")
 
-def run_async(coro):
-    """Run async coroutine in sync context."""
-    with ThreadPoolExecutor(max_workers=1) as executor:
-        future = executor.submit(asyncio.run, coro)
-        return future.result()
+def run_async(coro: Coroutine[Any, Any, T]) -> T:
+    """Run async coroutine in sync context.
+    
+    Uses asyncio.run() which is the standard approach for CLI applications.
+    Properly handles cleanup and exception propagation.
+    """
+    try:
+        return asyncio.run(coro)
+    except KeyboardInterrupt:
+        # Let the signal handler deal with this
+        raise
+    except asyncio.CancelledError:
+        # Convert to a regular exception for CLI context
+        raise RuntimeError("Operation was cancelled")
```

---

## 2. Centralized Exception Hierarchy & Error Handling

### Analysis
The current plan scatters error handling across commands with ad-hoc `try/except` blocks. This leads to:
- Inconsistent error messages
- Duplicated error handling logic
- Difficulty in maintaining error codes for AI agents

### Rationale
A centralized exception hierarchy with a decorator-based error handler provides:
- Single source of truth for error types and codes
- Consistent JSON error output for AI agents
- Cleaner command implementations
- Easier testing of error paths

### Proposed Change

```diff
+# src/monarch_cli/core/exceptions.py
+"""Centralized exception hierarchy for consistent error handling."""
+
+from enum import Enum
+from typing import Any
+
+
+class ErrorCode(str, Enum):
+    """Error codes for AI agent consumption."""
+    AUTH_REQUIRED = "AUTH_REQUIRED"
+    AUTH_EXPIRED = "AUTH_EXPIRED"
+    AUTH_FAILED = "AUTH_FAILED"
+    NOT_FOUND = "NOT_FOUND"
+    INVALID_INPUT = "INVALID_INPUT"
+    API_ERROR = "API_ERROR"
+    RATE_LIMITED = "RATE_LIMITED"
+    NETWORK_ERROR = "NETWORK_ERROR"
+    TIMEOUT = "TIMEOUT"
+    UNKNOWN = "UNKNOWN"
+
+
+class MonarchCLIError(Exception):
+    """Base exception for all CLI errors."""
+    
+    def __init__(
+        self,
+        message: str,
+        code: ErrorCode = ErrorCode.UNKNOWN,
+        details: dict[str, Any] | None = None,
+        exit_code: int = 1,
+    ):
+        super().__init__(message)
+        self.message = message
+        self.code = code
+        self.details = details or {}
+        self.exit_code = exit_code
+
+    def to_dict(self) -> dict[str, Any]:
+        """Convert to JSON-serializable dict for AI agents."""
+        result = {
+            "error": True,
+            "code": self.code.value,
+            "message": self.message,
+        }
+        if self.details:
+            result["details"] = self.details
+        return result
+
+
+class AuthenticationError(MonarchCLIError):
+    """Authentication-related errors."""
+    
+    def __init__(self, message: str = "Not authenticated. Run 'monarch auth login' first."):
+        super().__init__(message, ErrorCode.AUTH_REQUIRED, exit_code=1)
+
+
+class AuthExpiredError(MonarchCLIError):
+    """Session token expired."""
+    
+    def __init__(self):
+        super().__init__(
+            "Session expired. Run 'monarch auth login' to re-authenticate.",
+            ErrorCode.AUTH_EXPIRED,
+            exit_code=1,
+        )
+
+
+class NotFoundError(MonarchCLIError):
+    """Resource not found."""
+    
+    def __init__(self, resource_type: str, resource_id: str):
+        super().__init__(
+            f"{resource_type} '{resource_id}' not found",
+            ErrorCode.NOT_FOUND,
+            details={"resource_type": resource_type, "resource_id": resource_id},
+            exit_code=1,
+        )
+
+
+class ValidationError(MonarchCLIError):
+    """Input validation error."""
+    
+    def __init__(self, message: str, field: str | None = None):
+        details = {"field": field} if field else {}
+        super().__init__(message, ErrorCode.INVALID_INPUT, details, exit_code=2)
+
+
+class APIError(MonarchCLIError):
+    """Monarch Money API error."""
+    
+    def __init__(self, message: str, status_code: int | None = None):
+        details = {"status_code": status_code} if status_code else {}
+        super().__init__(message, ErrorCode.API_ERROR, details, exit_code=1)
+
+
+class RateLimitError(MonarchCLIError):
+    """Rate limit exceeded."""
+    
+    def __init__(self, retry_after: int | None = None):
+        details = {"retry_after_seconds": retry_after} if retry_after else {}
+        super().__init__(
+            "Rate limit exceeded. Please wait before retrying.",
+            ErrorCode.RATE_LIMITED,
+            details,
+            exit_code=1,
+        )
+
+
+class NetworkError(MonarchCLIError):
+    """Network connectivity error."""
+    
+    def __init__(self, message: str = "Network error. Check your internet connection."):
+        super().__init__(message, ErrorCode.NETWORK_ERROR, exit_code=1)
+
+
+class TimeoutError(MonarchCLIError):
+    """Operation timed out."""
+    
+    def __init__(self, operation: str, timeout_seconds: int):
+        super().__init__(
+            f"Operation '{operation}' timed out after {timeout_seconds}s",
+            ErrorCode.TIMEOUT,
+            details={"operation": operation, "timeout_seconds": timeout_seconds},
+            exit_code=1,
+        )
```

```diff
+# src/monarch_cli/core/error_handler.py
+"""Decorator for consistent error handling across commands."""
+
+import functools
+import sys
+from typing import Callable, TypeVar, ParamSpec
+import httpx
+
+from .exceptions import (
+    MonarchCLIError,
+    AuthenticationError,
+    AuthExpiredError,
+    APIError,
+    NetworkError,
+    RateLimitError,
+)
+from ..output import console, output_error
+
+P = ParamSpec("P")
+R = TypeVar("R")
+
+
+def handle_errors(func: Callable[P, R]) -> Callable[P, R]:
+    """Decorator that catches exceptions and outputs consistent errors.
+    
+    Converts library exceptions to our exception hierarchy and ensures
+    consistent JSON error output for AI agents.
+    """
+    @functools.wraps(func)
+    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
+        try:
+            return func(*args, **kwargs)
+        except MonarchCLIError as e:
+            # Our own exceptions - output and exit
+            output_error(e)
+            sys.exit(e.exit_code)
+        except httpx.HTTPStatusError as e:
+            # HTTP errors from the API
+            if e.response.status_code == 401:
+                output_error(AuthExpiredError())
+                sys.exit(1)
+            elif e.response.status_code == 429:
+                retry_after = e.response.headers.get("Retry-After")
+                output_error(RateLimitError(int(retry_after) if retry_after else None))
+                sys.exit(1)
+            else:
+                output_error(APIError(str(e), e.response.status_code))
+                sys.exit(1)
+        except httpx.ConnectError:
+            output_error(NetworkError())
+            sys.exit(1)
+        except httpx.TimeoutException:
+            output_error(NetworkError("Request timed out. Try again or check your connection."))
+            sys.exit(1)
+        except RuntimeError as e:
+            if "Not authenticated" in str(e):
+                output_error(AuthenticationError())
+                sys.exit(1)
+            raise
+        except Exception as e:
+            # Unexpected error - log full traceback in verbose mode
+            from ..output import is_verbose
+            if is_verbose():
+                import traceback
+                console.print_exception()
+            output_error(MonarchCLIError(f"Unexpected error: {e}"))
+            sys.exit(1)
+    
+    return wrapper
```

Then update commands to use the decorator:

```diff
 # src/monarch_cli/commands/accounts.py
 import typer
 from typing import Optional
 from ..core.client import get_client
 from ..core.async_utils import run_async
+from ..core.error_handler import handle_errors
 from ..output import output, OutputFormat, error

 app = typer.Typer(help="Account management")

 @app.command("list")
+@handle_errors
 def list_accounts(
     format: OutputFormat = typer.Option(OutputFormat.JSON, "--format", "-f")
 ):
     """List all linked financial accounts."""
-    try:
-        client = get_client()
-        accounts = run_async(client.get_accounts())
-
-        # Transform to cleaner structure
-        result = []
-        for acc in accounts.get("accounts", []):
-            result.append({
-                "id": acc.get("id"),
-                "name": acc.get("displayName"),
-                "type": acc.get("type", {}).get("display"),
-                "balance": acc.get("currentBalance"),
-                "institution": acc.get("institution", {}).get("name"),
-                "is_active": not acc.get("isHidden", False),
-            })
-
-        output(result, format)
-    except Exception as e:
-        error(str(e))
+    client = get_client()
+    accounts = run_async(client.get_accounts())
+
+    # Transform to cleaner structure
+    result = []
+    for acc in accounts.get("accounts", []):
+        result.append({
+            "id": acc.get("id"),
+            "name": acc.get("displayName"),
+            "type": acc.get("type", {}).get("display"),
+            "balance": acc.get("currentBalance"),
+            "institution": acc.get("institution", {}).get("name"),
+            "is_active": not acc.get("isHidden", False),
+        })
+
+    output(result, format)
```

---

## 3. Configuration System with Proper Precedence

### Analysis
The plan mentions config precedence but doesn't provide implementation. A proper config system is essential for:
- Persistent user preferences (default format, etc.)
- Environment-specific settings (CI vs local)
- Reducing repetitive flag usage

### Rationale
Having a centralized config system:
- Makes the CLI more pleasant to use (fewer flags needed)
- Enables environment-specific behavior
- Follows the stated precedence: CLI flags > env vars > config file > defaults

### Proposed Change

```diff
+# src/monarch_cli/core/config.py
+"""Configuration management with proper precedence."""
+
+import json
+import os
+from dataclasses import dataclass, field
+from pathlib import Path
+from typing import Any
+
+from ..output import OutputFormat
+
+
+# XDG-compliant config location
+def get_config_dir() -> Path:
+    """Get config directory, respecting XDG_CONFIG_HOME."""
+    xdg_config = os.environ.get("XDG_CONFIG_HOME")
+    if xdg_config:
+        return Path(xdg_config) / "monarch-cli"
+    return Path.home() / ".config" / "monarch-cli"
+
+
+CONFIG_FILE = get_config_dir() / "config.json"
+
+
+@dataclass
+class Config:
+    """CLI configuration with defaults."""
+    
+    # Output settings
+    format: OutputFormat = OutputFormat.JSON
+    color: bool = True
+    verbose: bool = False
+    
+    # API settings
+    timeout_seconds: int = 30
+    max_retries: int = 3
+    
+    # Behavior settings
+    confirm_destructive: bool = True  # Prompt before delete operations
+    
+    @classmethod
+    def load(cls) -> "Config":
+        """Load config with precedence: env vars > file > defaults."""
+        config = cls()
+        
+        # Load from file if exists
+        if CONFIG_FILE.exists():
+            try:
+                with open(CONFIG_FILE) as f:
+                    file_config = json.load(f)
+                config = cls._apply_dict(config, file_config)
+            except (json.JSONDecodeError, OSError):
+                pass  # Ignore invalid config file
+        
+        # Override with environment variables
+        config = cls._apply_env(config)
+        
+        return config
+    
+    @classmethod
+    def _apply_dict(cls, config: "Config", data: dict[str, Any]) -> "Config":
+        """Apply dict values to config."""
+        if "format" in data:
+            try:
+                config.format = OutputFormat(data["format"])
+            except ValueError:
+                pass
+        if "color" in data:
+            config.color = bool(data["color"])
+        if "verbose" in data:
+            config.verbose = bool(data["verbose"])
+        if "timeout_seconds" in data:
+            config.timeout_seconds = int(data["timeout_seconds"])
+        if "max_retries" in data:
+            config.max_retries = int(data["max_retries"])
+        if "confirm_destructive" in data:
+            config.confirm_destructive = bool(data["confirm_destructive"])
+        return config
+    
+    @classmethod
+    def _apply_env(cls, config: "Config") -> "Config":
+        """Apply environment variable overrides."""
+        if fmt := os.environ.get("MONARCH_FORMAT"):
+            try:
+                config.format = OutputFormat(fmt.lower())
+            except ValueError:
+                pass
+        
+        # NO_COLOR is a standard (https://no-color.org/)
+        if os.environ.get("NO_COLOR"):
+            config.color = False
+        elif os.environ.get("MONARCH_COLOR") == "0":
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
+    def save(self) -> None:
+        """Save current config to file."""
+        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
+        with open(CONFIG_FILE, "w") as f:
+            json.dump({
+                "format": self.format.value,
+                "color": self.color,
+                "verbose": self.verbose,
+                "timeout_seconds": self.timeout_seconds,
+                "max_retries": self.max_retries,
+                "confirm_destructive": self.confirm_destructive,
+            }, f, indent=2)
+
+
+# Global config instance (loaded once)
+_config: Config | None = None
+
+
+def get_config() -> Config:
+    """Get the global config instance."""
+    global _config
+    if _config is None:
+        _config = Config.load()
+    return _config
```

Add a config command:

```diff
+# src/monarch_cli/commands/config.py
+"""Configuration management commands."""
+
+import typer
+from ..core.config import get_config, get_config_dir, CONFIG_FILE
+from ..output import output, OutputFormat, console
+
+app = typer.Typer(help="Configuration management")
+
+
+@app.command("show")
+def show_config(
+    format: OutputFormat = typer.Option(OutputFormat.JSON, "--format", "-f")
+):
+    """Show current configuration."""
+    config = get_config()
+    output({
+        "format": config.format.value,
+        "color": config.color,
+        "verbose": config.verbose,
+        "timeout_seconds": config.timeout_seconds,
+        "max_retries": config.max_retries,
+        "confirm_destructive": config.confirm_destructive,
+        "config_file": str(CONFIG_FILE),
+        "config_file_exists": CONFIG_FILE.exists(),
+    }, format)
+
+
+@app.command("set")
+def set_config(
+    key: str = typer.Argument(..., help="Config key to set"),
+    value: str = typer.Argument(..., help="Value to set"),
+):
+    """Set a configuration value.
+    
+    Examples:
+        monarch config set format table
+        monarch config set timeout_seconds 60
+        monarch config set confirm_destructive false
+    """
+    config = get_config()
+    
+    if key == "format":
+        config.format = OutputFormat(value.lower())
+    elif key == "color":
+        config.color = value.lower() in ("true", "1", "yes")
+    elif key == "verbose":
+        config.verbose = value.lower() in ("true", "1", "yes")
+    elif key == "timeout_seconds":
+        config.timeout_seconds = int(value)
+    elif key == "max_retries":
+        config.max_retries = int(value)
+    elif key == "confirm_destructive":
+        config.confirm_destructive = value.lower() in ("true", "1", "yes")
+    else:
+        console.print(f"[red]Unknown config key: {key}[/red]")
+        raise typer.Exit(2)
+    
+    config.save()
+    console.print(f"[green]Set {key} = {value}[/green]")
+
+
+@app.command("path")
+def config_path():
+    """Show config file path."""
+    print(CONFIG_FILE)
```

---

## 4. Retry Logic with Exponential Backoff

### Analysis
Network operations can fail transiently. The current plan has no retry logic, which means:
- Temporary network blips cause failures
- Rate limits aren't handled gracefully
- AI agents must implement their own retry logic

### Rationale
Built-in retry with exponential backoff:
- Improves reliability significantly
- Handles transient failures automatically
- Respects rate limits with proper backoff
- Reduces burden on AI agent implementations

### Proposed Change

```diff
+# src/monarch_cli/core/retry.py
+"""Retry logic with exponential backoff."""
+
+import asyncio
+import functools
+import random
+from typing import TypeVar, Callable, Awaitable, Any
+
+from .config import get_config
+from .exceptions import RateLimitError, NetworkError
+from ..output import console
+
+T = TypeVar("T")
+
+# Exceptions that should trigger retry
+RETRYABLE_EXCEPTIONS = (
+    ConnectionError,
+    TimeoutError,
+    OSError,  # Includes network errors
+)
+
+
+async def with_retry(
+    coro_factory: Callable[[], Awaitable[T]],
+    max_retries: int | None = None,
+    base_delay: float = 1.0,
+    max_delay: float = 30.0,
+    jitter: bool = True,
+) -> T:
+    """Execute an async operation with exponential backoff retry.
+    
+    Args:
+        coro_factory: Callable that returns a new coroutine for each attempt
+        max_retries: Maximum retry attempts (None = use config)
+        base_delay: Initial delay in seconds
+        max_delay: Maximum delay between retries
+        jitter: Add randomness to prevent thundering herd
+    
+    Returns:
+        Result of the successful operation
+    
+    Raises:
+        The last exception if all retries fail
+    """
+    if max_retries is None:
+        max_retries = get_config().max_retries
+    
+    last_exception: Exception | None = None
+    
+    for attempt in range(max_retries + 1):
+        try:
+            return await coro_factory()
+        except RETRYABLE_EXCEPTIONS as e:
+            last_exception = e
+            
+            if attempt == max_retries:
+                break
+            
+            # Calculate delay with exponential backoff
+            delay = min(base_delay * (2 ** attempt), max_delay)
+            
+            # Add jitter (±25%)
+            if jitter:
+                delay = delay * (0.75 + random.random() * 0.5)
+            
+            console.print(
+                f"[dim]Retry {attempt + 1}/{max_retries} after {delay:.1f}s: {e}[/dim]",
+                stderr=True
+            )
+            
+            await asyncio.sleep(delay)
+    
+    # All retries exhausted
+    if last_exception:
+        raise NetworkError(f"Operation failed after {max_retries} retries: {last_exception}")
+    raise RuntimeError("Unexpected retry state")
+
+
+def retryable(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
+    """Decorator to make an async function retryable.
+    
+    Usage:
+        @retryable
+        async def fetch_data():
+            return await client.get_accounts()
+    """
+    @functools.wraps(func)
+    async def wrapper(*args: Any, **kwargs: Any) -> T:
+        return await with_retry(lambda: func(*args, **kwargs))
+    return wrapper
```

Update the client to use retry:

```diff
 # src/monarch_cli/core/client.py
 from monarchmoney import MonarchMoney
 from .session import get_session_token
-from .async_utils import run_async
+from .retry import with_retry

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

+
+async def call_api(coro_factory):
+    """Call API method with retry logic.
+    
+    Usage:
+        result = run_async(call_api(lambda: client.get_accounts()))
+    """
+    return await with_retry(coro_factory)
```

---

## 5. Date Presets for Common Queries

### Analysis
The current plan only supports `--start` and `--end` date flags. Users frequently want:
- This month's transactions
- Last 30 days
- Year-to-date
- Last month

Forcing manual date calculation is tedious and error-prone.

### Rationale
Date presets:
- Dramatically improve CLI ergonomics
- Reduce cognitive load
- Are especially valuable for AI agents that can use semantic presets
- Follow the "make common things easy" principle

### Proposed Change

```diff
+# src/monarch_cli/core/dates.py
+"""Date utilities and presets."""
+
+from datetime import date, timedelta
+from enum import Enum
+from typing import Tuple
+
+
+class DatePreset(str, Enum):
+    """Common date range presets."""
+    TODAY = "today"
+    YESTERDAY = "yesterday"
+    THIS_WEEK = "this-week"
+    LAST_WEEK = "last-week"
+    THIS_MONTH = "this-month"
+    LAST_MONTH = "last-month"
+    LAST_30_DAYS = "last-30-days"
+    LAST_90_DAYS = "last-90-days"
+    THIS_YEAR = "this-year"
+    LAST_YEAR = "last-year"
+    YTD = "ytd"  # Year-to-date (alias for this-year)
+    ALL = "all"
+
+
+def resolve_preset(preset: DatePreset) -> Tuple[date | None, date | None]:
+    """Convert a preset to (start_date, end_date) tuple.
+    
+    Returns None for open-ended ranges.
+    """
+    today = date.today()
+    
+    match preset:
+        case DatePreset.TODAY:
+            return (today, today)
+        
+        case DatePreset.YESTERDAY:
+            yesterday = today - timedelta(days=1)
+            return (yesterday, yesterday)
+        
+        case DatePreset.THIS_WEEK:
+            # Start of week (Monday)
+            start = today - timedelta(days=today.weekday())
+            return (start, today)
+        
+        case DatePreset.LAST_WEEK:
+            # Previous Monday to Sunday
+            this_monday = today - timedelta(days=today.weekday())
+            last_monday = this_monday - timedelta(days=7)
+            last_sunday = this_monday - timedelta(days=1)
+            return (last_monday, last_sunday)
+        
+        case DatePreset.THIS_MONTH:
+            start = today.replace(day=1)
+            return (start, today)
+        
+        case DatePreset.LAST_MONTH:
+            first_of_this_month = today.replace(day=1)
+            last_of_prev_month = first_of_this_month - timedelta(days=1)
+            first_of_prev_month = last_of_prev_month.replace(day=1)
+            return (first_of_prev_month, last_of_prev_month)
+        
+        case DatePreset.LAST_30_DAYS:
+            start = today - timedelta(days=30)
+            return (start, today)
+        
+        case DatePreset.LAST_90_DAYS:
+            start = today - timedelta(days=90)
+            return (start, today)
+        
+        case DatePreset.THIS_YEAR | DatePreset.YTD:
+            start = today.replace(month=1, day=1)
+            return (start, today)
+        
+        case DatePreset.LAST_YEAR:
+            start = today.replace(year=today.year - 1, month=1, day=1)
+            end = today.replace(year=today.year - 1, month=12, day=31)
+            return (start, end)
+        
+        case DatePreset.ALL:
+            return (None, None)
+    
+    return (None, None)
+
+
+def parse_date_range(
+    preset: DatePreset | None = None,
+    start: str | None = None,
+    end: str | None = None,
+) -> Tuple[str | None, str | None]:
+    """Parse date range from preset or explicit dates.
+    
+    Explicit dates take precedence over preset.
+    Returns (start_date, end_date) as ISO format strings or None.
+    """
+    # Explicit dates override preset
+    if start is not None or end is not None:
+        return (start, end)
+    
+    if preset is not None:
+        start_date, end_date = resolve_preset(preset)
+        return (
+            start_date.isoformat() if start_date else None,
+            end_date.isoformat() if end_date else None,
+        )
+    
+    return (None, None)
```

Update transaction commands:

```diff
 # src/monarch_cli/commands/transactions.py
 import typer
 from typing import Optional
-from datetime import date
 from ..core.client import get_client
 from ..core.async_utils import run_async
+from ..core.dates import DatePreset, parse_date_range
+from ..core.error_handler import handle_errors
 from ..output import output, OutputFormat, error

 app = typer.Typer(help="Transaction management")

 @app.command("list")
+@handle_errors
 def list_transactions(
     limit: int = typer.Option(100, "--limit", "-l", help="Max transactions to return"),
     offset: int = typer.Option(0, "--offset", "-o", help="Pagination offset"),
     start_date: Optional[str] = typer.Option(None, "--start", "-s", help="Start date (YYYY-MM-DD)"),
     end_date: Optional[str] = typer.Option(None, "--end", "-e", help="End date (YYYY-MM-DD)"),
+    preset: Optional[DatePreset] = typer.Option(
+        None, "--preset", "-p",
+        help="Date range preset (overridden by --start/--end)"
+    ),
     account_id: Optional[str] = typer.Option(None, "--account", "-a", help="Filter by account ID"),
+    search: Optional[str] = typer.Option(None, "--search", "-q", help="Search transactions"),
     format: OutputFormat = typer.Option(OutputFormat.JSON, "--format", "-f")
 ):
-    """List transactions with optional filters."""
+    """List transactions with optional filters.
+    
+    Examples:
+        monarch transactions list --preset this-month
+        monarch transactions list --preset last-30-days --limit 50
+        monarch transactions list --start 2024-01-01 --end 2024-01-31
+        monarch transactions list --search "Amazon" --preset ytd
+    """
+    # Resolve date range (explicit dates override preset)
+    resolved_start, resolved_end = parse_date_range(preset, start_date, end_date)
+    
     client = get_client()
     transactions = run_async(client.get_transactions(
         limit=limit,
         offset=offset,
-        start_date=start_date,
-        end_date=end_date,
-        search=None,
+        start_date=resolved_start,
+        end_date=resolved_end,
+        search=search,
         account_ids=[account_id] if account_id else None,
     ))
     # ... rest of implementation
```

---

## 6. Progress Indicators for Long Operations

### Analysis
The plan mentions "print something within 100ms" but doesn't implement progress indicators. Operations like account refresh can take 30+ seconds with no feedback.

### Rationale
Progress indicators:
- Prevent users from thinking the CLI is frozen
- Provide useful status information
- Improve perceived performance
- Are disabled automatically in non-TTY contexts (piping)

### Proposed Change

```diff
+# src/monarch_cli/output/progress.py
+"""Progress indicators for long-running operations."""
+
+import sys
+from contextlib import contextmanager
+from typing import Generator
+
+from rich.console import Console
+from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
+
+console = Console(stderr=True)
+
+
+def is_interactive() -> bool:
+    """Check if we're in an interactive terminal."""
+    return sys.stderr.isatty()
+
+
+@contextmanager
+def spinner(message: str) -> Generator[None, None, None]:
+    """Show a spinner while an operation is in progress.
+    
+    Only shows spinner in interactive terminals.
+    In non-interactive mode, just prints the message.
+    
+    Usage:
+        with spinner("Fetching accounts..."):
+            accounts = run_async(client.get_accounts())
+    """
+    if not is_interactive():
+        console.print(f"[dim]{message}[/dim]")
+        yield
+        return
+    
+    with Progress(
+        SpinnerColumn(),
+        TextColumn("[progress.description]{task.description}"),
+        TimeElapsedColumn(),
+        console=console,
+        transient=True,  # Remove spinner when done
+    ) as progress:
+        progress.add_task(description=message, total=None)
+        yield
+
+
+@contextmanager
+def status(message: str) -> Generator[None, None, None]:
+    """Show a simple status message.
+    
+    For quick operations where a full spinner would flash too fast.
+    """
+    if is_interactive():
+        console.print(f"[dim]{message}[/dim]")
+    yield
```

Usage in commands:

```diff
 # src/monarch_cli/commands/accounts.py
 @app.command()
+@handle_errors
 def refresh():
     """Trigger account refresh from financial institutions."""
-    try:
+    from ..output.progress import spinner
+    
+    with spinner("Requesting account refresh from financial institutions..."):
         client = get_client()
         run_async(client.request_accounts_refresh_all())
-        output({
-            "status": "refresh_requested",
-            "message": "Account refresh requested from financial institutions"
-        })
-    except Exception as e:
-        error(str(e))
+    
+    output({
+        "status": "refresh_requested",
+        "message": "Account refresh requested. Balances will update shortly."
+    })
```

---

## 7. Shell Completions as P1 (Not P2)

### Analysis
The plan defers shell completions to P2 (post-release). However, Typer has built-in completion support that's trivial to enable and dramatically improves CLI usability.

### Rationale
Shell completions:
- Are essentially free with Typer
- Significantly improve discoverability
- Help users learn the CLI faster
- Are especially valuable for complex commands with many options

### Proposed Change

```diff
 ## Phase 5: Testing & Documentation
 **Priority**: P1
 
+### 5.0 Shell Completions (Trivial with Typer)
+
+Typer has built-in completion support. Add installation instructions:
+
+```bash
+# Install completions
+monarch --install-completion bash  # or zsh, fish, powershell
+
+# After reloading shell:
+monarch tr<TAB>          # → monarch transactions
+monarch transactions li<TAB>  # → monarch transactions list
+monarch transactions list --<TAB>  # Shows all options
+```
+
+No code changes needed - Typer handles this automatically when using its app structure.
+
+**Add to README:**
+```markdown
+## Shell Completions
+
+Enable tab completion for your shell:
+
+\`\`\`bash
+# Bash
+monarch --install-completion bash
+source ~/.bashrc
+
+# Zsh
+monarch --install-completion zsh
+source ~/.zshrc
+
+# Fish
+monarch --install-completion fish
+\`\`\`
+```
+
 ### 5.1 Unit Tests
```

Move from P2 to already-done in P1:

```diff
 ### 🟡 P2: Post-Release (v0.2.0+)
 
 - [ ] `CODE_OF_CONDUCT.md`
 - [ ] `SECURITY.md` (vulnerability reporting)
 - [ ] GitHub issue/PR templates
 - [ ] PyPI publish workflow (on version tags)
 - [ ] Coverage thresholds in CI
-- [ ] Shell completions (`--install-completion`)
 - [ ] Man page generation
```

---

## 8. CSV Export Format

### Analysis
The plan only supports JSON and table output. CSV is a common need for:
- Spreadsheet import (Excel, Google Sheets)
- Data analysis tools
- Simple scripting with `cut`, `awk`, etc.

### Rationale
CSV export:
- Is trivial to implement
- Covers a major use case (spreadsheet users)
- Enables integration with a broader ecosystem
- Is especially useful for transaction exports

### Proposed Change

```diff
 # src/monarch_cli/output/__init__.py
 import json
 import sys
+import csv
+from io import StringIO
 from enum import Enum
 from typing import Any
 from rich.console import Console
 from rich.table import Table

 class OutputFormat(str, Enum):
     JSON = "json"
     TABLE = "table"
     COMPACT = "compact"  # Single-line JSON
+    CSV = "csv"          # CSV for spreadsheet import

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
+    elif format == OutputFormat.CSV:
+        if isinstance(data, list):
+            print_csv(data)
+        else:
+            # Single object - wrap in list
+            print_csv([data] if isinstance(data, dict) else [{"value": data}])
+
+
+def print_csv(items: list[dict]) -> None:
+    """Print list of dicts as CSV."""
+    if not items:
+        return
+    
+    output = StringIO()
+    writer = csv.DictWriter(output, fieldnames=items[0].keys())
+    writer.writeheader()
+    writer.writerows(items)
+    print(output.getvalue(), end="")
```

Usage:

```bash
monarch transactions list --preset this-month --format csv > transactions.csv
# Opens directly in Excel/Sheets

monarch accounts list -f csv | column -t -s,
# Pretty-print in terminal
```

---

## 9. Dry Run Mode for Mutations

### Analysis
Mutation operations (create, update, delete) are destructive. The plan has no way to preview what would happen without actually doing it.

### Rationale
Dry run mode:
- Reduces risk of mistakes
- Helps users build confidence with the CLI
- Is valuable for scripting (validate before execute)
- Follows the principle of least surprise

### Proposed Change

```diff
+# Add to global options section in plan
+
+| `--dry-run` | bool | false | Preview operation without executing |
```

```diff
 # src/monarch_cli/commands/transactions.py

 @app.command()
+@handle_errors
 def update(
     transaction_id: str = typer.Argument(..., help="Transaction ID to update"),
     amount: Optional[float] = typer.Option(None, "--amount", help="New amount"),
     description: Optional[str] = typer.Option(None, "--description", "-d", help="New description"),
     category_id: Optional[str] = typer.Option(None, "--category", "-c", help="New category ID"),
     date: Optional[str] = typer.Option(None, "--date", help="New date (YYYY-MM-DD)"),
+    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without applying"),
     format: OutputFormat = typer.Option(OutputFormat.JSON, "--format", "-f")
 ):
     """Update an existing transaction."""
     client = get_client()

     # Build update kwargs - only include non-None values
     update_kwargs = {"transaction_id": transaction_id}
     if amount is not None:
         update_kwargs["amount"] = amount
     if description is not None:
         update_kwargs["merchant_name"] = description
     if category_id is not None:
         update_kwargs["category_id"] = category_id

+    if dry_run:
+        output({
+            "dry_run": True,
+            "operation": "update_transaction",
+            "transaction_id": transaction_id,
+            "changes": {k: v for k, v in update_kwargs.items() if k != "transaction_id"},
+            "message": "No changes made (dry run)"
+        }, format)
+        return
+
     result = run_async(client.update_transaction(**update_kwargs))
     output({
         "status": "updated",
         "transaction_id": transaction_id
     }, format)
```

```diff
 @app.command()
+@handle_errors
 def delete(
     transaction_id: str = typer.Argument(..., help="Transaction ID to delete"),
+    dry_run: bool = typer.Option(False, "--dry-run", help="Preview deletion without executing"),
+    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
     format: OutputFormat = typer.Option(OutputFormat.JSON, "--format", "-f")
 ):
     """Delete a transaction."""
+    from ..core.config import get_config
+    
+    if dry_run:
+        output({
+            "dry_run": True,
+            "operation": "delete_transaction",
+            "transaction_id": transaction_id,
+            "message": "Transaction would be deleted (dry run)"
+        }, format)
+        return
+    
+    # Confirmation prompt for destructive operation
+    if get_config().confirm_destructive and not force:
+        if sys.stdin.isatty():
+            confirm = typer.confirm(f"Delete transaction {transaction_id}?")
+            if not confirm:
+                raise typer.Abort()
+    
     client = get_client()
     run_async(client.delete_transaction(transaction_id))
     output({
         "status": "deleted",
         "transaction_id": transaction_id
     }, format)
```

---

## 10. Caching for Stable Data

### Analysis
Some data rarely changes (categories, tags, account list). Fetching these on every command adds latency and API load.

### Rationale
A simple TTL cache:
- Reduces API calls for stable data
- Improves response time
- Is transparent to users
- Can be disabled with `--no-cache` if needed

### Proposed Change

```diff
+# src/monarch_cli/core/cache.py
+"""Simple TTL cache for stable data."""
+
+import json
+import time
+from pathlib import Path
+from typing import Any, TypeVar, Callable
+from functools import wraps
+
+from .config import get_config_dir
+
+T = TypeVar("T")
+
+CACHE_DIR = get_config_dir() / "cache"
+
+# TTL in seconds for different data types
+CACHE_TTL = {
+    "categories": 3600,      # 1 hour - rarely change
+    "tags": 3600,            # 1 hour
+    "accounts": 300,         # 5 minutes - balance changes, but list is stable
+    "institutions": 3600,    # 1 hour
+}
+
+
+def get_cache_path(key: str) -> Path:
+    """Get path for cache file."""
+    return CACHE_DIR / f"{key}.json"
+
+
+def get_cached(key: str) -> Any | None:
+    """Get cached value if valid."""
+    cache_path = get_cache_path(key)
+    
+    if not cache_path.exists():
+        return None
+    
+    try:
+        with open(cache_path) as f:
+            cached = json.load(f)
+        
+        # Check TTL
+        ttl = CACHE_TTL.get(key, 300)
+        if time.time() - cached.get("timestamp", 0) > ttl:
+            return None
+        
+        return cached.get("data")
+    except (json.JSONDecodeError, OSError):
+        return None
+
+
+def set_cached(key: str, data: Any) -> None:
+    """Store value in cache."""
+    CACHE_DIR.mkdir(parents=True, exist_ok=True)
+    cache_path = get_cache_path(key)
+    
+    with open(cache_path, "w") as f:
+        json.dump({
+            "timestamp": time.time(),
+            "data": data,
+        }, f)
+
+
+def clear_cache(key: str | None = None) -> None:
+    """Clear cache. If key is None, clear all."""
+    if key:
+        path = get_cache_path(key)
+        if path.exists():
+            path.unlink()
+    else:
+        if CACHE_DIR.exists():
+            for f in CACHE_DIR.glob("*.json"):
+                f.unlink()
+
+
+def cached(key: str):
+    """Decorator to cache function results.
+    
+    Usage:
+        @cached("categories")
+        def get_categories():
+            return run_async(client.get_transaction_categories())
+    """
+    def decorator(func: Callable[..., T]) -> Callable[..., T]:
+        @wraps(func)
+        def wrapper(*args, no_cache: bool = False, **kwargs) -> T:
+            if not no_cache:
+                cached_value = get_cached(key)
+                if cached_value is not None:
+                    return cached_value
+            
+            result = func(*args, **kwargs)
+            set_cached(key, result)
+            return result
+        
+        return wrapper
+    return decorator
```

Usage:

```diff
 # src/monarch_cli/commands/categories.py
+from ..core.cache import cached

+@cached("categories")
+def _fetch_categories(client) -> dict:
+    """Fetch categories (cached for 1 hour)."""
+    return run_async(client.get_transaction_categories())
+
 @app.command("list")
+@handle_errors
 def list_categories(
+    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass cache"),
     format: OutputFormat = typer.Option(OutputFormat.JSON, "--format", "-f")
 ):
     """List all transaction categories."""
     client = get_client()
-    categories = run_async(client.get_transaction_categories())
+    categories = _fetch_categories(client, no_cache=no_cache)
     output(categories, format)
```

Add cache management command:

```diff
+# In src/monarch_cli/commands/config.py
+
+@app.command("clear-cache")
+def clear_cache_cmd():
+    """Clear cached data."""
+    from ..core.cache import clear_cache
+    clear_cache()
+    console.print("[green]Cache cleared[/green]")
```

---

## 11. Improved Project Structure

### Analysis
The current structure is good but could be improved with:
- Separating data transformation from API calls
- Better organization of shared types

### Rationale
- **Transformers**: Separating data transformation makes it testable in isolation
- **Types**: Centralized types improve consistency and IDE support
- **Clearer separation**: API layer vs presentation layer

### Proposed Change

```diff
 monarch-cli/
 ├── src/
 │   └── monarch_cli/
 │       ├── __init__.py
 │       ├── py.typed
 │       ├── main.py
 │       ├── commands/
 │       │   ├── __init__.py
 │       │   ├── auth.py
 │       │   ├── accounts.py
 │       │   ├── transactions.py
 │       │   ├── budgets.py
 │       │   ├── cashflow.py
-│       │   └── categories.py
+│       │   ├── categories.py
+│       │   └── config.py           # Config management commands
 │       ├── core/
 │       │   ├── __init__.py
 │       │   ├── client.py
 │       │   ├── session.py
-│       │   └── async_utils.py
+│       │   ├── async_utils.py
+│       │   ├── config.py           # Configuration system
+│       │   ├── exceptions.py       # Exception hierarchy
+│       │   ├── error_handler.py    # Error handling decorator
+│       │   ├── retry.py            # Retry with backoff
+│       │   ├── cache.py            # TTL caching
+│       │   └── dates.py            # Date utilities and presets
 │       └── output/
 │           ├── __init__.py
-│           └── formatters.py
+│           ├── formatters.py       # JSON, table, CSV, compact
+│           └── progress.py         # Spinners and progress bars
+│       └── transformers/           # API response → CLI output
+│           ├── __init__.py
+│           ├── accounts.py         # Transform account data
+│           ├── transactions.py     # Transform transaction data
+│           └── budgets.py          # Transform budget data
```

Example transformer:

```diff
+# src/monarch_cli/transformers/accounts.py
+"""Transform account API responses to CLI-friendly format."""
+
+from typing import Any
+
+
+def transform_account(raw: dict[str, Any]) -> dict[str, Any]:
+    """Transform a single account."""
+    return {
+        "id": raw.get("id"),
+        "name": raw.get("displayName"),
+        "type": raw.get("type", {}).get("display"),
+        "subtype": raw.get("subtype", {}).get("display"),
+        "balance": raw.get("currentBalance"),
+        "institution": raw.get("institution", {}).get("name"),
+        "is_active": not raw.get("isHidden", False),
+        "is_manual": raw.get("isManual", False),
+        "last_updated": raw.get("updatedAt"),
+    }
+
+
+def transform_accounts(raw: dict[str, Any]) -> list[dict[str, Any]]:
+    """Transform accounts API response."""
+    return [
+        transform_account(acc)
+        for acc in raw.get("accounts", [])
+    ]
+
+
+def transform_holding(raw: dict[str, Any]) -> dict[str, Any]:
+    """Transform a single holding."""
+    return {
+        "id": raw.get("id"),
+        "symbol": raw.get("ticker"),
+        "name": raw.get("name"),
+        "quantity": raw.get("quantity"),
+        "price": raw.get("closingPrice"),
+        "value": raw.get("value"),
+        "cost_basis": raw.get("costBasis"),
+        "gain_loss": raw.get("gainLoss"),
+        "gain_loss_percent": raw.get("gainLossPercent"),
+    }
```

Then commands become cleaner:

```diff
 # src/monarch_cli/commands/accounts.py
+from ..transformers.accounts import transform_accounts

 @app.command("list")
 @handle_errors
 def list_accounts(
     format: OutputFormat = typer.Option(OutputFormat.JSON, "--format", "-f")
 ):
     """List all linked financial accounts."""
     client = get_client()
-    accounts = run_async(client.get_accounts())
-
-    # Transform to cleaner structure
-    result = []
-    for acc in accounts.get("accounts", []):
-        result.append({
-            "id": acc.get("id"),
-            "name": acc.get("displayName"),
-            "type": acc.get("type", {}).get("display"),
-            "balance": acc.get("currentBalance"),
-            "institution": acc.get("institution", {}).get("name"),
-            "is_active": not acc.get("isHidden", False),
-        })
-
-    output(result, format)
+    raw = run_async(client.get_accounts())
+    output(transform_accounts(raw), format)
```

---

## 12. VCR/Response Recording for Tests

### Analysis
The current test plan uses mocks, but mocks can drift from real API behavior. The live tests require actual credentials and hit real APIs.

### Rationale
VCR-style recording:
- Captures real API responses once
- Replays them in tests without network calls
- Catches when API behavior changes
- Allows realistic tests without credentials

### Proposed Change

```diff
 [project.optional-dependencies]
 dev = [
     "pytest>=8.0.0",
     "pytest-asyncio>=0.23.0",
     "pytest-cov>=4.0.0",
+    "pytest-recording>=0.13.0",  # VCR-style HTTP recording
+    "respx>=0.21.0",             # HTTPX mocking (monarchmoney uses httpx)
     "ruff>=0.4.0",
     "mypy>=1.10.0",
 ]
```

```diff
+# tests/conftest.py additions
+
+import pytest
+
+
+@pytest.fixture
+def vcr_config():
+    """VCR configuration for recording API responses."""
+    return {
+        "filter_headers": ["authorization", "cookie"],
+        "filter_query_parameters": ["token"],
+        "record_mode": "once",  # Record once, replay forever
+        "cassette_library_dir": "tests/cassettes",
+    }
+
+
+# Usage in tests:
+# @pytest.mark.vcr()
+# def test_list_accounts():
+#     ...  # First run records, subsequent runs replay
```

```diff
 ### 5.1 Unit Tests
+
+#### VCR/Recording Tests
+
+For realistic tests without hitting live APIs:
+
+```python
+# tests/test_accounts_recorded.py
+import pytest
+from monarch_cli.commands.accounts import list_accounts
+
+
+@pytest.mark.vcr()
+class TestAccountsRecorded:
+    """Tests using recorded API responses."""
+    
+    def test_list_accounts_structure(self, capsys):
+        """Verify account list structure matches recorded response."""
+        list_accounts(format="json")
+        
+        captured = capsys.readouterr()
+        # Validates against real (recorded) API response structure
+        import json
+        accounts = json.loads(captured.out)
+        
+        assert isinstance(accounts, list)
+        assert all("id" in acc for acc in accounts)
+        assert all("balance" in acc for acc in accounts)
+```
+
+**Recording new cassettes:**
+```bash
+# Set credentials and record
+MONARCH_TOKEN=... pytest tests/test_accounts_recorded.py --vcr-record=all
+
+# Commit cassettes (sanitized of auth tokens)
+git add tests/cassettes/
+```
```

---

## 13. Summary of Changes by Section

| Section | Change Type | Impact |
|---------|-------------|--------|
| Async utilities | Architecture | More efficient, cleaner |
| Exception hierarchy | Architecture | Consistent errors for AI agents |
| Error handler decorator | Architecture | Cleaner commands, less duplication |
| Configuration system | Feature | User preferences, env var support |
| Retry logic | Reliability | Handles transient failures |
| Date presets | Feature | Better ergonomics |
| Progress indicators | UX | Better feedback for long ops |
| Shell completions | Feature | Discoverability |
| CSV export | Feature | Spreadsheet integration |
| Dry run mode | Feature | Safer mutations |
| Caching | Performance | Faster for stable data |
| Transformers | Architecture | Testable, maintainable |
| VCR testing | Testing | Realistic tests without live API |

---

## 14. Updated Dependencies

```diff
 [project]
 dependencies = [
     "typer[all]>=0.9.0",
     "monarchmoneycommunity>=1.0.0",
     "keyring>=24.0.0",
     "rich>=13.0.0",
+    "httpx>=0.27.0",  # For retry/timeout handling (monarchmoney uses this)
 ]

 [project.optional-dependencies]
 dev = [
     "pytest>=8.0.0",
     "pytest-asyncio>=0.23.0",
     "pytest-cov>=4.0.0",
+    "pytest-recording>=0.13.0",
+    "respx>=0.21.0",
     "ruff>=0.4.0",
     "mypy>=1.10.0",
 ]
```

---

## 15. Updated Phase Order

The original phase order is good, but I'd add a step:

```diff
 Phase 0 (Setup) ──► Phase 1 (Auth) ──► 🔑 USER AUTH ──► Phase 2 (Output)
                                                               │
                                                               ▼
-                                                    Phase 3 (Commands)
+                                                    Phase 2.5 (Core Utils)
+                                                    - Exceptions, error handler
+                                                    - Config system
+                                                    - Retry logic
+                                                    - Date utilities
+                                                    - Caching
+                                                              │
+                                                              ▼
+                                                    Phase 3 (Commands)
                                                               │
                                                               ▼
                                                     Phase 4 (AI Optimization)
```

This ensures the infrastructure is in place before building commands, making them cleaner from the start.
