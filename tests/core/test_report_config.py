"""Saved report creation preserves URL filters and rejects unsupported settings."""

import pytest

from monarch_cli.core.exceptions import ValidationError
from monarch_cli.core.report_config import build_create_input

URL = "https://app.monarch.com/reports/cash-flow?tags=253277239843441604"


def test_example_url():
    data = build_create_input(" Trip ", url=URL)
    assert data == {
        "displayName": "Trip",
        "transactionFilters": {
            "tags": ["253277239843441604"],
            "transactionVisibility": "non_hidden_transactions_only",
        },
        "reportView": {
            "analysisScope": "cash_flow",
            "chartType": "sankey",
            "chartCalculation": "sum",
            "dimensions": ["category", "category_group"],
        },
    }


def test_multiple_tags_exclusions_and_false():
    data = build_create_input(
        "Example", url=URL + ",42&tags=43&excludeAccounts=10,20&isPending=false"
    )
    assert data["transactionFilters"]["tags"] == ["253277239843441604", "42", "43"]
    assert data["transactionFilters"]["excludeAccounts"] == ["10", "20"]
    assert data["transactionFilters"]["isPending"] is False


def test_relative_dates_and_chart():
    data = build_create_input(
        "Income",
        url="https://app.monarch.com/reports/income?timeframeUnit=month&timeframeValue=3&timeframeIncludeCurrent=true&chartType=stackedBarChart&groupByTimeframe=month",
    )
    assert data["transactionFilters"]["timeframePeriod"] == {
        "unit": "month",
        "value": 3,
        "includeCurrent": True,
    }
    assert data["reportView"] == {
        "analysisScope": "income",
        "chartType": "bar",
        "chartLayout": "vertical",
        "chartDensity": "stacked",
        "chartCalculation": "difference",
        "dimensions": ["category"],
        "timeframe": "month",
    }


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/reports/cash-flow?tags=1",
        "https://app.monarch.com/transactions?tags=1",
        URL + "&unknown=true",
        URL + "&isPending=perhaps",
        URL + "&chartType=unknown",
        URL + "&startDate=bad",
        URL + "&startDate=2026-11-15&endDate=2026-11-01",
        URL + "&timeframeUnit=month",
        URL + "&timeframeValue=3",
        URL + "&timeframeUnit=month&timeframeValue=3&startDate=2026-11-01",
        URL + "&isPending=true&isPending=false",
        URL + "&tags=",
        URL + "&chartType=pieChart",
        URL + "&groupMode=unknown",
    ],
)
def test_invalid_url_is_not_silently_changed(url):
    with pytest.raises(ValidationError):
        build_create_input("Example", url=url)


def test_explicit_filters_and_view():
    data = build_create_input(
        "Custom",
        filters={"tags": ["1"], "hasNotes": False},
        view={"analysisScope": "spending", "chartType": "pie", "dimensions": ["merchant"]},
    )
    assert data["reportView"]["chartType"] == "pie"
    assert data["transactionFilters"]["hasNotes"] is False


@pytest.mark.parametrize(
    "kwargs",
    [
        {"filters": {"tagIds": ["1"]}},
        {"filters": {"tags": "1"}},
        {"filters": {"hasNotes": "false"}},
        {"view": {"unknown": "x"}},
        {"view": {"analysisScope": "cash_flow", "chartType": "bad"}},
        {"url": URL, "filters": {"tags": ["2"]}},
        {"url": URL, "view": {}},
    ],
)
def test_invalid_config(kwargs):
    with pytest.raises(ValidationError):
        build_create_input("Example", **kwargs)


def test_empty_name():
    with pytest.raises(ValidationError):
        build_create_input(" ")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"filters": {"timeframePeriod": {"unit": [], "value": 1, "includeCurrent": True}}},
        {"filters": {"transactionVisibility": []}},
        {"view": {"analysisScope": [], "chartType": "pie"}},
        {"view": {"analysisScope": "income", "chartType": "pie", "timeframe": []}},
        {"view": {"analysisScope": "cash_flow", "chartType": "pie"}},
        {"url": "https://[bad"},
        {"url": URL + "&chartType=horizontalBarChart&groupByEntity=made_up"},
    ],
)
def test_malformed_types_and_unsupported_chart_combinations(kwargs):
    with pytest.raises(ValidationError):
        build_create_input("Example", **kwargs)
