"""Mutation policy tests (mc-k48z).

Pin the centralized read-only-by-default mutation policy: explicit operation
metadata for every registered command, per-invocation ``--allow-mutations``
authorization, and a shared remote-operation boundary that refuses to execute
mutations through the read path.

These tests never touch the network or real credentials; client creation and
API calls are patched.
"""

from __future__ import annotations

import json
import re
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

import monarch_cli.core.adapter as adapter_module
from monarch_cli.core.operations import (
    Effect,
    MissingOperationMetadataError,
    Operation,
    PolicyViolationError,
    collect_command_effects,
    declared_effects,
    operation_effects,
    require_mutation_authorization,
    reset_mutation_authorization,
    resolve_invocation,
    run_mutation_call,
    run_read_call,
    set_mutation_authorized,
)
from monarch_cli.main import app

runner = CliRunner()

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")

#: The complete reviewed command inventory with declared effects. A new or
#: renamed command must update this mapping (and its declarations) explicitly.
EXPECTED_INVENTORY: dict[str, frozenset[Effect]] = {
    "accounts list": frozenset({Effect.READ_ONLY}),
    "accounts types": frozenset({Effect.READ_ONLY}),
    "accounts history": frozenset({Effect.READ_ONLY}),
    "accounts recent-balances": frozenset({Effect.READ_ONLY}),
    "accounts snapshots": frozenset({Effect.READ_ONLY}),
    "accounts snapshots-by-type": frozenset({Effect.READ_ONLY}),
    "accounts refresh-status": frozenset({Effect.READ_ONLY}),
    "accounts refresh": frozenset({Effect.REMOTE_MUTATION}),
    "auth doctor": frozenset({Effect.READ_ONLY}),
    "auth login": frozenset({Effect.REMOTE_AUTHENTICATION, Effect.LOCAL_CREDENTIAL_CHANGE}),
    "auth logout": frozenset({Effect.LOCAL_CREDENTIAL_CHANGE}),
    "auth ping": frozenset({Effect.READ_ONLY}),
    "auth setup": frozenset({Effect.READ_ONLY}),
    "auth status": frozenset({Effect.READ_ONLY}),
    "budgets list": frozenset({Effect.READ_ONLY}),
    "cashflow summary": frozenset({Effect.READ_ONLY}),
    "cashflow detail": frozenset({Effect.READ_ONLY}),
    "categories list": frozenset({Effect.READ_ONLY}),
    "transactions batch-update": frozenset({Effect.REMOTE_MUTATION}),
    "transactions get": frozenset({Effect.READ_ONLY}),
    "transactions list": frozenset({Effect.READ_ONLY}),
    "transactions recurring": frozenset({Effect.READ_ONLY}),
    "transactions summary": frozenset({Effect.READ_ONLY}),
    "transactions update": frozenset({Effect.REMOTE_MUTATION}),
    "transactions tags create": frozenset({Effect.REMOTE_MUTATION}),
    "transactions tags replace": frozenset({Effect.REMOTE_MUTATION}),
    "transactions tags clear": frozenset({Effect.REMOTE_MUTATION}),
    "transactions splits replace": frozenset({Effect.REMOTE_MUTATION}),
    "transactions splits clear": frozenset({Effect.REMOTE_MUTATION}),
    "transactions splits show": frozenset({Effect.READ_ONLY}),
    "transactions tags list": frozenset({Effect.READ_ONLY}),
    "transactions tags show": frozenset({Effect.READ_ONLY}),
}

MUTATION_OPERATIONS: dict[str, list[str]] = {
    "transactions update": ["transactions", "update", "TXN1", "--amount", "1.0"],
    "transactions batch-update": ["transactions", "batch-update", "TXN1", "--notes", "x"],
    "accounts refresh": ["accounts", "refresh"],
}


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Isolate config/session state and reset per-invocation authorization."""
    monkeypatch.setenv("MONARCH_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("MONARCH_TOKEN", raising=False)
    monkeypatch.delenv("MONARCH_ALLOW_MUTATIONS", raising=False)
    reset_mutation_authorization()
    adapter_module.reset_client()
    yield
    reset_mutation_authorization()
    adapter_module.reset_client()


def _blocked(result) -> None:
    """Assert a result is a clean MUTATION_BLOCKED failure (exit code 3)."""
    assert result.exit_code == 3, result.output
    stderr = ANSI_ESCAPE_RE.sub("", result.stderr or "")
    assert "MUTATION_BLOCKED" in stderr, stderr


# --- Layer 1: registration metadata ----------------------------------------


class TestRegistrationMetadata:
    """Every registered command must carry explicit effect metadata."""

    def test_every_registered_command_has_metadata(self) -> None:
        # Raises MissingOperationMetadataError if any command lacks metadata.
        inventory = collect_command_effects(app)
        assert inventory == EXPECTED_INVENTORY

    def test_missing_metadata_is_detected(self) -> None:
        def bare_callback() -> None:  # pragma: no cover - never invoked
            raise AssertionError("should not run")

        sub_app = type(app)(name="synthetic")
        sub_app.command()(bare_callback)
        root = type(app)(name="root", no_args_is_help=True)
        root.add_typer(sub_app, name="synthetic")

        with pytest.raises(MissingOperationMetadataError, match="synthetic bare-callback"):
            collect_command_effects(root)

    def test_missing_metadata_on_root_level_command_is_detected(self) -> None:
        # Commands registered directly on the root app (outside any group)
        # must also be covered by the inventory, so they cannot silently
        # bypass the metadata requirement.
        def bare_root_callback() -> None:  # pragma: no cover - never invoked
            raise AssertionError("should not run")

        root = type(app)(name="root", no_args_is_help=True)
        root.command(name="rogue")(bare_root_callback)

        with pytest.raises(MissingOperationMetadataError, match="'rogue'"):
            collect_command_effects(root)

    def test_multi_effect_command_keeps_both_effects(self) -> None:
        # A real multi-effect command: auth login must not collapse to one.
        inventory = collect_command_effects(app)
        login_effects = inventory["auth login"]
        assert Effect.REMOTE_AUTHENTICATION in login_effects
        assert Effect.LOCAL_CREDENTIAL_CHANGE in login_effects
        assert len(login_effects) == 2

    def test_synthetic_multi_effect_metadata(self) -> None:
        @operation_effects(Effect.REMOTE_MUTATION, Effect.LOCAL_CREDENTIAL_CHANGE)
        def synthetic() -> None:  # pragma: no cover - never invoked
            raise AssertionError("should not run")

        declared = declared_effects(synthetic)
        assert declared == frozenset({Effect.REMOTE_MUTATION, Effect.LOCAL_CREDENTIAL_CHANGE})

    def test_current_mutations_declare_remote_mutation(self) -> None:
        inventory = collect_command_effects(app)
        for command in MUTATION_OPERATIONS:
            assert Effect.REMOTE_MUTATION in inventory[command], command

    def test_credential_commands_do_not_require_flag(self) -> None:
        # Authorization is keyed to remote_mutation only; other effects never
        # imply it.
        inventory = collect_command_effects(app)
        for command in ("auth login", "auth logout"):
            require_mutation_authorization(
                Operation(command=command, effects=inventory[command])
            )  # must not raise


# --- Layer 2: execution boundary -------------------------------------------


class TestExecutionBoundary:
    """The shared remote-operation boundary cannot be silently bypassed."""

    def test_read_executor_refuses_mutation_operation(self) -> None:
        executed = MagicMock(return_value="data")
        operation = Operation(
            command="transactions update", effects=frozenset({Effect.REMOTE_MUTATION})
        )
        with pytest.raises(
            PolicyViolationError,
            match="read executor",
        ):
            run_read_call(executed, operation)
        executed.assert_not_called()

    def test_mutation_executor_refuses_read_only_operation(self) -> None:
        executed = MagicMock(return_value="data")
        operation = Operation(command="accounts list", effects=frozenset({Effect.READ_ONLY}))
        with pytest.raises(PolicyViolationError, match="not a remote mutation"):
            run_mutation_call(executed, operation)
        executed.assert_not_called()

    def test_mutation_executor_requires_authorization(self) -> None:
        executed = AsyncMock(return_value="ok")
        operation = Operation(
            command="accounts refresh", effects=frozenset({Effect.REMOTE_MUTATION})
        )
        with pytest.raises(Exception, match="read-only"):  # MutationBlockedError
            run_mutation_call(executed, operation)
        executed.assert_not_called()

        set_mutation_authorized(True)
        assert run_mutation_call(executed, operation) == "ok"
        executed.assert_called_once_with()

    def test_authorization_check_is_noop_for_non_mutations(self) -> None:
        require_mutation_authorization(
            Operation(command="auth login", effects=frozenset({Effect.PREVIEW}))
        )

    def test_preview_classification_of_dry_run(self) -> None:
        operation = resolve_invocation(
            "transactions update",
            frozenset({Effect.REMOTE_MUTATION}),
            dry_run=True,
        )
        assert operation.effects == frozenset({Effect.PREVIEW})
        # A validated preview never requires authorization.
        require_mutation_authorization(operation)


# --- CLI-level behavior ------------------------------------------------------


class TestReadOnlyDefault:
    """The CLI defaults to read-only and blocks every remote mutation."""

    @pytest.mark.parametrize("command", sorted(MUTATION_OPERATIONS))
    def test_mutations_blocked_by_default_with_no_api_call(
        self, command: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # If execution reaches client creation or the API while blocked, these
        # fail the test loudly.
        def _no_client() -> None:
            raise AssertionError("authenticated client must not be created while blocked")

        monkeypatch.setattr(adapter_module, "get_authenticated_client", _no_client)

        result = runner.invoke(app, MUTATION_OPERATIONS[command])
        _blocked(result)

    def test_blocked_before_authentication_lookup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _no_token_lookup() -> str:
            raise AssertionError("session token must not be read before authorization")

        monkeypatch.setattr(adapter_module, "get_session_token", _no_token_lookup)
        result = runner.invoke(app, MUTATION_OPERATIONS["accounts refresh"])
        _blocked(result)

    def test_blocked_before_confirmation_prompt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _no_prompt(*_args: Any, **_kwargs: Any) -> None:
            raise AssertionError("blocked mutations must not prompt for confirmation")

        monkeypatch.setattr("typer.confirm", _no_prompt)
        result = runner.invoke(app, MUTATION_OPERATIONS["transactions update"])
        _blocked(result)

    def test_blocked_error_is_single_valid_json_without_ansi(self) -> None:
        result = runner.invoke(app, MUTATION_OPERATIONS["accounts refresh"])
        _blocked(result)
        stderr = ANSI_ESCAPE_RE.sub("", result.stderr or "").strip()
        assert "\x1b" not in (result.stderr or "")
        # Exactly one valid structured JSON error object on stderr.
        payload = json.loads(stderr)
        assert payload["error"] is True
        assert payload["code"] == "MUTATION_BLOCKED"
        # Actionable example on stderr.
        assert "--allow-mutations" in payload["details"]["example"]
        # No success payload on stdout.
        assert result.stdout.strip() == ""

    def test_flag_must_precede_command_path(self) -> None:
        # The flag is a global option; after the command path it is a parse
        # error, not authorization.
        result = runner.invoke(
            app, ["transactions", "update", "TXN1", "--amount", "1.0", "--allow-mutations"]
        )
        assert result.exit_code != 0
        assert result.exit_code != 3  # a usage error, not a blocked mutation

    def test_environment_variable_does_not_authorize(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MONARCH_ALLOW_MUTATIONS", "1")
        result = runner.invoke(app, MUTATION_OPERATIONS["accounts refresh"])
        _blocked(result)

    def test_authorization_does_not_persist_between_invocations(self) -> None:
        # First invocation authorized, second (same process, module state)
        # must be blocked again: authorization is per-invocation only.
        authorized = runner.invoke(
            app, ["--allow-mutations", *MUTATION_OPERATIONS["accounts refresh"]]
        )
        # With a fake token absent this fails as AUTH_REQUIRED (exit 1),
        # never MUTATION_BLOCKED.
        assert authorized.exit_code != 3, authorized.output
        assert "MUTATION_BLOCKED" not in (authorized.stderr or "")

        blocked = runner.invoke(app, MUTATION_OPERATIONS["accounts refresh"])
        _blocked(blocked)

    def test_read_only_commands_usable_without_authorization(self) -> None:
        # Read commands must reach authentication (and fail with AUTH_REQUIRED
        # here), never the mutation gate.
        result = runner.invoke(app, ["transactions", "list", "--format", "json"])
        assert result.exit_code == 1, result.output
        stderr = ANSI_ESCAPE_RE.sub("", result.stderr or "")
        assert "AUTH_REQUIRED" in stderr
        assert "MUTATION_BLOCKED" not in stderr

    def test_credential_commands_usable_without_authorization(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MONARCH_CONFIG_DIR", str(tmp_path))
        result = runner.invoke(app, ["auth", "logout"])
        assert result.exit_code == 0, result.output
        assert "MUTATION_BLOCKED" not in (result.stderr or "")

    def test_validated_dry_run_needs_no_authorization_and_no_client(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _no_client() -> None:
            raise AssertionError("dry-run must not create an authenticated client")

        def _no_mutation(*_args: Any, **_kwargs: Any) -> None:
            raise AssertionError("dry-run must not call a mutation API")

        monkeypatch.setattr(adapter_module, "get_authenticated_client", _no_client)

        with patch("monarchmoney.MonarchMoney.update_transaction", _no_mutation):
            result = runner.invoke(
                app,
                ["transactions", "update", "TXN1", "--dry-run", "--amount", "1.0"],
            )
        assert result.exit_code == 0, result.output
        assert "dry_run" in result.stdout
        assert "MUTATION_BLOCKED" not in (result.stderr or "")

        result = runner.invoke(
            app,
            ["transactions", "batch-update", "TXN1", "--notes", "x", "--dry-run"],
        )
        assert result.exit_code == 0, result.output


class TestAuthorizedMutations:
    """--allow-mutations enables remote mutations for one invocation only."""

    def _invoke_update(self, mock_client: MagicMock, *prefix: str) -> Any:
        adapter_module.reset_client()
        with (
            patch.dict("os.environ", {"MONARCH_TOKEN": "test-token"}),
            patch.object(adapter_module, "_client", None),
            patch.object(adapter_module, "MonarchMoney", return_value=mock_client),
        ):
            return runner.invoke(app, [*prefix, *MUTATION_OPERATIONS["transactions update"]])

    def test_update_executes_with_flag(self) -> None:
        mock_client = MagicMock()
        mock_client.update_transaction = AsyncMock(return_value=True)
        result = self._invoke_update(mock_client, "--allow-mutations")
        assert result.exit_code == 0, result.output
        mock_client.update_transaction.assert_called_once()
        assert '"status": "succeeded"' in result.stdout

    def test_same_invocation_without_flag_is_blocked(self) -> None:
        mock_client = MagicMock()
        mock_client.update_transaction = AsyncMock(return_value=True)
        result = self._invoke_update(mock_client)
        _blocked(result)
        mock_client.update_transaction.assert_not_called()

    def test_refresh_executes_with_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_client = MagicMock()
        mock_client.request_accounts_refresh = AsyncMock(return_value=True)
        monkeypatch.setenv("MONARCH_TOKEN", "test-token")
        with (
            patch.object(adapter_module, "MonarchMoney", return_value=mock_client),
        ):
            result = runner.invoke(app, ["--allow-mutations", "accounts", "refresh", "-a", "ACC1"])
        assert result.exit_code == 0, result.output
        mock_client.request_accounts_refresh.assert_called_once_with(["ACC1"])
        mock_client.get_accounts.assert_not_called()
