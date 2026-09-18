"""Unit tests for account transformer."""

import pytest

from monarch_cli.core.exceptions import APIError
from monarch_cli.transformers.accounts import transform_account, transform_accounts

# Sample raw API response data
SAMPLE_ACCOUNT_FULL = {
    "id": "acc-123",
    "displayName": "Primary Checking",
    "type": {"display": "Checking"},
    "subtype": {"display": "Personal"},
    "currentBalance": 1234.56,
    "institution": {"name": "Big Bank"},
    "isHidden": False,
    "isManual": False,
    "updatedAt": "2024-01-15T10:30:00Z",
}

SAMPLE_ACCOUNT_MINIMAL = {
    "id": "acc-456",
}

SAMPLE_ACCOUNT_HIDDEN = {
    "id": "acc-789",
    "displayName": "Old Savings",
    "isHidden": True,
}


class TestTransformAccount:
    """Tests for transform_account function."""

    def test_extracts_id(self):
        result = transform_account(SAMPLE_ACCOUNT_FULL)
        assert result["id"] == "acc-123"

    def test_name_from_display_name(self):
        result = transform_account(SAMPLE_ACCOUNT_FULL)
        assert result["name"] == "Primary Checking"

    def test_type_from_nested_display(self):
        result = transform_account(SAMPLE_ACCOUNT_FULL)
        assert result["type"] == "Checking"

    def test_subtype_from_nested_display(self):
        result = transform_account(SAMPLE_ACCOUNT_FULL)
        assert result["subtype"] == "Personal"

    def test_balance_from_current_balance(self):
        result = transform_account(SAMPLE_ACCOUNT_FULL)
        assert result["balance"] == 1234.56

    def test_institution_from_nested_name(self):
        result = transform_account(SAMPLE_ACCOUNT_FULL)
        assert result["institution"] == "Big Bank"

    def test_is_active_inverts_is_hidden_false(self):
        result = transform_account(SAMPLE_ACCOUNT_FULL)
        assert result["is_active"] is True

    def test_is_active_inverts_is_hidden_true(self):
        result = transform_account(SAMPLE_ACCOUNT_HIDDEN)
        assert result["is_active"] is False

    def test_is_manual_extracted(self):
        result = transform_account(SAMPLE_ACCOUNT_FULL)
        assert result["is_manual"] is False

    def test_manual_account_is_manual_true(self):
        """A manually tracked account reports is_manual True."""
        result = transform_account({"id": "acc-manual", "isManual": True})
        assert result["is_manual"] is True
        assert isinstance(result["is_manual"], bool)

    def test_last_updated_from_updated_at(self):
        result = transform_account(SAMPLE_ACCOUNT_FULL)
        assert result["last_updated"] == "2024-01-15T10:30:00Z"

    def test_handles_minimal_data(self):
        """Missing nested fields should not raise errors."""
        result = transform_account(SAMPLE_ACCOUNT_MINIMAL)
        assert result["id"] == "acc-456"
        assert result["name"] is None
        assert result["type"] is None
        assert result["subtype"] is None
        assert result["balance"] is None
        assert result["institution"] is None
        assert result["is_active"] is True  # default: not hidden
        assert result["is_manual"] is False  # default
        assert result["last_updated"] is None

    def test_handles_empty_dict(self):
        """Empty input should not raise errors."""
        result = transform_account({})
        assert result["id"] is None
        assert result["is_active"] is True

    def test_handles_present_but_null_nested_relationships(self):
        """Present-but-null nested objects must not raise."""
        raw = {
            "id": "acc-null",
            "displayName": "Null Nested",
            "type": None,
            "subtype": None,
            "institution": None,
        }
        result = transform_account(raw)
        assert result["type"] is None
        assert result["subtype"] is None
        assert result["institution"] is None

    def test_present_but_null_scalar_values_become_none(self):
        """A present key whose value is null normalizes to null."""
        raw = {
            "id": "acc-null-scalar",
            "displayName": None,
            "currentBalance": None,
            "updatedAt": None,
        }
        result = transform_account(raw)
        assert result["name"] is None
        assert result["balance"] is None
        assert result["last_updated"] is None

    def test_is_manual_null_defaults_false(self):
        """Present-but-null isManual is a real bool (False)."""
        result = transform_account({"id": "acc-manual-null", "isManual": None})
        assert result["is_manual"] is False
        assert isinstance(result["is_manual"], bool)

    def test_is_hidden_null_defaults_active(self):
        """Present-but-null isHidden means not hidden -> active True."""
        result = transform_account({"id": "acc-hidden-null", "isHidden": None})
        assert result["is_active"] is True
        assert isinstance(result["is_active"], bool)

    def test_ignores_unknown_additive_fields(self):
        """Unknown upstream fields are dropped from normalized output."""
        raw = {**SAMPLE_ACCOUNT_FULL, "futureField": {"nested": 1}}
        result = transform_account(raw)
        assert "futureField" not in result
        assert set(result.keys()) == set(transform_account(SAMPLE_ACCOUNT_FULL).keys())

    def test_non_object_root_raises_typed_error(self):
        """A malformed (non-object) account payload fails deliberately."""
        with pytest.raises(APIError):
            transform_account(None)  # type: ignore[arg-type]
        with pytest.raises(APIError):
            transform_account(["not", "an", "object"])  # type: ignore[arg-type]

    def test_all_fields_snake_case(self):
        """All field names should be snake_case."""
        result = transform_account(SAMPLE_ACCOUNT_FULL)
        for key in result:
            assert key == key.lower(), f"Field {key} is not lowercase"
            assert " " not in key, f"Field {key} contains space"
            # camelCase check
            assert key == key.replace("A", "_a").replace("B", "_b"), f"Field {key} may be camelCase"


class TestTransformAccounts:
    """Tests for transform_accounts function."""

    def test_processes_accounts_list(self):
        raw = {"accounts": [SAMPLE_ACCOUNT_FULL, SAMPLE_ACCOUNT_MINIMAL]}
        result = transform_accounts(raw)
        assert len(result) == 2
        assert result[0]["id"] == "acc-123"
        assert result[1]["id"] == "acc-456"

    def test_handles_empty_accounts(self):
        raw = {"accounts": []}
        result = transform_accounts(raw)
        assert result == []

    def test_handles_missing_accounts_key(self):
        raw = {}
        result = transform_accounts(raw)
        assert result == []

    def test_handles_none_accounts(self):
        """None accounts value should return empty list."""
        raw = {"accounts": None}
        result = transform_accounts(raw)
        assert result == []

    def test_non_list_accounts_container_normalizes_empty(self):
        """A non-list accounts container is treated as no data, not a crash."""
        assert transform_accounts({"accounts": {"unexpected": "object"}}) == []

    def test_non_object_root_raises_typed_error(self):
        """Malformed collection roots produce a stable typed error."""
        with pytest.raises(APIError):
            transform_accounts(None)  # type: ignore[arg-type]
        with pytest.raises(APIError):
            transform_accounts(["not", "an", "object"])  # type: ignore[arg-type]


class TestSchemaContract:
    """Tests ensuring schema stability for AI agents."""

    REQUIRED_FIELDS = {
        "id",
        "name",
        "type",
        "subtype",
        "balance",
        "institution",
        "is_active",
        "is_manual",
        "last_updated",
    }

    def test_all_required_fields_present(self):
        """Transformed output must have all documented fields."""
        result = transform_account(SAMPLE_ACCOUNT_FULL)
        assert set(result.keys()) == self.REQUIRED_FIELDS

    def test_no_extra_fields(self):
        """No undocumented fields should be added."""
        result = transform_account(SAMPLE_ACCOUNT_FULL)
        extra = set(result.keys()) - self.REQUIRED_FIELDS
        assert extra == set(), f"Unexpected fields: {extra}"
