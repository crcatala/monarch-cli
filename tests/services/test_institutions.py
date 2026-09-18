"""Tests for institution and subscription read services."""

from unittest.mock import MagicMock, patch

from monarch_cli.core.operations import Effect, Operation
from monarch_cli.services.institutions import (
    INSTITUTIONS_OPERATION,
    SUBSCRIPTION_OPERATION,
    get_institutions_raw,
    get_subscription_raw,
    list_institutions,
    show_subscription,
)


def test_list_institutions_passes_include_deleted_to_transformer() -> None:
    raw = {"credentials": [], "accounts": []}
    with (
        patch("monarch_cli.services.institutions.get_institutions_raw", return_value=raw),
        patch(
            "monarch_cli.services.institutions.transform_institutions", return_value=[]
        ) as transform,
    ):
        assert list_institutions(include_deleted=True) == []
    transform.assert_called_once_with(raw, include_deleted=True)


def test_raw_institutions_uses_released_client_method() -> None:
    client = MagicMock()
    raw = {"credentials": [], "accounts": [], "subscription": {"x": 1}}
    with (
        patch("monarch_cli.services.institutions.get_authenticated_client", return_value=client),
        patch("monarch_cli.services.institutions.run_read_call", return_value=raw) as run,
    ):
        assert get_institutions_raw() == raw
    assert run.call_args.args[1] == INSTITUTIONS_OPERATION
    run.call_args.args[0]()
    client.get_institutions.assert_called_once_with()


def test_show_subscription_uses_one_normalized_contract() -> None:
    raw = {"subscription": {"isOnFreeTrial": False, "hasPremiumEntitlement": False}}
    with (
        patch("monarch_cli.services.institutions.get_subscription_raw", return_value=raw),
        patch(
            "monarch_cli.services.institutions.transform_subscription",
            return_value={"available": True},
        ) as transform,
    ):
        assert show_subscription() == {"available": True}
    transform.assert_called_once_with(raw)


def test_raw_subscription_calls_details_method() -> None:
    client = MagicMock()
    raw = {"subscription": None}
    operation = Operation("subscription show", frozenset({Effect.READ_ONLY}))
    with (
        patch("monarch_cli.services.institutions.get_authenticated_client", return_value=client),
        patch("monarch_cli.services.institutions.run_read_call", return_value=raw) as run,
    ):
        assert get_subscription_raw(operation) == raw
    assert run.call_args.args[1] == SUBSCRIPTION_OPERATION or run.call_args.args[1] == operation
    run.call_args.args[0]()
    client.get_subscription_details.assert_called_once_with()
