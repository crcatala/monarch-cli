"""
API Schema Contract Tests for AI Agents
=======================================

⚠️  IMPORTANT: BREAKING THESE TESTS = BREAKING CHANGE FOR AI AGENTS ⚠️

These tests validate representative *runtime* output against the published,
checked-in JSON Schema artifacts in ``monarch_cli.schemas``. The artifacts are
the normative contract; this module does not maintain a second independent
field list. Adding, removing, or retyping a normalized field is a contract
change and is detected here.

Contract Guarantees
-------------------
- Fields declared required in the schema are ALWAYS present.
- Field names are stable snake_case and never change in place.
- Types and nullability match the schema exactly.
- No undocumented stable field may appear (schemas use
  ``additionalProperties: false``).
- Closed enums (mutation-outcome statuses) only accept documented values.
- Open sets (structured error ``code``) may grow additively.

Compatibility policy
--------------------
Optional additive properties and new open error codes are additive and may
land without a version change. Removals, required-field additions,
type/nullability changes, and closed-enum changes require a new schema
version. See ``docs/schema-contracts.md`` for the full policy.

The richer single-transaction detail shape is published separately as
``urn:monarch-cli:schema:transaction-detail:v1``.
"""

from __future__ import annotations

from typing import Any

import pytest
from jsonschema import Draft202012Validator

from monarch_cli.core.exceptions import APIError, ValidationError
from monarch_cli.core.mutation_outcomes import (
    ambiguous_item,
    build_mutation_outcome,
    failed_item,
    succeeded_item,
    verification_object,
)
from monarch_cli.schemas import (
    ATTACHMENT_ENTITY,
    ATTACHMENT_MEDIA_ENTITY,
    OPERATION_CONTRACTS,
    SCHEMA_ARTIFACTS,
    SCHEMA_ARTIFACTS_BY_URN,
    load_schema,
    operation_contract,
    schema_artifact,
    schema_artifact_by_urn,
)
from monarch_cli.transformers.accounts import transform_account, transform_accounts
from monarch_cli.transformers.transactions import (
    transform_transaction,
    transform_transaction_detail,
    transform_transactions,
)

# =============================================================================
# SCHEMA-DERIVED CONTRACT VIEWS
# =============================================================================

ACCOUNT_SCHEMA = load_schema("account")
TRANSACTION_SCHEMA = load_schema("transaction")
TRANSACTION_DETAIL_SCHEMA = load_schema("transaction-detail")
ERROR_SCHEMA = load_schema("error")
MUTATION_OUTCOME_SCHEMA = load_schema("mutation-outcome")

ACCOUNT_REQUIRED_FIELDS = set(ACCOUNT_SCHEMA["required"])
TRANSACTION_REQUIRED_FIELDS = set(TRANSACTION_SCHEMA["required"])


def _assert_valid(instance: Any, contract: str) -> dict[str, Any]:
    """Validate ``instance`` against a published artifact, or fail loudly."""
    validator = Draft202012Validator(load_schema(contract))
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
    assert not errors, f"{contract} output violates the published schema:\n" + "\n".join(
        f"- {list(e.absolute_path)}: {e.message}" for e in errors
    )
    return instance


def _assert_mutation_outcome_contract(outcome: dict[str, Any]) -> dict[str, Any]:
    """Validate the envelope and enforce its non-schema arithmetic invariants.

    JSON Schema Draft 2020-12 cannot express ``summary.total == len(items)`` or
    per-status counts matching items, so those cross-field rules are enforced
    here in addition to schema validation.
    """
    _assert_valid(outcome, "mutation-outcome")
    items = outcome["items"]
    summary = outcome["summary"]
    assert summary["total"] == len(items), "summary.total must equal len(items)"
    counts = {"succeeded": 0, "failed": 0, "ambiguous": 0}
    for item in items:
        counts[item["status"]] += 1
    for status, count in counts.items():
        assert summary[status] == count, f"summary.{status} must match items"
    return outcome


# =============================================================================
# TEST DATA
# =============================================================================

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

FULL_TRANSACTION_DETAIL_RAW = {
    "getTransaction": {
        "id": "txn-789012",
        "date": "2024-01-15",
        "amount": -42.50,
        "merchant": {"name": "Coffee Shop"},
        "category": {"id": "cat-food", "name": "Food & Drink"},
        "account": {"id": "acc-123456", "displayName": "Primary Checking"},
        "pending": False,
        "needsReview": True,
        "reviewStatus": "REVIEWED",
        "reviewedAt": "2024-01-16T10:00:00Z",
        "reviewedByUser": {"id": "user-1", "name": "Alex"},
        "notes": "Team lunch",
        "isRecurring": False,
        "hideFromReports": False,
        "isManual": False,
        "isSplitTransaction": True,
        "hasSplitTransactions": True,
        "originalTransaction": {
            "id": "txn-original",
            "date": "2024-01-14",
            "amount": -42.50,
            "merchant": {"name": "Coffee Shop"},
        },
        "attachments": [
            {"id": "att-1", "filename": "receipt.pdf", "extension": "pdf", "sizeBytes": 12345}
        ],
        "tags": [{"id": "tag-1", "name": "Work", "color": "#ff0000"}],
        "splitTransactions": [
            {
                "id": "split-1",
                "amount": -21.25,
                "merchant": {"name": "Coffee Shop"},
                "category": {"name": "Food & Drink"},
            }
        ],
    }
}


# =============================================================================
# PUBLISHED ARTIFACT MAPPING
# =============================================================================


class TestPublishedSchemaArtifacts:
    """The module-level mapping is the normative, packaged contract."""

    def test_every_artifact_is_packaged_valid_json_schema(self):
        for artifact in SCHEMA_ARTIFACTS.values():
            document = artifact.load()
            assert isinstance(document, dict), artifact.resource
            assert document.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
            # The packaged artifact is itself a valid Draft 2020-12 schema.
            Draft202012Validator.check_schema(document)

    def test_artifact_id_matches_stable_urn(self):
        for artifact in SCHEMA_ARTIFACTS.values():
            assert artifact.load()["$id"] == artifact.urn, artifact.resource
            assert artifact.urn.startswith("urn:monarch-cli:schema:")

    def test_expected_contracts_are_published(self):
        published = {
            (artifact.contract, artifact.version) for artifact in SCHEMA_ARTIFACTS.values()
        }
        assert published == {
            ("account", "v1"),
            ("transaction", "v1"),
            ("transaction-detail", "v1"),
            ("error", "v1"),
            ("mutation-outcome", "v1"),
        }

    def test_lookup_by_name_version_and_urn_agree(self):
        artifact = schema_artifact("account", "v1")
        assert schema_artifact_by_urn(artifact.urn) is artifact
        assert SCHEMA_ARTIFACTS_BY_URN[artifact.urn] is artifact

    def test_unknown_lookups_fail(self):
        with pytest.raises(KeyError):
            schema_artifact("account", "v2")
        with pytest.raises(KeyError):
            schema_artifact_by_urn("urn:monarch-cli:schema:account:v9")

    def test_every_property_is_documented(self):
        """Every published property carries a description for consumers."""
        documents = [artifact.load() for artifact in SCHEMA_ARTIFACTS.values()]
        for document in documents:
            for name, prop in document.get("properties", {}).items():
                assert prop.get("description"), f"{name} lacks a description"


# =============================================================================
# OPERATION / SCHEMA MAPPING
# =============================================================================


class TestOperationSchemaMapping:
    """The shared operation mapping links outcomes to schemas and entities."""

    def test_every_operation_references_a_published_schema(self):
        for contract in OPERATION_CONTRACTS.values():
            assert schema_artifact(contract.schema_contract).contract == "mutation-outcome"
            assert contract.effect_entities, contract.operation

    def test_attachment_operation_and_effect_entities(self):
        contract = operation_contract("transactions.attachments.add")
        assert contract.schema_contract == "mutation-outcome"
        assert contract.effect_entities == (ATTACHMENT_MEDIA_ENTITY, ATTACHMENT_ENTITY)

    def test_unknown_operation_fails(self):
        with pytest.raises(KeyError):
            operation_contract("transactions.made.up")

    def test_mapping_covers_every_registered_outcome_operation(self):
        from monarch_cli.core.mutation_outcomes import OUTCOME_OPERATIONS

        assert set(OPERATION_CONTRACTS) == set(OUTCOME_OPERATIONS.values())


# =============================================================================
# ACCOUNT SCHEMA CONTRACT
# =============================================================================


class TestAccountSchemaContract:
    """Normalized account output conforms to the published account schema."""

    def test_core_fields_present(self):
        result = transform_account(FULL_ACCOUNT_RAW)
        for field in ACCOUNT_REQUIRED_FIELDS:
            assert field in result, f"Missing required field: {field}"

    def test_matches_published_schema(self):
        _assert_valid(transform_account(FULL_ACCOUNT_RAW), "account")

    def test_no_undocumented_fields(self):
        """additionalProperties: false rejects any undocumented stable field."""
        result = transform_account(FULL_ACCOUNT_RAW)
        assert set(result) == set(ACCOUNT_SCHEMA["properties"])

    def test_handles_minimal_input_gracefully(self):
        result = transform_account({"id": "acc-minimal"})
        assert result["name"] is None
        assert result["balance"] is None
        assert result["type"] is None
        _assert_valid(result, "account")

    def test_boolean_fields_never_none(self):
        absent = transform_account({"id": "acc"})
        assert absent["is_active"] is True
        assert absent["is_manual"] is False
        nulled = transform_account({"id": "acc", "isHidden": None, "isManual": None})
        assert nulled["is_active"] is True
        assert nulled["is_manual"] is False
        _assert_valid(absent, "account")
        _assert_valid(nulled, "account")

    def test_nullable_owner_and_liability_fields(self):
        raw = {
            **FULL_ACCOUNT_RAW,
            "ownedByUser": {"id": "user-1", "displayName": "Alex"},
            "isAsset": False,
            "limit": 5000,
            "apr": 0.2499,
            "interestRate": 24.99,
            "minimumPayment": 25.0,
            "excludedFromDebtPaydown": False,
        }
        result = transform_account(raw)
        assert result["owner_id"] == "user-1"
        assert result["is_asset"] is False
        _assert_valid(result, "account")

    def test_malformed_root_raises_typed_error(self):
        with pytest.raises(APIError):
            transform_accounts(None)  # type: ignore[arg-type]
        with pytest.raises(APIError):
            transform_transactions(None)  # type: ignore[arg-type]

    def test_snake_case_field_names(self):
        for field_name in transform_account(FULL_ACCOUNT_RAW):
            assert field_name == field_name.lower(), f"Field '{field_name}' not lowercase"
            assert field_name.islower() or "_" in field_name


# =============================================================================
# TRANSACTION SCHEMA CONTRACT
# =============================================================================


class TestTransactionSchemaContract:
    """Normalized transaction list output matches the published schema."""

    def test_core_fields_present(self):
        result = transform_transaction(FULL_TRANSACTION_RAW)
        for field in TRANSACTION_REQUIRED_FIELDS:
            assert field in result, f"Missing required field: {field}"

    def test_matches_published_schema(self):
        _assert_valid(transform_transaction(FULL_TRANSACTION_RAW), "transaction")

    def test_no_undocumented_fields(self):
        result = transform_transaction(FULL_TRANSACTION_RAW)
        assert set(result) == set(TRANSACTION_SCHEMA["properties"])

    def test_handles_minimal_input_gracefully(self):
        result = transform_transaction({"id": "txn-minimal"})
        assert result["date"] is None
        assert result["amount"] is None
        assert result["description"] is None
        _assert_valid(result, "transaction")

    def test_boolean_fields_never_none(self):
        assert transform_transaction({"id": "t"})["is_pending"] is False
        assert transform_transaction({"id": "t", "pending": None})["is_pending"] is False
        _assert_valid(transform_transaction({"id": "t", "pending": None}), "transaction")

    def test_owner_and_override_fields_nullable(self):
        complete = transform_transaction(
            {
                **FULL_TRANSACTION_RAW,
                "ownedByUser": {"id": "user-1", "name": "Alex"},
                "ownershipOverriddenAt": "2026-01-02T03:04:05Z",
            }
        )
        assert complete["owner_id"] == "user-1"
        assert complete["ownership_overridden_at"] == "2026-01-02T03:04:05Z"
        _assert_valid(complete, "transaction")

    def test_date_format_consistent(self):
        import re

        result = transform_transaction(FULL_TRANSACTION_RAW)
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", result["date"])

    def test_snake_case_field_names(self):
        for field_name in transform_transaction(FULL_TRANSACTION_RAW):
            assert field_name == field_name.lower(), f"Field '{field_name}' not lowercase"
            assert field_name.islower() or "_" in field_name


class TestTransactionDetailSchemaContract:
    """Normalized single-transaction detail matches the detail schema."""

    def test_matches_published_schema(self):
        result = transform_transaction_detail(
            FULL_TRANSACTION_DETAIL_RAW, requested_id="txn-789012"
        )
        _assert_valid(result, "transaction-detail")

    def test_no_undocumented_fields(self):
        result = transform_transaction_detail(
            FULL_TRANSACTION_DETAIL_RAW, requested_id="txn-789012"
        )
        assert set(result) == set(TRANSACTION_DETAIL_SCHEMA["properties"])

    def test_nested_collections_normalize_to_arrays(self):
        raw = {
            "getTransaction": {
                "id": "txn-detail",
                "attachments": None,
                "tags": [],
                "splitTransactions": None,
                "originalTransaction": None,
            }
        }
        result = transform_transaction_detail(raw, requested_id="txn-detail")
        assert result["attachments"] == []
        assert result["tags"] == []
        assert result["split"]["splits"] == []
        assert result["original_transaction"] is None
        _assert_valid(result, "transaction-detail")

    def test_redirected_is_boolean(self):
        result = transform_transaction_detail(
            {"getTransaction": {"id": "txn-new"}}, requested_id="txn-old"
        )
        assert result["redirected"] is True


# =============================================================================
# STRUCTURED ERROR CONTRACT
# =============================================================================


class TestErrorSchemaContract:
    """Structured errors conform to the published error schema."""

    def test_validation_error_matches_schema(self):
        error = ValidationError("Invalid input", field="transaction_id")
        _assert_valid(error.to_dict(), "error")

    def test_error_code_is_an_open_string(self):
        document = ERROR_SCHEMA["properties"]["code"]
        assert document["type"] == "string"
        assert "enum" not in document


# =============================================================================
# MUTATION OUTCOME CONTRACT
# =============================================================================


class TestMutationOutcomeSchemaContract:
    """The mutation-outcome.v1 envelope and attachment workflow fixtures."""

    def test_single_effect_success(self):
        outcome = build_mutation_outcome(
            "transactions update",
            [succeeded_item("transaction", "txn-1", {"changes": {"notes": "Review"}})],
        )
        assert outcome["status"] == "succeeded"
        assert outcome["verification"] is None
        _assert_mutation_outcome_contract(outcome)

    def test_attachment_success_is_ordered_two_stage(self):
        outcome = build_mutation_outcome(
            "transactions attachments add",
            [
                succeeded_item(
                    ATTACHMENT_MEDIA_ENTITY,
                    "media-public-id",
                    {
                        "public_id": "media-public-id",
                        "extension": "pdf",
                        "size_bytes": 12345,
                        "filename": "receipt.pdf",
                    },
                ),
                succeeded_item(
                    ATTACHMENT_ENTITY,
                    "att-1",
                    {
                        "transaction_id": "txn-1",
                        "attachment_id": "att-1",
                        "public_id": "att-public-1",
                        "filename": "receipt.pdf",
                        "extension": "pdf",
                        "size_bytes": 12345,
                    },
                ),
            ],
        )
        assert outcome["operation"] == "transactions.attachments.add"
        assert outcome["status"] == "succeeded"
        assert [item["entity"] for item in outcome["items"]] == [
            ATTACHMENT_MEDIA_ENTITY,
            ATTACHMENT_ENTITY,
        ]
        _assert_mutation_outcome_contract(outcome)

    def test_attachment_definitive_stage_failure(self):
        outcome = build_mutation_outcome(
            "transactions attachments add",
            [
                failed_item(
                    ATTACHMENT_MEDIA_ENTITY,
                    "receipt.pdf",
                    "API_ERROR",
                    "The media upload was rejected by the service.",
                    {"stage": "upload_media"},
                )
            ],
        )
        assert outcome["status"] == "failed"
        assert outcome["verification"] is None
        _assert_mutation_outcome_contract(outcome)

    def test_attachment_ambiguous_registration(self):
        outcome = build_mutation_outcome(
            "transactions attachments add",
            [
                succeeded_item(
                    ATTACHMENT_MEDIA_ENTITY,
                    "media-public-id",
                    {"public_id": "media-public-id", "filename": "receipt.pdf"},
                ),
                ambiguous_item(
                    ATTACHMENT_ENTITY,
                    "receipt.pdf",
                    "The attachment registration could not be confirmed.",
                    {"remote_state": "unknown", "reason": "missing_identity"},
                ),
            ],
            verification=verification_object(
                "Read the transaction detail before retrying.",
                command=["monarch", "transactions", "get", "txn-1"],
            ),
        )
        assert outcome["status"] == "partial"
        assert outcome["verification"]["required"] is True
        _assert_mutation_outcome_contract(outcome)

    def test_attachment_partial_orphaned_media(self):
        outcome = build_mutation_outcome(
            "transactions attachments add",
            [
                succeeded_item(
                    ATTACHMENT_MEDIA_ENTITY,
                    "media-public-id",
                    {"public_id": "media-public-id", "filename": "receipt.pdf"},
                ),
                failed_item(
                    ATTACHMENT_ENTITY,
                    "receipt.pdf",
                    "API_ERROR",
                    "The attachment registration was rejected by the service.",
                    {"stage": "register_attachment"},
                ),
            ],
        )
        assert outcome["status"] == "partial"
        assert outcome["verification"] is None
        _assert_mutation_outcome_contract(outcome)

    def test_invalid_status_enum_is_rejected(self):
        outcome = build_mutation_outcome(
            "transactions update",
            [succeeded_item("transaction", "txn-1", {"changes": {}})],
        )
        outcome["status"] = "ok"
        with pytest.raises(AssertionError):
            _assert_mutation_outcome_contract(outcome)

    def test_impossible_summary_counts_are_rejected(self):
        outcome = build_mutation_outcome(
            "transactions update",
            [succeeded_item("transaction", "txn-1", {"changes": {}})],
        )
        # Passes JSON Schema (non-negative integers) but violates the
        # arithmetic invariant, which the contract validator must catch.
        outcome["summary"]["total"] = 99
        with pytest.raises(AssertionError):
            _assert_mutation_outcome_contract(outcome)

    def test_result_and_error_cannot_both_be_non_null(self):
        outcome = build_mutation_outcome(
            "transactions update",
            [succeeded_item("transaction", "txn-1", {"changes": {}})],
        )
        outcome["items"][0]["error"] = {"code": "API_ERROR", "message": "x", "details": {}}
        with pytest.raises(AssertionError):
            _assert_mutation_outcome_contract(outcome)


# =============================================================================
# NEGATIVE FIXTURES (validation must fail; never pass vacuously)
# =============================================================================


class TestNegativeFixtures:
    """Representative invalid payloads must fail schema validation."""

    @staticmethod
    def _account() -> dict[str, Any]:
        return transform_account(FULL_ACCOUNT_RAW)

    @staticmethod
    def _transaction() -> dict[str, Any]:
        return transform_transaction(FULL_TRANSACTION_RAW)

    def test_missing_required_field_fails(self):
        payload = self._account()
        del payload["balance"]
        with pytest.raises(AssertionError):
            _assert_valid(payload, "account")

    def test_wrong_type_fails(self):
        payload = self._account()
        payload["balance"] = "lots"
        with pytest.raises(AssertionError):
            _assert_valid(payload, "account")

    def test_invalid_nullability_fails(self):
        payload = self._transaction()
        payload["is_pending"] = None
        with pytest.raises(AssertionError):
            _assert_valid(payload, "transaction")

    def test_undocumented_field_fails(self):
        payload = self._account()
        payload["mystery_field"] = 1
        with pytest.raises(AssertionError):
            _assert_valid(payload, "account")

    def test_error_wrong_type_fails(self):
        with pytest.raises(AssertionError):
            _assert_valid({"error": True, "code": 5, "message": "x", "details": {}}, "error")


# =============================================================================
# COLLECTION SHAPES
# =============================================================================


class TestCollectionSchemaContract:
    """Collection output is a JSON array of records following the schema."""

    def test_accounts_returns_list(self):
        result = transform_accounts({"accounts": [FULL_ACCOUNT_RAW]})
        assert isinstance(result, list)
        _assert_valid(result[0], "account")

    def test_accounts_empty_returns_empty_list(self):
        assert transform_accounts({"accounts": []}) == []
        assert transform_accounts({}) == []

    def test_transactions_returns_list(self):
        result = transform_transactions({"allTransactions": {"results": [FULL_TRANSACTION_RAW]}})
        assert isinstance(result, list)
        _assert_valid(result[0], "transaction")

    def test_transactions_empty_returns_empty_list(self):
        assert transform_transactions({"allTransactions": {"results": []}}) == []
        assert transform_transactions({}) == []
