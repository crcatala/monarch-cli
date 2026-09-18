"""Contract tests for the shared mutation outcome contract (mc-ik8o).

Pin the normative ``mutation-outcome.v1`` envelope: required fields and
nullability, mutually exclusive ``result``/``error``, deterministic top-level
aggregation, summary-count consistency, atomic/batch/multi-stage item
behavior, stable ordering, verification guidance for ambiguity, sanitized
error objects, and exit-code semantics.

These tests are pure unit tests; they never touch the network or real
credentials.
"""

from __future__ import annotations

from typing import Any

import pytest

from monarch_cli.core.exceptions import (
    APIError,
)
from monarch_cli.core.mutation_outcomes import (
    ITEM_SUCCEEDED,
    SCHEMA_VERSION,
    STATUS_AMBIGUOUS,
    STATUS_FAILED,
    STATUS_PARTIAL,
    STATUS_SUCCEEDED,
    aggregate_status,
    ambiguous_item,
    build_mutation_outcome,
    error_from_exception,
    failed_item,
    outcome_exit_code,
    succeeded_item,
    verification_object,
)
from monarch_cli.core.operations import PolicyViolationError

REQUIRED_TOP_LEVEL = {"schema_version", "operation", "status", "summary", "items", "verification"}
REQUIRED_ITEM = {"entity", "id", "status", "result", "error"}


def _item(status: str, item_id: str = "x1", entity: str = "transaction") -> dict[str, Any]:
    """Build a contract item of the given status."""
    if status == ITEM_SUCCEEDED:
        return succeeded_item(entity, item_id, {})
    if status == "failed":
        return failed_item(entity, item_id, "API_ERROR", "definitive rejection")
    return ambiguous_item(entity, item_id, "outcome unknown")


class TestEnvelopeRequiredFields:
    """Every outcome includes all required fields with documented nullability."""

    def test_all_top_level_fields_always_present(self) -> None:
        outcome = build_mutation_outcome("transactions update", [_item("succeeded")])
        assert set(outcome) >= REQUIRED_TOP_LEVEL
        assert outcome["schema_version"] == SCHEMA_VERSION == "mutation-outcome.v1"
        assert outcome["operation"] == "transactions.update"

    def test_every_item_has_all_required_fields(self) -> None:
        items = [_item("succeeded", "t1"), _item("failed", "t2"), _item("ambiguous", "t3")]
        outcome = build_mutation_outcome("transactions batch-update", items)
        for item in outcome["items"]:
            assert set(item) >= REQUIRED_ITEM

    def test_result_and_error_are_never_both_non_null(self) -> None:
        succeeded = _item("succeeded")
        assert succeeded["result"] is not None and succeeded["error"] is None
        failed = _item("failed")
        assert failed["result"] is None and failed["error"] is not None
        amb = _item("ambiguous")
        assert amb["result"] is None and amb["error"] is not None

    def test_result_must_be_an_object_on_success(self) -> None:
        item = succeeded_item("transaction", "t1", {"changes": {"notes": "x"}})
        assert isinstance(item["result"], dict)

    def test_builder_refuses_items_with_both_result_and_error(self) -> None:
        bad = _item("succeeded")
        bad["error"] = {"code": "X", "message": "m", "details": {}}
        with pytest.raises(PolicyViolationError, match="exactly one non-null"):
            build_mutation_outcome("transactions update", [bad])

    def test_builder_refuses_missing_item_fields(self) -> None:
        with pytest.raises(PolicyViolationError, match="missing required fields"):
            build_mutation_outcome("transactions update", [{"id": "t1"}])

    def test_builder_refuses_unknown_item_status(self) -> None:
        bad = _item("succeeded")
        bad["status"] = "completed"
        with pytest.raises(PolicyViolationError, match="Invalid mutation outcome item status"):
            build_mutation_outcome("transactions update", [bad])

    def test_builder_refuses_ambiguous_code_on_failed_item(self) -> None:
        bad = failed_item("transaction", "t1", "MUTATION_AMBIGUOUS", "not ambiguous")
        with pytest.raises(PolicyViolationError, match="reserved for ambiguous"):
            build_mutation_outcome("transactions update", [bad])


class TestSummaryConsistency:
    """summary.total equals len(items) and counts match the items exactly."""

    def test_counts_match_items(self) -> None:
        items = [
            _item(ITEM_SUCCEEDED, "t1"),
            _item("failed", "t2"),
            _item("ambiguous", "t3"),
            _item(ITEM_SUCCEEDED, "t4"),
        ]
        outcome = build_mutation_outcome("transactions batch-update", items)
        assert outcome["summary"] == {
            "total": 4,
            "succeeded": 2,
            "failed": 1,
            "ambiguous": 1,
        }
        assert outcome["summary"]["total"] == len(outcome["items"])

    def test_empty_items_summarize_to_zero(self) -> None:
        outcome = build_mutation_outcome("accounts refresh", [])
        assert outcome["summary"] == {
            "total": 0,
            "succeeded": 0,
            "failed": 0,
            "ambiguous": 0,
        }


class TestAggregation:
    """Top-level aggregation is deterministic across all outcome mixtures."""

    @pytest.mark.parametrize(
        ("statuses", "expected"),
        [
            (["succeeded"], STATUS_SUCCEEDED),
            (["succeeded", "succeeded"], STATUS_SUCCEEDED),
            ([], STATUS_SUCCEEDED),
            (["failed"], STATUS_FAILED),
            (["failed", "failed"], STATUS_FAILED),
            (["ambiguous"], STATUS_AMBIGUOUS),
            # No success with any ambiguity is ambiguous, even when mixed
            # with definitive failures.
            (["failed", "ambiguous"], STATUS_AMBIGUOUS),
            # Any mixture containing a success is partial.
            (["succeeded", "failed"], STATUS_PARTIAL),
            (["succeeded", "ambiguous"], STATUS_PARTIAL),
            (["succeeded", "failed", "ambiguous"], STATUS_PARTIAL),
        ],
    )
    def test_deterministic_rules(self, statuses: list[str], expected: str) -> None:
        items = [_item(status, f"id_{i}") for i, status in enumerate(statuses)]
        assert aggregate_status(items) == expected
        outcome = build_mutation_outcome("transactions batch-update", items)
        assert outcome["status"] == expected

    def test_aggregation_is_independent_of_item_order(self) -> None:
        forward = [_item(s, f"id_{i}") for i, s in enumerate(["succeeded", "ambiguous"])]
        reverse = list(reversed(forward))
        assert aggregate_status(forward) == aggregate_status(reverse) == STATUS_PARTIAL


class TestItemShapes:
    """Atomic, batch, and multi-stage operations share one item model."""

    def test_atomic_operation_uses_exactly_one_item(self) -> None:
        outcome = build_mutation_outcome(
            "transactions update",
            [succeeded_item("transaction", "txn_1", {"changes": {}})],
        )
        assert len(outcome["items"]) == 1

    def test_batch_items_preserve_normalized_input_order(self) -> None:
        items = [
            succeeded_item("transaction", f"txn_{i}", {})
            for i in ["c", "a", "b"]  # deliberately unsorted input order
        ]
        outcome = build_mutation_outcome("transactions batch-update", items)
        assert [item["id"] for item in outcome["items"]] == ["txn_c", "txn_a", "txn_b"]

    def test_multi_stage_preserves_remote_effect_order(self) -> None:
        """Multi-stage items keep remote-effect order and stable entities."""
        items = [
            succeeded_item("transaction", "txn_1", {"stage": "update"}),
            succeeded_item("attachment", "att_9", {"stage": "upload"}),
        ]
        outcome = build_mutation_outcome("transactions update", items)
        assert [item["entity"] for item in outcome["items"]] == ["transaction", "attachment"]
        assert [item["id"] for item in outcome["items"]] == ["txn_1", "att_9"]

    def test_multi_stage_mixed_effects_aggregate_to_partial(self) -> None:
        """Mixed effect outcomes aggregate to partial without envelope changes."""
        items = [
            succeeded_item("transaction", "txn_1", {}),
            failed_item("attachment", "att_9", "API_ERROR", "upload rejected"),
        ]
        outcome = build_mutation_outcome("transactions update", items)
        assert outcome["status"] == STATUS_PARTIAL
        assert set(outcome) == REQUIRED_TOP_LEVEL  # no extra top-level fields


class TestVerification:
    """Ambiguity requires recovery guidance; clean outcomes need no follow-up."""

    def test_verification_null_when_no_ambiguous_items(self) -> None:
        outcome = build_mutation_outcome(
            "transactions batch-update",
            [_item("succeeded", "t1"), _item("failed", "t2")],
            verification=verification_object("should be ignored"),
        )
        assert outcome["verification"] is None

    def test_verification_required_with_tokenized_command(self) -> None:
        outcome = build_mutation_outcome(
            "transactions update",
            [_item("ambiguous", "t1")],
            verification=verification_object(
                "Confirm the update was applied before retrying.",
                command=["monarch", "transactions", "list"],
            ),
        )
        verification = outcome["verification"]
        assert verification["required"] is True
        assert verification["message"]
        assert verification["command"] == ["monarch", "transactions", "list"]

    def test_verification_command_null_when_no_safe_command_exists(self) -> None:
        outcome = build_mutation_outcome(
            "accounts refresh",
            [_item("ambiguous", "acc_1")],
            verification=verification_object("Check the web UI.", command=None),
        )
        assert outcome["verification"]["required"] is True
        assert outcome["verification"]["command"] is None


class TestErrorSanitization:
    """Error objects carry stable codes and sanitized messages only."""

    def test_structured_error_contributes_stable_fields(self) -> None:
        error = error_from_exception(APIError("upstream rejected the update", status_code=422))
        assert error["code"] == "API_ERROR"
        assert error["message"] == "upstream rejected the update"
        assert error["details"]["status_code"] == 422

    def test_arbitrary_exception_text_is_never_copied(self) -> None:
        secret = "password=hunter2 and raw graphql body"
        error = error_from_exception(RuntimeError(secret))
        assert error["code"] == "UNKNOWN"
        assert secret not in error["message"]
        assert secret not in str(error["details"])
        # Only structural information survives sanitization.
        assert error["details"] == {"exception_class": "RuntimeError"}

    def test_ambiguous_items_use_the_stable_ambiguity_code(self) -> None:
        item = ambiguous_item("transaction", "txn_1", "outcome unknown")
        assert item["error"]["code"] == "MUTATION_AMBIGUOUS"
        assert isinstance(item["error"]["details"], dict)


class TestExitCodes:
    """All-succeeded exits 0, definitive failure 1, partial/ambiguous 4."""

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (STATUS_SUCCEEDED, 0),
            (STATUS_FAILED, 1),
            (STATUS_AMBIGUOUS, 4),
            (STATUS_PARTIAL, 4),
        ],
    )
    def test_exit_code_mapping(self, status: str, expected: int) -> None:
        assert outcome_exit_code(status) == expected

    def test_unknown_status_is_refused(self) -> None:
        with pytest.raises(PolicyViolationError, match="Unknown mutation outcome status"):
            outcome_exit_code("completed")


class TestOperationRegistry:
    """The envelope operation is an explicit stable identifier, never inferred."""

    def test_registered_operations(self) -> None:
        from monarch_cli.core.mutation_outcomes import OUTCOME_OPERATIONS

        assert OUTCOME_OPERATIONS == {
            "accounts refresh": "accounts.refresh",
            "transactions update": "transactions.update",
            "transactions batch-update": "transactions.batch-update",
            "transactions tags create": "transactions.tags.create",
            "transactions tags replace": "transactions.tags.replace",
            "transactions tags clear": "transactions.tags.clear",
            # Test-only disposable-fixture operations (mc-584r): real remote
            # effects used only by the gated live mutation adapter.
            "live-fixture account create": "live-fixture.account.create",
            "live-fixture transaction create": "live-fixture.transaction.create",
            "live-fixture transaction delete": "live-fixture.transaction.delete",
            "live-fixture account delete": "live-fixture.account.delete",
        }

    def test_unknown_command_is_refused(self) -> None:
        with pytest.raises(PolicyViolationError, match="no registered mutation-outcome"):
            build_mutation_outcome("transactions split", [])


class TestEnvelopeIsJsonSerializable:
    """Envelopes must round-trip through JSON for machine consumers."""

    def test_round_trip(self) -> None:
        import json

        outcome = build_mutation_outcome(
            "transactions batch-update",
            [
                succeeded_item("transaction", "txn_1", {"changes": {"notes": "x"}}),
                ambiguous_item("transaction", "txn_2", "outcome unknown"),
            ],
            verification=verification_object("Verify both transactions."),
        )
        restored = json.loads(json.dumps(outcome))
        assert restored == outcome
