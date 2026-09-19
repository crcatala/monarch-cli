"""Gated live mutation contract suite (mc-584r) - LOCAL, OPERATOR-APPROVED ONLY.

This module mutates exactly one disposable fixture: a uniquely named manual
account and a uniquely marked manual transaction created by this run. It is
isolated from every normal and read-only live run:

- nodes carry both ``live`` and ``live_mutation`` markers;
- ``tests/live/conftest.py`` deselects ``live_mutation`` nodes unless
  ``MONARCH_LIVE_MUTATION_TESTS=1`` is present (collection guard);
- an independent runtime guard fails closed before any fixture setup unless
  that opt-in is present and ``MONARCH_LIVE_MUTATION_HOUSEHOLD_ID`` names the
  owner-approved disposable household;
- before the first mutation, a minimal read-only ``myHousehold { id }`` lookup
  must match the approved ID exactly;
- the fixture effects use the shared mutation machinery and a restricted,
  git-ignored recovery manifest is journaled around every attempt.

Run (never in CI):

    make test-live-mutation

The only fixture effect driven through the public installed CLI is the
transaction-notes update, invoked with the global ``--allow-mutations``
authorization. The suite never registers, edits, or deletes any existing
household record.
"""

from __future__ import annotations

import contextlib
import json
from datetime import date
from pathlib import Path

import pytest

from monarch_cli.core.adapter import get_authenticated_client
from tests.live.live_cli import run_cli
from tests.live.live_fixture_adapter import (
    FIXTURE_ACCOUNT_DELETE,
    FIXTURE_TRANSACTION_DELETE,
    LiveFixtureAdapter,
    fixture_mutation_authorization,
)
from tests.live.live_mutation_gates import (
    RuntimePrerequisites,
    enforce_runtime_prerequisites,
    verify_household_identity,
)
from tests.live.live_mutation_manifest import RecoveryManifest, generate_run_id

# Both markers: normal (`not live`) and read-only live
# (`live and not live_mutation`) runs must never collect these nodes.
pytestmark = [pytest.mark.live, pytest.mark.live_mutation]

#: Repository root, resolved from this file (tests/live/<file>).
REPO_ROOT = Path(__file__).resolve().parents[2]

#: Bounded per-CLI-call timeout for the mutation invocation.
CLI_MUTATION_TIMEOUT_SECONDS = 60


@pytest.fixture(scope="module")
def runtime_prerequisites() -> RuntimePrerequisites:
    """Runtime gate: fail closed before any other fixture or client setup."""
    return enforce_runtime_prerequisites()


@pytest.fixture(scope="module")
def adapter(runtime_prerequisites: RuntimePrerequisites) -> LiveFixtureAdapter:
    """Authenticated fixture adapter; only built after the runtime gate passes."""
    assert runtime_prerequisites.household_id  # keeps the gate ordering explicit
    return LiveFixtureAdapter(get_authenticated_client())


def _cleanup_fixtures(
    adapter: LiveFixtureAdapter,
    manifest: RecoveryManifest,
    *,
    transaction_id: str | None,
    account_id: str | None,
) -> str | None:
    """Attempt conservative, single-attempt fixture cleanup.

    Returns:
        ``None`` when both fixture removals are definitively known to have
        succeeded. Otherwise a sanitized message (with the manifest path and
        run marker for manual recovery) and the manifest is preserved.
    """
    problems: list[str] = []

    if transaction_id is not None:
        manifest.record(
            operation=FIXTURE_TRANSACTION_DELETE.command,
            phase="intent",
            status="pending",
            remote_ids=[transaction_id],
            recovery_steps=[f"Manually delete the fixture transaction {transaction_id}."],
        )
        result = adapter.delete_transaction(transaction_id)
        manifest.record(
            operation=FIXTURE_TRANSACTION_DELETE.command,
            phase="observed",
            status=result.status,
            remote_ids=[transaction_id],
            recovery_steps=[f"Manually delete the fixture transaction {transaction_id}."],
        )
        if not result.succeeded:
            problems.append(f"transaction delete {result.status}")
    elif account_id is not None:
        # Account creation succeeded but the transaction never did: nothing
        # transaction-scoped to remove.
        pass

    if account_id is not None:
        manifest.record(
            operation=FIXTURE_ACCOUNT_DELETE.command,
            phase="intent",
            status="pending",
            remote_ids=[account_id],
            recovery_steps=[f"Manually delete the fixture account {account_id}."],
        )
        result = adapter.delete_account(account_id)
        manifest.record(
            operation=FIXTURE_ACCOUNT_DELETE.command,
            phase="observed",
            status=result.status,
            remote_ids=[account_id],
            recovery_steps=[f"Manually delete the fixture account {account_id}."],
        )
        if not result.succeeded:
            problems.append(f"account delete {result.status}")

    if not problems:
        return None

    return (
        "Fixture cleanup did not complete definitively ("
        + ", ".join(problems)
        + "). The recovery manifest was preserved at "
        f"{manifest.path} (run marker {manifest.run_id}); use it for a bounded "
        "read-only lookup and manual cleanup. Do not retry a timed-out or "
        "disconnected delete blindly."
    )


def _recover_ambiguous_account(
    adapter: LiveFixtureAdapter,
    manifest: RecoveryManifest,
    marker: str,
) -> None:
    """Record a bounded, read-only marker lookup for an ambiguous account create."""
    with contextlib.suppress(Exception):
        matches = adapter.find_account_ids_by_marker(marker)
        manifest.record(
            operation="live-fixture account create",
            phase="observed",
            status="ambiguous",
            remote_ids=matches,
            recovery_steps=[
                "Account creation outcome unknown; inspect the marker matches above "
                "in the disposable household and delete only confirmed fixture accounts.",
            ],
        )


def test_transaction_notes_round_trip(
    adapter: LiveFixtureAdapter,
    runtime_prerequisites: RuntimePrerequisites,
) -> None:
    """End-to-end fixture lifecycle: create, update notes, read back, delete."""
    run_id = generate_run_id()
    marker = f"mc584r-{run_id}"

    # Identity is authoritative only from the minimal household lookup.
    verify_household_identity(runtime_prerequisites.household_id, adapter.household_id())

    manifest = RecoveryManifest.create(REPO_ROOT, run_id)
    account_id: str | None = None
    transaction_id: str | None = None
    body_succeeded = False

    try:
        with fixture_mutation_authorization():
            # 1. Create a uniquely named zero-balance manual account.
            manifest.record(
                operation="live-fixture account create",
                phase="intent",
                status="pending",
                remote_ids=[],
                recovery_steps=[
                    "Account creation outcome unknown; use the run marker for a "
                    "bounded read-only account lookup before deleting anything."
                ],
            )
            account_result = adapter.create_manual_account(
                marker=marker, name=f"MC584R fixture {marker}"
            )
            if account_result.succeeded:
                account_id = account_result.remote_id
                manifest.record(
                    operation="live-fixture account create",
                    phase="observed",
                    status="succeeded",
                    remote_ids=[account_id] if account_id else [],
                    recovery_steps=[f"Manually delete the fixture account {account_id}."],
                )
            else:
                manifest.record(
                    operation="live-fixture account create",
                    phase="observed",
                    status=account_result.status,
                    remote_ids=[],
                    recovery_steps=[
                        "Account creation outcome unknown; use the run marker for a "
                        "bounded read-only account lookup."
                    ],
                )
                _recover_ambiguous_account(adapter, manifest, marker)
                pytest.fail(
                    f"Fixture account create {account_result.status}: "
                    f"{json.dumps(account_result.envelope)}",
                    pytrace=False,
                )

            # 2. Create a uniquely marked manual transaction, referencing an
            #    existing category read-only only because the upstream create
            #    contract requires one.
            category_id = adapter.reference_category_id()
            assert category_id is not None, "No existing category reference is available."
            manifest.record(
                operation="live-fixture transaction create",
                phase="intent",
                status="pending",
                remote_ids=[],
                recovery_steps=[
                    "Transaction creation outcome unknown; use the run marker for a "
                    "bounded read-only transaction lookup before deleting anything."
                ],
            )
            transaction_result = adapter.create_manual_transaction(
                marker=marker,
                account_id=account_id,
                category_id=category_id,
                date=date.today().isoformat(),
            )
            if not transaction_result.succeeded:
                manifest.record(
                    operation="live-fixture transaction create",
                    phase="observed",
                    status=transaction_result.status,
                    remote_ids=adapter.find_transaction_ids_by_marker(marker),
                    recovery_steps=[
                        "Transaction creation outcome unknown; use the run marker for "
                        "a bounded read-only transaction lookup."
                    ],
                )
                pytest.fail(
                    f"Fixture transaction create {transaction_result.status}: "
                    f"{json.dumps(transaction_result.envelope)}",
                    pytrace=False,
                )
            transaction_id = transaction_result.remote_id
            assert transaction_id is not None
            manifest.record(
                operation="live-fixture transaction create",
                phase="observed",
                status="succeeded",
                remote_ids=[transaction_id],
                recovery_steps=[f"Manually delete the fixture transaction {transaction_id}."],
            )

            # 3. Update only that transaction's notes through the installed CLI,
            #    with the global per-invocation authorization.
            notes = f"live-fixture:{marker}:updated"
            manifest.record(
                operation="transactions update",
                phase="intent",
                status="pending",
                remote_ids=[transaction_id],
                recovery_steps=[
                    f"Verify the notes on fixture transaction {transaction_id} before "
                    "retrying the update."
                ],
            )
            cli_result = run_cli(
                "--allow-mutations",
                "--json",
                "transactions",
                "update",
                "--transaction-id",
                transaction_id,
                "--notes",
                notes,
                timeout=CLI_MUTATION_TIMEOUT_SECONDS,
            )
            envelope = json.loads(cli_result.stdout)
            assert envelope["schema_version"] == "mutation-outcome.v1", envelope
            assert envelope["operation"] == "transactions.update", envelope
            assert envelope["status"] == "succeeded", envelope
            manifest.record(
                operation="transactions update",
                phase="observed",
                status="succeeded",
                remote_ids=[transaction_id],
                recovery_steps=[
                    f"Verify the notes on fixture transaction {transaction_id} before "
                    "retrying the update."
                ],
            )

            # 4. Bounded transaction-detail readback confirms the update.
            observed_notes = adapter.read_transaction_notes(transaction_id)
            assert observed_notes == notes, (
                "Bounded readback mismatch for the fixture transaction; the notes "
                "update outcome could not be confirmed."
            )

        body_succeeded = True
    except BaseException:
        with fixture_mutation_authorization():
            problem = _cleanup_fixtures(
                adapter, manifest, transaction_id=transaction_id, account_id=account_id
            )
        if problem is not None:
            manifest.record(
                operation="cleanup",
                phase="observed",
                status="failed",
                remote_ids=[value for value in (transaction_id, account_id) if value],
                recovery_steps=[problem],
            )
            raise AssertionError(problem) from None
        # Cleanup was definitive, but the run failed: keep the manifest for review.
        raise
    else:
        with fixture_mutation_authorization():
            problem = _cleanup_fixtures(
                adapter, manifest, transaction_id=transaction_id, account_id=account_id
            )
        if problem is not None:
            pytest.fail(problem, pytrace=False)
        if body_succeeded:
            # Remove only after both fixture removals are definitively known.
            manifest.remove()
