"""Saved-report API uses native configurations and guarded, verified mutations."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from monarch_cli.core.exceptions import APIError, NotFoundError, ValidationError
from monarch_cli.core.report_api import (
    create_report,
    delete_report,
    list_reports,
    rename_report,
    show_report,
)


def report(name="Example", id="r1"):
    return {
        "id": id,
        "displayName": name,
        "transactionFilterSet": {"id": "f1", "tags": [{"id": "1"}], "hiddenFromReports": False},
        "reportView": {
            "analysisScope": "cash_flow",
            "chartType": "sankey",
            "chartCalculation": "sum",
            "dimensions": ["category", "category_group"],
        },
    }


def spec():
    return {
        "displayName": "Example",
        "transactionFilters": {
            "tags": ["1"],
            "transactionVisibility": "non_hidden_transactions_only",
        },
        "reportView": report()["reportView"],
    }


def client_with(*responses):
    return MagicMock(gql_call=AsyncMock(side_effect=list(responses)))


async def test_list_and_show():
    client = client_with({"reportConfigurations": [report()]}, {"reportConfigurations": [report()]})
    assert await list_reports(client) == [report()]
    assert await show_report(client, "r1") == report()
    assert client.gql_call.call_args.kwargs["operation"] == "Common_GetReportConfigurations"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"reportConfigurations": None},
        {"reportConfigurations": [None]},
        {"reportConfigurations": [{"id": "x"}]},
        {"reportConfigurations": [report(), report()]},
    ],
)
async def test_list_rejects_incomplete_or_duplicate_records(payload):
    with pytest.raises(APIError):
        await list_reports(client_with(payload))


async def test_missing_report():
    with pytest.raises(NotFoundError):
        await show_report(client_with({"reportConfigurations": []}), "missing")


async def test_create_preview_no_calls():
    client = client_with()
    data = await create_report(client, spec(), dry_run=True)
    assert data["status"] == "dry_run"
    assert data["input"] == spec()
    client.gql_call.assert_not_called()


async def test_create_and_verify():
    client = client_with(
        {"reportConfigurations": []},
        {"createReportConfiguration": {"reportConfiguration": report(), "errors": None}},
        {"reportConfigurations": [report()]},
    )
    result = await create_report(client, spec())
    assert result["status"] == "created" and result["verified"] is True
    assert result["id"] == "r1"
    call = client.gql_call.call_args_list[1].kwargs
    assert call["operation"] == "Common_CreateReportConfiguration"
    assert call["variables"] == {"input": spec()}


async def test_create_rejects_duplicate_name_before_write():
    client = client_with({"reportConfigurations": [report()]})
    with pytest.raises(ValidationError):
        await create_report(client, spec())
    assert client.gql_call.await_count == 1


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"createReportConfiguration": None},
        {"createReportConfiguration": {"errors": {}}},
        {"createReportConfiguration": {"errors": {"message": "denied"}}},
    ],
)
async def test_create_rejects_payload_errors(payload):
    with pytest.raises(APIError):
        await create_report(client_with({"reportConfigurations": []}, payload), spec())


async def test_create_rejects_wrong_filter_readback():
    wrong = report()
    wrong["transactionFilterSet"]["tags"] = []
    client = client_with(
        {"reportConfigurations": []},
        {"createReportConfiguration": {"reportConfiguration": report(), "errors": None}},
        {"reportConfigurations": [wrong]},
    )
    with pytest.raises(APIError, match="verify"):
        await create_report(client, spec())


async def test_rename_preserves_configuration():
    before = report()
    after = report("Renamed")
    client = client_with(
        {"reportConfigurations": [before]},
        {"updateReportConfiguration": {"reportConfiguration": after, "errors": None}},
        {"reportConfigurations": [after]},
    )
    result = await rename_report(client, "r1", "Renamed")
    assert result["status"] == "renamed" and result["verified"] is True
    assert client.gql_call.call_args_list[1].kwargs["variables"] == {
        "input": {"id": "r1", "displayName": "Renamed"}
    }


async def test_rename_detects_configuration_changes():
    before = report()
    after = report("Renamed")
    after["transactionFilterSet"]["tags"] = []
    client = client_with(
        {"reportConfigurations": [before]},
        {"updateReportConfiguration": {"reportConfiguration": after, "errors": None}},
        {"reportConfigurations": [after]},
    )
    with pytest.raises(APIError, match="verify"):
        await rename_report(client, "r1", "Renamed")


async def test_rename_preview_and_unchanged():
    client = client_with({"reportConfigurations": [report()]}, {"reportConfigurations": [report()]})
    assert (await rename_report(client, "r1", "New", dry_run=True))["status"] == "dry_run"
    assert (await rename_report(client, "r1", "Example"))["status"] == "unchanged"
    assert client.gql_call.await_count == 2


async def test_delete_confirmed_and_verified():
    client = client_with(
        {"reportConfigurations": [report()]},
        {"deleteReportConfiguration": {"deleted": True, "errors": None}},
        {"reportConfigurations": []},
    )
    result = await delete_report(client, "r1")
    assert result["status"] == "deleted" and result["verified"] is True
    assert client.gql_call.call_args_list[1].kwargs["variables"] == {"id": "r1"}


async def test_delete_preview():
    client = client_with({"reportConfigurations": [report()]})
    assert (await delete_report(client, "r1", dry_run=True))["status"] == "dry_run"
    assert client.gql_call.await_count == 1


@pytest.mark.parametrize("deleted", [False, None, "true"])
async def test_delete_rejects_unconfirmed_result(deleted):
    client = client_with(
        {"reportConfigurations": [report()]},
        {"deleteReportConfiguration": {"deleted": deleted, "errors": None}},
    )
    with pytest.raises(APIError):
        await delete_report(client, "r1")


async def test_delete_requires_absent_readback():
    client = client_with(
        {"reportConfigurations": [report()]},
        {"deleteReportConfiguration": {"deleted": True, "errors": None}},
        {"reportConfigurations": [report()]},
    )
    with pytest.raises(APIError, match="verify"):
        await delete_report(client, "r1")


async def test_transport_error_reports_uncertain_outcome():
    client = client_with({"reportConfigurations": []}, RuntimeError("connection closed"))
    with pytest.raises(APIError, match="before retrying"):
        await create_report(client, spec())
    assert client.gql_call.await_count == 2


async def test_create_verifies_exclude_filters():
    expected = spec()
    expected["transactionFilters"]["excludeTags"] = ["2"]
    row = report()
    row["transactionFilterSet"]["excludedTags"] = [{"id": "2"}]
    client = client_with(
        {"reportConfigurations": []},
        {"createReportConfiguration": {"reportConfiguration": row, "errors": None}},
        {"reportConfigurations": [row]},
    )
    assert (await create_report(client, expected))["verified"] is True


async def test_create_accepts_semantic_default_calculation():
    row = report()
    row["reportView"]["chartCalculation"] = None
    client = client_with(
        {"reportConfigurations": []},
        {"createReportConfiguration": {"reportConfiguration": row, "errors": None}},
        {"reportConfigurations": [row]},
    )
    assert (await create_report(client, spec()))["verified"] is True


async def test_create_verification_requires_visibility_field():
    expected = spec()
    expected["transactionFilters"]["transactionVisibility"] = "all_transactions"
    row = report()
    del row["transactionFilterSet"]["hiddenFromReports"]
    client = client_with(
        {"reportConfigurations": []},
        {"createReportConfiguration": {"reportConfiguration": row, "errors": None}},
        {"reportConfigurations": [row]},
    )
    with pytest.raises(APIError, match="verify"):
        await create_report(client, expected)


async def test_rename_rejects_duplicate_name():
    client = client_with({"reportConfigurations": [report(), report("Taken", "r2")]})
    with pytest.raises(ValidationError):
        await rename_report(client, "r1", "Taken")
    assert client.gql_call.await_count == 1
