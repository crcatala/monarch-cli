"""Tests for cashflow transformer."""

from __future__ import annotations

import pytest

from monarch_cli.core.exceptions import APIError
from monarch_cli.transformers.cashflow import (
    transform_cashflow_detail,
    transform_cashflow_summary,
)


class TestTransformCashflowDetail:
    """Tests for the complete get_cashflow normalization contract."""

    def test_normalizes_all_detail_blocks_and_shared_summary(self) -> None:
        result = transform_cashflow_detail(
            {
                "byCategory": [
                    {
                        "groupBy": {
                            "category": {
                                "id": "cat-food",
                                "name": "Food",
                                "group": {"id": "group-need", "type": "needs"},
                            }
                        },
                        "summary": [{"sum": -125.5}],
                    }
                ],
                "byCategoryGroup": [
                    {
                        "groupBy": {
                            "categoryGroup": {"id": "group-need", "name": "Needs", "type": "needs"}
                        },
                        "summary": [{"sum": -125.5}],
                    }
                ],
                "byMerchant": [
                    {
                        "groupBy": {
                            "merchant": {
                                "id": "merchant-1",
                                "name": "Market",
                                "logoUrl": "https://logo",
                            }
                        },
                        "summary": [{"sumIncome": 10.0, "sumExpense": -125.5}],
                    }
                ],
                "summary": [
                    {
                        "summary": {
                            "sumIncome": 10.0,
                            "sumExpense": -125.5,
                            "savings": -115.5,
                            "savingsRate": -1155.0,
                        }
                    }
                ],
            }
        )

        assert result == {
            "categories": [
                {
                    "id": "cat-food",
                    "name": "Food",
                    "group_id": "group-need",
                    "group_type": "needs",
                    "amount": -125.5,
                }
            ],
            "category_groups": [
                {"id": "group-need", "name": "Needs", "type": "needs", "amount": -125.5}
            ],
            "merchants": [
                {
                    "id": "merchant-1",
                    "name": "Market",
                    "logo_url": "https://logo",
                    "income": 10.0,
                    "expenses": 125.5,
                }
            ],
            "summary": {
                "income": 10.0,
                "expenses": 125.5,
                "savings": -115.5,
                "savings_rate": -1155.0,
            },
        }

    def test_normalizes_released_object_summary_shape(self) -> None:
        result = transform_cashflow_detail(
            {
                "byCategory": [
                    {
                        "groupBy": {
                            "category": {
                                "id": "cat-food",
                                "name": "Food",
                                "group": {"id": "group-need", "type": "needs"},
                            }
                        },
                        "summary": {"sum": -25.0},
                    }
                ],
                "byCategoryGroup": [
                    {
                        "groupBy": {
                            "categoryGroup": {
                                "id": "group-need",
                                "name": "Needs",
                                "type": "needs",
                            }
                        },
                        "summary": {"sum": -25.0},
                    }
                ],
                "byMerchant": [
                    {
                        "groupBy": {
                            "merchant": {
                                "id": "merchant-1",
                                "name": "Market",
                                "logoUrl": "https://logo",
                            }
                        },
                        "summary": {"sumIncome": 5.0, "sumExpense": -25.0},
                    }
                ],
                "summary": [
                    {
                        "summary": {
                            "sumIncome": 5.0,
                            "sumExpense": -25.0,
                            "savings": -20.0,
                            "savingsRate": -400.0,
                        }
                    }
                ],
            }
        )

        assert result["categories"][0]["amount"] == -25.0
        assert result["category_groups"][0]["amount"] == -25.0
        assert result["merchants"][0]["income"] == 5.0
        assert result["merchants"][0]["expenses"] == 25.0
        assert result["summary"] == {
            "income": 5.0,
            "expenses": 25.0,
            "savings": -20.0,
            "savings_rate": -400.0,
        }

    def test_missing_and_partial_detail_data_is_stable(self) -> None:
        result = transform_cashflow_detail(
            {
                "byCategory": [None, {"groupBy": {"category": None}, "summary": [None]}],
                "byCategoryGroup": None,
                "byMerchant": [{"groupBy": {"merchant": None}, "summary": None}],
                "summary": None,
            }
        )

        assert result == {
            "categories": [
                {"id": None, "name": None, "group_id": None, "group_type": None, "amount": None},
                {"id": None, "name": None, "group_id": None, "group_type": None, "amount": None},
            ],
            "category_groups": [],
            "merchants": [
                {"id": None, "name": None, "logo_url": None, "income": None, "expenses": None}
            ],
            "summary": {"income": 0.0, "expenses": 0.0, "savings": 0.0, "savings_rate": 0.0},
        }

    def test_non_object_root_raises_typed_error(self) -> None:
        with pytest.raises(APIError):
            transform_cashflow_detail(None)


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

    def test_handles_present_but_null_summary_container(self) -> None:
        """A present-but-null summary container normalizes to the zero summary."""
        result = transform_cashflow_summary({"summary": None})
        assert result == {
            "income": 0.0,
            "expenses": 0.0,
            "savings": 0.0,
            "savings_rate": 0.0,
        }

    def test_handles_present_but_null_inner_summary(self) -> None:
        """A null inner summary block normalizes to the zero summary."""
        result = transform_cashflow_summary({"summary": [{"summary": None}]})
        assert result == {
            "income": 0.0,
            "expenses": 0.0,
            "savings": 0.0,
            "savings_rate": 0.0,
        }

    def test_handles_null_summary_element(self) -> None:
        """A null element in the summary list normalizes to the zero summary."""
        result = transform_cashflow_summary({"summary": [None]})
        assert result == {
            "income": 0.0,
            "expenses": 0.0,
            "savings": 0.0,
            "savings_rate": 0.0,
        }

    def test_handles_partial_summary(self) -> None:
        """Missing aggregate keys fall back to zero without raising."""
        result = transform_cashflow_summary({"summary": [{"summary": {"sumIncome": 100.0}}]})
        assert result == {
            "income": 100.0,
            "expenses": 0,
            "savings": 0,
            "savings_rate": 0,
        }

    def test_handles_non_numeric_aggregates(self) -> None:
        """Non-numeric aggregate values degrade to the documented zero default."""
        result = transform_cashflow_summary(
            {"summary": [{"summary": {"sumIncome": "oops", "sumExpense": True}}]}
        )
        assert result["income"] == 0
        assert result["expenses"] == 0

    def test_non_object_root_raises_typed_error(self) -> None:
        """A malformed (non-object) cashflow payload fails deliberately."""
        with pytest.raises(APIError):
            transform_cashflow_summary(None)  # type: ignore[arg-type]
        with pytest.raises(APIError):
            transform_cashflow_summary(["not", "an", "object"])  # type: ignore[arg-type]

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
