"""Unit tests for transaction transformer."""

from monarch_cli.transformers.transactions import (
    transform_transaction,
    transform_transactions,
)

# Sample raw API response data
SAMPLE_TRANSACTION_FULL = {
    "id": "txn-123",
    "date": "2024-01-15",
    "amount": -50.00,
    "merchant": {"name": "Coffee Shop"},
    "plaidName": "COFFEE SHOP #123",
    "category": {"id": "cat-1", "name": "Food & Drink"},
    "account": {"id": "acc-1", "displayName": "Primary Checking"},
    "isPending": False,
    "notes": "Morning coffee",
}

SAMPLE_TRANSACTION_NO_MERCHANT = {
    "id": "txn-456",
    "date": "2024-01-16",
    "amount": -25.00,
    "plaidName": "TRANSFER TO SAVINGS",
    "category": {"id": "cat-2", "name": "Transfer"},
    "account": {"id": "acc-2", "displayName": "Savings"},
    "isPending": True,
}

SAMPLE_TRANSACTION_MINIMAL = {
    "id": "txn-789",
}


class TestTransformTransaction:
    """Tests for transform_transaction function."""

    def test_extracts_id(self):
        result = transform_transaction(SAMPLE_TRANSACTION_FULL)
        assert result["id"] == "txn-123"

    def test_extracts_date(self):
        result = transform_transaction(SAMPLE_TRANSACTION_FULL)
        assert result["date"] == "2024-01-15"

    def test_extracts_amount(self):
        result = transform_transaction(SAMPLE_TRANSACTION_FULL)
        assert result["amount"] == -50.00

    def test_description_prefers_merchant_name(self):
        result = transform_transaction(SAMPLE_TRANSACTION_FULL)
        assert result["description"] == "Coffee Shop"

    def test_description_falls_back_to_plaid_name(self):
        result = transform_transaction(SAMPLE_TRANSACTION_NO_MERCHANT)
        assert result["description"] == "TRANSFER TO SAVINGS"

    def test_category_from_nested_name(self):
        result = transform_transaction(SAMPLE_TRANSACTION_FULL)
        assert result["category"] == "Food & Drink"

    def test_category_id_extracted(self):
        result = transform_transaction(SAMPLE_TRANSACTION_FULL)
        assert result["category_id"] == "cat-1"

    def test_account_from_display_name(self):
        result = transform_transaction(SAMPLE_TRANSACTION_FULL)
        assert result["account"] == "Primary Checking"

    def test_account_id_extracted(self):
        result = transform_transaction(SAMPLE_TRANSACTION_FULL)
        assert result["account_id"] == "acc-1"

    def test_is_pending_false(self):
        result = transform_transaction(SAMPLE_TRANSACTION_FULL)
        assert result["is_pending"] is False

    def test_is_pending_true(self):
        result = transform_transaction(SAMPLE_TRANSACTION_NO_MERCHANT)
        assert result["is_pending"] is True

    def test_notes_extracted(self):
        result = transform_transaction(SAMPLE_TRANSACTION_FULL)
        assert result["notes"] == "Morning coffee"

    def test_handles_minimal_data(self):
        """Missing nested fields should not raise errors."""
        result = transform_transaction(SAMPLE_TRANSACTION_MINIMAL)
        assert result["id"] == "txn-789"
        assert result["date"] is None
        assert result["amount"] is None
        assert result["description"] is None
        assert result["category"] is None
        assert result["category_id"] is None
        assert result["account"] is None
        assert result["account_id"] is None
        assert result["is_pending"] is False  # default
        assert result["notes"] is None

    def test_handles_null_nested_objects(self):
        """Present-but-null nested fields should not raise errors."""
        raw = {
            "id": "txn-null",
            "merchant": None,
            "plaidName": "Fallback Name",
            "category": None,
            "account": None,
        }

        result = transform_transaction(raw)

        assert result["id"] == "txn-null"
        assert result["description"] == "Fallback Name"
        assert result["category"] is None
        assert result["category_id"] is None
        assert result["account"] is None
        assert result["account_id"] is None

    def test_handles_empty_dict(self):
        """Empty input should not raise errors."""
        result = transform_transaction({})
        assert result["id"] is None
        assert result["is_pending"] is False

    def test_merchant_with_empty_name(self):
        """Empty merchant name should fall back to plaidName."""
        raw = {
            "id": "txn-empty",
            "merchant": {"name": ""},
            "plaidName": "Fallback Name",
        }
        result = transform_transaction(raw)
        assert result["description"] == "Fallback Name"

    def test_merchant_with_none_name(self):
        """None merchant name should fall back to plaidName."""
        raw = {
            "id": "txn-none",
            "merchant": {"name": None},
            "plaidName": "Fallback Name",
        }
        result = transform_transaction(raw)
        assert result["description"] == "Fallback Name"

    def test_all_fields_snake_case(self):
        """All field names should be snake_case."""
        result = transform_transaction(SAMPLE_TRANSACTION_FULL)
        for key in result:
            assert key == key.lower(), f"Field {key} is not lowercase"
            assert " " not in key, f"Field {key} contains space"


class TestTransformTransactions:
    """Tests for transform_transactions function."""

    def test_processes_results_list(self):
        raw = {
            "allTransactions": {
                "results": [SAMPLE_TRANSACTION_FULL, SAMPLE_TRANSACTION_NO_MERCHANT]
            }
        }
        result = transform_transactions(raw)
        assert len(result) == 2
        assert result[0]["id"] == "txn-123"
        assert result[1]["id"] == "txn-456"

    def test_handles_empty_results(self):
        raw = {"allTransactions": {"results": []}}
        result = transform_transactions(raw)
        assert result == []

    def test_handles_missing_all_transactions_key(self):
        raw = {}
        result = transform_transactions(raw)
        assert result == []

    def test_handles_missing_results_key(self):
        raw = {"allTransactions": {}}
        result = transform_transactions(raw)
        assert result == []

    def test_handles_none_results(self):
        """None results value should return empty list."""
        raw = {"allTransactions": {"results": None}}
        result = transform_transactions(raw)
        assert result == []

    def test_handles_none_all_transactions(self):
        """None allTransactions value should return empty list."""
        raw = {"allTransactions": None}
        result = transform_transactions(raw)
        assert result == []


class TestSchemaContract:
    """Tests ensuring schema stability for AI agents."""

    REQUIRED_FIELDS = {
        "id",
        "date",
        "amount",
        "description",
        "category",
        "category_id",
        "account",
        "account_id",
        "is_pending",
        "notes",
    }

    def test_all_required_fields_present(self):
        """Transformed output must have all documented fields."""
        result = transform_transaction(SAMPLE_TRANSACTION_FULL)
        assert set(result.keys()) == self.REQUIRED_FIELDS

    def test_no_extra_fields(self):
        """No undocumented fields should be added."""
        result = transform_transaction(SAMPLE_TRANSACTION_FULL)
        extra = set(result.keys()) - self.REQUIRED_FIELDS
        assert extra == set(), f"Unexpected fields: {extra}"
