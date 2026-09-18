"""Contract tests for transaction tag reads and guarded full-set writes."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from monarch_cli.commands.transaction_tags import app
from monarch_cli.core.config import Config, reset_config, set_config
from monarch_cli.core.operations import reset_mutation_authorization, set_mutation_authorized

runner = CliRunner()


@pytest.fixture(autouse=True)
def policy() -> None:
    set_mutation_authorized(True)
    set_config(Config(confirm_destructive=False))
    yield
    reset_mutation_authorization()
    reset_config()


def client() -> MagicMock:
    mock = MagicMock()
    mock.get_transaction_tags = AsyncMock()
    mock.get_transaction_details = AsyncMock()
    mock.create_transaction_tag = AsyncMock()
    mock.set_transaction_tags = AsyncMock()
    return mock


def invoke(mock: MagicMock, args: list[str]):
    with (
        patch("monarch_cli.commands.transaction_tags.get_authenticated_client", return_value=mock),
        patch("monarch_cli.output.progress.is_interactive", return_value=False),
    ):
        return runner.invoke(app, args)


def tag(tag_id: str = "tag-1") -> dict[str, str]:
    return {"id": tag_id, "name": "Work", "color": "#112233"}


def test_list_is_read_only_and_normalized() -> None:
    mock = client()
    mock.get_transaction_tags.return_value = {"householdTransactionTags": [tag()]}
    result = invoke(mock, ["list", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)[0]["id"] == "tag-1"
    mock.get_transaction_tags.assert_awaited_once()


def test_show_reads_transaction_assignment() -> None:
    mock = client()
    mock.get_transaction_details.return_value = {"getTransaction": {"id": "txn-1", "tags": [tag()]}}
    result = invoke(mock, ["show", "txn-1", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["tags"][0]["id"] == "tag-1"


def test_create_validates_and_handles_payload_errors() -> None:
    mock = client()
    mock.create_transaction_tag.return_value = {
        "createTransactionTag": {"errors": [{"message": "duplicate"}], "tag": None}
    }
    result = invoke(mock, ["create", "--name", " Work ", "--color", "#aBc123"])
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    assert payload["items"][0]["error"]["details"]["payload_errors"]
    mock.create_transaction_tag.assert_called_once_with(name="Work", color="#aBc123")


def test_replace_deduplicates_validates_before_mutation_and_verifies() -> None:
    mock = client()
    mock.get_transaction_tags.return_value = {"householdTransactionTags": [tag(), tag("tag-2")]}
    mock.get_transaction_details.return_value = {"getTransaction": {"id": "txn-1", "tags": []}}
    mock.set_transaction_tags.return_value = {
        "setTransactionTags": {
            "errors": [],
            "transaction": {"id": "txn-1", "tags": [{"id": "tag-1"}, {"id": "tag-2"}]},
        }
    }
    result = invoke(mock, ["replace", "txn-1", "tag-1", "tag-1", "tag-2"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["items"][0]["result"] == {
        "tag_ids": ["tag-1", "tag-2"],
        "no_op": False,
    }
    mock.set_transaction_tags.assert_called_once_with(
        transaction_id="txn-1", tag_ids=["tag-1", "tag-2"]
    )


def test_unknown_id_fails_before_set() -> None:
    mock = client()
    mock.get_transaction_tags.return_value = {"householdTransactionTags": [tag()]}
    result = invoke(mock, ["replace", "txn-1", "missing"])
    assert result.exit_code == 2
    assert "unknown_ids" in result.stderr
    mock.set_transaction_tags.assert_not_called()


def test_clear_is_explicit_and_noop_is_deterministic() -> None:
    mock = client()
    mock.get_transaction_tags.return_value = {"householdTransactionTags": [tag()]}
    mock.get_transaction_details.return_value = {"getTransaction": {"id": "txn-1", "tags": []}}
    result = invoke(mock, ["clear", "txn-1"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["items"][0]["result"]["no_op"] is True
    mock.set_transaction_tags.assert_not_called()


def test_replace_verification_mismatch_is_ambiguous() -> None:
    mock = client()
    mock.get_transaction_tags.return_value = {"householdTransactionTags": [tag()]}
    mock.get_transaction_details.return_value = {"getTransaction": {"id": "txn-1", "tags": []}}
    mock.set_transaction_tags.return_value = {
        "setTransactionTags": {
            "errors": [],
            "transaction": {"id": "txn-1", "tags": []},
        }
    }
    result = invoke(mock, ["replace", "txn-1", "tag-1"])
    assert result.exit_code == 4
    payload = json.loads(result.stdout)
    assert payload["status"] == "ambiguous"
    assert payload["verification"]["command"][-1] == "txn-1"
