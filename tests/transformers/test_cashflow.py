"""Tests for cashflow transformer."""

from __future__ import annotations

from monarch_cli.transformers.cashflow import transform_cashflow_summary


class TestTransformCashflowSummary:
    """Tests for transform_cashflow_summary function."""

    def test_transforms_nested_api_response(self) -> None:
        """Transform nested API response to flat structure."""
        api_response = {
            "summary": [
                {
                    "summary": {
                        "sumIncome": 5000.00,
                        "sumExpense": -3500.00,
                        "savings": 1500.00,
                        "savingsRate": 30.0,
                        "__typename": "TransactionsSummary",
                    },
                    "__typename": "AggregateData",
                }
            ]
        }

        result = transform_cashflow_summary(api_response)

        assert result == {
            "income": 5000.00,
            "expenses": 3500.00,  # Converted to positive
            "savings": 1500.00,
            "savings_rate": 30.0,
        }

    def test_converts_negative_expenses_to_positive(self) -> None:
        """Expenses are converted from negative to positive."""
        api_response = {
            "summary": [
                {
                    "summary": {
                        "sumIncome": 1000.00,
                        "sumExpense": -750.50,
                        "savings": 249.50,
                        "savingsRate": 24.95,
                    },
                }
            ]
        }

        result = transform_cashflow_summary(api_response)

        assert result["expenses"] == 750.50  # Positive value

    def test_handles_zero_values(self) -> None:
        """Handle zero values correctly."""
        api_response = {
            "summary": [
                {
                    "summary": {
                        "sumIncome": 0.0,
                        "sumExpense": 0.0,
                        "savings": 0.0,
                        "savingsRate": 0.0,
                    },
                }
            ]
        }

        result = transform_cashflow_summary(api_response)

        assert result == {
            "income": 0.0,
            "expenses": 0.0,
            "savings": 0.0,
            "savings_rate": 0.0,
        }

    def test_handles_negative_savings(self) -> None:
        """Handle negative savings (spending more than income)."""
        api_response = {
            "summary": [
                {
                    "summary": {
                        "sumIncome": 1000.00,
                        "sumExpense": -1500.00,
                        "savings": -500.00,
                        "savingsRate": -50.0,
                    },
                }
            ]
        }

        result = transform_cashflow_summary(api_response)

        assert result["income"] == 1000.00
        assert result["expenses"] == 1500.00  # Still positive
        assert result["savings"] == -500.00  # Negative is preserved
        assert result["savings_rate"] == -50.0

    def test_handles_empty_summary_list(self) -> None:
        """Handle empty summary list gracefully."""
        api_response = {"summary": []}

        result = transform_cashflow_summary(api_response)

        assert result == {
            "income": 0.0,
            "expenses": 0.0,
            "savings": 0.0,
            "savings_rate": 0.0,
        }

    def test_handles_missing_summary_key(self) -> None:
        """Handle missing summary key gracefully."""
        api_response = {}

        result = transform_cashflow_summary(api_response)

        assert result == {
            "income": 0.0,
            "expenses": 0.0,
            "savings": 0.0,
            "savings_rate": 0.0,
        }

    def test_handles_none_values_in_response(self) -> None:
        """Handle None values in API response."""
        api_response = {
            "summary": [
                {
                    "summary": {
                        "sumIncome": None,
                        "sumExpense": None,
                        "savings": None,
                        "savingsRate": None,
                    },
                }
            ]
        }

        result = transform_cashflow_summary(api_response)

        assert result == {
            "income": 0.0,
            "expenses": 0.0,
            "savings": 0.0,
            "savings_rate": 0.0,
        }

    def test_handles_missing_inner_summary(self) -> None:
        """Handle missing inner summary key."""
        api_response = {
            "summary": [
                {
                    "__typename": "AggregateData",
                }
            ]
        }

        result = transform_cashflow_summary(api_response)

        assert result == {
            "income": 0.0,
            "expenses": 0.0,
            "savings": 0.0,
            "savings_rate": 0.0,
        }

    def test_output_keys_are_snake_case(self) -> None:
        """Output uses snake_case keys for consistency."""
        api_response = {
            "summary": [
                {
                    "summary": {
                        "sumIncome": 100.0,
                        "sumExpense": -50.0,
                        "savings": 50.0,
                        "savingsRate": 50.0,
                    },
                }
            ]
        }

        result = transform_cashflow_summary(api_response)

        assert "income" in result
        assert "expenses" in result
        assert "savings" in result
        assert "savings_rate" in result
        # Should NOT have camelCase keys
        assert "sumIncome" not in result
        assert "savingsRate" not in result
