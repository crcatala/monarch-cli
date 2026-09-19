"""Tests for retry-safe, ambiguity-aware remote mutation execution (mc-t9o7).

Pins the conservative execution semantics: remote mutations make exactly one
attempt (never inheriting the read retry policy), ambiguous transport
failures raise ``MutationAmbiguousError`` (exit code 4) identifying the
operation and affected entities with a verification step, and definite
application rejections stay on the normal API error path.

These tests never touch the network or real credentials.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from monarch_cli.core.async_utils import (
    run_mutation_api_call,
    run_mutation_api_call_async,
)
from monarch_cli.core.config import Config, reset_config, set_config
from monarch_cli.core.exceptions import (
    APIError,
    ErrorCode,
    MonarchCLIError,
    MutationAmbiguousError,
    NetworkError,
)
from monarch_cli.core.operations import (
    MUTATION_RETRY_CLASSIFICATIONS,
    Effect,
    MutationRetryPolicy,
    Operation,
    PolicyViolationError,
    run_mutation_async_call,
    run_mutation_call,
)

READ_OPERATION = Operation(command="accounts list", effects=frozenset({Effect.READ_ONLY}))
MUTATION_OPERATION = Operation(
    command="transactions update", effects=frozenset({Effect.REMOTE_MUTATION})
)


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Isolate config so retry/timeout settings are deterministic."""
    monkeypatch.setenv("MONARCH_CONFIG_DIR", str(tmp_path))
    # High configured retries: mutations must ignore this entirely.
    set_config(Config(timeout_seconds=2, max_retries=5))
    yield
    reset_config()


class TestMutationSingleAttempt:
    """Mutations make exactly one attempt on ambiguous transport failures."""

    @pytest.mark.parametrize(
        "transport_failure",
        [
            TimeoutError("simulated timeout"),
            ConnectionError("simulated disconnect"),
            asyncio.CancelledError(),
        ],
        ids=["timeout", "disconnect", "cancelled"],
    )
    @pytest.mark.asyncio
    async def test_async_executor_never_retries(self, transport_failure: BaseException) -> None:
        """Timeout/disconnect/cancellation after invocation => one attempt only."""
        attempts = 0

        async def may_have_dispatched() -> str:
            nonlocal attempts
            attempts += 1
            raise transport_failure

        with pytest.raises(MutationAmbiguousError):
            await run_mutation_api_call_async(
                may_have_dispatched,
                operation="transactions update",
                entity_ids=("TXN1",),
            )

        assert attempts == 1

    @pytest.mark.parametrize(
        "transport_failure",
        [
            TimeoutError("simulated timeout"),
            ConnectionError("simulated disconnect"),
            asyncio.CancelledError(),
        ],
        ids=["timeout-sync", "disconnect-sync", "cancelled-sync"],
    )
    def test_sync_executor_never_retries(self, transport_failure: BaseException) -> None:
        """The synchronous bridge also makes exactly one attempt."""
        attempts = 0

        async def may_have_dispatched() -> str:
            nonlocal attempts
            attempts += 1
            raise transport_failure

        with pytest.raises(MutationAmbiguousError):
            run_mutation_api_call(
                may_have_dispatched,
                operation="accounts refresh",
                entity_ids=("ACC1",),
            )

        assert attempts == 1

    @pytest.mark.asyncio
    async def test_timeout_expiry_is_ambiguous_and_single_attempt(self) -> None:
        """A per-attempt timeout expiry raises ambiguity, with one attempt."""

        async def hangs() -> None:
            await asyncio.sleep(10)

        with pytest.raises(MutationAmbiguousError) as exc_info:
            await run_mutation_api_call_async(
                hangs,
                operation="transactions update",
                entity_ids=("TXN1",),
                timeout_seconds=0.05,
            )

        assert exc_info.value.details["reason"] == "timeout"

    @pytest.mark.asyncio
    async def test_reads_retry_but_mutations_do_not(self) -> None:
        """Same configured retries: reads use them, mutations ignore them."""
        read_attempts = 0

        async def read_fails() -> str:
            nonlocal read_attempts
            read_attempts += 1
            raise TimeoutError("read timed out")

        with pytest.raises(NetworkError):
            await asyncio.wait_for(_run_with_retry(read_fails), timeout=5)
        # Reads honor the configured max_retries (5 configured => 6 attempts).
        assert read_attempts == 6


async def _run_with_retry(coro_factory: Any) -> Any:
    """Helper: execute a call through the configured read retry path."""
    from monarch_cli.core.async_utils import run_api_call

    # run_api_call is synchronous by design; its bridge safely runs the read
    # coroutine in a worker thread when this async test already has a loop.
    return run_api_call(coro_factory)


class TestMutationAmbiguityError:
    """Ambiguous structured errors identify the operation and safe next step."""

    @pytest.mark.asyncio
    async def test_structured_details(self) -> None:
        async def fails() -> None:
            raise ConnectionError("secret-header-value")

        with pytest.raises(MutationAmbiguousError) as exc_info:
            await run_mutation_api_call_async(
                fails,
                operation="transactions update",
                entity_ids=("TXN42",),
            )

        err = exc_info.value
        assert err.code is ErrorCode.MUTATION_AMBIGUOUS
        assert err.exit_code == 4
        details = err.details
        assert details["operation"] == "transactions update"
        assert details["entity_ids"] == ["TXN42"]
        assert details["remote_state"] == "unknown"
        assert details["attempts"] == 1
        assert "may have changed" in err.message
        assert "verify" in details["verification"].lower()
        # No raw upstream exception text, request bodies, or credentials leak
        # into the message or details.
        assert "secret-header-value" not in err.to_dict()["message"]
        assert "ConnectionError" not in err.to_dict()["message"]

    @pytest.mark.asyncio
    async def test_custom_verification_step_is_used(self) -> None:
        async def fails() -> None:
            raise TimeoutError()

        with pytest.raises(MutationAmbiguousError) as exc_info:
            await run_mutation_api_call_async(
                fails,
                operation="accounts refresh",
                entity_ids=("ACC1",),
                verification="Check the web UI refresh status.",
            )

        assert exc_info.value.details["verification"] == "Check the web UI refresh status."

    def test_exit_code_is_four(self) -> None:
        err = MutationAmbiguousError()
        assert err.exit_code == 4
        assert err.code.value == "MUTATION_AMBIGUOUS"


class TestDefiniteFailureStaysFailed:
    """Definite application rejections are ordinary failed operations."""

    @pytest.mark.asyncio
    async def test_api_error_propagates_unchanged(self) -> None:
        attempts = 0

        async def rejected() -> str:
            nonlocal attempts
            attempts += 1
            raise APIError("transaction not found")

        with pytest.raises(APIError, match="transaction not found"):
            await run_mutation_api_call_async(
                rejected,
                operation="transactions update",
                entity_ids=("TXN1",),
            )

        assert attempts == 1

    @pytest.mark.asyncio
    async def test_value_error_is_not_ambiguous(self) -> None:
        async def bad_input() -> str:
            raise ValueError("definite local validation failure")

        with pytest.raises(ValueError):
            await run_mutation_api_call_async(
                bad_input,
                operation="transactions update",
            )


class TestRetryPolicyGate:
    """No generic unsafe retry override exists; named policies must be earned."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "policy",
        [
            MutationRetryPolicy.IDEMPOTENCY_KEY,
            MutationRetryPolicy.READ_AFTER_WRITE,
        ],
    )
    async def test_unearned_named_policies_are_refused(self, policy: MutationRetryPolicy) -> None:
        executed = AsyncMock(return_value="ok")

        with pytest.raises(MonarchCLIError, match="operation-specific"):
            await run_mutation_api_call_async(
                executed,
                operation="transactions update",
                retry_policy=policy,
            )

        executed.assert_not_awaited()

    def test_boolean_retry_override_does_not_exist(self) -> None:
        # run_mutation_call accepts only the named MutationRetryPolicy enum;
        # there is no generic safe_to_retry-style boolean parameter.
        import inspect

        from monarch_cli.core.operations import run_mutation_call

        params = inspect.signature(run_mutation_call).parameters
        assert "safe_to_retry" not in params
        assert "retry" not in params
        assert "max_retries" not in params
        assert "retry_policy" in params
        assert params["retry_policy"].default is MutationRetryPolicy.NO_RETRY

    @pytest.mark.asyncio
    async def test_boundary_refuses_non_default_policy(self) -> None:
        executed = AsyncMock(return_value="ok")

        with pytest.raises(MonarchCLIError):
            await run_mutation_async_call(
                executed,
                MUTATION_OPERATION,
                retry_policy=MutationRetryPolicy.IDEMPOTENCY_KEY,
            )

        executed.assert_not_called()


class TestSharedBoundaryRouting:
    """Mutations cannot be routed through the read executor or vice versa."""

    def test_mutation_call_uses_single_attempt_executor(self) -> None:
        executed = AsyncMock(return_value="ok")

        with (
            patch("monarch_cli.core.async_utils.run_api_call") as mock_read_path,
            patch("monarch_cli.core.operations.require_mutation_authorization"),
        ):
            result = run_mutation_call(executed, MUTATION_OPERATION)

        assert result == "ok"
        mock_read_path.assert_not_called()
        executed.assert_called_once()

    def test_read_call_refuses_mutation_operation(self) -> None:
        from monarch_cli.core.operations import run_read_call

        executed = AsyncMock(return_value="ok")
        with pytest.raises(PolicyViolationError, match="read executor"):
            run_read_call(executed, MUTATION_OPERATION)
        executed.assert_not_called()


class TestRetryClassifications:
    """Every current remote mutation has a documented retry classification."""

    def test_all_current_mutations_classified(self) -> None:
        assert set(MUTATION_RETRY_CLASSIFICATIONS) == {
            "accounts refresh",
            "transactions update",
            "transactions batch-update",
            "transactions tags create",
            "transactions tags replace",
            "transactions tags clear",
            "transactions splits replace",
            "transactions splits clear",
            "transactions attachments add",
            "transactions review mark",
            "transactions review return",
        }

    def test_classifications_require_a_named_mechanism_to_change(self) -> None:
        for operation, classification in MUTATION_RETRY_CLASSIFICATIONS.items():
            assert classification.startswith("no_retry:"), operation


class TestKeyboardInterruptIsAmbiguous:
    """Ctrl-C during a mutation reports ambiguity, never a plain interrupt.

    A KeyboardInterrupt is delivered to the main thread outside the running
    coroutine, so it stops the event loop before the coroutine's internal
    ambiguity conversion can surface. The executors must still report the
    uncertain outcome (exit code 4) rather than exit 130 as an ordinary
    "Interrupted." with no verification guidance.
    """

    def test_sync_bridge_reports_ambiguity_on_interrupt(self, monkeypatch) -> None:
        """The sync bridge converts a surfaced KeyboardInterrupt."""
        executed = AsyncMock(return_value="ok")
        monkeypatch.setattr(
            "monarch_cli.core.async_utils.run_async",
            lambda _coro: (_ for _ in ()).throw(KeyboardInterrupt()),
        )

        with pytest.raises(MutationAmbiguousError) as exc_info:
            run_mutation_api_call(
                executed,
                operation="transactions update",
                entity_ids=("TXN7",),
            )

        details = exc_info.value.details
        assert details["reason"] == "cancelled"
        assert details["entity_ids"] == ["TXN7"]
        assert details["remote_state"] == "unknown"
        assert "may have changed" in exc_info.value.message

    def test_real_interrupt_mid_mutation_is_single_attempt_and_ambiguous(self) -> None:
        """A signal-driven KeyboardInterrupt mid-coroutine surfaces ambiguity."""
        import signal

        attempts = 0

        async def dispatched_then_slow() -> None:
            nonlocal attempts
            attempts += 1
            await asyncio.sleep(10)

        def factory() -> Any:
            return dispatched_then_slow()

        def _raise_interrupt(*_args: Any) -> None:
            raise KeyboardInterrupt()

        previous_handler = signal.signal(signal.SIGALRM, _raise_interrupt)
        signal.setitimer(signal.ITIMER_REAL, 0.5)
        try:
            with pytest.raises(MutationAmbiguousError) as exc_info:
                run_mutation_api_call(
                    factory,
                    operation="transactions update",
                    entity_ids=("TXN1",),
                    timeout_seconds=30,
                )
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)

        # Exactly one attempt was made before the interrupt.
        assert attempts == 1
        assert exc_info.value.details["reason"] == "cancelled"
        assert exc_info.value.exit_code == 4
