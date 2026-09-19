"""Account transformers - convert raw API responses to CLI-friendly format.

The transformed schema is a contract with AI agents. Field names and types
are stable - changes are breaking.

Normalization rules (v1 contract):

- Unavailable non-boolean values (``id``, ``name``, ``type``, ``subtype``,
  ``balance``, ``institution``, ``last_updated``) normalize to ``null``;
  financial values are never invented (a missing balance is not ``0``).
- ``is_active`` and ``is_manual`` are always booleans. Absent or ``null``
  source values default to ``is_active=True`` (not hidden) and
  ``is_manual=False``.
- ``owner_id`` and ``owner_name`` mirror the optional upstream
  ``ownedByUser`` relationship (``id`` and ``displayName``). A missing,
  ``null``, or non-object owner relationship yields ``null`` for both fields;
  null ownership means only that owner identity was not provided and does not
  distinguish shared, unassigned, unavailable, or unsupported upstream states.
- A present-but-null nested relationship (for example ``institution: null``)
  yields ``null`` rather than raising.
- Unknown additive upstream fields are ignored.
- ``--raw`` output bypasses these transformers entirely and preserves the
  upstream structure, including null containers and unknown fields.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .nesting import bool_or_default, list_or_empty, nested_get, require_list, require_object


def transform_account(raw: Any) -> dict[str, Any]:
    """Transform a single account from raw API format.

    Args:
        raw: Raw account object from the Monarch API. Must be an object.

    Returns:
        Normalized account dict with stable field names.

    Raises:
        APIError: If ``raw`` is not an object.

    Example:
        >>> raw = {"id": "123", "displayName": "Checking", "type": {"display": "Checking"}}
        >>> transform_account(raw)
        {"id": "123", "name": "Checking", "type": "Checking", ...}
    """
    account = require_object(raw, "account")
    is_hidden = bool_or_default(nested_get(account, "isHidden"), False)
    return {
        "id": nested_get(account, "id"),
        "name": nested_get(account, "displayName"),
        "type": nested_get(account, "type", "display"),
        "subtype": nested_get(account, "subtype", "display"),
        "balance": nested_get(account, "currentBalance"),
        "institution": nested_get(account, "institution", "name"),
        "is_active": not is_hidden,
        "is_manual": bool_or_default(nested_get(account, "isManual"), False),
        "owner_id": nested_get(account, "ownedByUser", "id"),
        "owner_name": nested_get(account, "ownedByUser", "displayName"),
        "last_updated": nested_get(account, "updatedAt"),
    }


def transform_accounts(raw: Any) -> list[dict[str, Any]]:
    """Transform accounts API response.

    Args:
        raw: Raw API response object containing an ``accounts`` list. The
            container may be absent or ``null`` (normalizes to ``[]``).

    Returns:
        List of normalized account dicts.

    Raises:
        APIError: If ``raw`` is not an object.
    """
    response = require_object(raw, "accounts")
    return [transform_account(acc) for acc in list_or_empty(nested_get(response, "accounts"))]


#: Stable field names for one normalized account type-discovery record (v1
#: contract). ``group`` is the parent of ``type``; ``type`` is the parent of
#: ``subtype``. The un-suffixed fields are the upstream ``name`` identifiers
#: that account workflows (for example manual-account creation and snapshot
#: filters) send back to the API; the ``*_display`` fields are human labels.
ACCOUNT_TYPE_RECORD_FIELDS: tuple[str, ...] = (
    "group",
    "type",
    "type_display",
    "subtype",
    "subtype_display",
)


def _optional_mapping(value: Any) -> Mapping[str, Any] | None:
    """Return ``value`` when it is a mapping, else ``None``."""
    return value if isinstance(value, Mapping) else None


def transform_account_types(raw: Any) -> list[dict[str, Any]]:
    """Normalize the account type-discovery response into deterministic records.

    The upstream ``accountTypeOptions`` payload describes the supported account
    hierarchy. Each option carries a ``type`` object (``name``/``display``/
    ``group`` and, usually, ``possibleSubtypes``) and optionally a ``subtype``
    object. This transformer flattens that hierarchy into one stable record per
    ``(group, type, subtype)`` leaf:

    - ``group`` / ``type`` / ``subtype`` are the upstream ``name`` identifiers;
      ``type_display`` / ``subtype_display`` are human labels when available.
    - Ordering is deterministic: types follow upstream first-seen order; within
      a type, subtypes follow the upstream ``possibleSubtypes`` order and the
      option's own ``subtype`` is appended only when not already listed. A type
      with no subtype information yields one row with ``subtype: null``.
    - Duplicate ``(group, type, subtype)`` records are collapsed (first wins).
    - Empty, absent, ``null``, or non-list ``accountTypeOptions`` normalize to
      ``[]``; partial or unknown fields never invent values.

    Args:
        raw: Raw account type-discovery response object.

    Returns:
        List of normalized account type records (see
        :data:`ACCOUNT_TYPE_RECORD_FIELDS`).

    Raises:
        APIError: If ``raw`` is not an object.
    """
    response = require_object(raw, "account type options")
    options = list_or_empty(nested_get(response, "accountTypeOptions"))

    records: list[dict[str, Any]] = []
    seen: set[tuple[str | None, str | None, str | None]] = set()

    for option in options:
        option_mapping = _optional_mapping(option)
        if option_mapping is None:
            continue

        type_obj = _optional_mapping(nested_get(option_mapping, "type"))
        group = nested_get(type_obj, "group")
        type_name = nested_get(type_obj, "name")
        type_display = nested_get(type_obj, "display")

        # Prefer the type's authoritative ``possibleSubtypes`` ordering; fall
        # back to the option's own ``subtype`` when that list is unavailable.
        candidates: list[Mapping[str, Any] | None] = []
        possible = list_or_empty(nested_get(type_obj, "possibleSubtypes"))
        for possible_subtype in possible:
            possible_mapping = _optional_mapping(possible_subtype)
            if possible_mapping is not None:
                candidates.append(possible_mapping)

        explicit_subtype = _optional_mapping(nested_get(option_mapping, "subtype"))
        if explicit_subtype is not None:
            explicit_name = nested_get(explicit_subtype, "name")
            if all(nested_get(candidate, "name") != explicit_name for candidate in candidates):
                candidates.append(explicit_subtype)

        if not candidates:
            candidates = [None]

        for candidate in candidates:
            subtype_name = nested_get(candidate, "name")
            subtype_display = nested_get(candidate, "display")
            key = (group, type_name, subtype_name)
            if key in seen:
                continue
            seen.add(key)
            records.append(
                {
                    "group": group,
                    "type": type_name,
                    "type_display": type_display,
                    "subtype": subtype_name,
                    "subtype_display": subtype_display,
                }
            )

    return records


#: Stable field names for one normalized account-history record (v1 contract).
#: ``balance`` is the upstream ``signedBalance`` (asset-positive convention);
#: it is never invented, so a missing balance stays ``null``.
ACCOUNT_HISTORY_RECORD_FIELDS: tuple[str, ...] = (
    "date",
    "balance",
    "account_id",
    "account_name",
)

#: Stable field names for one normalized recent-balances record (v1 contract).
RECENT_BALANCES_RECORD_FIELDS: tuple[str, ...] = ("id", "recent_balances")

#: Stable field names for one normalized aggregate snapshot record (v1 contract).
AGGREGATE_SNAPSHOT_RECORD_FIELDS: tuple[str, ...] = ("date", "balance")

#: Stable field names for one normalized type-scoped snapshot record (v1 contract).
#: ``period`` preserves the upstream ``month`` value verbatim: ``YYYY-MM`` for
#: the ``month`` timeframe, ``YYYY`` for the ``year`` timeframe.
SNAPSHOT_BY_TYPE_RECORD_FIELDS: tuple[str, ...] = ("account_type", "period", "balance")

#: Stable field names for one normalized type-scoped snapshot collection (v1 contract).
SNAPSHOTS_BY_TYPE_FIELDS: tuple[str, ...] = ("snapshots", "account_types")


def _snapshot_record(item: Any, date_key: str, balance_key: str) -> dict[str, Any]:
    """Normalize one balance-history/snapshot entry without inventing values.

    A non-mapping entry, or one with missing fields, yields ``None`` for the
    affected keys rather than a fabricated zero.
    """
    return {
        "date": nested_get(item, date_key),
        "balance": nested_get(item, balance_key),
    }


def transform_account_history(raw: Any) -> list[dict[str, Any]]:
    """Normalize one account's balance-history response.

    The upstream method returns a list of snapshot objects with ``date``,
    ``signedBalance``, and (added by the client) ``accountId``/``accountName``.

    Normalization rules:

    - Records keep upstream order and carry ``date``, ``balance`` (the
      upstream ``signedBalance``), ``account_id``, and ``account_name``.
    - Missing balances and sparse histories stay ``null``/empty; no zero is
      ever fabricated.
    - An absent, ``null``, or non-list root fails with a typed
      :class:`APIError` (the upstream contract is a list).

    Args:
        raw: Raw account-history response (a list of snapshot objects).

    Returns:
        List of normalized history records (see
        :data:`ACCOUNT_HISTORY_RECORD_FIELDS`), in upstream order.

    Raises:
        APIError: If ``raw`` is not a list.
    """
    snapshots = require_list(raw, "account history")
    return [
        {
            "date": nested_get(s, "date"),
            "balance": nested_get(s, "signedBalance"),
            "account_id": nested_get(s, "accountId"),
            "account_name": nested_get(s, "accountName"),
        }
        for s in (item if isinstance(item, Mapping) else {} for item in snapshots)
    ]


def transform_recent_balances(raw: Any) -> list[dict[str, Any]]:
    """Normalize the recent-balances response for all accounts.

    The upstream response is an object with an ``accounts`` list whose items
    carry ``id`` and ``recentBalances`` (each entry with ``date``/``balance``).

    Normalization rules:

    - One stable record per discovered account: ``id`` plus
      ``recent_balances`` (a list of ``date``/``balance`` entries in upstream
      order).
    - Absent or ``null`` account or balance containers normalize to ``[]``;
      missing balance values stay ``null``.

    Args:
        raw: Raw recent-balances response object.

    Returns:
        List of normalized per-account records (see
        :data:`RECENT_BALANCES_RECORD_FIELDS`).

    Raises:
        APIError: If ``raw`` is not an object.
    """
    response = require_object(raw, "recent balances")
    records: list[dict[str, Any]] = []
    for account in list_or_empty(nested_get(response, "accounts")):
        balances = list_or_empty(nested_get(account, "recentBalances"))
        records.append(
            {
                "id": nested_get(account, "id"),
                "recent_balances": [
                    {
                        "date": nested_get(entry, "date"),
                        "balance": nested_get(entry, "balance"),
                    }
                    for entry in (e if isinstance(e, Mapping) else {} for e in balances)
                ],
            }
        )
    return records


def transform_aggregate_snapshots(raw: Any) -> list[dict[str, Any]]:
    """Normalize the aggregate (net-worth) snapshots response.

    Args:
        raw: Raw aggregate-snapshots response object with an
            ``aggregateSnapshots`` list of ``date``/``balance`` entries.

    Returns:
        List of normalized snapshot records (see
        :data:`AGGREGATE_SNAPSHOT_RECORD_FIELDS`), in upstream order.

    Raises:
        APIError: If ``raw`` is not an object.
    """
    response = require_object(raw, "aggregate snapshots")
    return [
        {
            "date": nested_get(entry, "date"),
            "balance": nested_get(entry, "balance"),
        }
        for entry in (
            e if isinstance(e, Mapping) else {}
            for e in list_or_empty(nested_get(response, "aggregateSnapshots"))
        )
    ]


def transform_snapshots_by_type(raw: Any) -> dict[str, Any]:
    """Normalize the type-scoped snapshots response.

    The upstream response carries ``snapshotsByAccountType`` (entries with
    ``accountType``, ``month``, and ``balance``) plus an ``accountTypes``
    list (``name``/``group``). The ``month`` value is preserved verbatim:
    ``YYYY-MM`` precision for the ``month`` timeframe (no day component is
    ever appended) and the upstream's yearly form for the ``year`` timeframe.

    Args:
        raw: Raw type-scoped snapshots response object.

    Returns:
        Dict with documented stable keys (see
        :data:`SNAPSHOTS_BY_TYPE_FIELDS`): ``snapshots`` (records per
        :data:`SNAPSHOT_BY_TYPE_RECORD_FIELDS`) and ``account_types``.

    Raises:
        APIError: If ``raw`` is not an object.
    """
    response = require_object(raw, "type-scoped snapshots")
    snapshots = [
        {
            "account_type": nested_get(entry, "accountType"),
            "period": nested_get(entry, "month"),
            "balance": nested_get(entry, "balance"),
        }
        for entry in (
            e if isinstance(e, Mapping) else {}
            for e in list_or_empty(nested_get(response, "snapshotsByAccountType"))
        )
    ]
    account_types = [
        {
            "name": nested_get(entry, "name"),
            "group": nested_get(entry, "group"),
        }
        for entry in (
            e if isinstance(e, Mapping) else {}
            for e in list_or_empty(nested_get(response, "accountTypes"))
        )
    ]
    return {"snapshots": snapshots, "account_types": account_types}
