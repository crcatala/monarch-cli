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
- A present-but-null nested relationship (for example ``institution: null``)
  yields ``null`` rather than raising.
- Unknown additive upstream fields are ignored.
- ``--raw`` output bypasses these transformers entirely and preserves the
  upstream structure, including null containers and unknown fields.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .nesting import bool_or_default, list_or_empty, nested_get, require_object


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
