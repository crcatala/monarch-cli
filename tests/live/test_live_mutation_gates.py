"""Unit tests for the live mutation collection/runtime gates (mc-584r).

These are ordinary, non-live tests: they never spawn a CLI subprocess or call
the Monarch API, so they run in the default ``-m "not live"`` suite. They prove
the collection guard, the independent runtime prerequisite guard, and the
explicit household identity validation all fail closed.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.live import live_mutation_gates as gates


class _FakeItem:
    """Minimal pytest-item stand-in exposing ``keywords``."""

    def __init__(self, nodeid: str, keywords: set[str]) -> None:
        self.nodeid = nodeid
        self.keywords = set(keywords)


def _live_mutation_item() -> _FakeItem:
    return _FakeItem("tests/live/test_live_mutation_api.py::test_x", {"live", "live_mutation"})


def _read_only_item() -> _FakeItem:
    return _FakeItem("tests/live/test_live_api.py::test_y", {"live"})


# --- Dedicated opt-in -------------------------------------------------------


def test_opt_in_requires_exact_value() -> None:
    assert gates.mutation_opt_in_enabled({gates.MUTATION_OPT_IN_ENV: "1"}) is True
    assert gates.mutation_opt_in_enabled({gates.MUTATION_OPT_IN_ENV: "true"}) is False
    assert gates.mutation_opt_in_enabled({gates.MUTATION_OPT_IN_ENV: "0"}) is False
    assert gates.mutation_opt_in_enabled({}) is False


def test_read_only_live_opt_in_never_enables_mutations() -> None:
    # MONARCH_LIVE_TESTS is a different, deliberate opt-in.
    env = {"MONARCH_LIVE_TESTS": "1"}
    assert gates.mutation_opt_in_enabled(env) is False
    with pytest.raises(gates.LiveMutationPrerequisiteError):
        gates.enforce_runtime_prerequisites(env)


# --- Collection guard -------------------------------------------------------


def test_collection_guard_deselects_mutation_nodes_without_opt_in() -> None:
    items: list[Any] = [_read_only_item(), _live_mutation_item()]
    deselected = gates.deselect_live_mutation_unless_opted_in(items, env={})
    assert [item.nodeid for item in deselected] == ["tests/live/test_live_mutation_api.py::test_x"]


def test_collection_guard_keeps_mutation_nodes_with_opt_in() -> None:
    items: list[Any] = [_read_only_item(), _live_mutation_item()]
    deselected = gates.deselect_live_mutation_unless_opted_in(
        items, env={gates.MUTATION_OPT_IN_ENV: "1"}
    )
    assert deselected == []


# --- Household ID validation ------------------------------------------------


def test_validate_household_id_missing_or_empty_fails() -> None:
    for value in (None, "", 123, b"abc"):
        with pytest.raises(gates.LiveMutationPrerequisiteError):
            gates.validate_household_id(value)


def test_validate_household_id_malformed_fails() -> None:
    for value in ("has space", "line\nbreak", "x" * 257):
        with pytest.raises(gates.LiveMutationPrerequisiteError):
            gates.validate_household_id(value)


def test_validate_household_id_valid_token() -> None:
    assert gates.validate_household_id("opaque-token-123") == "opaque-token-123"


def test_validate_household_id_error_never_echoes_value() -> None:
    secret_like = "SECRET-VALUE-SHOULD-NOT-APPEAR" + " " + "extra"
    with pytest.raises(gates.LiveMutationPrerequisiteError) as excinfo:
        gates.validate_household_id(secret_like)
    assert "SECRET-VALUE" not in str(excinfo.value)


# --- Household identity verification ---------------------------------------


def test_verify_household_identity_exact_match() -> None:
    assert gates.verify_household_identity("hh-abc", "hh-abc") == "hh-abc"


def test_verify_household_identity_mismatch_fails() -> None:
    with pytest.raises(gates.LiveMutationPrerequisiteError):
        gates.verify_household_identity("hh-abc", "hh-other")


def test_verify_household_identity_empty_or_malformed_fails() -> None:
    for observed in (None, "", 0, "bad value"):
        with pytest.raises(gates.LiveMutationPrerequisiteError):
            gates.verify_household_identity("hh-abc", observed)


def test_verify_household_identity_error_never_echoes_identities() -> None:
    with pytest.raises(gates.LiveMutationPrerequisiteError) as excinfo:
        gates.verify_household_identity("APPROVED-SECRET", "OBSERVED-SECRET")
    message = str(excinfo.value)
    assert "APPROVED-SECRET" not in message
    assert "OBSERVED-SECRET" not in message


# --- Runtime prerequisite guard --------------------------------------------


def test_runtime_guard_fails_without_opt_in() -> None:
    with pytest.raises(gates.LiveMutationPrerequisiteError):
        gates.enforce_runtime_prerequisites({gates.HOUSEHOLD_ID_ENV: "hh-abc"})


def test_runtime_guard_fails_without_household_id() -> None:
    with pytest.raises(gates.LiveMutationPrerequisiteError):
        gates.enforce_runtime_prerequisites({gates.MUTATION_OPT_IN_ENV: "1"})


def test_runtime_guard_passes_with_opt_in_and_valid_id() -> None:
    prereqs = gates.enforce_runtime_prerequisites(
        {gates.MUTATION_OPT_IN_ENV: "1", gates.HOUSEHOLD_ID_ENV: "hh-abc"}
    )
    assert prereqs.household_id == "hh-abc"


def test_household_id_from_env_reads_and_validates() -> None:
    assert gates.household_id_from_env({gates.HOUSEHOLD_ID_ENV: "hh-abc"}) == "hh-abc"
    with pytest.raises(gates.LiveMutationPrerequisiteError):
        gates.household_id_from_env({})
