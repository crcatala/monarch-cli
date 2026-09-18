"""Unit tests for the reusable null-safe transformer traversal boundary.

These helpers are the single place where the account, transaction, and
cashflow transformers tolerate incomplete, nullable, or evolving upstream
response shapes. They are exercised indirectly by the entity transformer
tests; this module pins their behavior directly so the boundary contract does
not drift silently.
"""

from __future__ import annotations

import math

import pytest

from monarch_cli.core.exceptions import APIError
from monarch_cli.transformers.nesting import (
    bool_or_default,
    list_or_empty,
    mapping_or_empty,
    nested_get,
    number_or_zero,
    require_object,
)


class TestRequireObject:
    """``require_object`` fails malformed roots deliberately and typed."""

    def test_returns_same_mapping_for_object(self) -> None:
        payload = {"a": 1}
        assert require_object(payload, "thing") is payload

    @pytest.mark.parametrize("value", [None, [], ["x"], "string", 3, 3.5, True])
    def test_non_object_root_raises_typed_error(self, value: object) -> None:
        with pytest.raises(APIError) as exc_info:
            require_object(value, "widget")
        assert exc_info.value.code.value == "API_ERROR"
        assert exc_info.value.details["expected"] == "object"
        assert exc_info.value.details["received"] == type(value).__name__

    def test_error_message_names_the_context(self) -> None:
        with pytest.raises(APIError) as exc_info:
            require_object(None, "cashflow summary")
        assert "cashflow summary" in exc_info.value.message


class TestNestedGet:
    """``nested_get`` walks mappings and stops safely on unusable nodes."""

    def test_follows_path_through_nested_mappings(self) -> None:
        source = {"a": {"b": {"c": 42}}}
        assert nested_get(source, "a", "b", "c") == 42
        assert nested_get(source, "a", "b") == {"c": 42}

    def test_missing_key_yields_none(self) -> None:
        assert nested_get({}, "a") is None
        assert nested_get({"a": {}}, "a", "b") is None

    def test_present_but_null_intermediate_yields_none(self) -> None:
        # The regression this boundary exists to fix: `.get("a", {}).get("b")`
        # would raise AttributeError on a present-but-null intermediate.
        assert nested_get({"a": None}, "a", "b") is None

    def test_non_mapping_intermediate_yields_none(self) -> None:
        assert nested_get({"a": [1, 2]}, "a", "b") is None
        assert nested_get({"a": "text"}, "a", "b") is None
        assert nested_get(None, "a", "b") is None

    def test_returns_existing_falsy_value_unchanged(self) -> None:
        assert nested_get({"a": {"b": 0}}, "a", "b") == 0
        assert nested_get({"a": {"b": False}}, "a", "b") is False
        assert nested_get({"a": {"b": ""}}, "a", "b") == ""


class TestMappingOrEmpty:
    """``mapping_or_empty`` normalizes unusable containers to ``{}``."""

    def test_mapping_passes_through(self) -> None:
        payload = {"a": 1}
        assert mapping_or_empty(payload) is payload

    @pytest.mark.parametrize("value", [None, [], [1, 2], "text", 3])
    def test_non_mapping_normalizes_empty(self, value: object) -> None:
        assert mapping_or_empty(value) == {}


class TestListOrEmpty:
    """``list_or_empty`` normalizes absent/null/unusable containers to ``[]``."""

    def test_list_is_copied(self) -> None:
        payload = [1, 2, 3]
        result = list_or_empty(payload)
        assert result == payload
        assert result is not payload

    @pytest.mark.parametrize("value", [None, {}, {"a": 1}, "text", 3, (1, 2)])
    def test_non_list_normalizes_empty(self, value: object) -> None:
        assert list_or_empty(value) == []


class TestBoolOrDefault:
    """``bool_or_default`` always yields a real ``bool``."""

    def test_real_booleans_are_preserved(self) -> None:
        assert bool_or_default(True, False) is True
        assert bool_or_default(False, True) is False

    def test_none_uses_documented_default(self) -> None:
        assert bool_or_default(None, True) is True
        assert bool_or_default(None, False) is False

    @pytest.mark.parametrize(
        ("value", "expected"),
        [(0, False), (1, True), ("", False), ("x", True), ([], False), ([1], True)],
    )
    def test_present_non_bool_coerced_by_truthiness(self, value: object, expected: bool) -> None:
        result = bool_or_default(value, False)
        assert result is expected
        assert isinstance(result, bool)


class TestNumberOrZero:
    """``number_or_zero`` backs the documented cashflow zero-for-no-data rule."""

    @pytest.mark.parametrize("value", [0, 0.0, 12, -3.5, 1e9])
    def test_numeric_values_pass_through_unchanged(self, value: int | float) -> None:
        assert number_or_zero(value) == value

    def test_unavailable_or_malformed_yields_zero(self) -> None:
        assert number_or_zero(None) == 0
        assert number_or_zero("12") == 0
        assert number_or_zero("oops") == 0
        assert number_or_zero([]) == 0

    def test_booleans_are_rejected(self) -> None:
        # A boolean must never leak in as a monetary amount.
        assert number_or_zero(True) == 0
        assert number_or_zero(False) == 0

    def test_nan_and_infinity_are_left_to_the_caller(self) -> None:
        # The helper does not silently sanitize real numeric payloads.
        assert math.isnan(number_or_zero(float("nan")))
