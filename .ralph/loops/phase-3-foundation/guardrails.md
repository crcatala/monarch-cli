# Phase 3 Foundation Guardrails

## ⚠️ CRITICAL: No Write Operations During Testing

**The local machine has personal Monarch Money credentials. Do NOT execute any write or mutating operations against the live API.**

- ✅ Read operations (list accounts, fetch transactions) are OK for live testing
- ❌ `refresh_accounts()` - do NOT call against live API during testing
- ❌ Any operation that modifies user data

**For testing write operations:**
- Use mocks/stubs in unit tests
- Verify code logic without executing against live API
- The `--dry-run` pattern should preview changes without applying

## Transformer Rules

1. **Stable output schema**: Once a field is added, it cannot be removed without deprecation
2. **Snake_case fields**: Always use Python conventions, not camelCase from API
3. **Graceful missing data**: Use `.get()` with defaults, never raise KeyError
4. **Flat structure**: Flatten nested objects where possible

```python
# Good
"institution": raw.get("institution", {}).get("name")

# Bad - will raise KeyError if institution is missing
"institution": raw["institution"]["name"]
```

## Service Layer Guidelines

Use service layer when:
- Multi-step orchestration needed (refresh: get IDs → refresh)
- Business logic beyond simple fetch

Don't use service layer when:
- Simple fetch + transform (do it in command)
- No orchestration needed

## Config Precedence

```
CLI flags (highest)
    ↓
Environment variables
    ↓
Defaults (lowest)
```

## Testing Transformers

Transformers are pure functions - easy to unit test:
```python
def test_transform_account_extracts_name():
    raw = {"id": "123", "displayName": "Checking", ...}
    result = transform_account(raw)
    assert result["name"] == "Checking"
```

## Reference

- Tickets: `.tickets/mc-78e5.md`, `.tickets/mc-f913.md`, `.tickets/mc-4c28.md`, `.tickets/mc-7fda.md`
- Schema contract tests: Added in Phase 5
