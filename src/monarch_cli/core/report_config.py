"""Validate saved-report input and convert supported Monarch report URLs."""

import math
from datetime import date
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .exceptions import ValidationError

LIST_FILTERS = {
    "accounts",
    "categories",
    "categoryGroups",
    "merchants",
    "tags",
    "goals",
    "savingsGoals",
    "excludeAccounts",
    "excludeCategories",
    "excludeCategoryGroups",
    "excludeMerchants",
    "excludeTags",
    "excludeGoals",
    "excludeSavingsGoals",
}
BOOL_FILTERS = {
    "isUntagged",
    "isSplit",
    "isRecurring",
    "isInvestmentAccount",
    "isPending",
    "creditsOnly",
    "debitsOnly",
    "hasNotes",
    "hasAttachments",
    "importedFromMint",
    "syncedFromInstitution",
    "needsReview",
    "needsReviewUnassigned",
    "isUncategorized",
    "isFlexSpending",
}
STRING_FILTERS = {
    "search",
    "tagMatchMode",
    "excludeTagMatchMode",
    "categoryType",
    "budgetVariability",
    "needsReviewByUser",
    "transactionVisibility",
}
DATE_FILTERS = {"startDate", "endDate", "createdBefore", "createdAfter"}
NUMBER_FILTERS = {"absAmountGte", "absAmountLte"}
VISIBILITY = {"non_hidden_transactions_only", "hidden_transactions_only", "all_transactions"}
UNITS = {"day", "week", "month", "quarter", "year"}
VIEW_FIELDS = {
    "analysisScope",
    "chartType",
    "chartCalculation",
    "chartLayout",
    "chartDensity",
    "dimensions",
    "timeframe",
}
SCOPES = {"cash-flow": "cash_flow", "spending": "spending", "income": "income"}
CHARTS = {
    "pieChart": {"chartType": "pie"},
    "treemapChart": {"chartType": "treemap"},
    "horizontalBarChart": {"chartType": "bar", "chartLayout": "horizontal"},
    "barChart": {"chartType": "bar", "chartLayout": "vertical", "chartDensity": "split"},
    "stackedBarChart": {"chartType": "bar", "chartLayout": "vertical", "chartDensity": "stacked"},
    "cashFlowChart": {"chartType": "bar", "chartLayout": "vertical", "chartDensity": "split"},
    "stackedCashFlowChart": {
        "chartType": "bar",
        "chartLayout": "vertical",
        "chartDensity": "stacked",
    },
    "sankeyCashFlowChart": {"chartType": "sankey"},
    "profitLossTable": {"chartType": "table"},
}


def clean_name(value: str) -> str:
    """Use the web app's trimmed, nonempty report name rule."""
    value = value.strip()
    if not value:
        raise ValidationError("Report name must not be empty")
    return value


def _validate_dates(filters: dict[str, Any]) -> None:
    for key in DATE_FILTERS:
        value = filters.get(key)
        if value is not None:
            try:
                if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
                    raise ValueError
            except ValueError as exc:
                raise ValidationError(f"{key} must be YYYY-MM-DD") from exc
    if (
        filters.get("startDate")
        and filters.get("endDate")
        and filters["startDate"] > filters["endDate"]
    ):
        raise ValidationError("startDate must be on or before endDate")


def validate_filters(filters: dict[str, Any]) -> dict[str, Any]:
    """Reject unsupported keys instead of silently broadening a saved report."""
    known = (
        LIST_FILTERS
        | BOOL_FILTERS
        | STRING_FILTERS
        | DATE_FILTERS
        | NUMBER_FILTERS
        | {"timeframePeriod"}
    )
    unknown = filters.keys() - known
    if unknown:
        raise ValidationError(f"Unsupported report filters: {', '.join(sorted(unknown))}")
    result = {k: v for k, v in filters.items() if v is not None}
    for key, value in result.items():
        if key in LIST_FILTERS:
            if not isinstance(value, list) or any(
                not isinstance(v, str) or not v.strip() for v in value
            ):
                raise ValidationError(f"{key} must be a list of nonempty string IDs")
        elif key in BOOL_FILTERS and type(value) is not bool:
            raise ValidationError(f"{key} must be a boolean")
        elif key in STRING_FILTERS and not isinstance(value, str):
            raise ValidationError(f"{key} must be a string")
        elif key in NUMBER_FILTERS and (
            type(value) not in (int, float) or not math.isfinite(value) or value < 0
        ):
            raise ValidationError(f"{key} must be a finite nonnegative number")
    _validate_dates(result)
    period = result.get("timeframePeriod")
    if period is not None:
        if not isinstance(period, dict) or period.keys() != {"unit", "value", "includeCurrent"}:
            raise ValidationError("timeframePeriod requires unit, value, and includeCurrent")
        if (
            not isinstance(period["unit"], str)
            or period["unit"] not in UNITS
            or type(period["value"]) is not int
            or period["value"] <= 0
            or type(period["includeCurrent"]) is not bool
        ):
            raise ValidationError("Invalid timeframePeriod")
        if result.get("startDate") or result.get("endDate"):
            raise ValidationError("Use a relative timeframe or explicit dates, not both")
    if result.get("absAmountGte", 0) > result.get("absAmountLte", float("inf")):
        raise ValidationError("absAmountGte must not exceed absAmountLte")
    if result.get("creditsOnly") and result.get("debitsOnly"):
        raise ValidationError("creditsOnly and debitsOnly cannot both be true")
    result.setdefault("transactionVisibility", "non_hidden_transactions_only")
    if result["transactionVisibility"] not in VISIBILITY:
        raise ValidationError("Invalid transactionVisibility")
    return result


def validate_view(view: dict[str, Any]) -> dict[str, Any]:
    """Only send observed ReportViewInput fields."""
    if view.keys() - VIEW_FIELDS:
        raise ValidationError("Unsupported report view fields")
    if view.get("analysisScope") not in SCOPES.values() or view.get("chartType") not in {
        "pie",
        "treemap",
        "bar",
        "sankey",
        "table",
    }:
        raise ValidationError("Invalid report analysisScope or chartType")
    result = {k: v for k, v in view.items() if v is not None}
    for key, values in {
        "chartCalculation": {"sum", "difference"},
        "chartLayout": {"horizontal", "vertical"},
        "chartDensity": {"split", "stacked"},
        "timeframe": UNITS,
    }.items():
        if key in result and (not isinstance(result[key], str) or result[key] not in values):
            raise ValidationError(f"Invalid report view {key}")
    if "dimensions" in result and (
        not isinstance(result["dimensions"], list)
        or any(not isinstance(v, str) or not v for v in result["dimensions"])
    ):
        raise ValidationError("Report dimensions must be a list of strings")
    cash_flow = result["analysisScope"] == "cash_flow"
    if (cash_flow and result["chartType"] not in {"sankey", "bar", "table"}) or (
        not cash_flow and result["chartType"] not in {"pie", "treemap", "bar"}
    ):
        raise ValidationError("Unsupported chartType for this report analysisScope")
    allowed_dimensions = {
        "category",
        "category_group",
        "merchant",
        "owner",
        "business_entity",
        "budget_variability",
    }
    if any(d not in allowed_dimensions for d in result.get("dimensions", [])):
        raise ValidationError("Unsupported report dimension")
    return result


def _url_input(url: str) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise ValidationError("Invalid report URL") from exc
    scope = SCOPES.get(parsed.path.removeprefix("/reports/"))
    if (
        parsed.scheme != "https"
        or parsed.netloc != "app.monarch.com"
        or not parsed.path.startswith("/reports/")
        or scope is None
        or parsed.fragment
    ):
        raise ValidationError(
            "Use an https://app.monarch.com/reports/{cash-flow,spending,income} URL"
        )
    params = parse_qs(parsed.query, keep_blank_values=True)
    view_keys = {"chartType", "groupMode", "groupByEntity", "groupByTimeframe"}
    period_keys = {"timeframeUnit", "timeframeValue", "timeframeIncludeCurrent"}
    allowed = (
        LIST_FILTERS
        | BOOL_FILTERS
        | STRING_FILTERS
        | DATE_FILTERS
        | NUMBER_FILTERS
        | view_keys
        | period_keys
    )
    unknown = params.keys() - allowed
    if unknown:
        raise ValidationError(f"Unsupported URL parameters: {', '.join(sorted(unknown))}")
    filters: dict[str, Any] = {}
    scalar: dict[str, Any] = {}
    for key, values in params.items():
        if key in LIST_FILTERS:
            parts = [part for value in values for part in value.split(",")]
            if any(not part.strip() for part in parts):
                raise ValidationError(f"{key} contains an empty ID")
            filters[key] = list(dict.fromkeys(parts))
            continue
        if len(values) != 1 or not values[0]:
            raise ValidationError(f"{key} requires exactly one nonempty value")
        value: Any = values[0]
        if key in BOOL_FILTERS | {"timeframeIncludeCurrent"}:
            if value not in ("true", "false"):
                raise ValidationError(f"{key} must be true or false")
            value = value == "true"
        elif key in NUMBER_FILTERS | {"timeframeValue"}:
            try:
                value = int(value) if key == "timeframeValue" else float(value)
            except ValueError as exc:
                raise ValidationError(f"Invalid numeric {key}") from exc
        if key in view_keys | period_keys:
            scalar[key] = value
        else:
            filters[key] = value
    if period_keys.intersection(scalar):
        filters["timeframePeriod"] = {
            "unit": scalar.get("timeframeUnit"),
            "value": scalar.get("timeframeValue"),
            "includeCurrent": scalar.get("timeframeIncludeCurrent", False),
        }
    default_chart = "sankeyCashFlowChart" if scope == "cash_flow" else "pieChart"
    chart = scalar.get("chartType", default_chart)
    valid_charts = (
        {
            "sankeyCashFlowChart",
            "profitLossTable",
            "cashFlowChart",
            "stackedCashFlowChart",
            "horizontalBarChart",
        }
        if scope == "cash_flow"
        else {"pieChart", "treemapChart", "horizontalBarChart", "barChart", "stackedBarChart"}
    )
    if chart not in valid_charts:
        raise ValidationError("Unsupported chartType for this report tab")
    group = scalar.get("groupMode", "both")
    if group not in {"category", "group", "both"}:
        raise ValidationError("Invalid groupMode")
    view: dict[str, Any] = {"analysisScope": scope, **CHARTS[chart]}
    trends = chart in {"barChart", "stackedBarChart", "cashFlowChart", "stackedCashFlowChart"}
    view["chartCalculation"] = "difference" if trends else "sum"
    if scope == "cash_flow" and chart in {"sankeyCashFlowChart", "profitLossTable"}:
        view["dimensions"] = {
            "both": ["category", "category_group"],
            "category": ["category"],
            "group": ["category_group"],
        }[group]
    elif scope != "cash_flow" or chart == "horizontalBarChart":
        view["dimensions"] = [scalar.get("groupByEntity", "category")]
    if trends:
        view["timeframe"] = scalar.get("groupByTimeframe", "month")
    if "groupMode" in scalar and not (
        scope == "cash_flow" and chart in {"sankeyCashFlowChart", "profitLossTable"}
    ):
        raise ValidationError("groupMode does not apply to this chart")
    if "groupByTimeframe" in scalar and not trends:
        raise ValidationError("groupByTimeframe does not apply to this chart")
    if "groupByEntity" in scalar and (scope == "cash_flow" and chart != "horizontalBarChart"):
        raise ValidationError("groupByEntity does not apply to this chart")
    return filters, view


def build_create_input(
    name: str,
    *,
    url: str | None = None,
    filters: dict[str, Any] | None = None,
    view: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare an explicit, previewable native create input."""
    if url is not None and (filters is not None or view is not None):
        raise ValidationError("Use --url or JSON configuration files, not both")
    if url is not None:
        filters, view = _url_input(url)
    if view is None:
        view = {
            "analysisScope": "cash_flow",
            "chartType": "sankey",
            "chartCalculation": "sum",
            "dimensions": ["category", "category_group"],
        }
    return {
        "displayName": clean_name(name),
        "transactionFilters": validate_filters(filters or {}),
        "reportView": validate_view(view),
    }
