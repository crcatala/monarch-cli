"""Normalize credential-centric institution and subscription responses.

The released upstream institution query associates accounts with credentials,
not with institution objects.  This module keeps that relationship explicit
and uses ``null`` for unavailable status values instead of inventing a healthy
connection.  The embedded subscription fragment in the institutions response
is deliberately ignored; :func:`transform_subscription` is the sole
normalized subscription contract.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .nesting import list_or_empty, nested_get, require_object

INSTITUTION_RECORD_FIELDS: tuple[str, ...] = (
    "credential_id",
    "provider",
    "institution_id",
    "institution_name",
    "update_required",
    "disconnected",
    "disconnected_at",
    "last_updated",
    "issue",
    "balance_status",
    "transaction_status",
    "accounts",
)

INSTITUTION_ACCOUNT_FIELDS: tuple[str, ...] = (
    "id",
    "name",
    "subtype",
    "mask",
    "is_deleted",
    "deleted_at",
)

SUBSCRIPTION_FIELDS: tuple[str, ...] = (
    "available",
    "is_on_free_trial",
    "has_premium_entitlement",
)


def _mapping(value: Any) -> Mapping[str, Any] | None:
    """Return a mapping value, or ``None`` for a null/evolved shape."""
    return value if isinstance(value, Mapping) else None


def _optional_bool(value: Any) -> bool | None:
    """Accept only real upstream booleans; preserve unavailable as ``null``."""
    if isinstance(value, bool):
        return value
    return None


def _transform_account(raw: Any) -> dict[str, Any] | None:
    """Normalize one institution-associated account."""
    account = _mapping(raw)
    if account is None:
        return None

    deleted_at = account.get("deletedAt")
    return {
        "id": account.get("id"),
        "name": account.get("displayName"),
        "subtype": nested_get(account, "subtype", "display"),
        "mask": account.get("mask"),
        # A non-null deletedAt is the upstream deletion signal.  Unlike
        # connection health, this is not a default: it is explicit state.
        "is_deleted": deleted_at is not None,
        "deleted_at": deleted_at,
    }


def transform_institutions(raw: Any, *, include_deleted: bool = False) -> list[dict[str, Any]]:
    """Normalize the credential-centric ``get_institutions`` response.

    Deleted accounts are omitted unless ``include_deleted`` is true.  Every
    credential is retained, including credentials with no institution or no
    associated accounts, so absent status cannot look like a healthy result.
    The response's embedded subscription fragment is not returned here.
    """
    response = require_object(raw, "institutions")
    accounts_by_credential: dict[Any, list[dict[str, Any]]] = {}
    for raw_account in list_or_empty(response.get("accounts")):
        account = _transform_account(raw_account)
        if account is None:
            continue
        credential_id = nested_get(raw_account, "credential", "id")
        if credential_id is None or not isinstance(credential_id, (str, int, float, bool)):
            continue
        if not include_deleted and account["is_deleted"]:
            continue
        accounts_by_credential.setdefault(credential_id, []).append(account)

    records: list[dict[str, Any]] = []
    for raw_credential in list_or_empty(response.get("credentials")):
        credential = _mapping(raw_credential)
        if credential is None:
            continue
        institution = _mapping(credential.get("institution"))
        disconnected_at = credential.get("disconnectedFromDataProviderAt")
        reported = _optional_bool(nested_get(institution, "hasIssuesReported"))
        issue_message = nested_get(institution, "hasIssuesReportedMessage")
        issue = None
        if reported is not None or issue_message is not None:
            issue = {"reported": reported, "message": issue_message}

        credential_id = credential.get("id")
        if credential_id is not None and not isinstance(credential_id, (str, int, float, bool)):
            credential_id = None
        records.append(
            {
                "credential_id": credential_id,
                "provider": credential.get("dataProvider"),
                "institution_id": nested_get(institution, "id"),
                "institution_name": nested_get(institution, "name"),
                "update_required": _optional_bool(credential.get("updateRequired")),
                # A missing/null timestamp is unknown, not a healthy False.
                "disconnected": None if disconnected_at is None else True,
                "disconnected_at": disconnected_at,
                "last_updated": credential.get("displayLastUpdatedAt"),
                "issue": issue,
                "balance_status": nested_get(institution, "balanceStatus"),
                "transaction_status": nested_get(institution, "transactionsStatus"),
                "accounts": accounts_by_credential.get(credential_id, []),
            }
        )
    return records


def transform_subscription(raw: Any) -> dict[str, Any]:
    """Normalize ``get_subscription_details`` without exposing sensitive data.

    ``available`` is false when the upstream subscription object is absent;
    that state is distinct from an available subscription reporting either
    entitlement boolean as false.  Referral and payment-source fields are not
    copied to this contract.
    """
    response = require_object(raw, "subscription")
    subscription = _mapping(response.get("subscription"))
    if subscription is None:
        return {
            "available": False,
            "is_on_free_trial": None,
            "has_premium_entitlement": None,
        }
    return {
        "available": True,
        "is_on_free_trial": _optional_bool(subscription.get("isOnFreeTrial")),
        "has_premium_entitlement": _optional_bool(subscription.get("hasPremiumEntitlement")),
    }


__all__ = [
    "INSTITUTION_ACCOUNT_FIELDS",
    "INSTITUTION_RECORD_FIELDS",
    "SUBSCRIPTION_FIELDS",
    "transform_institutions",
    "transform_subscription",
]
