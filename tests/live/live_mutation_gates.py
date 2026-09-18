"""Environment collection/runtime gates for the live mutation suite (mc-584r).

Two independent layers keep the disposable-fixture mutation suite from ever
collecting or executing without an explicit, deliberate opt-in:

1. **Collection guard** (:func:`deselect_live_mutation_unless_opted_in`,
   applied by ``tests/live/conftest.py``): nodes marked ``live_mutation`` are
   deselected unless ``MONARCH_LIVE_MUTATION_TESTS=1`` is present. This keeps
   normal (``-m "not live"``) and read-only live
   (``-m "live and not live_mutation"``) runs from ever seeing them.
2. **Runtime guard** (:func:`enforce_runtime_prerequisites`): called from a
   module-scoped/autouse fixture before any fixture setup, it fails closed
   when the dedicated opt-in is absent or the approved household ID is
   missing/malformed. ``MONARCH_LIVE_TESTS`` alone enables neither layer.

Marker-level isolation for the supported ``make`` targets remains the primary
defense; these environment checks are defense in depth, never a substitute.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

#: Dedicated execution opt-in. Deliberately distinct from MONARCH_LIVE_TESTS.
MUTATION_OPT_IN_ENV = "MONARCH_LIVE_MUTATION_TESTS"

#: Exact opaque ID of the owner-approved disposable test household.
HOUSEHOLD_ID_ENV = "MONARCH_LIVE_MUTATION_HOUSEHOLD_ID"

#: Marker identifying live mutation contract nodes.
LIVE_MUTATION_MARKER = "live_mutation"

#: Opaque household identities are single non-empty tokens without whitespace
#: or control characters. The bound is generous but finite so a pasted blob
#: (for example an entire JSON payload) is rejected as malformed.
_HOUSEHOLD_ID_RE = re.compile(r"\S{1,256}\Z")


class LiveMutationPrerequisiteError(RuntimeError):
    """A live mutation prerequisite (collection or runtime) is not satisfied."""


@dataclass(frozen=True)
class RuntimePrerequisites:
    """Verified runtime prerequisites for the live mutation suite."""

    household_id: str


def _env(env: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if env is None else env


def mutation_opt_in_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Return whether ``MONARCH_LIVE_MUTATION_TESTS=1`` is present."""
    return _env(env).get(MUTATION_OPT_IN_ENV) == "1"


def validate_household_id(raw: object) -> str:
    """Validate an approved household ID value.

    Missing, empty, non-string, or malformed values fail closed. The error
    never echoes the supplied value.

    Raises:
        LiveMutationPrerequisiteError: If the value is missing or malformed.
    """
    if not isinstance(raw, str) or not raw:
        raise LiveMutationPrerequisiteError(
            f"{HOUSEHOLD_ID_ENV} must be set to the exact opaque ID of the "
            "owner-approved disposable household; it is missing or empty."
        )
    if not _HOUSEHOLD_ID_RE.match(raw):
        raise LiveMutationPrerequisiteError(
            f"{HOUSEHOLD_ID_ENV} is malformed: the approved household ID must be "
            "a single non-empty token without whitespace or control characters."
        )
    return raw


def household_id_from_env(env: Mapping[str, str] | None = None) -> str:
    """Read and validate the approved household ID from the environment."""
    return validate_household_id(_env(env).get(HOUSEHOLD_ID_ENV))


def verify_household_identity(expected: str, observed: object) -> str:
    """Compare a minimal server-side household ID lookup with the approval.

    Args:
        expected: The validated approved household ID from the environment.
        observed: The value returned by the minimal ``myHousehold { id }``
            lookup.

    Returns:
        The observed ID when it matches exactly.

    Raises:
        LiveMutationPrerequisiteError: If the observed value is missing,
            empty, malformed, or does not match exactly. Messages never echo
            either identity value.
    """
    if not isinstance(observed, str) or not observed:
        raise LiveMutationPrerequisiteError(
            "Household verification failed: the minimal identity lookup did "
            "not return a household ID."
        )
    if not _HOUSEHOLD_ID_RE.match(observed):
        raise LiveMutationPrerequisiteError(
            "Household verification failed: the identity lookup returned a malformed household ID."
        )
    if observed != expected:
        raise LiveMutationPrerequisiteError(
            "Household verification failed: the approved household ID does not "
            "match the authenticated account's household. Refusing to mutate."
        )
    return observed


def enforce_runtime_prerequisites(
    env: Mapping[str, str] | None = None,
) -> RuntimePrerequisites:
    """Fail closed before any fixture setup unless runtime gates are satisfied.

    Independent of marker collection: even if a mutation node were selected
    directly, this guard refuses to proceed without the dedicated opt-in and a
    syntactically valid approved household ID.
    """
    if not mutation_opt_in_enabled(env):
        raise LiveMutationPrerequisiteError(
            f"Live mutation tests require {MUTATION_OPT_IN_ENV}=1. "
            "MONARCH_LIVE_TESTS alone never enables mutation execution; use "
            "`make test-live-mutation`."
        )
    return RuntimePrerequisites(household_id=household_id_from_env(env))


def deselect_live_mutation_unless_opted_in(
    items: Sequence[Any],
    env: Mapping[str, str] | None = None,
) -> list[Any]:
    """Return the ``live_mutation`` nodes to deselect without the opt-in.

    Args:
        items: Collected pytest items.
        env: Environment mapping override (defaults to ``os.environ``).

    Returns:
        The subset of items carrying the ``live_mutation`` marker, or an empty
        list when the dedicated opt-in is enabled.
    """
    if mutation_opt_in_enabled(env):
        return []
    return [item for item in items if LIVE_MUTATION_MARKER in item.keywords]


__all__ = [
    "MUTATION_OPT_IN_ENV",
    "HOUSEHOLD_ID_ENV",
    "LIVE_MUTATION_MARKER",
    "LiveMutationPrerequisiteError",
    "RuntimePrerequisites",
    "mutation_opt_in_enabled",
    "validate_household_id",
    "household_id_from_env",
    "verify_household_identity",
    "enforce_runtime_prerequisites",
    "deselect_live_mutation_unless_opted_in",
]
