# Phase 1 Auth: Progress Log

This file tracks completed work and patterns learned during this loop.

---

## Completed Tasks

## [2026-01-18 09:41] - mc-3eba: Minimal Output Helpers (Bootstrap)
- Implemented bootstrap output module for Phase 1 auth commands
- OutputFormat enum with JSON, TABLE, CSV, COMPACT (only JSON/COMPACT implemented now)
- output() function outputs JSON to stdout (indented or compact)
- output_error() outputs MonarchCLIError to stderr as JSON
- set_verbose()/is_verbose() for verbose flag tracking
- Rich console available on stderr for styled interactive output
- Fixed pre-existing formatting issue in session.py
- Files changed: `src/monarch_cli/output/__init__.py`, `src/monarch_cli/core/session.py`
- **Learnings:** Console uses stderr to keep stdout clean for data output
---

## [2026-01-18 09:43] - mc-e3e1: Error Handler Decorator
- Created @handle_errors decorator for consistent CLI error handling
- Catches KeyboardInterrupt, prints "Interrupted." to stderr, exits 130
- Catches MonarchCLIError, outputs via output_error(), exits with error's exit_code
- Catches unexpected Exception, wraps in MonarchCLIError, exits 1
- Shows full traceback when is_verbose() is True
- Uses typer.Exit() for testability with CliRunner
- Preserves function signature with functools.wraps
- Files changed: `src/monarch_cli/core/error_handler.py`
- **Learnings:** Ruff UP047 (new-style type params) conflicts with mypy for Callable+ParamSpec - use noqa: UP047 for decorator signatures
---

## [2026-01-18 09:45] - mc-5655: Main Entry Point (Auth Only)
- Updated main.py to import and register auth command group
- Created stub auth.py with placeholder commands (login, status, logout, doctor, ping, setup)
- Auth app is a sub-Typer with no_args_is_help=True
- `monarch --help` shows auth subcommand
- `monarch auth --help` shows all 6 auth commands  
- `monarch --version` shows "monarch-cli 0.1.0"
- Files changed: `src/monarch_cli/main.py`, `src/monarch_cli/commands/auth.py`
- **Learnings:** Typer sub-apps are registered with app.add_typer(sub_app, name='subcommand')
---

## [2026-01-18 09:46] - mc-73e3: Auth Commands Implementation
- Implemented all 6 auth commands with full functionality
- `login`: Prompts for email/password with getpass, handles MFA, saves to chosen backend, shows account count
- `status`: Returns JSON with authenticated, storage_backend, message fields
- `logout`: Clears tokens from all or specific backend, resets cached client
- `doctor`: Checks keyring availability, shows all token storage locations, tests API if authenticated
- `ping`: Tests API connectivity, returns {status: "ok", message: ...}
- `setup`: Shows formatted setup instructions with examples
- Added helper functions: _is_keyring_available(), _get_keyring_backend_name(), _prompt_storage_backend()
- Files changed: `src/monarch_cli/commands/auth.py`
- **Learnings:** Check keyring backend with `"fail" not in type(backend).__module__` to detect unavailable keyring
---

## Patterns & Decisions

### Keyring Availability Check
```python
def _is_keyring_available() -> bool:
    backend = keyring.get_keyring()
    return "fail" not in type(backend).__module__
```
The `keyring.backends.fail.Keyring` is the fallback when no real backend works.

## Issues Encountered

(recorded as tasks complete)

## Post-Loop Checkpoint

After this loop completes, authenticate:
```bash
monarch auth login
```

This enables live testing for all subsequent phases.
