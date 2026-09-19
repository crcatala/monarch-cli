"""
API Schema Contract Tests for AI Agents
=======================================

⚠️  IMPORTANT: BREAKING THESE TESTS = BREAKING CHANGE FOR AI AGENTS ⚠️

This module defines the guaranteed output schema contracts that AI agents
(Claude, GPT, etc.) can rely on when integrating with monarch-cli.

Why This Matters
----------------
AI agents parse the JSON output from monarch-cli commands to understand
financial data. They build prompts, make decisions, and take actions based
on specific field names and data types. If we change these schemas without
warning, agents will break silently or produce incorrect results.

Contract Guarantees
-------------------
For each entity type, we guarantee:

1. **Field Presence**: Listed fields will ALWAYS be present in output
2. **Field Names**: Names use snake_case and will not change
3. **Field Types**: Types (str, float, bool, None) are stable
4. **Null Safety**: Fields may be None but will never be missing

Adding new fields is safe (non-breaking).
Removing or renaming fields is BREAKING.

Schema Versions
---------------
- v1 (0.1.0): Initial schema, documented below

To upgrade schemas with breaking changes:
1. Bump major version (e.g., 1.0.0 → 2.0.0)
2. Document migration in CHANGELOG
3. Consider --schema-version flag for compatibility

"""

import pytest

from monarch_cli.transformers.accounts import transform_account, transform_accounts
from monarch_cli.transformers.transactions import (
    transform_transaction,
    transform_transactions,
)

# =============================================================================
# TEST DATA
# =============================================================================

# Realistic API response structures
FULL_ACCOUNT_RAW = {
    "id": "acc-123456",
    "displayName": "Primary Checking",
    "type": {"display": "Checking"},
    "subtype": {"display": "Personal"},
    "currentBalance": 5432.10,
    "institution": {"name": "Example Bank"},
    "isHidden": False,
    "isManual": False,
    "updatedAt": "2024-01-15T10:30:00Z",
}

FULL_TRANSACTION_RAW = {
    "id": "txn-789012",
    "date": "2024-01-15",
    "amount": -42.50,
    "merchant": {"name": "Coffee Shop"},
    "plaidName": "COFFEE SHOP #123",
    "category": {"id": "cat-food", "name": "Food & Drink"},
    "account": {"id": "acc-123456", "displayName": "Primary Checking"},
    "pending": False,
    "notes": "Team lunch",
}


# =============================================================================
# ACCOUNT SCHEMA CONTRACT
# =============================================================================


class TestAccountSchemaContract:
    """
    Account Schema Contract v1
    --------------------------

    AI agents can rely on these fields being present in all account output:

    REQUIRED CORE FIELDS (agents should expect these):
    - id: str | None - Unique account identifier
    - name: str | None - Human-readable account name
    - balance: float | None - Current balance in account currency
    - type: str | None - Account type (e.g., "Checking", "Savings", "Credit Card")
    - is_active: bool - Whether account is active (True) or hidden (False)

    ADDITIONAL STABLE FIELDS (also guaranteed):
    - subtype: str | None - Account subtype if available
    - institution: str | None - Financial institution name
    - is_manual: bool - Whether manually tracked (True) or linked (False)
    - owner_id: str | None - Upstream ownedByUser.id when provided, else None
    - owner_name: str | None - Upstream ownedByUser.displayName when provided
    - last_updated: str | None - ISO timestamp of last sync

    Example output:
    ```json
    {
      "id": "acc-123456",
      "name": "Primary Checking",
      "balance": 5432.10,
      "type": "Checking",
      "is_active": true,
      "subtype": "Personal",
      "institution": "Example Bank",
      "is_manual": false,
      "last_updated": "2024-01-15T10:30:00Z"
    }
    ```
    """

    # The core fields that AI agents absolutely depend on
    CORE_REQUIRED_FIELDS = {"id", "name", "balance", "type", "is_active"}

    # All fields in the account schema (core + additional)
    ALL_SCHEMA_FIELDS = {
        "id",
        "name",
        "balance",
        "type",
        "is_active",
        "subtype",
        "institution",
        "is_manual",
        "owner_id",
        "owner_name",
        "last_updated",
    }

    def test_core_fields_present(self):
        """
        CRITICAL: Core fields must always be present.

        These are the minimum fields an AI agent needs to understand accounts.
        Breaking this test means agents will crash or produce wrong results.
        """
        result = transform_account(FULL_ACCOUNT_RAW)

        for field in self.CORE_REQUIRED_FIELDS:
            assert field in result, f"Missing core field: {field}"

    def test_all_schema_fields_present(self):
        """All documented schema fields must be present."""
        result = transform_account(FULL_ACCOUNT_RAW)

        for field in self.ALL_SCHEMA_FIELDS:
            assert field in result, f"Missing schema field: {field}"

    def test_no_undocumented_fields(self):
        """
        No undocumented fields should appear.

        Adding new fields requires:
        1. Add to ALL_SCHEMA_FIELDS set
        2. Document in class docstring
        3. Note in CHANGELOG
        """
        result = transform_account(FULL_ACCOUNT_RAW)
        actual_fields = set(result.keys())
        extra_fields = actual_fields - self.ALL_SCHEMA_FIELDS

        assert extra_fields == set(), (
            f"Undocumented fields found: {extra_fields}. "
            "Add to ALL_SCHEMA_FIELDS and document in docstring."
        )

    def test_field_types_stable(self):
        """Field types must remain stable."""
        result = transform_account(FULL_ACCOUNT_RAW)

        # String or None fields
        assert result["id"] is None or isinstance(result["id"], str)
        assert result["name"] is None or isinstance(result["name"], str)
        assert result["type"] is None or isinstance(result["type"], str)
        assert result["subtype"] is None or isinstance(result["subtype"], str)
        assert result["institution"] is None or isinstance(result["institution"], str)
        assert result["last_updated"] is None or isinstance(result["last_updated"], str)

        # Numeric or None fields
        assert result["balance"] is None or isinstance(result["balance"], (int, float))

        # Boolean fields (never None)
        assert isinstance(result["is_active"], bool)
        assert isinstance(result["is_manual"], bool)

    def test_snake_case_field_names(self):
        """All field names must be snake_case for consistency."""
        result = transform_account(FULL_ACCOUNT_RAW)

        for field_name in result:
            # No spaces
            assert " " not in field_name, f"Field '{field_name}' contains space"
            # Lowercase
            assert field_name == field_name.lower(), f"Field '{field_name}' not lowercase"
            # No camelCase (no lowercase followed by uppercase)
            assert field_name.islower() or "_" in field_name, (
                f"Field '{field_name}' may be camelCase"
            )

    def test_handles_minimal_input_gracefully(self):
        """Schema works even with minimal API data (no crashes, predictable None values)."""
        minimal_raw = {"id": "acc-minimal"}
        result = transform_account(minimal_raw)

        # Core fields present
        for field in self.CORE_REQUIRED_FIELDS:
            assert field in result

        # None values for missing data (not KeyError)
        assert result["name"] is None
        assert result["balance"] is None
        assert result["type"] is None

    def test_boolean_fields_never_none_for_absent_or_null(self):
        """is_active/is_manual stay real bools when their sources are absent/null."""
        absent = transform_account({"id": "acc"})
        assert absent["is_active"] is True
        assert absent["is_manual"] is False
        nulled = transform_account({"id": "acc", "isHidden": None, "isManual": None})
        assert nulled["is_active"] is True
        assert nulled["is_manual"] is False

    def test_owner_fields_nullable_and_null_safe(self):
        """Owner fields exist for every shape and stay null without an owner object."""
        complete = transform_account(
            {**FULL_ACCOUNT_RAW, "ownedByUser": {"id": "user-1", "displayName": "Alex"}}
        )
        assert complete["owner_id"] == "user-1"
        assert complete["owner_name"] == "Alex"

        for raw in (
            FULL_ACCOUNT_RAW,
            {**FULL_ACCOUNT_RAW, "ownedByUser": None},
            {**FULL_ACCOUNT_RAW, "ownedByUser": "not-an-object"},
            {**FULL_ACCOUNT_RAW, "ownedByUser": {}},
            {**FULL_ACCOUNT_RAW, "ownedByUser": {"id": "user-1"}},
            {**FULL_ACCOUNT_RAW, "ownedByUser": {"displayName": "Alex"}},
        ):
            result = transform_account(raw)
            assert "owner_id" in result and "owner_name" in result
            assert result["owner_id"] is None or isinstance(result["owner_id"], str)
            assert result["owner_name"] is None or isinstance(result["owner_name"], str)

    def test_malformed_root_raises_typed_error(self):
        """Non-object account/transaction roots raise a typed APIError."""
        from monarch_cli.core.exceptions import APIError

        with pytest.raises(APIError):
            transform_accounts(None)  # type: ignore[arg-type]
        with pytest.raises(APIError):
            transform_transactions(None)  # type: ignore[arg-type]


# =============================================================================
# TRANSACTION SCHEMA CONTRACT
# =============================================================================


class TestTransactionSchemaContract:
    """
    Transaction Schema Contract v1
    ------------------------------

    AI agents can rely on these fields being present in all transaction output:

    REQUIRED CORE FIELDS (agents should expect these):
    - id: str | None - Unique transaction identifier
    - date: str | None - Transaction date (YYYY-MM-DD format)
    - amount: float | None - Transaction amount (negative = expense, positive = income)
    - description: str | None - Merchant name or transaction description
    - category: str | None - Category name for the transaction

    ADDITIONAL STABLE FIELDS (also guaranteed):
    - category_id: str | None - Category ID for programmatic use
    - account: str | None - Account name this transaction belongs to
    - account_id: str | None - Account ID for programmatic use
    - is_pending: bool - Whether transaction is pending (True) or posted (False)
    - needs_review: bool - Whether the transaction needs review
    - review_status: str | None - Opaque upstream review status when supplied
    - owner_id: str | None - Upstream ownedByUser.id when provided, else None
    - owner_name: str | None - Upstream ownedByUser.name when provided
    - ownership_overridden_at: str | None - Literal upstream override timestamp
      when provided; never implies an actor, previous owner, or shared state
    - notes: str | None - User-added notes

    Example output:
    ```json
    {
      "id": "txn-789012",
      "date": "2024-01-15",
      "amount": -42.50,
      "description": "Coffee Shop",
      "category": "Food & Drink",
      "category_id": "cat-food",
      "account": "Primary Checking",
      "account_id": "acc-123456",
      "is_pending": false,
      "needs_review": false,
      "review_status": null,
      "notes": "Team lunch"
    }
    ```

    Amount Sign Convention:
    - Negative amounts (-) = money leaving account (expenses, transfers out)
    - Positive amounts (+) = money entering account (income, transfers in)
    """

    # The core fields that AI agents absolutely depend on
    CORE_REQUIRED_FIELDS = {"id", "date", "amount", "description", "category"}

    # All fields in the transaction schema (core + additional)
    ALL_SCHEMA_FIELDS = {
        "id",
        "date",
        "amount",
        "description",
        "category",
        "category_id",
        "account",
        "account_id",
        "is_pending",
        "needs_review",
        "review_status",
        "owner_id",
        "owner_name",
        "ownership_overridden_at",
        "notes",
    }

    def test_core_fields_present(self):
        """
        CRITICAL: Core fields must always be present.

        These are the minimum fields an AI agent needs to understand transactions.
        Breaking this test means agents will crash or produce wrong results.
        """
        result = transform_transaction(FULL_TRANSACTION_RAW)

        for field in self.CORE_REQUIRED_FIELDS:
            assert field in result, f"Missing core field: {field}"

    def test_all_schema_fields_present(self):
        """All documented schema fields must be present."""
        result = transform_transaction(FULL_TRANSACTION_RAW)

        for field in self.ALL_SCHEMA_FIELDS:
            assert field in result, f"Missing schema field: {field}"

    def test_no_undocumented_fields(self):
        """
        No undocumented fields should appear.

        Adding new fields requires:
        1. Add to ALL_SCHEMA_FIELDS set
        2. Document in class docstring
        3. Note in CHANGELOG
        """
        result = transform_transaction(FULL_TRANSACTION_RAW)
        actual_fields = set(result.keys())
        extra_fields = actual_fields - self.ALL_SCHEMA_FIELDS

        assert extra_fields == set(), (
            f"Undocumented fields found: {extra_fields}. "
            "Add to ALL_SCHEMA_FIELDS and document in docstring."
        )

    def test_field_types_stable(self):
        """Field types must remain stable."""
        result = transform_transaction(FULL_TRANSACTION_RAW)

        # String or None fields
        assert result["id"] is None or isinstance(result["id"], str)
        assert result["date"] is None or isinstance(result["date"], str)
        assert result["description"] is None or isinstance(result["description"], str)
        assert result["category"] is None or isinstance(result["category"], str)
        assert result["category_id"] is None or isinstance(result["category_id"], str)
        assert result["account"] is None or isinstance(result["account"], str)
        assert result["account_id"] is None or isinstance(result["account_id"], str)
        assert result["notes"] is None or isinstance(result["notes"], str)

        # Numeric or None fields
        assert result["amount"] is None or isinstance(result["amount"], (int, float))

        # Boolean fields (never None)
        assert isinstance(result["is_pending"], bool)
        assert isinstance(result["needs_review"], bool)
        assert result["review_status"] is None or isinstance(result["review_status"], str)

    def test_snake_case_field_names(self):
        """All field names must be snake_case for consistency."""
        result = transform_transaction(FULL_TRANSACTION_RAW)

        for field_name in result:
            assert " " not in field_name, f"Field '{field_name}' contains space"
            assert field_name == field_name.lower(), f"Field '{field_name}' not lowercase"
            assert field_name.islower() or "_" in field_name, (
                f"Field '{field_name}' may be camelCase"
            )

    def test_handles_minimal_input_gracefully(self):
        """Schema works even with minimal API data (no crashes, predictable None values)."""
        minimal_raw = {"id": "txn-minimal"}
        result = transform_transaction(minimal_raw)

        # Core fields present
        for field in self.CORE_REQUIRED_FIELDS:
            assert field in result

        # None values for missing data (not KeyError)
        assert result["date"] is None
        assert result["amount"] is None
        assert result["description"] is None
        assert result["category"] is None

    def test_boolean_fields_never_none_for_absent_or_null(self):
        """is_pending stays a real bool when pending is absent or null."""
        assert transform_transaction({"id": "t"})["is_pending"] is False
        assert transform_transaction({"id": "t", "pending": None})["is_pending"] is False

    def test_owner_fields_nullable_and_null_safe(self):
        """Owner fields exist for every shape and stay null without an owner object."""
        complete = transform_transaction(
            {**FULL_TRANSACTION_RAW, "ownedByUser": {"id": "user-1", "name": "Alex"}}
        )
        assert complete["owner_id"] == "user-1"
        assert complete["owner_name"] == "Alex"

        for raw in (
            FULL_TRANSACTION_RAW,
            {**FULL_TRANSACTION_RAW, "ownedByUser": None},
            {**FULL_TRANSACTION_RAW, "ownedByUser": "not-an-object"},
            {**FULL_TRANSACTION_RAW, "ownedByUser": {}},
        ):
            result = transform_transaction(raw)
            assert result["owner_id"] is None
            assert result["owner_name"] is None

    def test_ownership_overridden_at_is_literal_passthrough(self):
        """The override timestamp passes through literally; nothing is derived."""
        assert (
            transform_transaction(
                {**FULL_TRANSACTION_RAW, "ownershipOverriddenAt": "2026-01-02T03:04:05Z"}
            )["ownership_overridden_at"]
            == "2026-01-02T03:04:05Z"
        )
        result = transform_transaction(FULL_TRANSACTION_RAW)
        assert result["ownership_overridden_at"] is None
        assert "is_shared" not in result
        assert "previous_owner" not in result
        assert "overridden_by" not in result

    def test_pending_reads_real_upstream_field(self):
        """Contract reads upstream `pending`, not a fabricated always-false default."""
        assert transform_transaction({"id": "t", "pending": True})["is_pending"] is True

    def test_date_format_consistent(self):
        """Date field uses ISO format YYYY-MM-DD when present."""
        result = transform_transaction(FULL_TRANSACTION_RAW)

        if result["date"] is not None:
            # Should match YYYY-MM-DD pattern
            import re

            assert re.match(r"^\d{4}-\d{2}-\d{2}$", result["date"]), (
                f"Date '{result['date']}' doesn't match YYYY-MM-DD format"
            )


# =============================================================================
# COLLECTION SCHEMA CONTRACT
# =============================================================================


class TestCollectionSchemaContract:
    """
    Collection Output Contract
    --------------------------

    When returning lists of entities (accounts, transactions), the output
    is a JSON array where each element follows the individual schema.

    Guarantees:
    - Empty results return [] (empty array), never None or error
    - Each element in array follows its entity schema exactly
    - Order may vary (don't depend on sort order without explicit --sort flag)
    """

    def test_accounts_returns_list(self):
        """transform_accounts must return a list."""
        raw = {"accounts": [FULL_ACCOUNT_RAW]}
        result = transform_accounts(raw)

        assert isinstance(result, list)

    def test_accounts_empty_returns_empty_list(self):
        """Empty accounts returns [], not None."""
        result = transform_accounts({"accounts": []})
        assert result == []

        result = transform_accounts({})
        assert result == []

    def test_transactions_returns_list(self):
        """transform_transactions must return a list."""
        raw = {"allTransactions": {"results": [FULL_TRANSACTION_RAW]}}
        result = transform_transactions(raw)

        assert isinstance(result, list)

    def test_transactions_empty_returns_empty_list(self):
        """Empty transactions returns [], not None."""
        result = transform_transactions({"allTransactions": {"results": []}})
        assert result == []

        result = transform_transactions({})
        assert result == []


# =============================================================================
# DOCUMENTATION
# =============================================================================


class TestSchemaDocumentation:
    """
    Meta-tests ensuring schema documentation stays in sync.

    These tests verify the test module itself is properly documented.
    """

    def test_account_docstring_lists_all_fields(self):
        """Account contract docstring must mention all schema fields."""
        docstring = TestAccountSchemaContract.__doc__

        for field in TestAccountSchemaContract.ALL_SCHEMA_FIELDS:
            assert field in docstring, f"Field '{field}' not documented in Account docstring"

    def test_transaction_docstring_lists_all_fields(self):
        """Transaction contract docstring must mention all schema fields."""
        docstring = TestTransactionSchemaContract.__doc__

        for field in TestTransactionSchemaContract.ALL_SCHEMA_FIELDS:
            assert field in docstring, f"Field '{field}' not documented in Transaction docstring"
