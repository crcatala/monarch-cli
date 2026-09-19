"""Unit tests for account transformer."""

import pytest

from monarch_cli.core.exceptions import APIError
from monarch_cli.transformers.accounts import (
    ACCOUNT_HISTORY_RECORD_FIELDS,
    ACCOUNT_TYPE_RECORD_FIELDS,
    AGGREGATE_SNAPSHOT_RECORD_FIELDS,
    RECENT_BALANCES_RECORD_FIELDS,
    SNAPSHOT_BY_TYPE_RECORD_FIELDS,
    SNAPSHOTS_BY_TYPE_FIELDS,
    transform_account,
    transform_account_history,
    transform_account_types,
    transform_accounts,
    transform_aggregate_snapshots,
    transform_recent_balances,
    transform_snapshots_by_type,
)

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
        "owner_id",
        "owner_name",
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


class TestOwnershipNormalization:
    """Owner attribution mirrors the optional upstream ownedByUser relationship.

    A missing, null, or malformed owner relationship yields null normalized
    owner fields. Null ownership must never be relabeled as a shared or
    unassigned state: the released upstream response has no field that
    distinguishes those meanings.
    """

    def test_complete_owner_relationship(self):
        raw = {**SAMPLE_ACCOUNT_FULL, "ownedByUser": {"id": "user-1", "displayName": "Alex"}}
        result = transform_account(raw)
        assert result["owner_id"] == "user-1"
        assert result["owner_name"] == "Alex"

    def test_missing_owner_relationship(self):
        result = transform_account(SAMPLE_ACCOUNT_FULL)
        assert result["owner_id"] is None
        assert result["owner_name"] is None

    def test_null_owner_relationship(self):
        result = transform_account({**SAMPLE_ACCOUNT_FULL, "ownedByUser": None})
        assert result["owner_id"] is None
        assert result["owner_name"] is None

    @pytest.mark.parametrize(
        "malformed",
        ["not-an-object", 42, ["user-1"], True],
        ids=["string", "number", "list", "boolean"],
    )
    def test_non_object_owner_relationship_yields_nulls(self, malformed):
        result = transform_account({**SAMPLE_ACCOUNT_FULL, "ownedByUser": malformed})
        assert result["owner_id"] is None
        assert result["owner_name"] is None

    def test_partially_populated_owner_relationship(self):
        id_only = transform_account({**SAMPLE_ACCOUNT_FULL, "ownedByUser": {"id": "user-1"}})
        assert id_only["owner_id"] == "user-1"
        assert id_only["owner_name"] is None

        name_only = transform_account(
            {**SAMPLE_ACCOUNT_FULL, "ownedByUser": {"displayName": "Alex"}}
        )
        assert name_only["owner_id"] is None
        assert name_only["owner_name"] == "Alex"

    def test_owner_null_values_inside_object_yield_nulls(self):
        result = transform_account(
            {**SAMPLE_ACCOUNT_FULL, "ownedByUser": {"id": None, "displayName": None}}
        )
        assert result["owner_id"] is None
        assert result["owner_name"] is None

    def test_no_invented_shared_or_unassigned_label(self):
        """Null owner fields stay null; no synthetic shared/unassigned state is added."""
        result = transform_account(SAMPLE_ACCOUNT_FULL)
        assert result["owner_id"] is None
        assert result["owner_name"] is None
        assert "is_shared" not in result
        assert "ownership_state" not in result


SAMPLE_TYPE_OPTIONS_RAW = {
    "accountTypeOptions": [
        {
            "type": {
                "name": "asset",
                "display": "Asset",
                "group": "assets",
                "possibleSubtypes": [
                    {"name": "checking", "display": "Checking"},
                    {"name": "savings", "display": "Savings"},
                ],
            },
            "subtype": {"name": "checking", "display": "Checking"},
        },
        {
            "type": {
                "name": "loan",
                "display": "Loan",
                "group": "liabilities",
                "possibleSubtypes": [
                    {"name": "mortgage", "display": "Mortgage"},
                ],
            },
            "subtype": None,
        },
    ]
}


class TestTransformAccountTypes:
    """Tests for transform_account_types function."""

    def test_flattens_hierarchy_into_leaf_records(self):
        """Each (group, type, subtype) combination becomes one record."""
        result = transform_account_types(SAMPLE_TYPE_OPTIONS_RAW)

        keys = [(r["group"], r["type"], r["subtype"]) for r in result]
        assert keys == [
            ("assets", "asset", "checking"),
            ("assets", "asset", "savings"),
            ("liabilities", "loan", "mortgage"),
        ]

    def test_preserves_identifiers_and_display_labels(self):
        """Identifiers come from upstream names; labels from displays."""
        result = transform_account_types(SAMPLE_TYPE_OPTIONS_RAW)

        assert result[0] == {
            "group": "assets",
            "type": "asset",
            "type_display": "Asset",
            "subtype": "checking",
            "subtype_display": "Checking",
        }

    def test_ordering_follows_upstream_first_seen_order(self):
        """Types follow option order; subtypes follow possibleSubtypes order."""
        result = transform_account_types(SAMPLE_TYPE_OPTIONS_RAW)

        assert [r["type"] for r in result] == ["asset", "asset", "loan"]
        assert [r["subtype"] for r in result] == ["checking", "savings", "mortgage"]

    def test_explicit_subtype_appended_when_missing_from_possible_subtypes(self):
        """An option subtype absent from possibleSubtypes is still listed."""
        raw = {
            "accountTypeOptions": [
                {
                    "type": {
                        "name": "asset",
                        "group": "assets",
                        "possibleSubtypes": [
                            {"name": "checking", "display": "Checking"},
                        ],
                    },
                    "subtype": {"name": "other", "display": "Other"},
                }
            ]
        }

        result = transform_account_types(raw)

        assert [(r["subtype"], r["subtype_display"]) for r in result] == [
            ("checking", "Checking"),
            ("other", "Other"),
        ]

    def test_duplicate_records_collapsed_first_wins(self):
        """Duplicate (group, type, subtype) identifiers keep the first row."""
        raw = {
            "accountTypeOptions": [
                {
                    "type": {
                        "name": "asset",
                        "group": "assets",
                        "possibleSubtypes": [
                            {"name": "checking", "display": "Checking"},
                        ],
                    },
                    "subtype": {"name": "checking", "display": "Checking"},
                },
                {
                    "type": {
                        "name": "asset",
                        "group": "assets",
                        "possibleSubtypes": [
                            {"name": "checking", "display": "Checking Again"},
                        ],
                    },
                    "subtype": None,
                },
            ]
        }

        result = transform_account_types(raw)

        assert len(result) == 1
        assert result[0]["subtype_display"] == "Checking"

    def test_type_without_subtypes_yields_single_null_subtype_row(self):
        """A type with no subtype information still produces one record."""
        raw = {
            "accountTypeOptions": [
                {"type": {"name": "vehicle", "group": "assets"}, "subtype": None}
            ]
        }

        result = transform_account_types(raw)

        assert result == [
            {
                "group": "assets",
                "type": "vehicle",
                "type_display": None,
                "subtype": None,
                "subtype_display": None,
            }
        ]

    def test_missing_type_object_yields_all_null_record(self):
        """A partially populated option keeps fields present but null."""
        raw = {"accountTypeOptions": [{"type": None, "subtype": None}]}

        result = transform_account_types(raw)

        assert result == [
            {
                "group": None,
                "type": None,
                "type_display": None,
                "subtype": None,
                "subtype_display": None,
            }
        ]

    def test_null_type_values_become_none_not_invented(self):
        """Null scalar fields inside type/subtype objects stay null."""
        raw = {
            "accountTypeOptions": [
                {
                    "type": {"name": None, "display": None, "group": None},
                    "subtype": {"name": None, "display": None},
                }
            ]
        }

        result = transform_account_types(raw)

        assert result[0] == {
            "group": None,
            "type": None,
            "type_display": None,
            "subtype": None,
            "subtype_display": None,
        }

    @pytest.mark.parametrize(
        "raw",
        [
            {},
            {"accountTypeOptions": []},
            {"accountTypeOptions": None},
            {"accountTypeOptions": {"unexpected": "object"}},
        ],
    )
    def test_empty_missing_or_non_list_options_normalize_empty(self, raw):
        """Absent, null, and non-list option containers normalize to []."""
        assert transform_account_types(raw) == []

    def test_skips_non_mapping_entries_without_inventing(self):
        """Non-object options and subtypes are skipped, not coerced."""
        raw = {
            "accountTypeOptions": [
                "not-an-object",
                {
                    "type": {
                        "name": "asset",
                        "group": "assets",
                        "possibleSubtypes": ["also-not-an-object"],
                    },
                    "subtype": 42,
                },
            ]
        }

        result = transform_account_types(raw)

        assert result == [
            {
                "group": "assets",
                "type": "asset",
                "type_display": None,
                "subtype": None,
                "subtype_display": None,
            }
        ]

    def test_ignores_unknown_additive_fields(self):
        """Unknown upstream fields never leak into normalized records."""
        raw = {
            "accountTypeOptions": [
                {
                    "futureField": {"nested": True},
                    "type": {
                        "name": "asset",
                        "group": "assets",
                        "newThing": 1,
                        "possibleSubtypes": [
                            {"name": "checking", "display": "Checking", "extra": None},
                        ],
                    },
                    "subtype": None,
                }
            ]
        }

        result = transform_account_types(raw)

        assert set(result[0].keys()) == set(ACCOUNT_TYPE_RECORD_FIELDS)

    def test_non_object_root_raises_typed_error(self):
        """Malformed roots produce a stable typed error."""
        with pytest.raises(APIError):
            transform_account_types(None)  # type: ignore[arg-type]
        with pytest.raises(APIError):
            transform_account_types(["not", "an", "object"])  # type: ignore[arg-type]


class TestAccountTypeSchemaContract:
    """Tests ensuring account type-discovery schema stability for AI agents."""

    REQUIRED_FIELDS = {"group", "type", "type_display", "subtype", "subtype_display"}

    def test_record_fields_constant_matches_contract(self):
        """The published field tuple is exactly the stable record schema."""
        assert set(ACCOUNT_TYPE_RECORD_FIELDS) == self.REQUIRED_FIELDS

    def test_all_fields_present(self):
        """Every record carries all documented fields, even when null."""
        result = transform_account_types({"accountTypeOptions": [{"type": None}]})
        assert set(result[0].keys()) == self.REQUIRED_FIELDS

    def test_no_extra_fields(self):
        """No undocumented fields should be added."""
        result = transform_account_types(SAMPLE_TYPE_OPTIONS_RAW)
        for record in result:
            extra = set(record.keys()) - self.REQUIRED_FIELDS
            assert extra == set(), f"Unexpected fields: {extra}"

    def test_identifiers_are_upstream_names_not_displays(self):
        """Workflow identifiers stay distinct from human labels."""
        result = transform_account_types(SAMPLE_TYPE_OPTIONS_RAW)

        for record in result:
            assert record["type"] != record["type_display"] or record["type"] is None
            assert record["subtype"] != record["subtype_display"] or record["subtype"] is None


class TestAccountHistoryAndSnapshots:
    """Tests for the normalized account history/snapshot contracts."""

    def test_history_preserves_opaque_metadata_and_null_balances(self):
        raw = [
            {
                "date": "2024-01-01",
                "signedBalance": None,
                "accountId": "opaque-001",
                "accountName": "Manual account",
            }
        ]
        assert transform_account_history(raw) == [
            {
                "date": "2024-01-01",
                "balance": None,
                "account_id": "opaque-001",
                "account_name": "Manual account",
            }
        ]

    def test_empty_history_is_empty_and_malformed_root_fails(self):
        assert transform_account_history([]) == []
        with pytest.raises(APIError):
            transform_account_history(None)  # type: ignore[arg-type]

    def test_recent_balances_normalize_sparse_accounts(self):
        raw = {
            "accounts": [
                {"id": "hidden-id", "recentBalances": [{"date": "2024-01", "balance": None}]},
                {"id": "manual-id", "recentBalances": None},
            ]
        }
        assert transform_recent_balances(raw) == [
            {"id": "hidden-id", "recent_balances": [{"date": "2024-01", "balance": None}]},
            {"id": "manual-id", "recent_balances": []},
        ]

    def test_snapshot_shapes_preserve_month_precision_and_empty_collections(self):
        assert transform_aggregate_snapshots({"aggregateSnapshots": None}) == []
        assert transform_snapshots_by_type({}) == {"snapshots": [], "account_types": []}
        result = transform_snapshots_by_type(
            {
                "snapshotsByAccountType": [
                    {"accountType": "asset", "month": "2024-01", "balance": 10}
                ],
                "accountTypes": [{"name": "asset", "group": "assets"}],
            }
        )
        assert result == {
            "snapshots": [{"account_type": "asset", "period": "2024-01", "balance": 10}],
            "account_types": [{"name": "asset", "group": "assets"}],
        }

    def test_schema_constants_match_normalized_records(self):
        assert set(ACCOUNT_HISTORY_RECORD_FIELDS) == {
            "date",
            "balance",
            "account_id",
            "account_name",
        }
        assert set(RECENT_BALANCES_RECORD_FIELDS) == {"id", "recent_balances"}
        assert set(AGGREGATE_SNAPSHOT_RECORD_FIELDS) == {"date", "balance"}
        assert set(SNAPSHOT_BY_TYPE_RECORD_FIELDS) == {"account_type", "period", "balance"}
        assert set(SNAPSHOTS_BY_TYPE_FIELDS) == {"snapshots", "account_types"}
