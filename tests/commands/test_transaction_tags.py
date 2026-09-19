"""Contract tests for transaction tag reads and guarded full-set writes."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from monarch_cli.commands.transaction_tags import app
from monarch_cli.core.config import Config, reset_config, set_config
from monarch_cli.core.operations import reset_mutation_authorization, set_mutation_authorized
from monarch_cli.core.prompting import reset_non_interactive, set_non_interactive

runner = CliRunner()


@pytest.fixture(autouse=True)
def policy() -> None:
    set_mutation_authorized(True)
    set_config(Config(confirm_destructive=False))
    yield
    reset_mutation_authorization()
    reset_non_interactive()
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


def test_show_rejects_malformed_assignment_instead_of_dropping_it() -> None:
    mock = client()
    mock.get_transaction_details.return_value = {
        "getTransaction": {"id": "txn-1", "tags": [{"name": "Work"}]}
    }
    result = invoke(mock, ["show", "txn-1", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stderr)["code"] == "API_ERROR"


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
    result = invoke(
        mock,
        [
            "replace",
            "--transaction-id",
            "txn-1",
            "--tag-id",
            "tag-1",
            "--tag-id",
            "tag-1",
            "--tag-id",
            "tag-2",
        ],
    )
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
    result = invoke(mock, ["replace", "--transaction-id", "txn-1", "--tag-id", "missing"])
    assert result.exit_code == 2
    assert "unknown_ids" in result.stderr
    mock.set_transaction_tags.assert_not_called()


def test_malformed_current_assignment_fails_closed_before_set() -> None:
    mock = client()
    mock.get_transaction_tags.return_value = {"householdTransactionTags": [tag()]}
    mock.get_transaction_details.return_value = {
        "getTransaction": {"id": "txn-1", "tags": [{"name": "Work"}]}
    }
    result = invoke(mock, ["clear", "--transaction-id", "txn-1"])
    assert result.exit_code == 1
    assert json.loads(result.stderr)["code"] == "API_ERROR"
    mock.set_transaction_tags.assert_not_called()


def test_mutation_is_blocked_before_authenticated_client_lookup() -> None:
    set_mutation_authorized(False)
    with patch(
        "monarch_cli.commands.transaction_tags.get_authenticated_client",
        side_effect=AssertionError("client lookup must be gated"),
    ):
        result = runner.invoke(app, ["create", "--name", "Work", "--color", "#112233"])
    assert result.exit_code == 3
    assert json.loads(result.stderr)["code"] == "MUTATION_BLOCKED"


def test_noninteractive_confirmation_blocks_before_set() -> None:
    mock = client()
    set_non_interactive(True)
    set_config(Config(confirm_destructive=True))
    mock.get_transaction_tags.return_value = {"householdTransactionTags": [tag()]}
    mock.get_transaction_details.return_value = {"getTransaction": {"id": "txn-1", "tags": []}}
    result = invoke(mock, ["replace", "--transaction-id", "txn-1", "--tag-id", "tag-1"])
    assert result.exit_code == 5
    assert json.loads(result.stderr)["code"] == "PROMPT_BLOCKED"
    mock.set_transaction_tags.assert_not_called()


def test_transport_ambiguity_is_structured_and_not_retried() -> None:
    mock = client()
    mock.get_transaction_tags.return_value = {"householdTransactionTags": [tag()]}
    mock.get_transaction_details.return_value = {"getTransaction": {"id": "txn-1", "tags": []}}
    mock.set_transaction_tags.side_effect = TimeoutError()
    result = invoke(mock, ["replace", "--transaction-id", "txn-1", "--tag-id", "tag-1"])
    assert result.exit_code == 4
    payload = json.loads(result.stdout)
    assert payload["status"] == "ambiguous"
    assert payload["verification"]["command"][-1] == "txn-1"
    mock.set_transaction_tags.assert_called_once()


def test_clear_is_explicit_and_noop_is_deterministic() -> None:
    mock = client()
    mock.get_transaction_tags.return_value = {"householdTransactionTags": [tag()]}
    mock.get_transaction_details.return_value = {"getTransaction": {"id": "txn-1", "tags": []}}
    result = invoke(mock, ["clear", "--transaction-id", "txn-1"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["items"][0]["result"]["no_op"] is True
    mock.set_transaction_tags.assert_not_called()


def test_clear_payload_error_is_failed_outcome() -> None:
    mock = client()
    mock.get_transaction_tags.return_value = {"householdTransactionTags": [tag()]}
    mock.get_transaction_details.return_value = {
        "getTransaction": {"id": "txn-1", "tags": [{"id": "tag-1"}]}
    }
    mock.set_transaction_tags.return_value = {
        "setTransactionTags": {
            "errors": [{"message": "cannot clear", "code": "DENIED"}],
            "transaction": None,
        }
    }
    result = invoke(mock, ["clear", "--transaction-id", "txn-1"])
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    assert payload["items"][0]["error"]["details"]["payload_errors"][0]["code"] == "DENIED"


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
    result = invoke(mock, ["replace", "--transaction-id", "txn-1", "--tag-id", "tag-1"])
    assert result.exit_code == 4
    payload = json.loads(result.stdout)
    assert payload["status"] == "ambiguous"
    assert payload["verification"]["command"][-1] == "txn-1"


def test_replace_accepts_tag_names_and_mixed_refs() -> None:
    mock = client()
    mock.get_transaction_tags.return_value = {
        "householdTransactionTags": [
            tag("tag-1"),
            {"id": "tag-2", "name": "Travel", "color": "#000000"},
        ]
    }
    mock.get_transaction_details.return_value = {"getTransaction": {"id": "txn-1", "tags": []}}
    mock.set_transaction_tags.return_value = {
        "setTransactionTags": {
            "errors": [],
            "transaction": {"id": "txn-1", "tags": [{"id": "tag-1"}, {"id": "tag-2"}]},
        }
    }
    result = invoke(
        mock,
        ["replace", "--transaction-id", "txn-1", "--tag-id", "tag-1", "--tag-name", "Travel"],
    )
    assert result.exit_code == 0
    mock.set_transaction_tags.assert_called_once_with(
        transaction_id="txn-1", tag_ids=["tag-1", "tag-2"]
    )


def test_replace_unknown_name_fails_before_mutation() -> None:
    mock = client()
    mock.get_transaction_tags.return_value = {"householdTransactionTags": [tag()]}
    result = invoke(mock, ["replace", "--transaction-id", "txn-1", "--tag-name", "Missing"])
    assert result.exit_code == 2
    assert "unknown_names" in result.stderr
    mock.set_transaction_tags.assert_not_called()


def test_replace_ambiguous_name_reports_candidates() -> None:
    mock = client()
    mock.get_transaction_tags.return_value = {
        "householdTransactionTags": [
            {"id": "tag-1", "name": "Work", "color": "#111111"},
            {"id": "tag-2", "name": "Work", "color": "#222222"},
        ]
    }
    result = invoke(mock, ["replace", "--transaction-id", "txn-1", "--tag-name", "Work"])
    assert result.exit_code == 2
    err = json.loads(result.stderr)
    assert err["details"]["ambiguous_names"]["Work"] == ["tag-1", "tag-2"]
    mock.set_transaction_tags.assert_not_called()


def test_replace_name_matching_is_case_sensitive_and_trimmed() -> None:
    mock = client()
    mock.get_transaction_tags.return_value = {"householdTransactionTags": [tag()]}
    result = invoke(mock, ["replace", "--transaction-id", "txn-1", "--tag-name", "  work  "])
    assert result.exit_code == 2  # exact case-sensitive match required
    mock.set_transaction_tags.assert_not_called()


def test_replace_requires_at_least_one_ref() -> None:
    mock = client()
    result = invoke(mock, ["replace", "--transaction-id", "txn-1"])
    assert result.exit_code == 2
    mock.set_transaction_tags.assert_not_called()


def test_add_preserves_existing_and_reports_added() -> None:
    mock = client()
    mock.get_transaction_tags.return_value = {
        "householdTransactionTags": [
            tag("tag-1"),
            {"id": "tag-2", "name": "Travel", "color": "#000000"},
        ]
    }
    mock.get_transaction_details.return_value = {
        "getTransaction": {"id": "txn-1", "tags": [{"id": "tag-1"}]}
    }
    mock.set_transaction_tags.return_value = {
        "setTransactionTags": {
            "errors": [],
            "transaction": {"id": "txn-1", "tags": [{"id": "tag-1"}, {"id": "tag-2"}]},
        }
    }
    result = invoke(mock, ["add", "--transaction-id", "txn-1", "--tag-id", "tag-2"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)["items"][0]["result"]
    assert data == {
        "tag_ids": ["tag-1", "tag-2"],
        "added_tag_ids": ["tag-2"],
        "skipped_tag_ids": [],
        "no_op": False,
    }
    mock.set_transaction_tags.assert_called_once_with(
        transaction_id="txn-1", tag_ids=["tag-1", "tag-2"]
    )


def test_add_is_noop_when_already_present() -> None:
    mock = client()
    mock.get_transaction_tags.return_value = {"householdTransactionTags": [tag()]}
    mock.get_transaction_details.return_value = {
        "getTransaction": {"id": "txn-1", "tags": [{"id": "tag-1"}]}
    }
    result = invoke(mock, ["add", "--transaction-id", "txn-1", "--tag-id", "tag-1"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)["items"][0]["result"]
    assert data["no_op"] is True
    assert data["added_tag_ids"] == []
    assert data["skipped_tag_ids"] == ["tag-1"]
    mock.set_transaction_tags.assert_not_called()


def test_add_preserves_stale_current_ids_verbatim() -> None:
    mock = client()
    mock.get_transaction_tags.return_value = {"householdTransactionTags": [tag("tag-1")]}
    mock.get_transaction_details.return_value = {
        "getTransaction": {"id": "txn-1", "tags": [{"id": "stale-9"}]}
    }
    mock.set_transaction_tags.return_value = {
        "setTransactionTags": {
            "errors": [],
            "transaction": {"id": "txn-1", "tags": [{"id": "stale-9"}, {"id": "tag-1"}]},
        }
    }
    result = invoke(mock, ["add", "--transaction-id", "txn-1", "--tag-id", "tag-1"])
    assert result.exit_code == 0
    mock.set_transaction_tags.assert_called_once_with(
        transaction_id="txn-1", tag_ids=["stale-9", "tag-1"]
    )


def test_add_reports_ambiguous_when_stale_id_dropped() -> None:
    mock = client()
    mock.get_transaction_tags.return_value = {"householdTransactionTags": [tag("tag-1")]}
    mock.get_transaction_details.return_value = {
        "getTransaction": {"id": "txn-1", "tags": [{"id": "stale-9"}]}
    }
    mock.set_transaction_tags.return_value = {
        "setTransactionTags": {
            "errors": [],
            "transaction": {"id": "txn-1", "tags": [{"id": "tag-1"}]},
        }
    }
    result = invoke(mock, ["add", "--transaction-id", "txn-1", "--tag-id", "tag-1"])
    assert result.exit_code == 4
    assert json.loads(result.stdout)["status"] == "ambiguous"


def test_tags_reject_removed_positional_targets() -> None:
    mock = client()
    for args in (
        ["replace", "txn-1", "--tag-id", "tag-1"],
        ["add", "txn-1", "--tag-id", "tag-1"],
        ["clear", "txn-1"],
    ):
        result = invoke(mock, args)
        assert result.exit_code != 0
    mock.set_transaction_tags.assert_not_called()


def test_replace_dry_run_previews_without_writing() -> None:
    mock = client()
    mock.get_transaction_tags.return_value = {
        "householdTransactionTags": [
            tag("tag-1"),
            {"id": "tag-2", "name": "Travel", "color": "#000000"},
        ]
    }
    mock.get_transaction_details.return_value = {
        "getTransaction": {"id": "txn-1", "tags": [{"id": "tag-1"}]}
    }
    result = invoke(
        mock, ["replace", "--transaction-id", "txn-1", "--tag-id", "tag-2", "--dry-run"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "dry_run"
    assert payload["operation"] == "transactions.tags.replace"
    assert payload["target"] == {"transaction_id": "txn-1"}
    assert "schema_version" not in payload
    detail = payload["detail"]
    assert detail["current_tag_ids"] == ["tag-1"]
    assert detail["final_tag_ids"] == ["tag-2"]
    assert detail["removed_tag_ids"] == ["tag-1"]
    mock.set_transaction_tags.assert_not_called()


def test_add_dry_run_reports_additive_without_writing() -> None:
    mock = client()
    mock.get_transaction_tags.return_value = {
        "householdTransactionTags": [
            tag("tag-1"),
            {"id": "tag-2", "name": "Travel", "color": "#000000"},
        ]
    }
    mock.get_transaction_details.return_value = {
        "getTransaction": {"id": "txn-1", "tags": [{"id": "tag-1"}]}
    }
    result = invoke(mock, ["add", "--transaction-id", "txn-1", "--tag-id", "tag-2", "--dry-run"])
    assert result.exit_code == 0, result.output
    detail = json.loads(result.stdout)["detail"]
    assert detail["final_tag_ids"] == ["tag-1", "tag-2"]
    assert detail["added_tag_ids"] == ["tag-2"]
    assert detail["no_op"] is False
    mock.set_transaction_tags.assert_not_called()


def test_clear_dry_run_previews_without_writing() -> None:
    mock = client()
    mock.get_transaction_tags.return_value = {"householdTransactionTags": [tag()]}
    mock.get_transaction_details.return_value = {
        "getTransaction": {"id": "txn-1", "tags": [{"id": "tag-1"}]}
    }
    result = invoke(mock, ["clear", "--transaction-id", "txn-1", "--dry-run"])
    assert result.exit_code == 0, result.output
    detail = json.loads(result.stdout)["detail"]
    assert detail["current_tag_ids"] == ["tag-1"]
    assert detail["final_tag_ids"] == []
    mock.set_transaction_tags.assert_not_called()


def test_tag_dry_run_does_not_require_mutation_authorization() -> None:
    set_mutation_authorized(False)
    mock = client()
    mock.get_transaction_tags.return_value = {"householdTransactionTags": [tag()]}
    mock.get_transaction_details.return_value = {"getTransaction": {"id": "txn-1", "tags": []}}
    result = invoke(
        mock, ["replace", "--transaction-id", "txn-1", "--tag-id", "tag-1", "--dry-run"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["status"] == "dry_run"
    mock.set_transaction_tags.assert_not_called()
