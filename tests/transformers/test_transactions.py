"""Unit tests for transaction transformer."""

import pytest

from monarch_cli.core.exceptions import APIError, NotFoundError
from monarch_cli.transformers.transactions import (
    transform_transaction,
    transform_transaction_detail,
    transform_transactions,
)

# Sample raw API response data (real upstream shape: pending, not isPending)
SAMPLE_TRANSACTION_FULL = {
    "id": "txn-123",
    "date": "2024-01-15",
    "amount": -50.00,
    "merchant": {"name": "Coffee Shop"},
    "plaidName": "COFFEE SHOP #123",
    "category": {"id": "cat-1", "name": "Food & Drink"},
    "account": {"id": "acc-1", "displayName": "Primary Checking"},
    "pending": False,
    "needsReview": True,
    "reviewStatus": "REVIEWED",
    "notes": "Morning coffee",
}

SAMPLE_TRANSACTION_NO_MERCHANT = {
    "id": "txn-456",
    "date": "2024-01-16",
    "amount": -25.00,
    "plaidName": "TRANSFER TO SAVINGS",
    "category": {"id": "cat-2", "name": "Transfer"},
    "account": {"id": "acc-2", "displayName": "Savings"},
    "pending": True,
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

    def test_preserves_list_review_state_independently(self):
        result = transform_transaction(SAMPLE_TRANSACTION_FULL)
        assert result["needs_review"] is True
        assert result["review_status"] == "REVIEWED"

    def test_pending_reads_real_upstream_field(self):
        """The real upstream `pending` field drives is_pending."""
        result = transform_transaction({"id": "t", "pending": True})
        assert result["is_pending"] is True

    def test_pending_false_is_not_regressed_by_missing_alias(self):
        """A present pending=False must not fall back to always-false default."""
        result = transform_transaction({"id": "t", "pending": False})
        assert result["is_pending"] is False

    def test_pending_null_defaults_false(self):
        """Present-but-null pending is a real bool (False)."""
        result = transform_transaction({"id": "t", "pending": None})
        assert result["is_pending"] is False
        assert isinstance(result["is_pending"], bool)

    def test_ispending_alias_is_ignored(self):
        """`isPending` is not a real upstream field and is not consulted."""
        assert transform_transaction({"id": "t", "isPending": True})["is_pending"] is False
        assert transform_transaction({"id": "t", "pending": True})["is_pending"] is True

    def test_present_but_null_nested_relationships(self):
        """Present-but-null merchant/category/account must not raise."""
        raw = {
            "id": "txn-null",
            "merchant": None,
            "category": None,
            "account": None,
            "plaidName": "FALLBACK",
        }
        result = transform_transaction(raw)
        assert result["category"] is None
        assert result["category_id"] is None
        assert result["account"] is None
        assert result["account_id"] is None
        assert result["description"] == "FALLBACK"

    def test_description_null_when_no_merchant_or_plaid_name(self):
        """Deterministic fallback ends at null, never an empty invented value."""
        assert transform_transaction({"id": "t"})["description"] is None
        assert transform_transaction({"id": "t", "merchant": None})["description"] is None

    def test_merchant_null_does_not_hide_plaid_name(self):
        """A null merchant object still permits the plaidName fallback."""
        raw = {"id": "t", "merchant": None, "plaidName": "PLAID NAME"}
        assert transform_transaction(raw)["description"] == "PLAID NAME"

    def test_ignores_unknown_additive_fields(self):
        """Unknown upstream fields are dropped from normalized output."""
        raw = {**SAMPLE_TRANSACTION_FULL, "futureField": {"nested": 1}}
        result = transform_transaction(raw)
        assert "futureField" not in result
        assert set(result.keys()) == set(transform_transaction(SAMPLE_TRANSACTION_FULL).keys())

    def test_non_object_root_raises_typed_error(self):
        """A malformed (non-object) transaction payload fails deliberately."""
        with pytest.raises(APIError):
            transform_transaction(None)  # type: ignore[arg-type]
        with pytest.raises(APIError):
            transform_transaction(["not", "an", "object"])  # type: ignore[arg-type]

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

    def test_non_list_results_container_normalizes_empty(self):
        """A non-list results container is treated as no data, not a crash."""
        assert transform_transactions({"allTransactions": {"results": "nope"}}) == []

    def test_non_object_root_raises_typed_error(self):
        """Malformed collection roots produce a stable typed error."""
        with pytest.raises(APIError):
            transform_transactions(None)  # type: ignore[arg-type]
        with pytest.raises(APIError):
            transform_transactions(["not", "an", "object"])  # type: ignore[arg-type]


class TestTransformTransactionDetail:
    """Tests for null-safe detail normalization and state separation."""

    def test_pending_and_review_are_independent(self):
        raw = {
            "getTransaction": {
                "id": "txn-detail",
                "pending": True,
                "needsReview": False,
                "reviewStatus": "REVIEWED",
                "attachments": None,
                "tags": [],
                "splitTransactions": None,
            }
        }
        result = transform_transaction_detail(raw, requested_id="txn-detail")
        assert result["is_pending"] is True
        assert result["needs_review"] is False
        assert result["review_status"] == "REVIEWED"
        assert result["attachments"] == []
        assert result["tags"] == []
        assert result["split"]["splits"] == []

    def test_null_detail_is_not_found(self):
        with pytest.raises(NotFoundError):
            transform_transaction_detail({"getTransaction": None}, requested_id="missing")
        with pytest.raises(NotFoundError):
            transform_transaction_detail({}, requested_id="missing")

    def test_malformed_detail_is_api_error(self):
        with pytest.raises(APIError):
            transform_transaction_detail({"getTransaction": []})
        with pytest.raises(APIError):
            transform_transaction_detail(None)  # type: ignore[arg-type]


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
        "needs_review",
        "review_status",
        "owner_id",
        "owner_name",
        "ownership_overridden_at",
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


class TestOwnershipNormalization:
    """Owner attribution mirrors the optional upstream ownedByUser relationship.

    A missing, null, or malformed owner relationship yields null normalized
    owner fields. Null ownership must never be relabeled as a shared or
    unassigned state. ``ownership_overridden_at`` is a literal passthrough:
    it never implies an actor, a previous owner, or a boolean shared state.
    """

    def test_complete_owner_relationship(self):
        raw = {**SAMPLE_TRANSACTION_FULL, "ownedByUser": {"id": "user-1", "name": "Alex"}}
        result = transform_transaction(raw)
        assert result["owner_id"] == "user-1"
        assert result["owner_name"] == "Alex"

    def test_missing_owner_relationship(self):
        result = transform_transaction(SAMPLE_TRANSACTION_FULL)
        assert result["owner_id"] is None
        assert result["owner_name"] is None
        assert result["ownership_overridden_at"] is None

    def test_null_owner_relationship(self):
        result = transform_transaction({**SAMPLE_TRANSACTION_FULL, "ownedByUser": None})
        assert result["owner_id"] is None
        assert result["owner_name"] is None

    @pytest.mark.parametrize(
        "malformed",
        ["not-an-object", 42, ["user-1"], True],
        ids=["string", "number", "list", "boolean"],
    )
    def test_non_object_owner_relationship_yields_nulls(self, malformed):
        result = transform_transaction({**SAMPLE_TRANSACTION_FULL, "ownedByUser": malformed})
        assert result["owner_id"] is None
        assert result["owner_name"] is None

    def test_partially_populated_owner_relationship(self):
        id_only = transform_transaction(
            {**SAMPLE_TRANSACTION_FULL, "ownedByUser": {"id": "user-1"}}
        )
        assert id_only["owner_id"] == "user-1"
        assert id_only["owner_name"] is None

        name_only = transform_transaction(
            {**SAMPLE_TRANSACTION_FULL, "ownedByUser": {"name": "Alex"}}
        )
        assert name_only["owner_id"] is None
        assert name_only["owner_name"] == "Alex"

    def test_override_timestamp_passthrough_without_derived_fields(self):
        """The override timestamp is passed through literally; nothing is derived."""
        result = transform_transaction(
            {
                **SAMPLE_TRANSACTION_FULL,
                "ownedByUser": {"id": "user-1", "name": "Alex"},
                "ownershipOverriddenAt": "2026-01-02T03:04:05Z",
            }
        )
        assert result["ownership_overridden_at"] == "2026-01-02T03:04:05Z"
        assert result["owner_id"] == "user-1"
        # No actor, previous-owner, direction, or boolean shared state exists.
        assert "overridden_by" not in result
        assert "previous_owner" not in result
        assert "is_shared" not in result

    def test_detail_owner_fields_mirror_list_contract(self):
        """Detail normalization uses the same owner fields as list normalization."""
        detail = {
            "getTransaction": {
                "id": "txn-123",
                "ownedByUser": {"id": "user-1", "name": "Alex"},
                "ownershipOverriddenAt": "2026-01-02T03:04:05Z",
            }
        }
        result = transform_transaction_detail(detail, requested_id="txn-123")
        assert result["owner_id"] == "user-1"
        assert result["owner_name"] == "Alex"
        assert result["ownership_overridden_at"] == "2026-01-02T03:04:05Z"

    def test_detail_malformed_owner_relationship_yields_nulls(self):
        for owned_by in (None, "not-an-object", ["user-1"], {}):
            detail = {"getTransaction": {"id": "txn-123", "ownedByUser": owned_by}}
            result = transform_transaction_detail(detail, requested_id="txn-123")
            assert result["owner_id"] is None
            assert result["owner_name"] is None
            assert result["ownership_overridden_at"] is None
