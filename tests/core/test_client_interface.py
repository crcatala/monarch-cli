"""Tests to verify MonarchMoney client has required methods.

These tests ensure the upstream monarchmoney library provides the methods
our CLI depends on. If a method is missing or renamed, we'll catch it here
rather than at runtime.
"""

from __future__ import annotations

import inspect

import pytest
from monarchmoney import MonarchMoney


class TestMonarchMoneyInterface:
    """Verify MonarchMoney client has expected methods."""

    # Methods required by our CLI commands
    REQUIRED_METHODS = [
        "get_accounts",
        "get_transactions",
        "get_transaction_details",
        "get_budgets",
        "get_cashflow_summary",
        "get_cashflow",
        "get_transaction_categories",
        "update_transaction",
        "request_accounts_refresh",
        "get_transaction_tags",
        "create_transaction_tag",
        "set_transaction_tags",
        "get_transaction_splits",
        "update_transaction_splits",
        "get_institutions",
        "get_subscription_details",
        "get_account_holdings",
    ]

    @pytest.mark.parametrize("method_name", REQUIRED_METHODS)
    def test_client_has_required_method(self, method_name: str) -> None:
        """Verify MonarchMoney client has the required method."""
        assert hasattr(MonarchMoney, method_name), (
            f"MonarchMoney is missing required method: {method_name}. "
            f"The upstream library may have changed its API."
        )

    def test_get_transactions_exposes_released_filter_surface(self) -> None:
        """The pinned minimum client exposes every CLI filter argument."""
        parameters = inspect.signature(MonarchMoney.get_transactions).parameters
        assert {
            "category_ids",
            "account_ids",
            "tag_ids",
            "has_attachments",
            "has_notes",
            "hidden_from_reports",
            "is_split",
            "is_recurring",
            "is_pending",
            "imported_from_mint",
            "synced_from_institution",
            "needs_review",
            "transaction_visibility",
        } <= set(parameters)

    @pytest.mark.parametrize("method_name", REQUIRED_METHODS)
    def test_required_method_is_callable(self, method_name: str) -> None:
        """Verify required methods are callable (not just attributes)."""
        method = getattr(MonarchMoney, method_name, None)
        assert callable(method), (
            f"MonarchMoney.{method_name} exists but is not callable. "
            f"Expected a method, got {type(method)}."
        )


class TestMonarchMoneyOwnershipSurface:
    """Contract for the declared upstream-client compatibility floor.

    Household ownership normalization (``owner_id``/``owner_name``/
    ``ownership_overridden_at``) is only meaningful when the pinned client
    floor (``monarchmoneycommunity>=1.5.2``) actually selects the upstream
    ``ownedByUser`` relationship and ``ownershipOverriddenAt`` timestamp.
    The CLI declares that floor in pyproject; clean installs resolve at least
    it, so these tests inspect the installed client source and fail loudly
    if a future resolution drops the fields this CLI normalizes.
    """

    @staticmethod
    def _client_source() -> str:
        import inspect

        return inspect.getsource(MonarchMoney)

    def test_accounts_query_selects_owned_by_user_with_display_name(
        self,
    ) -> None:
        """The accounts read selects ``ownedByUser { id displayName ... }``."""
        import re

        match = re.search(r"ownedByUser\s*\{[^}]*\}", self._client_source())
        assert match, "No ownedByUser selection found in the installed client"
        assert "id" in match.group(0)
        assert "displayName" in match.group(0)

    def test_transaction_queries_select_owned_by_user_with_name(self) -> None:
        """Transaction reads select ``ownedByUser { id name ... }``."""
        import re

        selections = re.findall(r"ownedByUser\s*\{[^}]*\}", self._client_source())
        assert selections, "No ownedByUser selection found in the installed client"
        assert any("name" in selection for selection in selections), (
            "No ownedByUser selection with `name` found; transaction owner_name "
            "normalization requires the declared client floor"
        )

    def test_client_selects_ownership_overridden_at(self) -> None:
        """Transaction reads select the literal ``ownershipOverriddenAt`` timestamp."""
        assert "ownershipOverriddenAt" in self._client_source(), (
            "ownershipOverriddenAt missing from the installed client; "
            "the declared monarchmoneycommunity>=1.5.2 floor must be preserved"
        )

    def test_accounts_query_selects_liability_and_debt_service_fields(self) -> None:
        """The accounts read selects the literal liability metadata fields."""
        client_source = self._client_source()
        for field in (
            "isAsset",
            "limit",
            "dataProviderCreditLimit",
            "apr",
            "interestRate",
            "minimumPayment",
            "plannedPayment",
            "excludeFromDebtPaydown",
        ):
            assert field in client_source, (
                f"{field} missing from the installed client; liability "
                "normalization requires the declared client floor"
            )

    def test_accounts_query_selects_stable_type_names(self) -> None:
        """The accounts read selects ``type.name``/``subtype.name`` identifiers."""
        import re

        client_source = self._client_source()
        type_block = re.search(r"type\s*\{[^}]*\}", client_source)
        subtype_block = re.search(r"subtype\s*\{[^}]*\}", client_source)
        assert type_block and subtype_block, "type/subtype selections missing"
        assert "name" in type_block.group(0)
        assert "name" in subtype_block.group(0)
