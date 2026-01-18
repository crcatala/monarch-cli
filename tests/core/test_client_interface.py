"""Tests to verify MonarchMoney client has required methods.

These tests ensure the upstream monarchmoney library provides the methods
our CLI depends on. If a method is missing or renamed, we'll catch it here
rather than at runtime.
"""

from __future__ import annotations

import pytest
from monarchmoney import MonarchMoney


class TestMonarchMoneyInterface:
    """Verify MonarchMoney client has expected methods."""

    # Methods required by our CLI commands
    REQUIRED_METHODS = [
        "get_accounts",
        "get_transactions",
        "get_budgets",
        "get_cashflow_summary",
        "get_transaction_categories",
        "update_transaction",
        "request_accounts_refresh",
    ]

    @pytest.mark.parametrize("method_name", REQUIRED_METHODS)
    def test_client_has_required_method(self, method_name: str) -> None:
        """Verify MonarchMoney client has the required method."""
        assert hasattr(MonarchMoney, method_name), (
            f"MonarchMoney is missing required method: {method_name}. "
            f"The upstream library may have changed its API."
        )

    @pytest.mark.parametrize("method_name", REQUIRED_METHODS)
    def test_required_method_is_callable(self, method_name: str) -> None:
        """Verify required methods are callable (not just attributes)."""
        method = getattr(MonarchMoney, method_name, None)
        assert callable(method), (
            f"MonarchMoney.{method_name} exists but is not callable. "
            f"Expected a method, got {type(method)}."
        )
