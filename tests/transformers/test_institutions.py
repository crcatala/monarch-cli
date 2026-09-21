"""Tests for credential-centric institution and subscription normalization."""

import pytest

from monarch_cli.core.exceptions import APIError
from monarch_cli.transformers.institutions import transform_institutions, transform_subscription

RAW_INSTITUTIONS = {
    "credentials": [
        {
            "id": "cred-1",
            "dataProvider": "PLAID",
            "updateRequired": False,
            "disconnectedFromDataProviderAt": None,
            "displayLastUpdatedAt": "2026-09-17T12:00:00Z",
            "institution": {
                "id": "inst-1",
                "name": "Example Bank",
                "status": "DEGRADED",
                "hasIssuesReported": True,
                "hasIssuesReportedMessage": "Reconnect required",
                "balanceStatus": "OK",
                "transactionsStatus": "DEGRADED",
            },
        },
        {"id": "cred-empty", "institution": None},
    ],
    "accounts": [
        {
            "id": "account-live",
            "displayName": "Checking",
            "subtype": {"display": "Checking"},
            "mask": "1234",
            "credential": {"id": "cred-1"},
            "deletedAt": None,
        },
        {
            "id": "account-deleted",
            "displayName": "Old Checking",
            "credential": {"id": "cred-1"},
            "deletedAt": "2026-01-01T00:00:00Z",
        },
    ],
    # This fragment must not become a second normalized subscription contract.
    "subscription": {"isOnFreeTrial": True, "hasPremiumEntitlement": True},
}


def test_groups_active_accounts_by_credential_and_omits_deleted() -> None:
    result = transform_institutions(RAW_INSTITUTIONS)

    assert result[0]["credential_id"] == "cred-1"
    assert result[0]["provider"] == "PLAID"
    assert result[0]["institution_id"] == "inst-1"
    assert result[0]["institution_name"] == "Example Bank"
    assert result[0]["institution_status"] == "DEGRADED"
    assert result[0]["disconnected"] is None
    assert result[0]["issue"] == {"reported": True, "message": "Reconnect required"}
    assert result[0]["accounts"] == [
        {
            "id": "account-live",
            "name": "Checking",
            "subtype": "Checking",
            "mask": "1234",
            "is_deleted": False,
            "deleted_at": None,
        }
    ]
    assert result[1]["credential_id"] == "cred-empty"
    assert result[1]["institution_name"] is None
    assert result[1]["accounts"] == []
    assert "subscription" not in result[0]


def test_include_deleted_preserves_deletion_state() -> None:
    result = transform_institutions(RAW_INSTITUTIONS, include_deleted=True)

    accounts = result[0]["accounts"]
    assert len(accounts) == 2
    assert accounts[1]["is_deleted"] is True
    assert accounts[1]["deleted_at"] == "2026-01-01T00:00:00Z"


def test_null_and_partial_containers_are_safe() -> None:
    result = transform_institutions({"credentials": None, "accounts": None})
    assert result == []

    partial = transform_institutions({"credentials": [{"id": "cred"}], "accounts": []})
    assert partial == [
        {
            "credential_id": "cred",
            "provider": None,
            "institution_id": None,
            "institution_name": None,
            "institution_status": None,
            "update_required": None,
            "disconnected": None,
            "disconnected_at": None,
            "last_updated": None,
            "issue": None,
            "balance_status": None,
            "transaction_status": None,
            "accounts": [],
        }
    ]


def test_subscription_normalizes_without_sensitive_defaults() -> None:
    result = transform_subscription(
        {
            "subscription": {
                "id": "sub-1",
                "paymentSource": "card",
                "referralCode": "secret-referral",
                "isOnFreeTrial": False,
                "hasPremiumEntitlement": True,
            }
        }
    )
    assert result == {
        "available": True,
        "is_on_free_trial": False,
        "has_premium_entitlement": True,
    }
    assert "paymentSource" not in result
    assert "referralCode" not in result


def test_subscription_unavailable_is_not_known_false() -> None:
    assert transform_subscription({"subscription": None}) == {
        "available": False,
        "is_on_free_trial": None,
        "has_premium_entitlement": None,
    }
    assert transform_subscription({})["available"] is False


def test_partial_subscription_without_usable_state_is_unavailable() -> None:
    assert transform_subscription({"subscription": {"paymentSource": "card"}}) == {
        "available": False,
        "is_on_free_trial": None,
        "has_premium_entitlement": None,
    }
    assert transform_subscription({"subscription": {"isOnFreeTrial": False}}) == {
        "available": True,
        "is_on_free_trial": False,
        "has_premium_entitlement": None,
    }


def test_malformed_roots_are_typed_errors() -> None:
    with pytest.raises(APIError):
        transform_institutions([])
    with pytest.raises(APIError):
        transform_subscription([])
