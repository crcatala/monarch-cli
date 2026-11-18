"""Native saved reports: validated reads and non-retried, verified writes."""

from typing import Any

from .exceptions import APIError, NotFoundError, ValidationError
from .report_config import LIST_FILTERS, clean_name
from .report_queries import CREATE_REPORTS, DELETE_REPORT, GET_REPORTS, UPDATE_REPORTS


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise APIError(f"Missing or invalid {label} in Monarch response")
    return value


def _report(value: Any) -> dict[str, Any]:
    row = _object(value, "report")
    if (
        not isinstance(row.get("id"), str)
        or not row["id"]
        or not isinstance(row.get("displayName"), str)
        or not row["displayName"].strip()
    ):
        raise APIError("Saved report is missing its ID or name")
    _object(row.get("transactionFilterSet"), "report transaction filters")
    if "reportView" not in row or (
        row["reportView"] is not None and not isinstance(row["reportView"], dict)
    ):
        raise APIError("Saved report is missing its view")
    return row


async def list_reports(client: Any) -> list[dict[str, Any]]:
    """The observed API returns all configurations, without pagination arguments."""
    data = _object(
        await client.gql_call(
            operation="Common_GetReportConfigurations", graphql_query=GET_REPORTS, variables={}
        ),
        "saved reports",
    )
    rows = data.get("reportConfigurations")
    if not isinstance(rows, list):
        raise APIError("Missing or invalid reportConfigurations list")
    reports = [_report(row) for row in rows]
    if len({row["id"] for row in reports}) != len(reports):
        raise APIError("Saved reports contain duplicate IDs")
    return reports


def _find(reports: list[dict[str, Any]], report_id: str) -> dict[str, Any]:
    for row in reports:
        if row["id"] == report_id:
            return row
    raise NotFoundError("Saved report not found", resource_type="report", resource_id=report_id)


async def show_report(client: Any, report_id: str) -> dict[str, Any]:
    """Read one configuration by exact ID from the complete list."""
    return _find(await list_reports(client), report_id)


def _unique_name(reports: list[dict[str, Any]], name: str, report_id: str | None = None) -> None:
    if any(row["displayName"] == name and row["id"] != report_id for row in reports):
        raise ValidationError("A saved report already has this name; inspect report list")


async def _write(
    client: Any, operation: str, query: Any, field: str, variables: dict[str, Any]
) -> dict[str, Any]:
    try:
        data = await client.gql_call(operation=operation, graphql_query=query, variables=variables)
    except Exception as exc:
        raise APIError(
            "Report request failed; inspect report list before retrying. "
            "A submitted write may have completed.",
            details={"operation": operation, "cause": str(exc)},
        ) from exc
    payload = _object(
        _object(data, "report mutation response").get(field), "report mutation payload"
    )
    if "errors" not in payload or payload["errors"] is not None:
        raise APIError(
            "Monarch rejected or did not confirm report mutation",
            details={"errors": payload.get("errors")},
        )
    return payload


def _filter_value(filters: dict[str, Any], key: str) -> Any:
    output_key = "excluded" + key[7:] if key.startswith("exclude") and key in LIST_FILTERS else key
    if key == "search":
        output_key = "searchQuery"
    if key == "transactionVisibility":
        if "hiddenFromReports" not in filters:
            raise APIError("Readback is missing filter hiddenFromReports")
        value = filters["hiddenFromReports"]
        return {
            True: "hidden_transactions_only",
            False: "non_hidden_transactions_only",
            None: "all_transactions",
        }.get(value)
    if output_key not in filters:
        raise APIError(f"Readback is missing filter {output_key}")
    value = filters[output_key]
    if key in LIST_FILTERS:
        if not isinstance(value, list) or any(
            not isinstance(row, dict) or not isinstance(row.get("id"), str) for row in value
        ):
            raise APIError(f"Invalid readback for {output_key}")
        return sorted(row["id"] for row in value)
    if key == "needsReviewByUser":
        return value.get("id") if isinstance(value, dict) else value
    return value


def _verify_spec(report: dict[str, Any], spec: dict[str, Any]) -> None:
    if report["displayName"] != spec["displayName"]:
        raise APIError("Saved report name differs from request")
    for key, expected in spec["transactionFilters"].items():
        actual = _filter_value(report["transactionFilterSet"], key)
        if actual != (sorted(expected) if key in LIST_FILTERS else expected):
            raise APIError(f"Saved report filter {key} differs from request")
    view = _object(report.get("reportView"), "saved report view")
    for key, expected in spec["reportView"].items():
        actual = view.get(key)
        if key == "chartCalculation" and actual is None:
            actual = (
                "difference"
                if view.get("chartType") == "bar" and view.get("chartLayout") != "horizontal"
                else "sum"
            )
        if key == "dimensions":
            actual = sorted(actual) if isinstance(actual, list) else actual
            expected = sorted(expected)
        if actual != expected:
            raise APIError(f"Saved report view {key} differs from request")


def _configuration(report: dict[str, Any]) -> dict[str, Any]:
    """Ignore identity/name metadata when verifying rename preserves settings."""
    filters = {
        k: v for k, v in report["transactionFilterSet"].items() if k not in {"id", "displayName"}
    }
    return {"filters": filters, "view": report["reportView"]}


async def create_report(
    client: Any, spec: dict[str, Any], *, dry_run: bool = False
) -> dict[str, Any]:
    """Create a native saved report, then verify its name, filters, and view."""
    if dry_run:
        return {"status": "dry_run", "entity": "report", "input": spec}
    before = await list_reports(client)
    _unique_name(before, spec["displayName"])
    payload = await _write(
        client,
        "Common_CreateReportConfiguration",
        CREATE_REPORTS,
        "createReportConfiguration",
        {"input": spec},
    )
    row = _report(payload.get("reportConfiguration"))
    try:
        if row["id"] in {r["id"] for r in before}:
            raise APIError("Create returned an existing report ID")
        after = await show_report(client, row["id"])
        _verify_spec(after, spec)
    except Exception as exc:
        raise APIError(
            "Report submitted but could not verify creation; inspect report list before retrying",
            details={"report_id": row["id"], "cause": str(exc)},
        ) from exc
    return {
        "status": "created",
        "entity": "report",
        "id": row["id"],
        "verified": True,
        "result": after,
    }


async def rename_report(
    client: Any, report_id: str, name: str, *, dry_run: bool = False
) -> dict[str, Any]:
    """The observed update operation changes displayName only."""
    name = clean_name(name)
    reports = await list_reports(client)
    before = _find(reports, report_id)
    _unique_name(reports, name, report_id)
    changes = {"id": report_id, "displayName": name}
    if dry_run:
        return {
            "status": "dry_run",
            "entity": "report",
            "id": report_id,
            "input": changes,
            "before": before,
        }
    if before["displayName"] == name:
        return {
            "status": "unchanged",
            "entity": "report",
            "id": report_id,
            "verified": True,
            "result": before,
        }
    payload = await _write(
        client,
        "Common_UpdateReportConfiguration",
        UPDATE_REPORTS,
        "updateReportConfiguration",
        {"input": changes},
    )
    row = _report(payload.get("reportConfiguration"))
    try:
        if row["id"] != report_id:
            raise APIError("Update returned a different report ID")
        after = await show_report(client, report_id)
        if after["displayName"] != name or _configuration(after) != _configuration(before):
            raise APIError("Report name or configuration differs from expected rename")
    except Exception as exc:
        raise APIError(
            "Report submitted but could not verify rename; inspect report show before retrying",
            details={"report_id": report_id, "cause": str(exc)},
        ) from exc
    return {
        "status": "renamed",
        "entity": "report",
        "id": report_id,
        "verified": True,
        "result": after,
    }


async def delete_report(client: Any, report_id: str, *, dry_run: bool = False) -> dict[str, Any]:
    """Delete an exact saved report ID and verify it is absent afterward."""
    before = await show_report(client, report_id)
    if dry_run:
        return {"status": "dry_run", "entity": "report", "id": report_id, "before": before}
    payload = await _write(
        client,
        "Common_DeleteReportConfiguration",
        DELETE_REPORT,
        "deleteReportConfiguration",
        {"id": report_id},
    )
    if payload.get("deleted") is not True:
        raise APIError("Monarch did not confirm report deletion; inspect report list")
    try:
        if any(row["id"] == report_id for row in await list_reports(client)):
            raise APIError("Deleted report remains in reportConfigurations")
    except Exception as exc:
        raise APIError(
            "Report submitted but could not verify deletion; inspect report list before retrying",
            details={"report_id": report_id, "cause": str(exc)},
        ) from exc
    return {"status": "deleted", "entity": "report", "id": report_id, "verified": True}
