---
id: mc-cd12
status: open
deps: [mc-f84a]
links: []
created: 2026-01-18T16:09:27Z
type: task
priority: 1
assignee: cc-vps
parent: mc-1568
tags: [phase-5, testing, contracts]
---
# Schema Contract Tests

Implement schema contract tests to ensure output stability for AI agents.

## Purpose
AI agents depend on consistent output schemas. Contract tests ensure we don't accidentally break the output format that agents rely on.

## Test Location
`tests/test_schemas.py`

## Implementation
```python
"""Schema contract tests for output stability.

These tests ensure that transformed output contains required fields.
Breaking these tests means a breaking change for AI agents.

Add fields carefully. Never remove fields without deprecation.
"""

from monarch_cli.transformers.accounts import transform_account
from monarch_cli.transformers.transactions import transform_transaction


class TestAccountSchema:
    """Account output schema contract."""

    def test_required_fields_present(self):
        """Account output must have these fields for agent compatibility."""
        raw = {
            "id": "ACC123",
            "displayName": "Test Account",
            "currentBalance": 1000.00,
            "type": {"display": "Checking"},
            "subtype": {"display": "Personal"},
            "institution": {"name": "Test Bank"},
            "isHidden": False,
            "isManual": False,
            "updatedAt": "2024-01-15T10:00:00Z",
        }

        result = transform_account(raw)

        # These fields MUST exist
        assert "id" in result
        assert "name" in result
        assert "type" in result
        assert "balance" in result
        assert "institution" in result
        assert "is_active" in result
        assert "is_manual" in result
        assert "last_updated" in result

    def test_field_types(self):
        """Verify field types are correct."""
        raw = {...}
        result = transform_account(raw)

        assert isinstance(result["id"], str)
        assert isinstance(result["balance"], (int, float))
        assert isinstance(result["is_active"], bool)


class TestTransactionSchema:
    """Transaction output schema contract."""

    def test_required_fields_present(self):
        raw = {
            "id": "TXN123",
            "date": "2024-01-15",
            "amount": -50.00,
            "merchant": {"name": "Coffee Shop"},
            "category": {"id": "CAT123", "name": "Food"},
            "account": {"id": "ACC123", "displayName": "Checking"},
            "pending": False,
            "notes": None,
        }

        result = transform_transaction(raw)

        # Required fields
        assert "id" in result
        assert "date" in result
        assert "amount" in result
        assert "description" in result
        assert "category" in result
        assert "category_id" in result
        assert "account" in result
        assert "account_id" in result
        assert "is_pending" in result
        assert "notes" in result


class TestErrorSchema:
    """Error output schema contract."""

    def test_error_has_required_fields(self):
        from monarch_cli.core.exceptions import MonarchCLIError, ErrorCode

        error = MonarchCLIError("Test error", ErrorCode.API_ERROR)
        d = error.to_dict()

        assert "error" in d
        assert d["error"] is True
        assert "code" in d
        assert "message" in d
```

## Why Contract Tests?
1. **Explicit API**: Documents what agents can rely on
2. **Change Detection**: Alerts us before breaking agents
3. **Documentation**: Shows expected output structure
4. **Confidence**: Safe to add features without breaking consumers

## Contract Test Rules
1. ✅ Add new optional fields (backward compatible)
2. ❌ Remove existing fields (breaking change)
3. ❌ Change field types (breaking change)
4. ⚠️ Add new required fields (semver major)

## Marking Breaking Changes
If a contract test must change, update:
1. CHANGELOG.md with breaking change note
2. Version bump (major version)
3. Migration guide in docs

## Acceptance Criteria

- [ ] Account schema contract test
- [ ] Transaction schema contract test
- [ ] Error schema contract test
- [ ] Tests verify required fields exist
- [ ] Tests verify field types
- [ ] Documentation in test file about contract rules

