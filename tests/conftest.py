"""Pytest configuration and shared fixtures.

This module provides common fixtures used across multiple test modules.
Fixtures are designed to be composable and represent common test data patterns.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

if TYPE_CHECKING:
    pass


@pytest.fixture
def mock_monarch_client() -> MagicMock:
    """Create a mock MonarchMoney client.

    This fixture provides a MagicMock that can be used to simulate
    the MonarchMoney API client in tests without making real API calls.

    Returns:
        MagicMock configured as a monarch client
    """
    mock_client = MagicMock()
    mock_client.token = "test-token-12345"
    return mock_client


@pytest.fixture
def sample_accounts() -> list[dict]:
    """Sample account data in transformed (output) format.

    Provides a list of account dictionaries as they would appear
    after transformation from the API response.

    Returns:
        List of account dictionaries
    """
    return [
        {
            "id": "acc_123",
            "name": "Chase Checking",
            "type": "Checking",
            "subtype": "Checking",
            "balance": 1234.56,
            "institution": "Chase",
            "is_hidden": False,
            "is_manual": False,
            "updated_at": "2024-01-15T10:30:00Z",
        },
        {
            "id": "acc_456",
            "name": "Savings Account",
            "type": "Savings",
            "subtype": "Savings",
            "balance": 5000.00,
            "institution": "Ally Bank",
            "is_hidden": False,
            "is_manual": True,
            "updated_at": "2024-01-14T09:00:00Z",
        },
        {
            "id": "acc_789",
            "name": "Credit Card",
            "type": "Credit",
            "subtype": "Credit Card",
            "balance": -500.00,
            "institution": "Capital One",
            "is_hidden": False,
            "is_manual": False,
            "updated_at": "2024-01-13T08:00:00Z",
        },
    ]


@pytest.fixture
def sample_transactions() -> list[dict]:
    """Sample transaction data in transformed (output) format.

    Provides a list of transaction dictionaries as they would appear
    after transformation from the API response.

    Returns:
        List of transaction dictionaries
    """
    return [
        {
            "id": "txn_001",
            "date": "2024-01-15",
            "amount": -45.67,
            "description": "Coffee Shop",
            "original_description": "COFFEE SHOP #123",
            "category": "Food & Drink",
            "account_id": "acc_123",
            "account_name": "Chase Checking",
            "is_pending": False,
            "notes": None,
            "tags": [],
        },
        {
            "id": "txn_002",
            "date": "2024-01-14",
            "amount": 2500.00,
            "description": "Payroll",
            "original_description": "ACME CORP PAYROLL",
            "category": "Income",
            "account_id": "acc_123",
            "account_name": "Chase Checking",
            "is_pending": False,
            "notes": "January paycheck",
            "tags": ["income", "salary"],
        },
        {
            "id": "txn_003",
            "date": "2024-01-13",
            "amount": -120.00,
            "description": "Electric Bill",
            "original_description": "POWER COMPANY",
            "category": "Utilities",
            "account_id": "acc_123",
            "account_name": "Chase Checking",
            "is_pending": True,
            "notes": None,
            "tags": ["bills"],
        },
    ]


@pytest.fixture
def sample_accounts_raw() -> dict:
    """Sample accounts in raw API response format.

    Provides account data as it comes from the MonarchMoney API
    before transformation.

    Returns:
        Dict with 'accounts' key containing list of raw account data
    """
    return {
        "accounts": [
            {
                "id": "acc_123",
                "displayName": "Chase Checking",
                "type": {"display": "Checking"},
                "subtype": {"display": "Checking"},
                "currentBalance": 1234.56,
                "institution": {"name": "Chase"},
                "isHidden": False,
                "isManual": False,
                "updatedAt": "2024-01-15T10:30:00Z",
            },
            {
                "id": "acc_456",
                "displayName": "Savings Account",
                "type": {"display": "Savings"},
                "subtype": {"display": "Savings"},
                "currentBalance": 5000.00,
                "institution": {"name": "Ally Bank"},
                "isHidden": False,
                "isManual": True,
                "updatedAt": "2024-01-14T09:00:00Z",
            },
        ]
    }


@pytest.fixture
def sample_transactions_raw() -> dict:
    """Sample transactions in raw API response format.

    Provides transaction data as it comes from the MonarchMoney API
    before transformation.

    Returns:
        Dict with transaction data in API format
    """
    return {
        "allTransactions": {
            "results": [
                {
                    "id": "txn_001",
                    "date": "2024-01-15",
                    "amount": -45.67,
                    "merchant": {"name": "Coffee Shop"},
                    "plaidName": "COFFEE SHOP #123",
                    "category": {"name": "Food & Drink"},
                    "account": {"id": "acc_123", "displayName": "Chase Checking"},
                    "pending": False,
                    "notes": None,
                    "tags": [],
                },
                {
                    "id": "txn_002",
                    "date": "2024-01-14",
                    "amount": 2500.00,
                    "merchant": {"name": "Payroll"},
                    "plaidName": "ACME CORP PAYROLL",
                    "category": {"name": "Income"},
                    "account": {"id": "acc_123", "displayName": "Chase Checking"},
                    "pending": False,
                    "notes": "January paycheck",
                    "tags": [{"name": "income"}, {"name": "salary"}],
                },
            ],
            "totalCount": 2,
        }
    }
