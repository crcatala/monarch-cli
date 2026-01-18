## High-level review (intent + where complexity creeps in)

The plan is aiming for a **scriptable, AI-agent-friendly CLI** over `monarchmoneycommunity`, with strong emphasis on:

- **Non-interactive automation** (JSON/NDJSON, stable schemas, exit codes)
- **Secure auth storage** (keyring default, portable file option)
- **Thin wrapper** philosophy (avoid re-implementing API logic)
- **Reliability** (retries, error mapping, progress feedback)
- **Good CLI ergonomics** (help examples, shell completion, config precedence)

That intent is solid. The main places the plan adds **more complexity than needed for a v0.1/v0.2 MVP** are:

1. **Too many layers early** (services + transformers + adapter for very simple pass-through calls).
2. **Config system in MVP** (TOML + precedence + commands) before there’s enough config to justify it.
3. **Dual output implementation** (minimal output in Phase 1, then “full version” in Phase 2) → duplication.
4. **Legacy pickle compat backend** in v1: security risk + code paths + support burden for marginal value.
5. **Retry/httpx dependency** that doesn’t clearly integrate with the upstream client (which may not use httpx).
6. **Error handling mechanics**: `sys.exit()` in decorators, errors printed to stdout, brittle string matching.
7. **Global flags spec vs implementation mismatch** (plan says “global flags”, examples implement per-command).

Below are concrete simplifications/revisions. For each: rationale + a git-diff style patch against your markdown plan.

---

# 1) Simplify MVP scope: defer config file + `monarch config` commands

### Why this makes the project better
- A config system (TOML file + precedence + persistence + commands) is a **lot of surface area** to test/support.
- In early versions, most settings can be handled via **env vars + CLI flags** (which is already agent-friendly).
- Deferring config reduces code and avoids circular import pitfalls (your `core/config.py` imports `OutputFormat` from `output`, while output imports exceptions, etc.).

### What you keep
- Env var support (`MONARCH_FORMAT`, `MONARCH_VERBOSE`, etc.)
- CLI flags on commands (or later, a Typer callback for globals)

### Diff
```diff
diff --git a/plans/monarch-cli-implementation-plan.md b/plans/monarch-cli-implementation-plan.md
--- a/plans/monarch-cli-implementation-plan.md
+++ b/plans/monarch-cli-implementation-plan.md
@@
-### Config Precedence (highest to lowest)
-
-1. CLI flags (`--format json`)
-2. Environment variables (`MONARCH_FORMAT=json`)
-3. User config (`~/.config/monarch-cli/config.toml` via platformdirs)
-4. Defaults
+### Config Precedence (highest to lowest) (MVP)
+
+1. CLI flags (`--format json`)
+2. Environment variables (`MONARCH_FORMAT=json`)
+3. Defaults
+
+> Defer persisted config file support (`config.toml`) and `monarch config` commands until post-MVP
+> once there are enough stable settings to justify the additional surface area.

@@
-│       ├── commands/            # CLI command handlers (thin)
+│       ├── commands/            # CLI command handlers (thin)
@@
-│       │   └── config.py        # Config management commands
+│       │   └── (defer) config.py        # Defer config commands until post-MVP
@@
-│       ├── core/                # Infrastructure
+│       ├── core/                # Infrastructure
@@
-│       │   ├── config.py        # Configuration system
+│       │   ├── (defer) config.py        # Defer persisted config until post-MVP
@@
-### 3.8 Config Commands
+### 3.8 (Defer) Config Commands
@@
-### 3.9 Configuration System
+### 3.9 (Defer) Configuration System
@@
-### MVP Commands (Priority 1)
+### MVP Commands (Priority 1)
@@
-| `monarch config show` | Show configuration | (local) |
-| `monarch config set` | Set configuration | (local) |
+> Defer `monarch config` commands until post-MVP.
```

---

# 2) Remove `FILE_COMPAT` (pickle) from v1

### Why this makes the project better
- Pickle-based session files are a **known footgun** (code execution risk if tampered with).
- Supporting it adds:
  - extra code paths
  - doc burden (“unsafe but supported”)
  - complexity in doctor/logout/status
- The value is marginal: users can re-auth or set `MONARCH_TOKEN` when they truly need portability/interop.

### Diff
```diff
diff --git a/plans/monarch-cli-implementation-plan.md b/plans/monarch-cli-implementation-plan.md
--- a/plans/monarch-cli-implementation-plan.md
+++ b/plans/monarch-cli-implementation-plan.md
@@
-| **Session file (compat)** | `~/.mm/mm_session.pickle` | ❌ Unsafe (pickle) | Only for library interop (opt-in) |
+> Do not support legacy pickle session files in v1. If a compatibility mode is needed later,
+> implement it as an explicit, separate migration command with clear warnings.

@@
-class StorageBackend(str, Enum):
-    KEYRING = "keyring"
-    FILE = "file"              # Safe JSON with 0600 perms
-    FILE_COMPAT = "file-compat"  # Legacy pickle (opt-in only)
+class StorageBackend(str, Enum):
+    KEYRING = "keyring"
+    FILE = "file"  # Safe JSON with 0600 perms

@@
-# Legacy compat path (pickle, unsafe)
-COMPAT_SESSION_PATH = Path.home() / ".mm" / "mm_session.pickle"
+## No legacy pickle compat in v1.

@@
-    elif backend == StorageBackend.FILE_COMPAT:
-        # Legacy pickle - explicit opt-in only
-        import pickle
-        COMPAT_SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
-        with open(COMPAT_SESSION_PATH, "wb") as f:
-            pickle.dump({"token": token}, f)
+    # No legacy pickle backend in v1.

@@
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

@@
-    compat_exists = COMPAT_SESSION_PATH.exists()
-
-    if keyring_token:
+    if keyring_token:
         active = StorageBackend.KEYRING
     elif file_exists:
         active = StorageBackend.FILE
-    elif compat_exists:
-        active = StorageBackend.FILE_COMPAT
     else:
         active = None
@@
-        "has_compat_token": compat_exists,
         "active_backend": active.value if active else None,
         "file_path": str(session_path),
-        "compat_path": str(COMPAT_SESSION_PATH),
     }
@@
-    if backend is None or backend == StorageBackend.FILE_COMPAT:
-        if COMPAT_SESSION_PATH.exists():
-            COMPAT_SESSION_PATH.unlink()
+    # No legacy pickle backend in v1.

@@
 def doctor():
@@
-    console.print(f"  Compat: {'[yellow]present[/yellow]' if info['has_compat_token'] else '[dim]empty[/dim]'} ({info['compat_path']})")
     console.print(f"  Active: {info['active_backend'] or '[red]none[/red]'}")
```

---

# 3) Add `MONARCH_TOKEN` env var support in the real load order (agent/CI value, low complexity)

### Why this makes the project better
- You already document `MONARCH_TOKEN` as a fallback, but the planned `get_session_token()` doesn’t check it.
- For agents/CI, env var auth is the **most important non-interactive path**.
- Small change, big practical value.

### Diff
```diff
diff --git a/plans/monarch-cli-implementation-plan.md b/plans/monarch-cli-implementation-plan.md
--- a/plans/monarch-cli-implementation-plan.md
+++ b/plans/monarch-cli-implementation-plan.md
@@
-def get_session_token() -> str | None:
-    """Retrieve token, checking keyring first, then file, then compat."""
+def get_session_token() -> str | None:
+    """Retrieve token.
+
+    Precedence (highest to lowest):
+      1) MONARCH_TOKEN env var (best for CI/agents)
+      2) Keyring
+      3) JSON session file
+    """
+    # 1) Env var (explicit override)
+    env_token = os.environ.get("MONARCH_TOKEN")
+    if env_token:
+        return env_token
+
     # Try keyring first
     try:
         token = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
         if token:
             return token
     except Exception:
         pass  # Keyring may not be available
```

---

# 4) Fix the session file permission/atomic write details (reduce “gotchas”)

### Why this makes the project better
This is less about “complexity” and more about avoiding subtle bugs/support tickets:

- `os.chmod(fd, 0o600)` is incorrect: `chmod` expects a path; you want `os.fchmod(fd, ...)`.
- `os.rename` isn’t guaranteed atomic across filesystems; `os.replace` is the safer standard.

### Diff
```diff
diff --git a/plans/monarch-cli-implementation-plan.md b/plans/monarch-cli-implementation-plan.md
--- a/plans/monarch-cli-implementation-plan.md
+++ b/plans/monarch-cli-implementation-plan.md
@@
-        fd, tmp_path = tempfile.mkstemp(dir=session_path.parent, suffix=".tmp")
+        fd, tmp_path = tempfile.mkstemp(dir=session_path.parent, suffix=".tmp")
         try:
-            os.chmod(fd, 0o600)  # Strict permissions before writing
+            os.fchmod(fd, 0o600)  # Strict permissions before writing
             with os.fdopen(fd, "w") as f:
                 json.dump({"token": token}, f)
-            os.rename(tmp_path, session_path)
+            os.replace(tmp_path, session_path)  # atomic replace on same filesystem
```

---

# 5) Remove duplicated “minimal output” vs “full output” phases; implement output once, and send errors to stderr

### Why this makes the project better
- The plan currently has **two different implementations** of `src/monarch_cli/output/__init__.py`.
- That duplication is pure complexity: it creates merge conflicts, inconsistent behavior, and extra work.
- Also: your plan says stderr is for errors, but `output_error()` prints to stdout in both snippets—this breaks piping for agents.

### Revised approach
- Implement the **full output module from day 1** (even if only JSON/compact are used initially).
- Ensure `output_error()` prints to **stderr**.

### Diff
```diff
diff --git a/plans/monarch-cli-implementation-plan.md b/plans/monarch-cli-implementation-plan.md
--- a/plans/monarch-cli-implementation-plan.md
+++ b/plans/monarch-cli-implementation-plan.md
@@
-### 1.8 Minimal Output Helpers
-
-For Phase 1, we only need basic output for auth commands. Full output system comes in Phase 2.
-
-```python
-# src/monarch_cli/output/__init__.py (minimal version for Phase 1)
-...
-def output_error(error: MonarchCLIError) -> None:
-    """Output structured error for AI agents."""
-    print(json.dumps(error.to_dict(), indent=2))
-...
-```
+### 1.8 Output Helpers (single implementation)
+
+Implement the full output module once (JSON + compact first; table/CSV optional),
+and ensure errors go to **stderr** to preserve clean stdout for piping/agents.

@@
 def output_error(error: MonarchCLIError) -> None:
     """Output structured error for AI agents."""
-    print(json.dumps(error.to_dict(), indent=2))
+    print(json.dumps(error.to_dict(), indent=2), file=sys.stderr)
```

---

# 6) Make error handling more testable + less brittle (no `sys.exit()` in decorators; no string matching)

### Why this makes the project better
- Using `sys.exit()` inside a decorator makes CLI-level unit tests harder and can lead to confusing control flow.
- The `RuntimeError` `"Not authenticated"` string matching is fragile and will break if upstream wording changes.
- Typer already provides `raise typer.Exit(code)` for clean exits.

### Diff
```diff
diff --git a/plans/monarch-cli-implementation-plan.md b/plans/monarch-cli-implementation-plan.md
--- a/plans/monarch-cli-implementation-plan.md
+++ b/plans/monarch-cli-implementation-plan.md
@@
-# src/monarch_cli/core/error_handler.py
+# src/monarch_cli/core/error_handler.py
 """Decorator for consistent error handling across commands."""
 
 import functools
-import sys
+import typer
 from typing import Callable, TypeVar, ParamSpec
@@
 def handle_errors(func: Callable[P, R]) -> Callable[P, R]:
     """Decorator that catches exceptions and outputs consistent errors."""
@@
     def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
         try:
             return func(*args, **kwargs)
         except MonarchCLIError as e:
             output_error(e)
-            sys.exit(e.exit_code)
-        except RuntimeError as e:
-            if "Not authenticated" in str(e):
-                output_error(AuthenticationError())
-                sys.exit(1)
-            raise
+            raise typer.Exit(e.exit_code)
         except Exception as e:
             if is_verbose():
                 import traceback
                 traceback.print_exc()
             output_error(MonarchCLIError(f"Unexpected error: {e}"))
-            sys.exit(1)
+            raise typer.Exit(1)
 
     return wrapper
```

---

# 7) Reduce early-layering: treat “services” as optional, not required (MVP can be Adapter + Transformers + Commands)

### Why this makes the project better
Right now the plan mandates:

- Commands (thin)
- Services layer
- Transformers
- Adapter
- Upstream library

That’s architecturally nice, but for a thin wrapper it’s often overkill—especially when many commands are essentially:

> call method → transform → output

A pragmatic middle ground:

- Keep **Adapter** (good isolation for token/header private attrs).
- Keep **Transformers** (good for stable agent schemas).
- Make **Services optional** (only when there’s actual business logic: batching, retries, multi-call workflows).

This reduces file count and cognitive load without sacrificing future structure.

### Diff
```diff
diff --git a/plans/monarch-cli-implementation-plan.md b/plans/monarch-cli-implementation-plan.md
--- a/plans/monarch-cli-implementation-plan.md
+++ b/plans/monarch-cli-implementation-plan.md
@@
 ### Architecture
 
 ### Overview
 
 ```
 ┌─────────────────────────────────────────────────────────────┐
 │                        CLI Layer                            │
 │  (Typer commands with argument parsing)                     │
 └─────────────────────────────────────────────────────────────┘
                               │
                               ▼
-┌─────────────────────────────────────────────────────────────┐
-│                     Service Layer                           │
-│  services/*.py: business logic, retries, error mapping      │
-└─────────────────────────────────────────────────────────────┘
-                              │
-                              ▼
 ┌─────────────────────────────────────────────────────────────┐
 │                  Adapter / Client Layer                     │
 │  adapter.py: isolates upstream library private details      │
 │  session.py: dual-backend auth (keyring + file)             │
 └─────────────────────────────────────────────────────────────┘
                               │
                               ▼
+┌─────────────────────────────────────────────────────────────┐
+│                 Transformers (stable schemas)               │
+│  transformers/*.py: raw API response → CLI output schemas   │
+└─────────────────────────────────────────────────────────────┘
+                              │
+                              ▼
 ┌─────────────────────────────────────────────────────────────┐
 │                 MonarchMoney Community Library              │
 │  43 async methods, GraphQL client for Monarch Money API     │
 └─────────────────────────────────────────────────────────────┘
 ```
@@
-2. **Service Layer**: Business logic (transforms, retries, error mapping) lives in `services/*.py`, not in command handlers. Commands stay thin.
+2. **Services (optional)**: Introduce `services/*.py` only when a command needs real business logic
+   (batching, concurrency control, multi-call workflows). For simple pass-through commands, calling
+   adapter + transformer directly keeps the wrapper thinner.
```

---

# 8) Remove `httpx` dependency + defer “retry module” until you observe real exception types from upstream

### Why this makes the project better
- The plan adds `httpx` “for retry/timeout handling”, but your sample code doesn’t use it.
- `monarchmoneycommunity` likely uses its own transport stack (GraphQL client). Retrying correctly depends on
  **actual exception classes** coming from that stack.
- Premature retries often cause:
  - catching the wrong exceptions
  - masking auth errors
  - retrying non-idempotent operations later (if expanded)

A better plan:
- Keep retries **as a later hardening task** once you’ve seen real failure modes in live tests.
- For MVP, rely on upstream errors + good error reporting.

### Diff
```diff
diff --git a/plans/monarch-cli-implementation-plan.md b/plans/monarch-cli-implementation-plan.md
--- a/plans/monarch-cli-implementation-plan.md
+++ b/plans/monarch-cli-implementation-plan.md
@@
 dependencies = [
     "typer[all]>=0.9.0",
     "monarchmoneycommunity>=1.0.0",
     "keyring>=24.0.0",
-    "rich>=13.0.0",
     "platformdirs>=4.0.0",
-    "tomli>=2.0.0;python_version<'3.11'",
     "tomli-w>=1.0.0",
-    "httpx>=0.27.0",  # For retry/timeout handling
     "jmespath>=1.0.0",  # For --query support
 ]
@@
-### 1.6 Retry Logic
+### 1.6 (Defer) Retry Logic
@@
-```python
-# src/monarch_cli/core/retry.py
-"""Retry logic with exponential backoff."""
-...
-```
+Defer implementing retries until after initial live testing reveals the real exception types thrown
+by `monarchmoneycommunity`’s transport stack. Start with strong error reporting; add retries later
+as a hardening step once you can target the right failures.
```

---

## Net effect of these revisions

If you adopt the changes above, you’ll have:

- A **smaller MVP** with fewer modules and fewer code paths
- **Better agent ergonomics** immediately (`MONARCH_TOKEN`, stderr errors)
- Less duplication (single output module)
- Reduced security/support risk (no pickle compat)
- Less premature “framework” (config + retry deferred until warranted)

If you want, I can also propose a **revised phase breakdown** (re-numbered phases) that reflects these deferrals cleanly while keeping your overall intent and command set intact.
