"""Unit tests for account transformer."""

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
        # raw.get("accounts", []) returns None when key exists with None value
        # We should handle this gracefully
        raw = {"accounts": None}
        result = transform_accounts(raw)
        # Current behavior: will fail - need to fix transformer
        assert result == []


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
