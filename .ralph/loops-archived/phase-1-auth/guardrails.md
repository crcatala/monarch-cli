# Phase 1 Auth Guardrails

## UX Requirements

1. **Immediate feedback**: Print something within 100ms, especially before network calls

2. **Clear prompts**: Use Rich console for styled output
   ```python
   console.print("[bold]Monarch Money Login[/bold]")
   ```

3. **Password security**: Always use `getpass.getpass()` for password input

4. **Success indicators**: Use green checkmarks ✓ for success
   ```python
   console.print("[green]✓ Logged in successfully[/green]")
   ```

## Error Handling

All commands (except login, setup) must use `@handle_errors`:
```python
@app.command()
@handle_errors
def status(...):
    ...
```

Login has special error handling for RequireMFAException - don't use the decorator there.

## Testing Auth

After implementing, manually test:
```bash
# Should prompt for credentials
uv run monarch auth login

# Should show status
uv run monarch auth status

# Should test API
uv run monarch auth ping

# Should show diagnostics  
uv run monarch auth doctor
```

## Dependencies

This loop depends on phase-1-core being complete:
- exceptions.py (AuthenticationError)
- session.py (save/get/delete token functions)
- adapter.py (get_authenticated_client)
- async_utils.py (run_async)

## Reference

- Implementation: `plans/monarch-cli-implementation-plan.md` (Auth Commands section)
- Tickets: `.tickets/mc-3eba.md`, `.tickets/mc-e3e1.md`, `.tickets/mc-5655.md`, `.tickets/mc-73e3.md`
